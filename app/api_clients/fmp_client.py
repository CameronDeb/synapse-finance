# app/api_clients/fmp_client.py
import os
import requests
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# --- Configuration ---
FMP_API_KEY = os.environ.get('FMP_API_KEY')
BASE_URL = "https://financialmodelingprep.com/api/v3"
REQUEST_TIMEOUT = 15

def _fmp_request(endpoint, params=None):
    """
    Private helper function to make requests to the FMP API.
    Handles adding the API key and generic error handling to reduce code duplication.
    """
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY is not set in environment variables.")
        return None
    
    if params is None:
        params = {}
    
    # Add API key to all requests
    params['apikey'] = FMP_API_KEY
    
    full_url = f"{BASE_URL}{endpoint}"
    logger.debug(f"Requesting FMP URL: {full_url}")

    try:
        response = requests.get(full_url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        
        data = response.json()
        if isinstance(data, dict) and "Error Message" in data:
            logger.error(f"FMP API returned an error for {endpoint}: {data['Error Message']}")
            return None
            
        return data

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP Error for {full_url}: {http_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"RequestException for {full_url}: {req_err}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during FMP request for {full_url}", exc_info=True)
        return None

# --- API Functions ---
# The @lru_cache decorator stores recent results of a function call.
# If the same function is called with the same arguments, the cached result is returned
# instantly instead of making another API call. This greatly improves performance.

@lru_cache(maxsize=256)
def get_quote(symbols):
    """Fetches real-time quotes for one or more symbols."""
    return _fmp_request(f"/quote/{symbols.upper()}")

@lru_cache(maxsize=128)
def get_historical_data(symbol, days=1300):
    """Fetches daily historical price data."""
    data = _fmp_request(f"/historical-price-full/{symbol.upper()}")
    if data and isinstance(data, dict) and 'historical' in data:
        # FMP returns data newest first, so we reverse it for charting
        historical_data = data['historical'][::-1]
        return historical_data[-days:]
    return []

def get_economic_calendar(from_date, to_date, limit=100):
    """Fetches economic calendar events for a date range."""
    params = {'from': from_date, 'to': to_date, 'limit': limit}
    return _fmp_request("/economic_calendar", params=params)

@lru_cache(maxsize=128)
def get_stock_rating(symbol):
    """Fetches the latest analyst rating for a stock."""
    data = _fmp_request(f"/rating/{symbol.upper()}")
    return data[0] if data and isinstance(data, list) else {}

@lru_cache(maxsize=128)
def get_company_profile(symbol):
    """Fetches company profile information."""
    data = _fmp_request(f"/profile/{symbol.upper()}")
    return data[0] if data and isinstance(data, list) else {}

def search_symbol(query, limit=10, exchange=''):
    """Searches for stock symbols matching a query."""
    return _fmp_request("/search", params={'query': query, 'limit': limit, 'exchange': exchange})

def get_earnings_calendar(from_date, to_date):
    """Fetches earnings calendar for a date range."""
    return _fmp_request("/earning_calendar", params={'from': from_date, 'to': to_date})

def get_economic_calendar(from_date, to_date):
    """Fetches economic calendar events for a date range."""
    return _fmp_request("/economic_calendar", params={'from': from_date, 'to': to_date})

def stock_screener(filters, limit=100):
    """Performs a stock screen based on a dictionary of filters."""
    filters['limit'] = limit
    return _fmp_request("/stock-screener", filters)

@lru_cache(maxsize=8)
def get_market_gainers():
    return _fmp_request("/stock_market/gainers")

@lru_cache(maxsize=8)
def get_market_losers():
    return _fmp_request("/stock_market/losers")

@lru_cache(maxsize=8)
def get_market_active():
    return _fmp_request("/stock_market/actives")

@lru_cache(maxsize=64)
def get_income_statement(symbol, period='annual', limit=5):
    """Fetches income statements."""
    return _fmp_request(f"/income-statement/{symbol.upper()}", params={'period': period, 'limit': limit})

@lru_cache(maxsize=64)
def get_balance_sheet(symbol, period='annual', limit=5):
    """Fetches balance sheets."""
    return _fmp_request(f"/balance-sheet-statement/{symbol.upper()}", params={'period': period, 'limit': limit})

@lru_cache(maxsize=128)
def get_historical_data_hourly(symbol):
    """Fetches 1-hour historical data from FMP."""
    return _fmp_request(f"/historical-chart/1hour/{symbol.upper()}")

def get_stock_news(symbol=None, limit=50):
    """Fetches financial news. Gets general news if symbol is None."""
    params = {'limit': limit}
    # Only add the 'tickers' parameter if a symbol is actually provided
    if symbol:
        params['tickers'] = symbol.upper()
    return _fmp_request("/stock_news", params=params)