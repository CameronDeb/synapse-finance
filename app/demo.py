# app/demo.py
"""
Throwaway demo accounts: each visitor gets their own Pro user pre-filled with a
portfolio, trade journal, watchlist and alerts, so nobody sees anyone else's edits.
"""
import logging
import random
import secrets
import time
from datetime import timedelta

from app import db
from app.models import User, WatchlistItem, Holding, Trade, Alert
from app.api_clients import market_data

logger = logging.getLogger(__name__)

DEMO_EMAIL_DOMAIN = 'demo.synapse.finance'
DEMO_USER_TTL_SECONDS = 24 * 60 * 60

WATCHLIST = ['AAPL', 'NVDA', 'MSFT', 'TSLA', 'JPM', 'BTCUSD']

# (symbol, quantity, bought this many days before the snapshot date)
HOLDINGS = [
    ('AAPL', 25, 720), ('NVDA', 40, 540), ('MSFT', 12, 400),
    ('JPM', 20, 300), ('KO', 50, 250), ('LLY', 5, 150), ('TSLA', 10, 90),
]

JOURNAL_SETUPS = {
    'Futures': (['/ES', '/NQ', '/CL'], ['Opening range breakout', 'Liquidity sweep into FVG', 'VWAP reclaim']),
    'Stock': (['AAPL', 'NVDA', 'TSLA', 'AMD'], ['Earnings gap and go', 'Bull flag breakout', 'VWAP reclaim']),
    'Crypto': (['BTCUSD', 'ETHUSD'], ['Range high rejection', 'Liquidity sweep into FVG']),
    'Forex': (['EURUSD', 'GBPUSD'], ['London session breakout', 'Range high rejection']),
    'Options': (['SPY', 'QQQ'], ['0DTE momentum', 'Earnings IV crush']),
}


def _demo_email():
    # The creation time is embedded so expired accounts can be found without a schema change.
    return f"demo-{int(time.time())}-{secrets.token_hex(4)}@{DEMO_EMAIL_DOMAIN}"


def is_demo_user(user):
    return bool(user and user.email.endswith('@' + DEMO_EMAIL_DOMAIN))


def purge_expired_demo_users():
    cutoff = time.time() - DEMO_USER_TTL_SECONDS
    users = db.session.scalars(db.select(User).where(User.email.like(f'demo-%@{DEMO_EMAIL_DOMAIN}'))).all()
    expired = [u for u in users if int(u.email.split('-')[1]) < cutoff]
    for user in expired:
        db.session.delete(user)
    if expired:
        db.session.commit()
        logger.info(f"Purged {len(expired)} expired demo accounts.")


def _close_on_or_before(history, target):
    """Closing price on the last trading day at or before `target`."""
    target_str = target.isoformat()
    candidates = [bar for bar in history if bar['date'] <= target_str]
    return (candidates[-1] if candidates else history[0])['close']


def create_demo_user():
    purge_expired_demo_users()

    user = User(email=_demo_email(), subscription_tier='pro')
    user.set_password(secrets.token_urlsafe(24))  # never shown; demo users log in via the demo button
    db.session.add(user)
    db.session.flush()

    anchor = market_data.today()

    for symbol in WATCHLIST:
        if market_data.is_supported(symbol):
            db.session.add(WatchlistItem(user_id=user.id, symbol=symbol))

    for symbol, quantity, days_ago in HOLDINGS:
        history = market_data.get_historical_data(symbol, days=days_ago + 30)
        if not history:
            continue
        purchase_date = anchor - timedelta(days=days_ago)
        db.session.add(Holding(
            user_id=user.id, symbol=symbol, quantity=quantity,
            purchase_price=_close_on_or_before(history, purchase_date),
            purchase_date=purchase_date,
        ))

    rng = random.Random(7)  # every demo account gets the same, realistic-looking journal
    trade_day = anchor
    for _ in range(24):
        trade_day -= timedelta(days=rng.choice([1, 1, 2, 3]))
        while trade_day.weekday() >= 5:
            trade_day -= timedelta(days=1)
        asset_class = rng.choice(list(JOURNAL_SETUPS))
        symbols, setups = JOURNAL_SETUPS[asset_class]
        won = rng.random() < 0.6
        pnl = round(rng.uniform(90, 650) if won else -rng.uniform(60, 380), 2)
        db.session.add(Trade(
            user_id=user.id, symbol=rng.choice(symbols), pnl=pnl, trade_date=trade_day,
            asset_class=asset_class, setup_reason=rng.choice(setups),
            notes='Followed the plan.' if won else 'Entered early; wait for confirmation.',
        ))

    for symbol, condition, factor in [('AAPL', 'above', 1.05), ('AAPL', 'below', 0.92), ('NVDA', 'above', 1.10)]:
        quote = market_data.get_quote(symbol)
        if quote:
            db.session.add(Alert(user_id=user.id, symbol=symbol, condition=condition,
                                 target_price=round(quote[0]['price'] * factor, 2)))

    db.session.commit()
    logger.info(f"Created demo account {user.email}")
    return user
