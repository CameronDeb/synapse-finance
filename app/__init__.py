# app/__init__.py
import os
import sys
import logging
from flask import Flask
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

load_dotenv()

from app.config import DEMO_MODE

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    app.logger.critical("FATAL ERROR: SECRET_KEY environment variable not set! Sessions will not work.")
    app.config['SECRET_KEY'] = 'insecure-dev-key-please-set-in-env'

if DEMO_MODE:
    # Demo data is disposable, so it lives in a local SQLite file instead of the production database.
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DEMO_DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, '..', 'demo.db')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, '..', 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

app.logger.info("--- Initializing application components ---")
try:
    from app import models
    app.logger.info("Successfully imported app.models")
except Exception as e:
    app.logger.error("--- ERROR importing app.models ---", exc_info=True)

try:
    from app import routes, seo # <-- ADD 'seo' HERE
    app.logger.info("Successfully imported app.routes and app.seo")
except Exception as e:
    app.logger.error("--- ERROR importing app.routes and app.seo ---", exc_info=True)

if DEMO_MODE:
    # The demo database is created on boot instead of through migrations.
    with app.app_context():
        try:
            db.create_all()
        except Exception:
            app.logger.warning("create_all failed (another worker may have created the tables first)", exc_info=True)

app.logger.info("--- Finished initializing application components ---")

app.logger.info(f"Demo mode: {'ON' if DEMO_MODE else 'OFF'}")
app.logger.debug(f"FMP Key Loaded: {'Yes' if os.environ.get('FMP_API_KEY') else 'No'}")
# Log only the scheme; the full URI contains credentials.
app.logger.info(f"Database backend: {app.config['SQLALCHEMY_DATABASE_URI'].split(':', 1)[0]}")