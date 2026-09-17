# app/api_clients/demo_client.py
"""
Market data client backed by the offline snapshot in app/demo_data.

Mirrors the function signatures and response shapes of fmp_client so routes and
services work unchanged. Regenerate the snapshot with scripts/build_demo_snapshot.py.
"""
import gzip
import json
import logging
import os
from datetime import date, datetime
from functools import lru_cache

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'demo_data')


@lru_cache(maxsize=1)
def _index():
    path = os.path.join(DATA_DIR, 'index.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        logger.critical(f"Demo snapshot missing or unreadable at {path}. Run scripts/build_demo_snapshot.py.")
        return {"symbols": {}, "economic_calendar": [], "as_of": date.today().isoformat()}


@lru_cache(maxsize=24)
def _symbol_record(symbol):
    entry = _index()["symbols"].get(symbol)
    if not entry:
        return None
    path = os.path.join(DATA_DIR, 'symbols', f'{symbol}.json.gz')
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        logger.error(f"Demo data file missing for {symbol}: {path}")
        return None


def _normalize(symbol):
    return (symbol or '').strip().upper()


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()


def _stock_quotes():
    return [v['quote'] for v in _index()['symbols'].values() if v['kind'] == 'stock']


# --- Snapshot metadata ---

def today():
    """The snapshot's 'current' trading day; date-relative views anchor to this."""
    return _as_date(_index()['as_of'])


def is_supported(symbol):
    return _normalize(symbol) in _index()['symbols']


def available_symbols(kind=None):
    return sorted(s for s, v in _index()['symbols'].items() if kind is None or v['kind'] == kind)


# --- API Functions (same contract as fmp_client) ---

def get_quote(symbols):
    quotes = []
    for symbol in _normalize(symbols).split(','):
        entry = _index()['symbols'].get(symbol.strip())
        if entry:
            quotes.append(dict(entry['quote']))
    return quotes


def get_historical_data(symbol, days=1300):
    record = _symbol_record(_normalize(symbol))
    if not record:
        return []
    rows = record['daily'][-days:]
    return [{"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v} for d, o, h, l, c, v in rows]


def get_historical_data_hourly(symbol):
    record = _symbol_record(_normalize(symbol))
    if not record:
        return []
    # FMP returns intraday bars newest first.
    return [{"date": d, "open": o, "high": h, "low": l, "close": c, "volume": v}
            for d, o, h, l, c, v in reversed(record['hourly'])]


def get_economic_calendar(from_date, to_date):
    start, end = _as_date(from_date), _as_date(to_date)
    return [e for e in _index().get('economic_calendar', []) if start <= _as_date(e['date']) <= end]


def get_stock_rating(symbol):
    entry = _index()['symbols'].get(_normalize(symbol))
    return dict(entry.get('rating') or {}) if entry else {}


def get_company_profile(symbol):
    symbol = _normalize(symbol)
    entry = _index()['symbols'].get(symbol)
    if not entry:
        return {}
    if entry.get('profile'):
        return dict(entry['profile'])
    # Indexes, crypto and forex have no company profile; synthesize a minimal one.
    quote = entry['quote']
    return {
        "symbol": symbol,
        "companyName": quote['name'],
        "sector": entry['kind'].capitalize(),
        "beta": None,
        "price": quote['price'],
    }


def search_symbol(query, limit=10, exchange=''):
    q = _normalize(query)
    if not q:
        return []
    matches = []
    for symbol, entry in _index()['symbols'].items():
        name = entry['quote']['name'] or ''
        if symbol == q:
            rank = 0
        elif symbol.startswith(q):
            rank = 1
        elif q in name.upper():
            rank = 2
        else:
            continue
        matches.append((rank, symbol, {"symbol": symbol, "name": name, "exchangeShortName": entry['quote'].get('exchange')}))
    return [m[2] for m in sorted(matches, key=lambda m: (m[0], m[1]))[:limit]]


def get_symbol_earnings(symbol):
    entry = _index()['symbols'].get(_normalize(symbol))
    return list(entry.get('earnings') or []) if entry else []


def get_earnings_calendar(from_date, to_date):
    start, end = _as_date(from_date), _as_date(to_date)
    return [e for s in available_symbols('stock') for e in get_symbol_earnings(s)
            if start <= _as_date(e['date']) <= end]


def stock_screener(filters, limit=100):
    def within(value, low_key, high_key):
        low, high = filters.get(low_key), filters.get(high_key)
        if low is None and high is None:
            return True
        if value is None:
            return False
        return (low is None or value >= float(low)) and (high is None or value <= float(high))

    results = []
    for symbol, entry in _index()['symbols'].items():
        profile = entry.get('profile')
        if entry['kind'] != 'stock' or not profile:
            continue
        quote = entry['quote']
        if filters.get('sector') and profile.get('sector') != filters['sector']:
            continue
        if filters.get('industry') and profile.get('industry') != filters['industry']:
            continue
        if filters.get('country') and profile.get('country') != filters['country']:
            continue
        if not (within(quote.get('marketCap'), 'marketCapMoreThan', 'marketCapLowerThan')
                and within(quote.get('pe'), 'peRatioMoreThan', 'peRatioLowerThan')
                and within(profile.get('beta'), 'betaMoreThan', 'betaLowerThan')
                and within(quote.get('avgVolume'), 'volumeMoreThan', 'volumeLowerThan')
                and within(profile.get('dividendYield'), 'dividendYieldMoreThan', 'dividendYieldLowerThan')):
            continue
        results.append({
            "symbol": symbol,
            "companyName": quote['name'],
            "price": quote['price'],
            "marketCap": quote.get('marketCap'),
            "volume": quote.get('avgVolume'),
            "beta": profile.get('beta'),
            "peRatio": quote.get('pe'),
            "dividendYield": profile.get('dividendYield'),
            "sector": profile.get('sector'),
            "industry": profile.get('industry'),
            "country": profile.get('country'),
        })
    results.sort(key=lambda r: r['marketCap'] or 0, reverse=True)
    return results[:int(filters.get('limit', limit))]


def get_market_gainers():
    return sorted(_stock_quotes(), key=lambda q: q['changesPercentage'], reverse=True)[:10]


def get_market_losers():
    return sorted(_stock_quotes(), key=lambda q: q['changesPercentage'])[:10]


def get_market_active():
    return sorted(_stock_quotes(), key=lambda q: q['volume'] or 0, reverse=True)[:10]


def get_income_statement(symbol, period='annual', limit=5):
    record = _symbol_record(_normalize(symbol))
    return list(record.get('income') or [])[:limit] if record else []


def get_balance_sheet(symbol, period='annual', limit=5):
    record = _symbol_record(_normalize(symbol))
    return list(record.get('balance') or [])[:limit] if record else []


def get_stock_news(symbol=None, limit=50):
    news = _index().get('news', [])  # already newest first
    if symbol:
        wanted = set(_normalize(symbol).split(','))
        news = [a for a in news if a['symbol'] in wanted]
    return news[:limit]
