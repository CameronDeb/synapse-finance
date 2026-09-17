# app/api_clients/__init__.py
from app.config import DEMO_MODE

# Both clients expose the same functions, so the rest of the app imports `market_data`
# and doesn't care where the numbers come from.
if DEMO_MODE:
    from . import demo_client as market_data
else:
    from . import fmp_client as market_data
