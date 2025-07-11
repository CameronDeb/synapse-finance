# app/api_clients/fmp_client.py
import os
import requests
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

FMP_API_KEY = os.environ.get('FMP_API_KEY')
BASE_URL_V3 = "https://financialmodelingprep.com/api/v3"
BASE_URL_V4 = "https://financialmodelingprep.com/api/v4"
REQUEST_TIMEOUT = 15

def get_economic_calendar(from_date, to_date):
    """ Fetches economic calendar events from FMP. """
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY missing for get_economic_calendar.")
        return None
    endpoint = "/economic_calendar"
    params = {'from': from_date, 'to': to_date, 'apikey': FMP_API_KEY}
    logger.debug(f"Fetching FMP economic calendar from {from_date} to {to_date}")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "Error Message" in data:
                logger.error(f"FMP API Error (Economic Calendar): {data['Error Message']}")
                return None
            else:
                logger.warning(f"Expected list for FMP economic calendar, got {type(data)}")
                return None
        else:
            logger.error(f"Unexpected content type FMP economic calendar: {content_type}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching FMP economic calendar: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError processing FMP economic calendar: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_economic_calendar", exc_info=True)
        return None

def stock_screener(filters, limit=100):
    """
    Performs a stock screen using the FMP API.
    'filters' is a dict of parameters for the API.
    """
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY missing for stock_screener.")
        return None
    endpoint = "/stock-screener"
    params = {'apikey': FMP_API_KEY, 'limit': limit}
    params.update(filters)
    logger.debug(f"Querying FMP Stock Screener with params: {params}")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "Error Message" in data:
                logger.error(f"FMP Screener API Error: {data['Error Message']}")
                return None
            else:
                logger.warning(f"Expected list for FMP screener, got {type(data)}")
                return None
        else:
            logger.error(f"Unexpected content type FMP screener: {content_type}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching FMP screener: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError processing FMP screener: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in stock_screener", exc_info=True)
        return None

def get_stock_rating(symbol):
    """ Fetches stock rating from FMP /v3/rating. Handles empty list. """
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY missing for get_stock_rating.")
        return None
    endpoint = f"/rating/{symbol}"
    params = {'apikey': FMP_API_KEY}
    logger.debug(f"Fetching FMP rating for {symbol}")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], dict):
                    return data[0]
                else:
                    logger.info(f"FMP returned empty list for rating: {symbol}. No rating available.")
                    return {}
            elif isinstance(data, dict) and "Error Message" in data:
                 logger.error(f"FMP Rating API Error for {symbol}: {data['Error Message']}")
                 return None
            else:
                 logger.warning(f"Unexpected data type/format from FMP rating for {symbol}: {type(data)}")
                 return None
        else:
            logger.error(f"Unexpected content type FMP rating for {symbol}: {content_type}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching FMP rating for {symbol}: {e}")
        return None
    except json.JSONDecodeError as e:
         logger.error(f"JSONDecodeError processing FMP rating for {symbol}: {e}")
         return None
    except Exception as e:
        logger.error(f"Unexpected error in get_stock_rating for {symbol}", exc_info=True)
        return None

def get_earnings_calendar_fmp(date_from=None, date_to=None):
    """ Fetches general earnings calendar from FMP /v3/earning_calendar """
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY missing for get_earnings_calendar_fmp.")
        return None
    endpoint = "/earning_calendar"
    params = {'apikey': FMP_API_KEY}
    if date_from: params['from'] = date_from
    if date_to: params['to'] = date_to
    logger.debug(f"Fetching FMP general earnings calendar (From: {date_from}, To: {date_to})")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "Error Message" in data:
                logger.error(f"FMP API Error (Earnings Calendar): {data['Error Message']}")
                return None
            else:
                logger.warning(f"Expected list for FMP general earnings, got {type(data)}")
                return None
        else:
            logger.error(f"Unexpected content type FMP general earnings: {content_type}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching FMP general earnings calendar: {e}")
        return None
    except json.JSONDecodeError as e:
         logger.error(f"JSONDecodeError processing FMP earnings calendar: {e}")
         return None
    except Exception as e:
        logger.error(f"Unexpected error fetching FMP earnings calendar", exc_info=True)
        return None

def get_company_profile(symbol):
    """ Fetches company profile from FMP /v3/profile """
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY missing for get_company_profile.")
        return None
    endpoint = f"/profile/{symbol}"
    params = {'apikey': FMP_API_KEY}
    logger.debug(f"Fetching FMP profile for {symbol}")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            elif isinstance(data, list) and len(data) == 0:
                 logger.info(f"FMP returned empty list for profile: {symbol}. Profile not found.");
                 return {}
            elif isinstance(data, dict) and "Error Message" in data:
                 logger.error(f"FMP Profile API Error for {symbol}: {data['Error Message']}")
                 return None
            else:
                 logger.warning(f"Expected list for FMP profile {symbol}, got {type(data)}")
                 return None
        else:
            logger.error(f"Unexpected content type FMP profile for {symbol}: {content_type}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching FMP profile for {symbol}: {e}")
        return None
    except json.JSONDecodeError as e:
         logger.error(f"JSONDecodeError processing FMP profile for {symbol}: {e}")
         return None
    except Exception as e:
        logger.error(f"Unexpected error fetching FMP profile for {symbol}", exc_info=True)
        return None

def search_symbol(query, limit=10, exchange=''):
    """ Searches for symbols using FMP /v3/search """
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY missing for search_symbol.")
        return None
    endpoint = "/search"
    params = {'query': query, 'limit': limit, 'apikey': FMP_API_KEY}
    if exchange: params['exchange'] = exchange
    logger.debug(f"Searching FMP symbols for query: '{query}' (Limit: {limit}, Exchange: {exchange or 'Any'})")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "Error Message" in data:
                 logger.error(f"FMP Search API Error for query '{query}': {data['Error Message']}")
                 return None
            else:
                 logger.warning(f"Expected list format for FMP search results for '{query}', got {type(data)}")
                 return None
        else:
            logger.error(f"Unexpected content type for FMP search query '{query}': {content_type}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException searching FMP symbols for query '{query}': {e}")
        return None
    except json.JSONDecodeError as e:
         logger.error(f"JSONDecodeError processing FMP search for query '{query}': {e}")
         return None
    except Exception as e:
        logger.error(f"Unexpected error fetching FMP search results for query '{query}'", exc_info=True)
        return None

def _fetch_market_list(endpoint_suffix, list_name):
    """ Helper function to fetch market lists (gainers, losers, active) """
    if not FMP_API_KEY:
        logger.error(f"FMP_API_KEY missing for _fetch_market_list ({list_name})")
        return None
    endpoint = f"/stock_market/{endpoint_suffix}"
    params = {'apikey': FMP_API_KEY}
    logger.debug(f"Fetching FMP market list: {list_name}")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "Error Message" in data:
                 logger.error(f"FMP API Error ({list_name}): {data['Error Message']}")
                 return None
            else:
                logger.warning(f"Expected list format for FMP {list_name}, got {type(data)}")
                return None
        else:
            logger.error(f"Unexpected content type FMP {list_name}: {content_type}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching FMP {list_name}: {e}")
        return None
    except json.JSONDecodeError as e:
         logger.error(f"JSONDecodeError processing FMP {list_name}: {e}")
         return None
    except Exception as e:
        logger.error(f"Unexpected error fetching FMP {list_name}", exc_info=True)
        return None

def get_market_gainers(): return _fetch_market_list("gainers", "Gainers")
def get_market_losers(): return _fetch_market_list("losers", "Losers")
def get_market_active(): return _fetch_market_list("actives", "Actives")

def get_income_statement(symbol, period='annual', limit=5):
    """ Fetches income statement reports for a symbol from FMP. """
    if not FMP_API_KEY: logger.error("FMP_API_KEY missing for get_income_statement."); return None
    endpoint = f"/income-statement/{symbol}"
    params = {'apikey': FMP_API_KEY, 'period': period, 'limit': limit }
    logger.debug(f"Fetching FMP Income Statement for {symbol} (Period: {period}, Limit: {limit})")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list): return data
            elif isinstance(data, dict) and "Error Message" in data: logger.error(f"FMP API Error (Income Statement {symbol}): {data['Error Message']}"); return None
            else: logger.warning(f"Expected list FMP income statement for {symbol}, got {type(data)}"); return None
        else: logger.error(f"Unexpected content type FMP income statement for {symbol}: {content_type}"); return None
    except requests.exceptions.RequestException as e: logger.error(f"RequestException fetching FMP income statement {symbol}: {e}"); return None
    except json.JSONDecodeError as e: logger.error(f"JSONDecodeError processing FMP income statement {symbol}: {e}"); return None
    except Exception as e: logger.error(f"Unexpected error in get_income_statement for {symbol}", exc_info=True); return None

def get_balance_sheet(symbol, period='annual', limit=5):
    """ Fetches balance sheet statement reports for a symbol from FMP. """
    if not FMP_API_KEY: logger.error("FMP_API_KEY missing for get_balance_sheet."); return None
    endpoint = f"/balance-sheet-statement/{symbol}"
    params = {'apikey': FMP_API_KEY, 'period': period, 'limit': limit }
    logger.debug(f"Fetching FMP Balance Sheet for {symbol} (Period: {period}, Limit: {limit})")
    try:
        response = requests.get(f"{BASE_URL_V3}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list): return data
            elif isinstance(data, dict) and "Error Message" in data: logger.error(f"FMP API Error (Balance Sheet {symbol}): {data['Error Message']}"); return None
            else: logger.warning(f"Expected list FMP balance sheet for {symbol}, got {type(data)}"); return None
        else: logger.error(f"Unexpected content type FMP balance sheet for {symbol}: {content_type}"); return None
    except requests.exceptions.RequestException as e: logger.error(f"RequestException fetching FMP balance sheet {symbol}: {e}"); return None
    except json.JSONDecodeError as e: logger.error(f"JSONDecodeError processing FMP balance sheet {symbol}: {e}"); return None
    except Exception as e: logger.error(f"Unexpected error in get_balance_sheet for {symbol}", exc_info=True); return None
