# app/__init__.py
import os
import sys
import logging # Import logging
from flask import Flask
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
# import traceback # No longer needed if using exc_info=True

# Load environment variables from .env file FIRST
load_dotenv()

# --- Database Setup ---
basedir = os.path.abspath(os.path.dirname(__file__))

# Create the Flask application instance
app = Flask(__name__)

# Configure basic logging - Flask's default logger goes to stderr.
# You might want more sophisticated configuration later (e.g., logging to a file).
logging.basicConfig(level=logging.INFO) # Set default level

# --- CRITICAL: Ensure SECRET_KEY is set and loaded ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    # Use app.logger which is configured by Flask
    app.logger.critical("FATAL ERROR: SECRET_KEY environment variable not set! Sessions will not work.")
    # Fallback ONLY for dev - CONSIDER REMOVING FOR PRODUCTION
    app.config['SECRET_KEY'] = 'insecure-dev-key-please-set-in-env'

# Configure the SQLite database URI
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(basedir, '..', 'app.db') # Place db outside 'app' folder
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disable modification tracking

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page' # Function name of the login route
login_manager.login_message = 'Please log in to access this page.' # Custom message
login_manager.login_message_category = 'info' # Category for flashed messages

# --- Import routes and models AFTER initializing extensions ---
# Use app.logger for import related messages
app.logger.info("--- Initializing application components ---")
try:
    from app import models # Must import models AFTER db is defined
    app.logger.info("Successfully imported app.models")
except Exception as e:
    app.logger.error("--- ERROR importing app.models ---", exc_info=True)
    # Decide if the app should exit or continue if models fail to import

try:
    from app import routes # Must import routes AFTER app and login_manager are defined
    app.logger.info("Successfully imported app.routes")
except Exception as e:
    app.logger.error("--- ERROR importing app.routes ---", exc_info=True)
     # Decide if the app should exit or continue if routes fail to import
app.logger.info("--- Finished initializing application components ---")
# -----------------------------------------------------

# Optional: Log loaded API keys (consider using DEBUG level)
app.logger.debug(f"EODHD Key Loaded: {'Yes' if os.environ.get('EODHD_API_KEY') else 'No'}")
app.logger.debug(f"FMP Key Loaded: {'Yes' if os.environ.get('FMP_API_KEY') else 'No'}")
app.logger.debug(f"API Ninjas Key Loaded: {'Yes' if os.environ.get('API_NINJAS_KEY') else 'No'}")
app.logger.info(f"Database URI configured: {app.config['SQLALCHEMY_DATABASE_URI']}") # Log DB URI maybe as INFO