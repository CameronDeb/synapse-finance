# run_alert_checker.py
import time
import logging
from datetime import datetime
from collections import defaultdict

from app import app, db
from app.models import Alert, User
from app.api_clients.fmp_client import get_quote
from app.email import send_price_alert_email

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CHECK_INTERVAL_SECONDS = 60 

def check_alerts():
    with app.app_context():
        active_alerts = db.session.scalars(db.select(Alert).where(Alert.is_active == True)).all()

        if not active_alerts:
            logging.info("No active alerts to check.")
            return

        alerts_by_symbol = defaultdict(list)
        for alert in active_alerts:
            alerts_by_symbol[alert.symbol].append(alert)
        
        logging.info(f"Found {len(active_alerts)} active alerts for {len(alerts_by_symbol)} unique symbols.")

        for symbol, alerts in alerts_by_symbol.items():
            try:
                quote_data = get_quote(symbol)
                
                if not quote_data or not isinstance(quote_data, list) or len(quote_data) == 0:
                    logging.warning(f"Could not get a valid quote for {symbol} from FMP. Skipping.")
                    continue

                quote = quote_data[0]
                if 'price' not in quote or quote['price'] is None:
                    logging.warning(f"Quote for {symbol} is missing 'price' field. Skipping.")
                    continue
                
                current_price = float(quote['price'])
                logging.info(f"Checking {symbol}: Current Price = ${current_price:.2f}")

                for alert in alerts:
                    target_price = alert.target_price
                    condition_met = False

                    if alert.condition == 'above' and current_price > target_price:
                        condition_met = True
                    elif alert.condition == 'below' and current_price < target_price:
                        condition_met = True
                    
                    if condition_met:
                        logging.warning(f"!!! ALERT TRIGGERED for User {alert.user_id}: {alert.symbol} {alert.condition} ${target_price:.2f} (Current: ${current_price:.2f})")
                        
                        alert.is_active = False
                        alert.triggered_at = datetime.utcnow()
                        db.session.add(alert)
                        
                        user = db.session.get(User, alert.user_id)
                        if user:
                            send_price_alert_email(user, alert)
                        else:
                            logging.error(f"Could not find user with ID {alert.user_id} to send alert email.")

            except Exception as e:
                logging.error(f"An error occurred while processing alerts for {symbol}: {e}", exc_info=True)
        
        try:
            db.session.commit()
        except Exception as e:
            logging.error(f"Failed to commit DB changes after checking alerts: {e}")
            db.session.rollback()


if __name__ == "__main__":
    logging.info("--- Starting Synapse Finance Alert Checker (FMP Consolidated) ---")
    while True:
        try:
            check_alerts()
        except Exception as e:
            logging.critical(f"An unhandled exception occurred in the main loop: {e}", exc_info=True)
        
        logging.info(f"Sleeping for {CHECK_INTERVAL_SECONDS} seconds...")
        time.sleep(CHECK_INTERVAL_SECONDS)
