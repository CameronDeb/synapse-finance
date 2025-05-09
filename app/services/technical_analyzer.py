# app/services/technical_analyzer.py
import pandas as pd
# import traceback # No longer needed if using exc_info=True
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger instance

# Try importing pandas_ta, handle if not installed
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
    logger.info("pandas-ta library found and imported.")
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logger.warning("pandas-ta library not found. RSI and MACD calculation will be skipped.")
    logger.warning("Please install it: pip install pandas-ta")


def calculate_indicators(historical_data_list):
    """
    Calculates technical indicators (SMA, RSI, MACD) from historical data.
    Input: list of dictionaries with 'date', 'close'.
    Output: dictionary containing 'indicators' and 'history', or 'error'.
    """
    required_days_sma50 = 50
    required_days_sma200 = 200
    required_days_rsi = 14 # Standard RSI period
    # MACD typically needs ~26 periods for EMA calculations + 9 for signal = ~35 minimum
    required_days_macd = 35
    cleaned_history = []

    if not historical_data_list or not isinstance(historical_data_list, list):
         logger.warning("calculate_indicators called with invalid historical data.")
         return {"error": "Invalid historical data provided."}

    # --- Initial Data Cleaning and DataFrame Creation ---
    try:
        relevant_data = []
        for item in historical_data_list:
            if isinstance(item, dict) and 'date' in item and 'close' in item:
                relevant_data.append({'date': item['date'], 'close': item['close']})

        if not relevant_data:
            logger.warning("No valid historical data items found with 'date' and 'close'.")
            return {"error": "No valid historical data items found with 'date' and 'close'."}

        df = pd.DataFrame(relevant_data)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        df = df.sort_values(by='date')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])

        if df.empty:
             logger.warning("No valid historical data found after cleaning and conversion.")
             return {"error": "No valid historical data found after cleaning and conversion."}

        # Store the cleaned data list for the chart
        cleaned_history = df[['date', 'close']].to_dict('records')
        for item in cleaned_history:
            item['date'] = item['date'].strftime('%Y-%m-%d')

    except Exception as e:
        logger.error(f"Error during DataFrame creation/cleaning in calculate_indicators", exc_info=True)
        return {"error": f"Failed during data preparation: {e}"}

    # --- Indicator Calculation ---
    try:
        # Calculate SMAs
        df['sma_50'] = df['close'].rolling(window=required_days_sma50).mean() if len(df) >= required_days_sma50 else None
        df['sma_200'] = df['close'].rolling(window=required_days_sma200).mean() if len(df) >= required_days_sma200 else None

        # Calculate RSI and MACD using pandas_ta if available and enough data
        rsi_value = None
        macd_line = None
        macd_hist = None
        macd_signal = None

        if PANDAS_TA_AVAILABLE:
            if len(df) >= required_days_rsi:
                # Calculate RSI (standard period 14)
                df.ta.rsi(length=required_days_rsi, append=True)
                # Column name will be 'RSI_14'
                rsi_value = df['RSI_14'].iloc[-1] if 'RSI_14' in df.columns else None
            else:
                 logger.warning(f"Insufficient data ({len(df)} days) for RSI calculation.")

            if len(df) >= required_days_macd:
                 # Calculate MACD (standard periods 12, 26, 9)
                 # This appends columns: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
                 df.ta.macd(append=True)
                 macd_line = df['MACD_12_26_9'].iloc[-1] if 'MACD_12_26_9' in df.columns else None
                 macd_hist = df['MACDh_12_26_9'].iloc[-1] if 'MACDh_12_26_9' in df.columns else None
                 macd_signal = df['MACDs_12_26_9'].iloc[-1] if 'MACDs_12_26_9' in df.columns else None
            else:
                 logger.warning(f"Insufficient data ({len(df)} days) for MACD calculation.")
        else:
             # Already logged warning at import time
             pass # logger.debug("Skipping RSI and MACD calculation as pandas-ta is not available.")


        # Get the latest row for current indicator values
        latest_indicators_series = df.iloc[-1]

        # Prepare results dictionary
        indicator_results = {
            'last_close': latest_indicators_series.get('close', None),
            'sma_50': latest_indicators_series.get('sma_50', None),
            'sma_200': latest_indicators_series.get('sma_200', None),
            'rsi_14': rsi_value, # Add RSI
            'macd_line': macd_line, # Add MACD line
            'macd_hist': macd_hist, # Add MACD histogram
            'macd_signal': macd_signal, # Add MACD signal line
            'last_calculation_date': latest_indicators_series.get('date').strftime('%Y-%m-%d') if pd.notna(latest_indicators_series.get('date')) else None
        }
        # Clean NaN values
        indicator_results = {k: (None if pd.isna(v) else v) for k, v in indicator_results.items()}

        # Return both indicators and the cleaned history list
        return {
            "indicators": indicator_results,
            "history": cleaned_history
        }

    except Exception as e:
        logger.error(f"Error calculating indicators", exc_info=True)
        return {"error": f"Failed to calculate indicators: {e}"}