# app/api_clients/api_ninjas_client.py
import os
import requests
import json
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger instance

API_NINJAS_KEY = os.environ.get('API_NINJAS_KEY')
BASE_URL = "https://api.api-ninjas.com/v1"
REQUEST_TIMEOUT = 10 # Add timeout

def get_earnings_calendar_ninja(symbol):
    """
    Fetches earnings calendar data for a specific symbol from API Ninjas.
    Requires symbol format like 'AAPL'. Free tier may limit results.
    """
    if not API_NINJAS_KEY:
        logger.error("API_NINJAS_KEY not found in environment variables.")
        return None

    endpoint = "/earningscalendar"
    params = {'ticker': symbol}
    headers = {'X-Api-Key': API_NINJAS_KEY}

    logger.debug(f"Fetching API Ninjas earnings for symbol: {symbol}") # Log API call attempt
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status() # Check for HTTP errors

        if 'application/json' in response.headers.get('Content-Type', ''):
            earnings_data = response.json()
            # API returns a list of earnings events
            if isinstance(earnings_data, list):
                logger.info(f"API Ninjas returned {len(earnings_data)} results for {symbol}.") # Use info level
                return earnings_data
            else:
                logger.warning(f"Expected list format from API Ninjas earnings for {symbol}, got {type(earnings_data)}")
                return None
        else:
            content_type = response.headers.get('Content-Type', 'N/A')
            logger.error(f"Unexpected content type from API Ninjas earnings for {symbol}: {content_type}")
            logger.error(f"Response text: {response.text[:500]}...") # Log beginning of text
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException fetching API Ninjas earnings for {symbol}: {e}")
        if e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            # Avoid logging full response text if it could be huge or sensitive, unless needed for debug
            try:
                error_detail = e.response.json() # Try to get JSON error detail
                logger.error(f"Response JSON detail: {error_detail}")
            except json.JSONDecodeError:
                 logger.error(f"Response text (non-JSON): {e.response.text[:500]}...")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError processing API Ninjas earnings for {symbol}: {e}")
        # Careful logging response text here if parsing failed
        # logger.error(f"Response text that failed JSON parsing: {response.text[:500]}...")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching API Ninjas earnings for {symbol}", exc_info=True)
        return None