# app/routes.py
from flask import jsonify, request, render_template, flash, redirect, url_for, abort, current_app, Response
from app import app, db # Import app for current_app access inside routes
from app.models import User, WatchlistItem
from flask_login import login_user, logout_user, current_user, login_required
import os
import traceback
import stripe
import logging # <--- Import standard logging

# --- Get Logger ---
# Get logger instance for module-level logging (safe during import)
logger = logging.getLogger(__name__)

# --- Import API Clients & Services ---
# Ensure these paths are correct relative to routes.py
try:
    from .api_clients.eodhd_client import get_delayed_quote, get_historical_data, get_stock_news
    from .api_clients.fmp_client import (
        get_stock_rating, get_earnings_calendar_fmp, get_company_profile,
        search_symbol, get_market_gainers, get_market_losers, get_market_active,
        get_income_statement, get_balance_sheet # Ensure these are imported
    )
    from .api_clients.api_ninjas_client import get_earnings_calendar_ninja
    from .services.technical_analyzer import calculate_indicators
    # Use standard logger here - safe during import
    logger.info("Successfully imported API clients and services.")
except ImportError as e:
    # Use standard logger here - safe during import
    logger.error(f"Could not import all API clients/services: {e}", exc_info=True)
    # Define dummy functions if imports fail to allow startup, but features will fail
    # Log warnings when these dummy functions are called (using standard logger is fine here too)
    def get_delayed_quote(symbol): logger.warning("Dummy get_delayed_quote called: EODHD client missing"); return None
    def get_historical_data(symbol, period_days=365): logger.warning("Dummy get_historical_data called: EODHD client missing"); return None
    def get_stock_news(symbol, limit=15): logger.warning("Dummy get_stock_news called: EODHD client missing"); return None
    def get_stock_rating(symbol): logger.warning("Dummy get_stock_rating called: FMP client missing"); return None
    def get_earnings_calendar_fmp(date_from=None, date_to=None): logger.warning("Dummy get_earnings_calendar_fmp called: FMP client missing"); return None
    def get_company_profile(symbol): logger.warning("Dummy get_company_profile called: FMP client missing"); return None
    def search_symbol(query, limit=10, exchange=''): logger.warning("Dummy search_symbol called: FMP client missing"); return None
    def get_market_gainers(): logger.warning("Dummy get_market_gainers called: FMP client missing"); return None
    def get_market_losers(): logger.warning("Dummy get_market_losers called: FMP client missing"); return None
    def get_market_active(): logger.warning("Dummy get_market_active called: FMP client missing"); return None
    def get_income_statement(symbol, period='annual', limit=5): logger.warning("Dummy get_income_statement called: FMP client missing"); return None
    def get_balance_sheet(symbol, period='annual', limit=5): logger.warning("Dummy get_balance_sheet called: FMP client missing"); return None
    def get_earnings_calendar_ninja(symbol): logger.warning("Dummy get_earnings_calendar_ninja called: API Ninjas client missing"); return None
    def calculate_indicators(historical_data_list): logger.warning("Dummy calculate_indicators called: Analysis service missing"); return {"error": "Analysis service unavailable."}

# --- Configure Stripe Key ---
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
stripe_webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

# --- Constants ---
WATCHLIST_LIMIT_FREE = 5

# --- Page Routes ---
# It's safe to use current_app.logger inside route functions
@app.route('/')
def index():
    """Renders the public home page."""
    return render_template('home.html', current_user=current_user)

@app.route('/dashboard')
@login_required
def dashboard():
    """Renders the user's dashboard page, including watchlist."""
    watchlist_items = [] # Initialize empty
    try:
        # Query using the relationship defined in User model
        watchlist_items = current_user.watchlist_items.order_by(WatchlistItem.symbol).all()
    except AttributeError:
        # Fallback query if relationship isn't loading correctly on current_user
        current_app.logger.warning(f"current_user.watchlist_items relationship failed. Querying directly for user {current_user.id}.")
        try:
            watchlist_items = db.session.execute(
                db.select(WatchlistItem).filter_by(user_id=current_user.id).order_by(WatchlistItem.symbol)
            ).scalars().all()
        except Exception as e_fallback:
             current_app.logger.error(f"Fallback watchlist query failed for user {current_user.id}", exc_info=True)
             flash("Could not load watchlist data.", "error")
    except Exception as e:
        current_app.logger.error(f"Exception fetching watchlist for user {current_user.id}", exc_info=True)
        flash("Could not load watchlist.", "error")

    return render_template('dashboard.html',
                           current_user=current_user,
                           watchlist=watchlist_items)

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Handles user login."""
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password'); remember = request.form.get('remember') == 'on';
        if not email or not password: flash('Email and password are required.', 'error'); return redirect(url_for('login_page'))
        user = db.session.scalar(db.select(User).where(User.email == email));
        if user is None or not user.check_password(password): flash('Invalid email or password.', 'error'); return redirect(url_for('login_page'))
        login_user(user, remember=remember);
        current_app.logger.info(f"User {user.email} logged in successfully.") # Log successful login
        flash('Login successful!', 'success'); next_page = request.args.get('next');
        if next_page and not next_page.startswith(('/', 'http://', 'https://')): next_page = None
        return redirect(next_page or url_for('dashboard'))
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    """Handles new user registration."""
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password'); confirm_password = request.form.get('confirm_password');
        if not email or not password or not confirm_password: flash('All fields are required.', 'error'); return redirect(url_for('signup_page'))
        if password != confirm_password: flash('Passwords do not match.', 'error'); return redirect(url_for('signup_page'))
        existing_user = db.session.scalar(db.select(User).where(User.email == email));
        if existing_user is not None: flash('Email address already registered.', 'warning'); return redirect(url_for('login_page'))
        try:
            new_user = User(email=email, subscription_tier='free'); new_user.set_password(password); db.session.add(new_user); db.session.commit();
            current_app.logger.info(f"New user created: {email}") # Log user creation
            flash('Account created successfully! Please log in.', 'success'); return redirect(url_for('login_page'))
        except Exception as e:
            db.session.rollback();
            current_app.logger.error(f"Error creating user {email}", exc_info=True)
            flash('An error occurred during registration.', 'error'); return redirect(url_for('signup_page'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    """Logs the current user out."""
    user_email = current_user.email # Get email before logout
    logout_user();
    current_app.logger.info(f"User {user_email} logged out.") # Log logout
    flash('You have been logged out.', 'success'); return redirect(url_for('index'))

@app.route('/pricing')
def pricing_page():
    """Displays the pricing page."""
    stripe_publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    return render_template('pricing.html', stripe_key=stripe_publishable_key, current_user=current_user)


# --- Payment Routes ---
@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """Initiates a Stripe Checkout session."""
    pro_price_id = os.environ.get('STRIPE_PRICE_ID')
    if not stripe.api_key:
        current_app.logger.error("STRIPE_SECRET_KEY not configured.")
        flash("Payment system configuration error.", "error"); return redirect(url_for('pricing_page'))
    if not pro_price_id:
        current_app.logger.error("STRIPE_PRICE_ID not set.")
        flash("Payment plan configuration error.", "error"); return redirect(url_for('pricing_page'))
    success_url = url_for('payment_success', _external=True); cancel_url = url_for('pricing_page', _external=True);
    current_app.logger.info(f"User {current_user.email} initiating checkout for Price ID: {pro_price_id}")
    try:
        checkout_session = stripe.checkout.Session.create( line_items=[{'price': pro_price_id, 'quantity': 1}], mode='subscription', success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}', cancel_url=cancel_url, client_reference_id=str(current_user.id) )
        current_app.logger.info(f"Created Stripe Session ID: {checkout_session.id} for user {current_user.id}");
        return redirect(checkout_session.url, code=303)
    except stripe.error.InvalidRequestError as e:
        msg = f"Payment error: {e.user_message}" if e.user_message else "Configuration error."
        current_app.logger.error(f"Stripe Invalid Request Error creating checkout session: {e}")
        flash(msg, "error"); return redirect(url_for('pricing_page'))
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe Error creating checkout session: {e}")
        flash("Payment processor communication error.", "error"); return redirect(url_for('pricing_page'))
    except Exception as e:
        current_app.logger.error("Other Exception creating checkout session", exc_info=True)
        flash("Unexpected checkout error.", "error"); return redirect(url_for('pricing_page'))

@app.route('/payment-success')
@login_required
def payment_success():
    """Page shown after successful checkout redirect."""
    session_id = request.args.get('session_id');
    current_app.logger.info(f"User {current_user.id} reached payment_success page. Stripe Session ID: {session_id}");
    flash("Payment successful! Your Pro upgrade is being processed.", "success"); return redirect(url_for('dashboard'))

@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    """Listens for events from Stripe."""
    payload = request.data; sig_header = request.headers.get('Stripe-Signature'); event = None;
    # Use current_app here as it's processing a request-like event
    current_app.logger.info("Stripe Webhook received...")
    if not stripe_webhook_secret:
        current_app.logger.critical("FATAL ERROR: STRIPE_WEBHOOK_SECRET not configured.")
        return jsonify(error="Webhook configuration error"), 500
    try:
        event = stripe.Webhook.construct_event( payload, sig_header, stripe_webhook_secret )
        current_app.logger.info(f"Webhook event verified. Type: {event['type']} ID: {event['id']}")
    except ValueError as e:
        current_app.logger.error(f"Invalid webhook payload: {e}")
        return jsonify(error="Invalid payload"), 400
    except stripe.error.SignatureVerificationError as e:
        current_app.logger.error(f"Invalid webhook signature: {e}")
        return jsonify(error="Invalid signature"), 400
    except Exception as e:
        current_app.logger.error(f"Webhook signature processing error", exc_info=True)
        return jsonify(error="Webhook signature processing error"), 500

    # Handle checkout session completed
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']; session_id = session.get('id'); payment_status = session.get('payment_status'); client_ref_id = session.get('client_reference_id');
        current_app.logger.info(f"Webhook: checkout.session.completed | Session: {session_id}, Status: {payment_status}, UserID: {client_ref_id}")

        if payment_status == 'paid':
            if not client_ref_id:
                current_app.logger.error(f"Webhook {event['id']} (checkout.session.completed) missing client_reference_id.")
                return jsonify(success=True, detail="Missing client ref ID"), 200 # Ack Stripe
            try:
                user_id = int(client_ref_id)
                # Need app context to interact with db session from webhook
                with app.app_context():
                    user = db.session.get(User, user_id) # Use db.session.get for primary key lookup
                    if user:
                        if user.subscription_tier != 'pro':
                            user.subscription_tier = 'pro'
                            db.session.commit()
                            current_app.logger.info(f"SUCCESS: Upgraded user {user_id} to 'pro' via webhook {event['id']}.")
                        else:
                            current_app.logger.info(f"Webhook {event['id']}: User {user_id} already 'pro'. No change needed.")
                    else:
                        current_app.logger.error(f"Webhook {event['id']}: User {client_ref_id} not found for checkout.session.completed.")
            except ValueError:
                current_app.logger.error(f"Webhook {event['id']}: Invalid client_reference_id format '{client_ref_id}'.")
                return jsonify(success=True, detail="Invalid client ref ID"), 200 # Ack Stripe
            except Exception as e:
                 # Log error within app context if possible
                current_app.logger.error(f"Webhook {event['id']}: DB error updating user tier {client_ref_id}", exc_info=True)
                try: # Attempt rollback within context if possible
                    with app.app_context():
                        db.session.rollback()
                except Exception as rb_e:
                     current_app.logger.error(f"Webhook {event['id']}: Failed to rollback DB session: {rb_e}")
                return jsonify(error="DB update failed"), 500
        else:
            current_app.logger.warning(f"Webhook {event['id']}: checkout.session.completed status was '{payment_status}'. No action taken.")

    # TODO: Handle other event types (add specific logic and logging)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']; stripe_customer_id = subscription.get('customer');
        current_app.logger.info(f"Webhook: customer.subscription.deleted for Customer: {stripe_customer_id} (Event ID: {event['id']}). Downgrade logic needed.")
        # Add downgrade logic here (find user by stripe_customer_id if stored, set tier to free)
        # Remember to use 'with app.app_context():' for DB operations
        pass
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']; stripe_customer_id = invoice.get('customer');
        current_app.logger.warning(f"Webhook: invoice.payment_failed for Customer: {stripe_customer_id} (Event ID: {event['id']}). Notification/downgrade logic needed.")
         # Add notification/downgrade logic here
         # Remember to use 'with app.app_context():' for DB operations
        pass
    else:
        current_app.logger.info(f"Webhook: Unhandled event type: {event['type']} (Event ID: {event['id']})")

    return jsonify(success=True), 200


# --- Watchlist Routes ---
@app.route('/watchlist/add', methods=['POST'])
@login_required
def add_to_watchlist():
    """Adds a symbol to the current user's watchlist."""
    symbol = request.form.get('symbol'); symbol = symbol.upper() if symbol else None
    if not symbol: return jsonify(success=False, error='Symbol required.'), 400
    try: current_count = db.session.query(db.func.count(WatchlistItem.id)).filter_by(user_id=current_user.id).scalar()
    except Exception as e:
        current_app.logger.error(f"DB error counting watchlist for user {current_user.id}", exc_info=True)
        return jsonify(success=False, error='DB error checking watchlist.'), 500
    if not current_user.is_pro:
        if current_count >= WATCHLIST_LIMIT_FREE:
             current_app.logger.warning(f"User {current_user.id} tried adding '{symbol}' but reached free limit ({WATCHLIST_LIMIT_FREE}).")
             return jsonify(success=False, error=f'Free tier limit ({WATCHLIST_LIMIT_FREE}) reached.'), 400
    exists = db.session.scalar(db.select(WatchlistItem).filter_by(owner=current_user, symbol=symbol))
    if exists: return jsonify(success=False, error=f'{symbol} already in watchlist.'), 400
    try:
        item = WatchlistItem(owner=current_user, symbol=symbol); db.session.add(item); db.session.commit();
        current_app.logger.info(f"Added '{symbol}' to watchlist for user {current_user.id}")
        return jsonify(success=True, symbol=symbol, message=f'{symbol} added.')
    except Exception as e:
        db.session.rollback();
        current_app.logger.error(f"DB error adding watchlist '{symbol}' for user {current_user.id}", exc_info=True)
        return jsonify(success=False, error='Database error adding symbol.'), 500

@app.route('/watchlist/remove', methods=['POST'])
@login_required
def remove_from_watchlist():
    """Removes a symbol from the current user's watchlist."""
    symbol = request.form.get('symbol'); symbol = symbol.upper() if symbol else None
    if not symbol: return jsonify(success=False, error='Symbol required.'), 400
    item = db.session.execute(db.select(WatchlistItem).filter_by(owner=current_user, symbol=symbol)).scalar_one_or_none();
    if item:
        try:
            db.session.delete(item); db.session.commit();
            current_app.logger.info(f"Removed '{symbol}' from watchlist for user {current_user.id}")
            return jsonify(success=True, symbol=symbol, message=f'{symbol} removed.')
        except Exception as e:
            db.session.rollback();
            current_app.logger.error(f"DB error removing watchlist '{symbol}' for user {current_user.id}", exc_info=True)
            return jsonify(success=False, error='Database error removing symbol.'), 500
    else: return jsonify(success=False, error='Symbol not found in watchlist.'), 404


# --- Market Mover API Endpoints ---
@app.route('/market/gainers')
@login_required
def market_gainers_api():
    current_app.logger.debug("Request received for /market/gainers")
    data = get_market_gainers()
    return jsonify(data) if data is not None else (jsonify({"error": "Could not retrieve gainers"}), 500)

@app.route('/market/losers')
@login_required
def market_losers_api():
    current_app.logger.debug("Request received for /market/losers")
    data = get_market_losers()
    return jsonify(data) if data is not None else (jsonify({"error": "Could not retrieve losers"}), 500)

@app.route('/market/active')
@login_required
def market_active_api():
    current_app.logger.debug("Request received for /market/active")
    data = get_market_active()
    return jsonify(data) if data is not None else (jsonify({"error": "Could not retrieve active"}), 500)


# --- Symbol-Specific Data API Endpoints ---
@app.route('/profile/<string:fmp_symbol>')
@login_required
def show_profile(fmp_symbol):
    current_app.logger.debug(f"Request received for /profile/{fmp_symbol}")
    profile_data = get_company_profile(fmp_symbol.upper())
    return jsonify(profile_data) if profile_data is not None else (jsonify({"error": f"Profile not found for {fmp_symbol}"}), 404)

@app.route('/quote/<string:eod_symbol>')
@login_required
def show_quote(eod_symbol):
    current_app.logger.debug(f"Request received for /quote/{eod_symbol}")
    if not current_user.is_pro: return jsonify({"error": "Pro subscription required"}), 403
    quote_data = get_delayed_quote(eod_symbol.upper())
    return jsonify(quote_data) if quote_data else (jsonify({"error": f"Quote not found for {eod_symbol}"}), 404)

@app.route('/rating/<string:fmp_symbol>')
@login_required
def show_rating(fmp_symbol):
    current_app.logger.debug(f"Request received for /rating/{fmp_symbol}")
    if not current_user.is_pro: return jsonify({"error": "Pro subscription required"}), 403
    rating_data = get_stock_rating(fmp_symbol.upper())
    # Check if rating_data is {} which means 'not found' vs None which means 'error'
    if rating_data is None:
         return jsonify({"error": f"Error retrieving rating for {fmp_symbol}"}), 500
    elif not rating_data: # Empty dict means not found
         return jsonify({"error": f"Rating not found for {fmp_symbol}"}), 404
    else:
         return jsonify(rating_data)


@app.route('/technicals/<string:eod_symbol>')
@login_required
def show_technicals(eod_symbol):
    current_app.logger.debug(f"Request received for /technicals/{eod_symbol}")
    if not current_user.is_pro: return jsonify({"error": "Pro subscription required"}), 403
    symbol = eod_symbol.upper()
    historical_data = get_historical_data(symbol, period_days=365); # Fetch ~1 year for calculations
    if not historical_data:
        current_app.logger.warning(f"Could not fetch history for technicals calculation: {symbol}")
        return jsonify({"error": f"Could not fetch history for {symbol}."}), 500

    analysis_result = calculate_indicators(historical_data);
    if isinstance(analysis_result, dict) and "error" in analysis_result:
        current_app.logger.error(f"Error calculating indicators for {symbol}: {analysis_result['error']}")
        return jsonify(analysis_result), 500
    elif not analysis_result or "indicators" not in analysis_result or "history" not in analysis_result:
        current_app.logger.error(f"Invalid analysis result structure for {symbol}")
        return jsonify({"error": "Analysis processing error."}), 500

    current_app.logger.debug(f"Successfully calculated technicals for {symbol}")
    return jsonify(analysis_result)

@app.route('/search/<string:query>')
@login_required
def search_symbols_api(query):
    current_app.logger.debug(f"Request received for /search/{query}")
    results = search_symbol(query.upper(), limit=8)
    return jsonify(results) if results is not None else (jsonify({"error": "Search failed"}), 500)

@app.route('/news/<string:eod_symbol>')
@login_required
def show_news(eod_symbol):
    current_app.logger.debug(f"Request received for /news/{eod_symbol}")
    if not current_user.is_pro: return jsonify({"error": "Pro subscription required"}), 403
    news_data = get_stock_news(eod_symbol.upper(), limit=20);
    return jsonify(news_data) if news_data is not None else (jsonify({"error": f"News not found for {eod_symbol}"}), 404)

@app.route('/earnings/<string:fmp_symbol>')
@login_required
def show_earnings(fmp_symbol):
    # Use the FMP symbol format here, the API client will adapt if needed
    symbol = fmp_symbol.upper()
    current_app.logger.debug(f"Request received for /earnings/{symbol}")
    if not current_user.is_pro: return jsonify({"error": "Pro subscription required"}), 403
    # Using Ninja API for earnings - needs plain symbol usually
    plain_symbol = symbol.replace('.US', '') # Adapt symbol if needed
    earnings_data = get_earnings_calendar_ninja(plain_symbol)
    return jsonify(earnings_data) if earnings_data is not None else (jsonify({"error": f"Earnings not found for {plain_symbol}."}), 500)


# --- Fundamental Data Routes ---
@app.route('/fundamentals/income/<string:fmp_symbol>')
@login_required
def get_income_statement_data(fmp_symbol):
    """API endpoint to fetch income statement data."""
    if not current_user.is_pro: return jsonify({"error": "Pro subscription required"}), 403
    symbol = fmp_symbol.upper()
    current_app.logger.debug(f"ROUTE: Fetching income statement for {symbol}")
    data = get_income_statement(symbol, period='annual', limit=5) # Fetching 5 years
    return jsonify(data) if data is not None else (jsonify({"error": f"Could not fetch income statement for {symbol}"}), 500)

@app.route('/fundamentals/balance/<string:fmp_symbol>')
@login_required
def get_balance_sheet_data(fmp_symbol):
    """API endpoint to fetch balance sheet data."""
    if not current_user.is_pro: return jsonify({"error": "Pro subscription required"}), 403
    symbol = fmp_symbol.upper()
    current_app.logger.debug(f"ROUTE: Fetching balance sheet for {symbol}")
    data = get_balance_sheet(symbol, period='annual', limit=5) # Fetching 5 years
    return jsonify(data) if data is not None else (jsonify({"error": f"Could not fetch balance sheet for {symbol}"}), 500)
# --- End of Fundamental Data Routes ---