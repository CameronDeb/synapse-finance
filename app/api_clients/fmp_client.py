# app/api_clients/fmp_client.py
import os
import requests
import json
# import traceback # No longer needed if using exc_info=True
from datetime import datetime, timedelta
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger instance

# Get the API key from environment variables
FMP_API_KEY = os.environ.get('FMP_API_KEY')

# Base URLs for FMP API
BASE_URL_V3 = "https://financialmodelingprep.com/api/v3"
BASE_URL_V4 = "https://financialmodelingprep.com/api/v4"
REQUEST_TIMEOUT = 10 # Seconds

# --- get_stock_rating function ---
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
        response.raise_for_status() # Check for HTTP errors like 4xx/5xx
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            # Handle FMP's potential responses: list (usually with one dict), or error dict
            if isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], dict):
                    return data[0] # Success, return the rating dict
                else:
                    logger.info(f"FMP returned empty list for rating: {symbol}. No rating available.")
                    return {} # Return empty dict to signify no rating found, not an error
            elif isinstance(data, dict) and "Error Message" in data:
                 logger.error(f"FMP Rating API Error for {symbol}: {data['Error Message']}")
                 return None # Actual API error
            else:
                 # Unexpected format, treat as error
                 logger.warning(f"Unexpected data type/format from FMP rating for {symbol}: {type(data)}")
                 return None
        else:
            # Non-JSON response
            logger.error(f"Unexpected content type FMP rating for {symbol}: {content_type}")
            logger.error(f"Response text: {response.text[:500]}...")
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

# --- get_earnings_calendar_fmp function ---
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
                return data # Expecting a list
            elif isinstance(data, dict) and "Error Message" in data:
                logger.error(f"FMP API Error (Earnings Calendar): {data['Error Message']}")
                return None
            else:
                logger.warning(f"Expected list for FMP general earnings, got {type(data)}")
                return None # Treat unexpected format as error
        else:
            logger.error(f"Unexpected content type FMP general earnings: {content_type}")
            logger.error(f"Response text: {response.text[:500]}...")
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

# --- get_company_profile function ---
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
                 return {} # Return empty dict for not found, not an error
            elif isinstance(data, dict) and "Error Message" in data:
                 logger.error(f"FMP Profile API Error for {symbol}: {data['Error Message']}")
                 return None # Actual API error
            else:
                 logger.warning(f"Expected list for FMP profile {symbol}, got {type(data)}")
                 return None # Treat unexpected format as error
        else:
            logger.error(f"Unexpected content type FMP profile for {symbol}: {content_type}")
            logger.error(f"Response text: {response.text[:500]}...")
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

# --- search_symbol function ---
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
                return data # Expecting a list of results
            elif isinstance(data, dict) and "Error Message" in data:
                 logger.error(f"FMP Search API Error for query '{query}': {data['Error Message']}")
                 return None
            else:
                 logger.warning(f"Expected list format for FMP search results for '{query}', got {type(data)}")
                 return None
        else:
            logger.error(f"Unexpected content type for FMP search query '{query}': {content_type}")
            logger.error(f"Response text: {response.text[:500]}...")
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

# --- _fetch_market_list helper function ---
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
            logger.error(f"Response text: {response.text[:500]}...")
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
def get_market_active(): return _fetch_market_list("actives", "Actives") # Note: FMP uses 'actives'

# --- Fundamental Data Functions ---
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
        else: logger.error(f"Unexpected content type FMP income statement for {symbol}: {content_type}"); logger.error(f"Response text: {response.text[:500]}..."); return None
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
        else: logger.error(f"Unexpected content type FMP balance sheet for {symbol}: {content_type}"); logger.error(f"Response text: {response.text[:500]}..."); return None
    except requests.exceptions.RequestException as e: logger.error(f"RequestException fetching FMP balance sheet {symbol}: {e}"); return None
    except json.JSONDecodeError as e: logger.error(f"JSONDecodeError processing FMP balance sheet {symbol}: {e}"); return None
    except Exception as e: logger.error(f"Unexpected error in get_balance_sheet for {symbol}", exc_info=True); return None