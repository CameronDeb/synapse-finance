# app/api_clients/eodhd_client.py
import os
import requests # Library to make HTTP requests
import json     # Library to work with JSON data
from datetime import datetime, timedelta # To potentially filter news by date later
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger instance

# Get the API key from environment variables
EODHD_API_KEY = os.environ.get('EODHD_API_KEY')

# Base URL for EODHD API
BASE_URL = "https://eodhd.com/api"
REQUEST_TIMEOUT = 10 # Add timeout

# --- get_delayed_quote function ---
def get_delayed_quote(symbol):
    """ Fetches delayed quote """
    if not EODHD_API_KEY:
        logger.error("EODHD_API_KEY missing for get_delayed_quote.")
        return None
    endpoint = f"/real-time/{symbol}"
    params = {'api_token': EODHD_API_KEY, 'fmt': 'json'}
    logger.debug(f"Fetching EODHD delayed quote for {symbol}")
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
             return response.json()
        else:
             logger.error(f"Unexpected content type for EODHD quote {symbol}: {content_type}")
             logger.error(f"Response text: {response.text[:500]}...")
             return None
    except requests.exceptions.RequestException as e:
         logger.error(f"RequestException fetching EODHD quote for {symbol}: {e}")
         return None
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError processing EODHD quote for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching EODHD quote for {symbol}", exc_info=True)
        return None


# --- get_historical_data function ---
def get_historical_data(symbol, period_days=365):
    """ Fetches daily historical data """
    if not EODHD_API_KEY:
        logger.error("EODHD_API_KEY missing for get_historical_data.")
        return None
    endpoint = f"/eod/{symbol}"
    params = {'api_token': EODHD_API_KEY, 'fmt': 'json', 'period': 'd'}
    logger.debug(f"Fetching EODHD historical data for {symbol} (up to {period_days} days)")
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                try:
                    # Sort by date (EODHD usually returns sorted, but good practice)
                    data.sort(key=lambda x: x.get('date', ''))
                except (TypeError, KeyError):
                    logger.warning(f"Could not sort historical data for {symbol} due to unexpected item format.")
                # Return the latest 'period_days' items
                return data[-period_days:] if len(data) >= period_days else data
            else:
                logger.warning(f"Expected list for EODHD historical data {symbol}, got {type(data)}")
                return None
        else:
             logger.error(f"Unexpected content type for EODHD historical data {symbol}: {content_type}")
             logger.error(f"Response text: {response.text[:500]}...")
             return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching EODHD historical data for {symbol}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError processing EODHD historical data for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching EODHD historical data for {symbol}", exc_info=True)
        return None


# --- get_stock_news function ---
def get_stock_news(symbol, limit=15):
    """ Fetches recent stock news """
    if not EODHD_API_KEY:
        logger.error("EODHD_API_KEY missing for get_stock_news.")
        return None
    endpoint = "/news"
    # EODHD uses 's' parameter for symbol in news endpoint
    params = {'api_token': EODHD_API_KEY, 's': symbol, 'limit': limit, 'fmt': 'json'}
    logger.debug(f"Fetching EODHD news for {symbol} (limit {limit})")
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = response.json()
            if isinstance(data, list):
                return data
            else:
                logger.warning(f"Expected list for EODHD news data {symbol}, got {type(data)}")
                return None
        else:
             logger.error(f"Unexpected content type for EODHD news data {symbol}: {content_type}")
             logger.error(f"Response text: {response.text[:500]}...")
             return None
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching EODHD news for {symbol}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError processing EODHD news for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching EODHD news for {symbol}", exc_info=True)
        return None

# --- Removed get_earnings_calendar function as it's not available on free plan ---