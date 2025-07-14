# app/services/backtesting_engine.py
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class BacktestEngine:
    """
    A class to run a backtest for a given strategy on historical data.
    Now includes detailed trade logging and returns data for advanced charting.
    """
    def __init__(self, symbol, historical_data, strategy_params, initial_capital=10000):
        self.symbol = symbol
        self.strategy_params = strategy_params
        self.initial_capital = float(initial_capital)
        self.df = self._prepare_data(historical_data)
        
        # Backtest state
        self.cash = self.initial_capital
        self.position_size = 0
        self.entry_price = 0
        self.equity_curve = []
        self.trades = [] # Will now store more detailed trade info

    def _prepare_data(self, historical_data):
        """Prepares the DataFrame with historical data and indicators."""
        if not historical_data:
            raise ValueError("Historical data is empty or invalid.")
        
        df = pd.DataFrame(historical_data)
        # Ensure all required columns are present
        required_cols = ['date', 'open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            raise ValueError("Historical data is missing required OHLC columns.")
            
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').set_index('date')
        
        # For SMA Crossover, we need short and long SMAs
        short_window = 50
        long_window = 200
        
        df['short_sma'] = df['close'].rolling(window=short_window).mean()
        df['long_sma'] = df['close'].rolling(window=long_window).mean()
        
        return df.dropna()

    def run(self):
        """Executes the backtest loop."""
        if self.df.empty:
            logger.warning(f"Not enough historical data for {self.symbol} to run backtest.")
            return None

        logger.info(f"Running backtest for {self.symbol} with initial capital ${self.initial_capital:,.2f}")

        for i, row in self.df.iterrows():
            current_price = row['close']
            
            # SMA Crossover Strategy Logic
            if row['short_sma'] > row['long_sma'] and self.position_size == 0:
                self._enter_position(row.name, current_price)

            elif row['short_sma'] < row['long_sma'] and self.position_size > 0:
                self._exit_position(row.name, current_price)

            current_equity = self.cash + (self.position_size * current_price)
            self.equity_curve.append({'date': row.name.strftime('%Y-%m-%d'), 'value': current_equity})

        logger.info(f"Backtest for {self.symbol} complete. Total trades: {len(self.trades)}")
        return self._calculate_results()

    def _enter_position(self, date, price):
        """Simulates buying the asset and logs the entry."""
        self.position_size = self.cash / price
        self.entry_price = price
        self.cash = 0
        # Log the entry part of a new trade
        self.trades.append({
            'entry_date': date.strftime('%Y-%m-%d'),
            'entry_price': price,
            'exit_date': None,
            'exit_price': None,
            'pnl': None
        })
        logger.debug(f"[{date.strftime('%Y-%m-%d')}] ENTER LONG @ ${price:.2f}")

    def _exit_position(self, date, price):
        """Simulates selling the asset and completes the trade record."""
        pnl = (price - self.entry_price) * self.position_size
        self.cash += self.position_size * price
        
        # Update the last open trade with exit info
        if self.trades and self.trades[-1]['exit_date'] is None:
            last_trade = self.trades[-1]
            last_trade['exit_date'] = date.strftime('%Y-%m-%d')
            last_trade['exit_price'] = price
            last_trade['pnl'] = pnl
        
        self.position_size = 0
        logger.debug(f"[{date.strftime('%Y-%m-%d')}] EXIT LONG @ ${price:.2f}, P&L: ${pnl:,.2f}")

    def _calculate_results(self):
        """Calculates and returns the final KPIs, equity curve, and trade data."""
        if not self.equity_curve:
            return {"kpis": {}, "equity_curve": [], "trades": [], "price_data": []}

        final_equity = self.equity_curve[-1]['value']
        net_pnl = final_equity - self.initial_capital
        total_return_pct = (net_pnl / self.initial_capital) * 100 if self.initial_capital > 0 else 0
        
        completed_trades = [t for t in self.trades if t['pnl'] is not None]
        winning_trades = [t for t in completed_trades if t['pnl'] > 0]
        win_rate = (len(winning_trades) / len(completed_trades)) * 100 if completed_trades else 0

        kpis = {
            "net_pnl": net_pnl,
            "total_return_pct": total_return_pct,
            "win_rate": win_rate,
            "total_trades": len(completed_trades),
            "initial_capital": self.initial_capital,
            "final_equity": final_equity
        }
        
        # Prepare price data for charting library (OHLC format)
        price_data_for_chart = []
        for index, row in self.df.iterrows():
            price_data_for_chart.append({
                "time": index.strftime('%Y-%m-%d'),
                "open": row['open'],
                "high": row['high'],
                "low": row['low'],
                "close": row['close']
            })

        return {
            "kpis": kpis,
            "equity_curve": self.equity_curve,
            "trades": self.trades,
            "price_data": price_data_for_chart
        }

def run_sma_crossover_backtest(symbol, start_date, end_date, initial_capital, asset_class='Stock'):
    """
    Orchestrates the backtest process for the SMA Crossover strategy.
    Handles fetching data for different asset classes.
    """
    from ..api_clients import fmp_client

    # FMP uses different API endpoints for different asset classes.
    # For now, we assume the main historical data endpoint works for all.
    # This can be expanded later if needed.
    logger.info(f"Fetching historical data for {symbol} (Asset Class: {asset_class})")
    
    # Fetch a longer period to ensure SMAs can be calculated before the start date
    # FMP's daily history endpoint is often the same for stocks, forex, and crypto.
    # Futures might require a different approach or symbol format (e.g., /ES)
    historical_data = fmp_client.get_historical_data(symbol, days=365*10)
    
    if not historical_data:
        raise ValueError(f"Could not fetch historical data for {symbol}. Check the symbol and asset class.")

    # Convert to DataFrame for easier filtering
    df = pd.DataFrame(historical_data)
    df['date'] = pd.to_datetime(df['date'])
    
    # We need data *before* the start date to calculate the initial SMA values.
    # Let's find the actual start date in the data that is on or after the requested start_date
    df = df[df['date'] >= pd.to_datetime(start_date) - pd.Timedelta(days=300)]
    df = df[df['date'] <= pd.to_datetime(end_date)]
    
    if df.empty:
        raise ValueError("No historical data available for the selected date range.")

    engine = BacktestEngine(
        symbol=symbol,
        historical_data=df.to_dict('records'),
        strategy_params={'name': 'sma_crossover'},
        initial_capital=initial_capital
    )
    
    return engine.run()
