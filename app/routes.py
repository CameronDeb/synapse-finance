# app/routes.py
from flask import jsonify, request, render_template, flash, redirect, url_for, session, abort
from app import app, db
from app.models import User, WatchlistItem, Holding, Trade, Alert
from app.email import send_password_reset_email, send_price_alert_email
from flask_login import login_user, logout_user, current_user, login_required
import os
import stripe
import logging
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from functools import wraps

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
    from .api_clients.eodhd_client import get_delayed_quote, get_historical_data, get_stock_news
    from .api_clients.fmp_client import (
        get_stock_rating, get_earnings_calendar_fmp, get_company_profile,
        search_symbol, get_market_gainers, get_market_losers, get_market_active,
        get_income_statement, get_balance_sheet, stock_screener
    )
    from .api_clients.api_ninjas_client import get_earnings_calendar_ninja
    from .services.technical_analyzer import calculate_indicators
    logger.info("Successfully imported API clients and services.")
except ImportError as e:
    logger.error(f"Could not import all API clients/services: {e}", exc_info=True)
    def get_delayed_quote(symbol): return None
    def get_historical_data(symbol, period_days=365): return None
    def get_stock_news(symbol, limit=15): return None
    def get_stock_rating(symbol): return None
    def get_earnings_calendar_fmp(date_from=None, date_to=None): return None
    def get_company_profile(symbol): return None
    def search_symbol(query, limit=10, exchange=''): return None
    def get_market_gainers(): return None
    def get_market_losers(): return None
    def get_market_active(): return None
    def get_income_statement(symbol, period='annual', limit=5): return None
    def get_balance_sheet(symbol, period='annual', limit=5): return None
    def get_earnings_calendar_ninja(symbol): return None
    def calculate_indicators(historical_data_list): return {"error": "Analysis service unavailable."}
    def stock_screener(filters, limit=100): return None


# --- Admin Decorator ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
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
@admin_required
def admin_panel():
    if request.method == 'POST':
        email = request.form.get('email')
        action = request.form.get('action')

        user = db.session.scalar(db.select(User).where(User.email == email))
        if not user:
            flash(f"User with email '{email}' not found.", 'error')
            return redirect(url_for('admin_panel'))

        if action == 'grant':
            user.subscription_tier = 'pro'
            flash(f"Successfully granted Pro access to {email}.", 'success')
        elif action == 'revoke':
            user.subscription_tier = 'free'
            user.stripe_subscription_id = None
            flash(f"Successfully revoked Pro access for {email}.", 'success')
        
        db.session.commit()
        return redirect(url_for('admin_panel'))

    return render_template('admin.html')


# --- Main Page Routes ---

@app.route('/')
def index():
    return render_template('home.html', current_user=current_user)

@app.route('/dashboard')
@login_required
def dashboard():
    watchlist_items = current_user.watchlist_items.order_by(WatchlistItem.symbol).all()
    return render_template('dashboard.html', current_user=current_user, watchlist=watchlist_items)

@app.route('/pricing')
def pricing_page():
    return render_template('pricing.html', current_user=current_user)

@app.route('/screener')
@login_required
def screener_page():
    return render_template('screener.html', current_user=current_user)

@app.route('/portfolio', methods=['GET'])
@login_required
def portfolio_page():
    user_holdings = current_user.holdings.order_by(Holding.symbol).all()
    total_invested_value = Decimal(0)
    for holding in user_holdings:
        total_invested_value += Decimal(str(holding.quantity)) * Decimal(str(holding.purchase_price))
    return render_template('portfolio.html', holdings=user_holdings, total_invested_value=total_invested_value, current_user=current_user)

@app.route('/journal', methods=['GET', 'POST'])
@login_required
def journal():
    if request.method == 'POST':
        try:
            symbol = request.form.get('symbol', '').upper().strip()
            pnl_str = request.form.get('pnl')
            trade_date_str = request.form.get('trade_date')
            asset_class = request.form.get('asset_class')
            setup_reason = request.form.get('setup_reason', '').strip()
            notes = request.form.get('notes', '').strip()
            if not all([symbol, pnl_str, trade_date_str]):
                flash('Symbol, P&L, and Date are required fields.', 'error')
                return redirect(url_for('journal'))
            pnl = float(pnl_str)
            trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
            new_trade = Trade(user_id=current_user.id, symbol=symbol, pnl=pnl, trade_date=trade_date, asset_class=asset_class, setup_reason=setup_reason, notes=notes)
            db.session.add(new_trade)
            db.session.commit()
            flash('Trade successfully logged!', 'success')
        except (ValueError, TypeError) as e:
            db.session.rollback()
            logger.error(f"Journal submission error for user {current_user.id}: {e}")
            flash('Invalid P&L or Date format.', 'error')
        return redirect(url_for('journal'))
    trades = current_user.trades.order_by(Trade.trade_date.desc()).all()
    return render_template('journal.html', trades=trades, current_user=current_user)

@app.route('/settings', methods=['GET'])
@login_required
def settings_page():
    return render_template('settings.html', current_user=current_user)


# --- User Authentication and Password Reset Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password'); remember = request.form.get('remember') == 'on'
        user = db.session.scalar(db.select(User).where(User.email == email))
        if user is None or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login_page'))
        login_user(user, remember=remember)
        flash('Login successful!', 'success')
        next_page = request.args.get('next')
        return redirect(next_page or url_for('dashboard'))
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password'); confirm_password = request.form.get('confirm_password')
        if not email or not password or not confirm_password: flash('All fields are required.', 'error'); return redirect(url_for('signup_page'))
        if password != confirm_password: flash('Passwords do not match.', 'error'); return redirect(url_for('signup_page'))
        existing_user = db.session.scalar(db.select(User).where(User.email == email))
        if existing_user is not None: flash('Email address already registered.', 'warning'); return redirect(url_for('login_page'))
        try:
            new_user = User(email=email, subscription_tier='free'); new_user.set_password(password); db.session.add(new_user); db.session.commit()
            flash('Account created successfully! Please log in.', 'success'); return redirect(url_for('login_page'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating user {email}", exc_info=True)
            flash('An error occurred during registration.', 'error'); return redirect(url_for('signup_page'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    user_email = current_user.email
    logout_user()
    session.pop('is_admin', None) # Clear admin session on logout
    flash('You have been logged out.', 'success'); return redirect(url_for('index'))

@app.route('/request-reset', methods=['GET', 'POST'])
def request_reset():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        user = db.session.scalar(db.select(User).where(User.email == email))
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
        confirm_password = request.form.get('confirm_password')
        if password and password == confirm_password:
            user.set_password(password)
            db.session.commit()
            flash('Your password has been updated! You are now able to log in.', 'success')
            return redirect(url_for('login_page'))
        else:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', token=token))
    return render_template('reset_password.html', token=token)

@app.route('/settings/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_new_password = request.form.get('confirm_new_password')
    if not current_user.check_password(current_password):
        flash('Your current password was incorrect. Please try again.', 'error')
        return redirect(url_for('settings_page'))
    if not new_password or new_password != confirm_new_password:
        flash('New passwords do not match. Please try again.', 'error')
        return redirect(url_for('settings_page'))
    try:
        current_user.set_password(new_password)
        db.session.commit()
        flash('Your password has been updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error changing password for user {current_user.email}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again.', 'error')
    return redirect(url_for('settings_page'))

@app.route('/settings/delete-account', methods=['POST'])
@login_required
def delete_account():
    try:
        user_email = current_user.email
        db.session.delete(current_user)
        db.session.commit()
        logout_user()
        flash('Your account has been permanently deleted.', 'info')
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting account for user {current_user.email}: {e}", exc_info=True)
        flash('An unexpected error occurred while deleting your account.', 'error')
        return redirect(url_for('settings_page'))


# --- Functional Routes (Portfolio, Watchlist, Alerts) ---

@app.route('/portfolio/add', methods=['POST'])
@login_required
def add_holding():
    try:
        symbol = request.form.get('symbol', '').upper().strip()
        quantity = Decimal(request.form.get('quantity', '0'))
        purchase_price = Decimal(request.form.get('purchase_price', '0'))
        purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date()
        new_holding = Holding(user_id=current_user.id, symbol=symbol, quantity=float(quantity), purchase_price=float(purchase_price), purchase_date=purchase_date)
        db.session.add(new_holding)
        db.session.commit()
        flash(f'{symbol} holding added successfully!', 'success')
    except (InvalidOperation, ValueError, Exception) as e:
        db.session.rollback()
        flash('Error adding holding.', 'error')
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
        flash('Holding not found or you do not have permission to delete it.', 'error')
    return redirect(url_for('portfolio_page'))

@app.route('/watchlist/add', methods=['POST'])
@login_required
def add_to_watchlist():
    return jsonify({'success': True, 'message': 'Added to watchlist.'})

@app.route('/watchlist/remove', methods=['POST'])
@login_required
def remove_from_watchlist():
    return jsonify({'success': True, 'message': 'Removed from watchlist.'})

@app.route('/alerts/create', methods=['POST'])
@login_required
def create_alert():
    if not current_user.is_pro:
        return jsonify({"error": "Upgrade to Pro to set price alerts."}), 403
    active_alert_count = db.session.scalar(db.select(db.func.count(Alert.id)).where(Alert.user_id == current_user.id, Alert.is_active == True))
    if active_alert_count >= ALERTS_LIMIT_PRO:
        return jsonify({"error": f"You have reached the maximum of {ALERTS_LIMIT_PRO} active alerts."}), 400
    try:
        symbol = request.form.get('symbol', '').upper().strip()
        condition = request.form.get('condition')
        target_price_str = request.form.get('target_price')
        if not all([symbol, condition, target_price_str]):
            return jsonify({"error": "Missing required fields."}), 400
        if condition not in ['above', 'below']:
            return jsonify({"error": "Invalid condition specified."}), 400
        target_price = float(target_price_str)
        new_alert = Alert(user_id=current_user.id, symbol=symbol, condition=condition, target_price=target_price)
        db.session.add(new_alert)
        db.session.commit()
        return jsonify({"message": "Alert set successfully!"})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid target price format."}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating alert for user {current_user.id}: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred."}), 500

@app.route('/alerts/delete/<int:alert_id>', methods=['POST'])
@login_required
def delete_alert(alert_id):
    alert = db.session.get(Alert, alert_id)
    if alert and alert.user_id == current_user.id:
        try:
            db.session.delete(alert)
            db.session.commit()
            return jsonify({"message": "Alert deleted."})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting alert {alert_id} for user {current_user.id}: {e}", exc_info=True)
            return jsonify({"error": "Could not delete alert."}), 500
    return jsonify({"error": "Alert not found or permission denied."}), 404


# --- Payment & Subscription Routes ---

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    if not STRIPE_PRO_PRICE_ID:
        flash('Payment system is not configured correctly.', 'error')
        return redirect(url_for('pricing_page'))
    try:
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            line_items=[{'price': STRIPE_PRO_PRICE_ID, 'quantity': 1}],
            mode='subscription',
            success_url=url_for('payment_success', _external=True),
            cancel_url=url_for('pricing_page', _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        logger.error(f"Stripe Checkout error for user {current_user.email}: {e}", exc_info=True)
        flash('An error occurred with our payment provider. Please try again later.', 'error')
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
        flash('An error occurred with our payment provider. Please try again later.', 'error')
        return redirect(url_for('settings_page'))

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    event = None
    if not stripe_webhook_secret:
        logger.critical("Stripe webhook secret is not configured.")
        return 'Webhook secret not configured', 500
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, stripe_webhook_secret)
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        return 'Invalid signature', 400
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        user = db.session.scalar(db.select(User).where(User.stripe_customer_id == customer_id))
        if user:
            user.subscription_tier = 'pro'
            user.stripe_subscription_id = subscription_id
            db.session.commit()
            logger.info(f"User {user.email} successfully upgraded to Pro.")
    elif event['type'] == 'customer.subscription.deleted':
        session = event['data']['object']
        customer_id = session.get('customer')
        user = db.session.scalar(db.select(User).where(User.stripe_customer_id == customer_id))
        if user:
            user.subscription_tier = 'free'
            db.session.commit()
            logger.info(f"User {user.email} subscription deleted, downgraded to Free.")
    else:
        logger.info(f"Unhandled Stripe event type: {event['type']}")
    return jsonify(success=True)


# --- API Data Endpoints ---

@app.route('/api/alerts/<string:symbol>')
@login_required
def get_alerts_for_symbol(symbol):
    if not current_user.is_pro:
        return jsonify({"error": "Pro subscription required for alerts."}), 403
    alerts = db.session.scalars(db.select(Alert).where(Alert.user_id == current_user.id, Alert.symbol == symbol, Alert.is_active == True).order_by(Alert.created_at.desc())).all()
    alerts_data = [{"id": alert.id, "symbol": alert.symbol, "condition": alert.condition, "target_price": alert.target_price} for alert in alerts]
    return jsonify(alerts_data)

@app.route('/market/gainers')
@login_required
def market_gainers_api():
    return jsonify(get_market_gainers() or [])

@app.route('/market/losers')
@login_required
def market_losers_api():
    return jsonify(get_market_losers() or [])

@app.route('/market/active')
@login_required
def market_active_api():
    return jsonify(get_market_active() or [])

@app.route('/profile/<string:fmp_symbol>')
@login_required
def show_profile(fmp_symbol):
    return jsonify(get_company_profile(fmp_symbol.upper()) or [])

@app.route('/quote/<string:eod_symbol>')
@login_required
def show_quote(eod_symbol):
    if not current_user.is_pro: return jsonify({"error": "Pro plan required"}), 403
    return jsonify(get_delayed_quote(eod_symbol.upper()) or {})

@app.route('/rating/<string:fmp_symbol>')
@login_required
def show_rating(fmp_symbol):
    if not current_user.is_pro: return jsonify({"error": "Pro plan required"}), 403
    return jsonify(get_stock_rating(fmp_symbol.upper()) or {})

@app.route('/technicals/<string:eod_symbol>')
@login_required
def show_technicals(eod_symbol):
    if not current_user.is_pro: return jsonify({"error": "Pro plan required"}), 403
    history = get_historical_data(eod_symbol.upper(), period_days=1300)
    if not history: return jsonify({"error": "Historical data unavailable"}), 500
    return jsonify(calculate_indicators(history))

@app.route('/news/<string:eod_symbol>')
@login_required
def show_news(eod_symbol):
    if not current_user.is_pro: return jsonify({"error": "Pro plan required"}), 403
    return jsonify(get_stock_news(eod_symbol.upper()) or [])

@app.route('/earnings/<string:fmp_symbol>')
@login_required
def show_earnings(fmp_symbol):
    if not current_user.is_pro: return jsonify({"error": "Pro plan required"}), 403
    return jsonify(get_earnings_calendar_ninja(fmp_symbol.upper().replace('.US', '')) or [])

@app.route('/fundamentals/income/<string:fmp_symbol>')
@login_required
def get_income_statement_data(fmp_symbol):
    if not current_user.is_pro: return jsonify({"error": "Pro plan required"}), 403
    return jsonify(get_income_statement(fmp_symbol.upper()) or [])

@app.route('/fundamentals/balance/<string:fmp_symbol>')
@login_required
def get_balance_sheet_data(fmp_symbol):
    if not current_user.is_pro: return jsonify({"error": "Pro plan required"}), 403
    return jsonify(get_balance_sheet(fmp_symbol.upper()) or [])

@app.route('/search/<string:query>')
@login_required
def search_symbols_api(query):
    return jsonify(search_symbol(query.upper(), limit=8) or [])

@app.route('/api/stock-screener')
@login_required
def run_stock_screener():
    if not current_user.is_pro:
        return jsonify({"error": "Pro subscription required to use the screener."}), 403
    param_map = {'marketCapMin': 'marketCapMoreThan', 'marketCapMax': 'marketCapLowerThan', 'peMin': 'peRatioMoreThan', 'peMax': 'peRatioLowerThan', 'sector': 'sector', 'industry': 'industry', 'country': 'country'}
    filters = {}
    for form_key, api_key in param_map.items():
        value = request.args.get(form_key)
        if value:
            if form_key in ['marketCapMin', 'marketCapMax']:
                try:
                    filters[api_key] = int(float(value) * 1_000_000_000)
                except (ValueError, TypeError):
                    return jsonify({"error": f"Invalid value for {form_key}"}), 400
            else:
                filters[api_key] = value
    try:
        results = stock_screener(filters, limit=100)
        if results is None:
            return jsonify({"error": "Failed to fetch screener results from the provider."}), 500
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error in run_stock_screener route for user {current_user.id}: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred."}), 500

@app.route('/api/journal/stats')
@login_required
def journal_stats_api():
    try:
        trades = current_user.trades.order_by(Trade.trade_date.asc(), Trade.id.asc()).all()
        pnl_trades = [t for t in trades if t.pnl is not None]
        if not pnl_trades:
            return jsonify({"total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0, "chart_data": {"labels": [], "pnl": [], "cumulative_pnl": []}})
        total_pnl = sum(t.pnl for t in pnl_trades)
        winning_trades = [t.pnl for t in pnl_trades if t.pnl > 0]
        losing_trades = [t.pnl for t in pnl_trades if t.pnl < 0]
        win_rate = (len(winning_trades) / len(pnl_trades)) * 100 if pnl_trades else 0
        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0
        cumulative_pnl_data = []
        current_cumulative_pnl = 0
        for trade in pnl_trades:
            current_cumulative_pnl += trade.pnl
            cumulative_pnl_data.append(current_cumulative_pnl)
        chart_labels = [f"{t.trade_date.strftime('%b %d')} ({t.symbol})" for t in pnl_trades]
        chart_pnl = [t.pnl for t in pnl_trades]
        return jsonify({"total_pnl": total_pnl, "win_rate": win_rate, "avg_win": avg_win, "avg_loss": avg_loss, "chart_data": {"labels": chart_labels, "pnl": chart_pnl, "cumulative_pnl": cumulative_pnl_data}})
    except Exception as e:
        logger.error(f"Error calculating journal stats for user {current_user.id}: {e}", exc_info=True)
        return jsonify({"error": "Could not calculate journal statistics"}), 500
