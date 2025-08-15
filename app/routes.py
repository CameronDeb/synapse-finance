# app/routes.py
from flask import jsonify, request, render_template, flash, redirect, url_for, session, abort
from app import app, db
from app.models import User, WatchlistItem, Holding, Trade, Alert
from app.email import send_password_reset_email, send_price_alert_email
from flask_login import login_user, logout_user, current_user, login_required
import os
import stripe
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from collections import defaultdict
import pandas as pd

# --- Get Logger ---
logger = logging.getLogger(__name__)

# --- Configure Stripe ---
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
stripe_webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
STRIPE_PRO_PRICE_ID = os.environ.get('STRIPE_PRO_PRICE_ID') 

# --- Admin Password ---
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

# --- Constants ---
WATCHLIST_LIMIT_FREE = 5
ALERTS_LIMIT_PRO = 20

# --- Import API Clients & Services ---
try:
    from .api_clients import fmp_client
    from .services.technical_analyzer import calculate_indicators
    from .services.backtesting_engine import run_sma_crossover_backtest
    logger.info("Successfully imported FMP client and services.")
except ImportError as e:
    logger.critical(f"FATAL: Could not import API clients/services: {e}", exc_info=True)
    # Create dummy functions if import fails to prevent app from crashing on startup
    class fmp_client:
        @staticmethod
        def __getattr__(name):
            def method(*args, **kwargs):
                logger.error(f"FMP client not available. {name} called but will return None.")
                return None
            return method
    def calculate_indicators(historical_data_list): return {"error": "Analysis service unavailable."}
    def run_sma_crossover_backtest(symbol, start_date, end_date, initial_capital, asset_class='Stock'): return {"error": "Backtesting service unavailable."}


# --- Decorators ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Admin access is required.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def pro_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_pro:
            return jsonify({"error": "Pro subscription required for this feature."}), 403
        return f(*args, **kwargs)
    return decorated_function


# --- Admin Routes ---

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin'):
        return redirect(url_for('admin_panel'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        if password and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('Admin access granted.', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Incorrect admin password.', 'error')
            return redirect(url_for('admin_login'))

    # A simple login form for admin, assuming you don't have a template for it.
    return '''
        <body style="background-color:#121212; color:white; font-family:sans-serif; text-align:center; padding-top:100px;">
            <h2>Admin Login</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </body>
    '''

@app.route('/admin-panel', methods=['GET', 'POST'])
@app.route('/admin-panel', methods=['GET', 'POST'])

@admin_required
def admin_panel():
    if request.method == 'POST':
        email = request.form.get('email')
        action = request.form.get('action')
        user = db.session.scalar(db.select(User).where(User.email == email))
        if not user:
            flash(f"User with email '{email}' not found.", 'error')
        elif action == 'grant':
            user.subscription_tier = 'pro'
            flash(f"Successfully granted Pro access to {email}.", 'success')
        elif action == 'revoke':
            user.subscription_tier = 'free'
            user.stripe_subscription_id = None
            flash(f"Successfully revoked Pro access for {email}.", 'success')
        db.session.commit()
        return redirect(url_for('admin_panel'))

    pro_users = db.session.scalars(db.select(User).where(User.subscription_tier == 'pro').order_by(User.email)).all()
    free_users = db.session.scalars(db.select(User).where(User.subscription_tier == 'free').order_by(User.email)).all()
    
    return render_template('admin.html', pro_users=pro_users, free_users=free_users)


@app.route('/')
def index():
    return render_template('home.html')

@app.route('/dashboard')
@login_required
def dashboard():
    query = request.args.get('query', '').strip().upper()
    profile_data = None
    if query:
        # Fetch basic profile data to use in the title and description
        # This is a good place to use a cached, lightweight endpoint
        profile_data = fmp_client.get_company_profile(query)

    watchlist_items = current_user.watchlist_items.order_by(WatchlistItem.symbol).all()
    return render_template('dashboard.html', 
                           watchlist=watchlist_items, 
                           query=query,
                           profile=profile_data)

@app.route('/news')
@login_required
def news_page():
    """ Renders the dedicated news & market activity page. """
    search_query = request.args.get('query', '').strip()
    
    try:
        # Fetch top headlines for the top section (always general news)
        top_headlines = fmp_client.get_stock_news(symbol=None, limit=5) or []

        # --- Logic for the Calendar Section ---
        # Fetch news and events for the calendar view
        if search_query:
            # If searching, focus the calendar on the specific ticker
            news_articles = fmp_client.get_stock_news(search_query, limit=100) or []
            page_title = f"Activity for ${search_query.upper()}"
            # Economic events are general, so we still fetch them
            economic_events = fmp_client.get_economic_calendar(date.today() - timedelta(days=14), date.today() + timedelta(days=14)) or []
        else:
            # Default view: general news and events
            news_articles = fmp_client.get_stock_news(symbol=None, limit=100) or []
            page_title = "Market Activity"
            economic_events = fmp_client.get_economic_calendar(date.today() - timedelta(days=14), date.today() + timedelta(days=14)) or []

        # --- Process and Group Data by Date for the Calendar ---
        grouped_feed = defaultdict(lambda: {'news': [], 'events': []})
        start_date = date.today() - timedelta(days=14)
        end_date = date.today() + timedelta(days=14)

        # Helper to parse dates safely
        def parse_date(date_str):
            if not date_str: return None
            try:
                return datetime.strptime(date_str.split(' ')[0], '%Y-%m-%d').date()
            except (ValueError, IndexError):
                return None

        for article in news_articles:
            article_date = parse_date(article.get('publishedDate'))
            if article_date and start_date <= article_date <= end_date:
                grouped_feed[article_date]['news'].append(article)

        for event in economic_events:
            event_date = parse_date(event.get('date'))
            if event_date:
                grouped_feed[event_date]['events'].append(event)
        
        all_days_in_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        sorted_feed = {day: grouped_feed[day] for day in all_days_in_range}

    except Exception as e:
        logger.error(f"Error in news_page route: {e}", exc_info=True)
        flash("An unexpected error occurred while fetching market activity.", "error")
        top_headlines = []
        sorted_feed = {}
        page_title = "Error"

    return render_template('news.html', 
                           headlines=top_headlines, 
                           feed_by_date=sorted_feed, 
                           title=page_title, 
                           query=search_query)

@app.route('/pricing')
def pricing_page():
    return render_template('pricing.html')

@app.route('/screener')
@login_required
def screener_page():
    return render_template('screener.html')

@app.route('/backtesting')
@login_required
def backtesting_page():
    """Renders the backtesting page."""
    return render_template('backtesting.html')

@app.route('/portfolio', methods=['GET'])
@login_required
def portfolio_page():
    user_holdings = current_user.holdings.order_by(Holding.symbol).all()
    total_invested_value = sum(Decimal(str(h.quantity)) * Decimal(str(h.purchase_price)) for h in user_holdings)

    # --- Portfolio Analysis Logic ---
    sector_allocation = defaultdict(Decimal)
    weighted_beta_sum = Decimal('0.0')
    current_total_value = Decimal('0.0')
    portfolio_beta = 0.0

    symbols = [h.symbol for h in user_holdings]
    if symbols:
        try:
            quotes_list = fmp_client.get_quote(",".join(symbols))
            profiles_list = [fmp_client.get_company_profile(s) for s in symbols]

            quotes = {q['symbol']: q for q in quotes_list if q and 'symbol' in q} if quotes_list else {}
            profiles = {p['symbol']: p for p in profiles_list if p and 'symbol' in p} if profiles_list else {}

            for h in user_holdings:
                holding_symbol = h.symbol
                quote = quotes.get(holding_symbol)
                profile = profiles.get(holding_symbol)

                if quote and 'price' in quote and quote['price'] is not None:
                    current_price = Decimal(str(quote['price']))
                    holding_value = Decimal(str(h.quantity)) * current_price
                    current_total_value += holding_value

                    sector = profile.get('sector', 'Other') if profile else 'Other'
                    sector_allocation[sector] += holding_value

                    if profile and profile.get('beta') is not None:
                        beta = Decimal(str(profile.get('beta')))
                        weighted_beta_sum += (holding_value * beta)
        except Exception as e:
            logger.error(f"Error during portfolio analysis API calls for user {current_user.id}: {e}", exc_info=True)
            flash("Could not perform portfolio analysis due to an external API error.", "warning")


    if current_total_value > 0:
        portfolio_beta = float(weighted_beta_sum / current_total_value)
    else:
        portfolio_beta = 0.0

    sector_data_for_chart = {
        'labels': list(sector_allocation.keys()),
        'values': [float(v) for v in sector_allocation.values()]
    }

    return render_template(
        'portfolio.html',
        holdings=user_holdings,
        total_invested_value=total_invested_value,
        sector_data=sector_data_for_chart,
        portfolio_beta=portfolio_beta
    )

@app.route('/journal', methods=['GET', 'POST'])
@login_required
def journal():
    if request.method == 'POST':
        try:
            new_trade = Trade(
                user_id=current_user.id,
                symbol=request.form.get('symbol', '').upper().strip(),
                pnl=float(request.form.get('pnl')),
                trade_date=datetime.strptime(request.form.get('trade_date'), '%Y-%m-%d').date(),
                asset_class=request.form.get('asset_class'),
                setup_reason=request.form.get('setup_reason', '').strip(),
                notes=request.form.get('notes', '').strip()
            )
            db.session.add(new_trade)
            db.session.commit()
            flash('Trade successfully logged!', 'success')
        except (ValueError, TypeError) as e:
            db.session.rollback()
            logger.error(f"Journal submission error for user {current_user.id}: {e}")
            flash('Invalid P&L or Date format.', 'error')
        return redirect(url_for('journal'))
    
    trades = current_user.trades.order_by(Trade.trade_date.desc(), Trade.id.desc()).all()
    return render_template('journal.html', trades=trades)

@app.route('/settings', methods=['GET'])
@login_required
def settings_page():
    return render_template('settings.html')


# --- User Authentication and Account Management ---

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.session.scalar(db.select(User).where(User.email == email))
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember') == 'on')
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if password != request.form.get('confirm_password'):
            flash('Passwords do not match.', 'error')
            return render_template('signup.html')
        if db.session.scalar(db.select(User).where(User.email == email)):
            flash('Email address already registered.', 'warning')
            return redirect(url_for('login_page'))
        new_user = User(email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login_page'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('is_admin', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/request-reset', methods=['GET', 'POST'])
def request_reset():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = db.session.scalar(db.select(User).where(User.email == request.form.get('email')))
        if user:
            send_password_reset_email(user)
        flash('If an account with that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('login_page'))
    return render_template('request_reset.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    user = User.verify_reset_password_token(token)
    if not user:
        flash('That is an invalid or expired token.', 'warning')
        return redirect(url_for('request_reset'))
    if request.method == 'POST':
        password = request.form.get('password')
        if password and password == request.form.get('confirm_password'):
            user.set_password(password)
            db.session.commit()
            flash('Your password has been updated! You can now log in.', 'success')
            return redirect(url_for('login_page'))
        else:
            flash('Passwords do not match.', 'error')
    return render_template('reset_password.html', token=token)

@app.route('/settings/change-password', methods=['POST'])
@login_required
def change_password():
    if not current_user.check_password(request.form.get('current_password')):
        flash('Your current password was incorrect.', 'error')
    elif request.form.get('new_password') != request.form.get('confirm_new_password'):
        flash('New passwords do not match.', 'error')
    else:
        current_user.set_password(request.form.get('new_password'))
        db.session.commit()
        flash('Your password has been updated successfully.', 'success')
    return redirect(url_for('settings_page'))

@app.route('/settings/delete-account', methods=['POST'])
@login_required
def delete_account():
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    flash('Your account has been permanently deleted.', 'info')
    return redirect(url_for('index'))


# --- Functional Routes (Portfolio, Watchlist, Alerts) ---

@app.route('/portfolio/add', methods=['POST'])
@login_required
def add_holding():
    try:
        new_holding = Holding(
            user_id=current_user.id,
            symbol=request.form.get('symbol', '').upper().strip(),
            quantity=float(Decimal(request.form.get('quantity'))),
            purchase_price=float(Decimal(request.form.get('purchase_price'))),
            purchase_date=datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
        )
        db.session.add(new_holding)
        db.session.commit()
        flash(f'{new_holding.symbol} holding added successfully!', 'success')
    except (InvalidOperation, ValueError) as e:
        db.session.rollback()
        logger.error(f"Portfolio add error for user {current_user.id}: {e}")
        flash('Error adding holding. Please check the number formats.', 'error')
    return redirect(url_for('portfolio_page'))

@app.route('/portfolio/delete/<int:holding_id>', methods=['POST'])
@login_required
def delete_holding(holding_id):
    holding = db.session.get(Holding, holding_id)
    if holding and holding.user_id == current_user.id:
        db.session.delete(holding)
        db.session.commit()
        flash('Holding deleted.', 'success')
    else:
        abort(403)
    return redirect(url_for('portfolio_page'))

# ... (Watchlist and Alert routes would go here if they had their own pages)


# --- Payment & Subscription Routes ---

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    if not STRIPE_PRO_PRICE_ID:
        flash('Payment system is not configured correctly.', 'error')
        return redirect(url_for('pricing_page'))
    try:
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email, name=current_user.email)
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            line_items=[{'price': STRIPE_PRO_PRICE_ID, 'quantity': 1}],
            mode='subscription',
            success_url=url_for('payment_success', _external=True),
            cancel_url=url_for('pricing_page', _external=True),
            allow_promotion_codes=True,
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        logger.error(f"Stripe Checkout error for user {current_user.email}: {e}", exc_info=True)
        flash('An error occurred with our payment provider. Please try again.', 'error')
        return redirect(url_for('pricing_page'))

@app.route('/payment-success')
@login_required
def payment_success():
    flash('Your subscription was successful! Welcome to Pro.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/create-portal-session', methods=['POST'])
@login_required
def create_portal_session():
    if not current_user.stripe_customer_id:
        flash('No subscription found to manage.', 'error')
        return redirect(url_for('settings_page'))
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=url_for('settings_page', _external=True),
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        logger.error(f"Stripe Portal error for user {current_user.email}: {e}", exc_info=True)
        flash('An error occurred with our payment provider.', 'error')
        return redirect(url_for('settings_page'))

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    if not stripe_webhook_secret:
        logger.critical("Stripe webhook secret is not configured.")
        return 'Webhook secret not configured', 500
    
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"Invalid webhook signature or payload: {e}")
        return 'Invalid payload or signature', 400
    
    # Handle the event
    if event['type'] in ['checkout.session.completed', 'customer.subscription.updated']:
        session = event['data']['object']
        customer_id = session.get('customer')
        user = db.session.scalar(db.select(User).where(User.stripe_customer_id == customer_id))
        if user:
            # Check subscription status
            status = session.get('status')
            if status == 'active':
                user.subscription_tier = 'pro'
                user.stripe_subscription_id = session.get('id') if event['type'] == 'customer.subscription.updated' else session.get('subscription')
                logger.info(f"User {user.email} subscription is active. Upgraded to Pro.")
            else:
                user.subscription_tier = 'free'
                logger.info(f"User {user.email} subscription status is '{status}'. Downgraded to Free.")
            db.session.commit()
            
    elif event['type'] == 'customer.subscription.deleted':
        session = event['data']['object']
        customer_id = session.get('customer')
        user = db.session.scalar(db.select(User).where(User.stripe_customer_id == customer_id))
        if user:
            user.subscription_tier = 'free'
            user.stripe_subscription_id = None
            db.session.commit()
            logger.info(f"User {user.email} subscription deleted. Downgraded to Free.")
    else:
        logger.info(f"Unhandled Stripe event type: {event['type']}")
        
    return jsonify(success=True)


# --- API Data Endpoints (Consolidated & Transformed) ---

@app.route('/api/ticker-data')
def ticker_data_api():
    ticker_symbols = 'AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,^GSPC,^IXIC,^DJI,BTCUSD,ETHUSD'
    data = fmp_client.get_quote(ticker_symbols)
    return jsonify(data or [])

@app.route('/api/economic-calendar')
@login_required
def economic_calendar_api():
    today = date.today()
    end_date = today + timedelta(days=7)
    events = fmp_client.get_economic_calendar(today.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    return jsonify(events or [])

@app.route('/api/alerts/<string:symbol>')
@login_required
@pro_required
def get_alerts_for_symbol(symbol):
    alerts = db.session.scalars(
        db.select(Alert).where(
            Alert.user_id == current_user.id, 
            Alert.symbol == symbol.upper(), 
            Alert.is_active == True
        ).order_by(Alert.created_at.desc())
    ).all()
    return jsonify([{"id": a.id, "condition": a.condition, "target_price": a.target_price} for a in alerts])

@app.route('/market/<string:mover_type>')
@login_required
def market_movers_api(mover_type):
    if mover_type == 'gainers':
        data = fmp_client.get_market_gainers()
    elif mover_type == 'losers':
        data = fmp_client.get_market_losers()
    elif mover_type == 'active':
        data = fmp_client.get_market_active()
    else:
        abort(404)
    return jsonify(data or [])

@app.route('/profile/<string:symbol>')
@login_required
def show_profile(symbol):
    data = fmp_client.get_company_profile(symbol)
    return jsonify(data or {})

@app.route('/quote/<string:symbol>')
@login_required
def show_quote(symbol):
    quote_list = fmp_client.get_quote(symbol)
    if not quote_list:
        return jsonify({})
    
    quote = quote_list[0]
    # Transform data to match frontend expectations (portfolio page needs 'close')
    transformed_quote = {
        **quote, # Include all original keys from FMP
        'close': quote.get('price'), # Add 'close' key for compatibility
    }
    return jsonify(transformed_quote)

@app.route('/rating/<string:symbol>')
@login_required
@pro_required
def show_rating(symbol):
    data = fmp_client.get_stock_rating(symbol)
    return jsonify(data or {})

@app.route('/technicals/<string:symbol>')
@login_required
@pro_required
def show_technicals(symbol):
    history = fmp_client.get_historical_data(symbol)
    if not history:
        return jsonify({"error": "Historical data unavailable"}), 500
    # calculate_indicators returns data in the format the frontend expects
    return jsonify(calculate_indicators(history))

@app.route('/news/<string:symbol>')
@login_required
@pro_required
def show_news(symbol):
    data = fmp_client.get_stock_news(symbol)
    return jsonify(data or [])

@app.route('/technicals/hourly/<string:symbol>')
@login_required
@pro_required
def show_technicals_hourly(symbol):
    """Provides 1-hour historical data for intraday charts."""
    history = fmp_client.get_historical_data_hourly(symbol)
    if not history:
        return jsonify({"error": "Hourly historical data unavailable"}), 500
    
    # For hourly data, we just return it directly without technicals
    return jsonify({"history": history})

@app.route('/earnings/<string:symbol>')
@login_required
@pro_required
def show_earnings(symbol):
    today = date.today()
    end_date = today + timedelta(days=90)
    events = fmp_client.get_earnings_calendar(today.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    if not events:
        return jsonify([])
    
    symbol_events = [event for event in events if event.get('symbol', '').upper() == symbol.upper()]
    return jsonify(symbol_events)

@app.route('/fundamentals/<string:statement_type>/<string:symbol>')
@login_required
@pro_required
def get_fundamental_statement_data(statement_type, symbol):
    if statement_type == 'income':
        data = fmp_client.get_income_statement(symbol)
    elif statement_type == 'balance':
        data = fmp_client.get_balance_sheet(symbol)
    else:
        abort(404)
    return jsonify(data or [])

@app.route('/search/<string:query>')
@login_required
def search_symbols_api(query):
    data = fmp_client.search_symbol(query)
    return jsonify(data or [])

@app.route('/api/stock-screener')
@login_required
@pro_required
def run_stock_screener():
    param_map = {
        'marketCapMin': 'marketCapMoreThan', 'marketCapMax': 'marketCapLowerThan',
        'peMin': 'peRatioMoreThan', 'peMax': 'peRatioLowerThan',
        'sector': 'sector', 'industry': 'industry', 'country': 'country'
    }
    filters = {}
    for form_key, api_key in param_map.items():
        value = request.args.get(form_key)
        if value:
            # Convert market cap from billions to absolute number
            if form_key in ['marketCapMin', 'marketCapMax']:
                try:
                    filters[api_key] = int(float(value) * 1_000_000_000)
                except (ValueError, TypeError):
                    return jsonify({"error": f"Invalid value for {form_key}"}), 400
            else:
                filters[api_key] = value
                
    results = fmp_client.stock_screener(filters, limit=100)
    return jsonify(results or [])

@app.route('/api/journal/stats')
@login_required
def journal_stats_api():
    trades = current_user.trades.order_by(Trade.trade_date.asc(), Trade.id.asc()).all()
    pnl_trades = [t for t in trades if t.pnl is not None]

    if not pnl_trades:
        return jsonify({
            "total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0,
            "chart_data": {"labels": [], "pnl": [], "cumulative_pnl": []}
        })
    
    total_pnl = sum(t.pnl for t in pnl_trades)
    winning_trades = [t.pnl for t in pnl_trades if t.pnl > 0]
    losing_trades = [t.pnl for t in pnl_trades if t.pnl < 0]

    stats = {
        "total_pnl": total_pnl,
        "win_rate": (len(winning_trades) / len(pnl_trades)) * 100 if pnl_trades else 0,
        "avg_win": sum(winning_trades) / len(winning_trades) if winning_trades else 0,
        "avg_loss": sum(losing_trades) / len(losing_trades) if losing_trades else 0
    }
    
    cumulative_pnl = 0
    cumulative_pnl_data = []
    for trade in pnl_trades:
        cumulative_pnl += trade.pnl
        cumulative_pnl_data.append(cumulative_pnl)

    stats["chart_data"] = {
        "labels": [f"{t.trade_date.strftime('%b %d')} ({t.symbol})" for t in pnl_trades],
        "pnl": [t.pnl for t in pnl_trades],
        "cumulative_pnl": cumulative_pnl_data
    }
    
    return jsonify(stats)

@app.route('/api/run-backtest')
@login_required
@pro_required
def run_backtest_api():
    """API endpoint to run a backtest and return the results."""
    try:
        # --- Get parameters from request ---
        symbol = request.args.get('symbol', '').upper().strip()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        initial_capital = request.args.get('initial_capital', 10000, type=float)
        strategy = request.args.get('strategy')
        asset_class = request.args.get('asset_class', 'Stock')

        # --- Basic validation ---
        if not all([symbol, start_date, end_date, strategy]):
            return jsonify({"error": "Missing required parameters (symbol, start_date, end_date, strategy)."}), 400

        # --- Run the appropriate backtest ---
        results = None
        if strategy == 'sma_crossover':
            results = run_sma_crossover_backtest(symbol, start_date, end_date, initial_capital, asset_class)
        else:
            return jsonify({"error": "Invalid strategy specified."}), 400

        if results is None:
             return jsonify({"error": "Backtest could not be completed. Not enough historical data for the selected range and strategy."}), 400

        return jsonify(results)

    except ValueError as ve:
        logger.warning(f"ValueError in backtest for user {current_user.id}: {ve}")
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Unhandled exception in backtest API for user {current_user.id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred."}), 500

# Add this with your other API endpoints in routes.py

@app.route('/api/journal/advanced-stats')
@login_required
@pro_required # This decorator ensures it's a Pro feature
def journal_advanced_stats_api():
    """ Provides advanced, aggregated statistics for the user's trade journal. """
    trades = current_user.trades.all()
    if not trades:
        return jsonify({
            "by_asset_class": {},
            "by_day_of_week": {},
            "by_setup": {},
            "win_loss_streaks": {"winning": 0, "losing": 0}
        })

    df = pd.DataFrame([t.__dict__ for t in trades])
    if df.empty:
         return jsonify({"error": "No trade data to analyze"}), 404

    # --- Analysis Calculations ---
    
    # P&L by Asset Class
    by_asset = df.groupby('asset_class')['pnl'].agg(['sum', 'mean', 'count']).reset_index()
    by_asset.columns = ['name', 'total_pnl', 'avg_pnl', 'trade_count']
    
    # P&L by Day of Week
    df['day_of_week'] = pd.to_datetime(df['trade_date']).dt.day_name()
    by_day = df.groupby('day_of_week')['pnl'].agg(['sum', 'count']).reset_index()
    by_day.columns = ['name', 'total_pnl', 'trade_count']
    # Sort days correctly
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day['name'] = pd.Categorical(by_day['name'], categories=days_order, ordered=True)
    by_day = by_day.sort_values('name')

    # P&L by Setup/Reason
    df_setups = df.dropna(subset=['setup_reason'])
    by_setup = df_setups[df_setups['setup_reason'] != ''].groupby('setup_reason')['pnl'].agg(['sum', 'count']).reset_index()
    by_setup.columns = ['name', 'total_pnl', 'trade_count']
    by_setup = by_setup.sort_values('total_pnl', ascending=False)

    # Win/Loss Streaks
    streaks = {"winning": 0, "losing": 0}
    current_win_streak = 0
    current_loss_streak = 0
    for pnl in df.sort_values('trade_date')['pnl']:
        if pnl > 0:
            current_win_streak += 1
            current_loss_streak = 0
        elif pnl < 0:
            current_loss_streak += 1
            current_win_streak = 0
        streaks['winning'] = max(streaks['winning'], current_win_streak)
        streaks['losing'] = max(streaks['losing'], current_loss_streak)

    return jsonify({
        "by_asset_class": by_asset.to_dict(orient='records'),
        "by_day_of_week": by_day.to_dict(orient='records'),
        "by_setup": by_setup.to_dict(orient='records'),
        "win_loss_streaks": streaks
    })

@app.route('/api/chart-data-for-journal/<string:symbol>/<string:trade_date_str>')
@login_required
@pro_required # Assuming pro is required, as per original file
def get_chart_data_for_journal(symbol, trade_date_str):
    try:
        trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
        
        # Define a window around the trade date to provide context
        start_date = trade_date - timedelta(days=30)
        end_date = trade_date + timedelta(days=30)
        
        # Fetch historical data
        # The original file fetches up to 365 days, which is good practice
        historical_data = fmp_client.get_historical_data(symbol, days=365)
        if not historical_data:
            return jsonify({"error": f"No historical data found for {symbol}."}), 404
            
        # Filter the data to the desired window using pandas
        df = pd.DataFrame(historical_data)
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        # --- Start of new/modified code ---

        # 1. Clean data: Drop any rows with nulls in critical columns before filtering
        df.dropna(subset=['open', 'high', 'low', 'close'], inplace=True)

        mask = (df['date'] >= start_date) & (df['date'] <= end_date)
        filtered_df = df.loc[mask].copy() # Use .copy() to avoid SettingWithCopyWarning

        # --- End of new/modified code ---

        if filtered_df.empty:
            return jsonify({"error": "No data available for the period around the trade."}), 404

        # Sort by date to ensure the chart is chronological
        filtered_df.sort_values(by='date', inplace=True)

        # Format data for the charting library
        price_data = [
            {
                "time": row.date.strftime('%Y-%m-%d'),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close
            } for index, row in filtered_df.iterrows()
        ]

        return jsonify({"price_data": price_data})

    except ValueError:
        return jsonify({"error": "Invalid date format. Please use YYYY-MM-DD."}), 400
    except Exception as e:
        logger.error(f"Error fetching journal chart data for {symbol} on {trade_date_str}: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route('/api/top-symbols/<string:asset_class>')
@login_required
def get_top_symbols(asset_class):
    top_symbols = {
        "Forex": [
            "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "NZDUSD", "USDCHF"
        ],
        "Crypto": [
            "BTCUSD", "ETHUSD", "XRPUSD", "LTCUSD", "BCHUSD", "ADAUSD", "SOLUSD"
        ]
    }
    symbols = top_symbols.get(asset_class, [])
    return jsonify(symbols)