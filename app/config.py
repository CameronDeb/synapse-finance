# app/config.py
import os

# Demo mode serves market data from the bundled snapshot in app/demo_data, uses a local
# SQLite database, and disables Stripe and outbound email. It is on unless explicitly
# turned off, so a fresh deploy works without any paid API keys.
DEMO_MODE = os.environ.get('DEMO_MODE', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
