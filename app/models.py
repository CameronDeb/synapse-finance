# app/models.py
from app import db, login_manager, app # Import app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import logging
from datetime import datetime, timedelta, timezone # Import timedelta and timezone
from itsdangerous import URLSafeTimedSerializer as Serializer # For timed tokens

logger = logging.getLogger(__name__)

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        logger.warning(f"Invalid user_id format in session: {user_id}")
        return None

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    subscription_tier = db.Column(db.String(50), nullable=False, default='free')
    free_searches_remaining = db.Column(db.Integer, nullable=False, default=5)
    stripe_customer_id = db.Column(db.String(120), unique=True)
    stripe_subscription_id = db.Column(db.String(120), unique=True)

    # Relationships
    watchlist_items = db.relationship('WatchlistItem', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    holdings = db.relationship('Holding', backref='portfolio_owner', lazy='dynamic', cascade='all, delete-orphan')
    trades = db.relationship('Trade', backref='trader', lazy='dynamic', cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='owner', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- NEW: Password Reset Token Methods ---
    def get_reset_password_token(self, expires_sec=900): # 15 minutes
        s = Serializer(app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_password_token(token, expires_sec=900):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=expires_sec)
            user_id = data.get('user_id')
        except Exception:
            return None
        return db.session.get(User, user_id)
    # ----------------------------------------

    @property
    def is_pro(self):
        return self.subscription_tier == 'pro'

    def __repr__(self):
        return f'<User {self.email} (Tier: {self.subscription_tier})>'

# ... (rest of your models: WatchlistItem, Holding, Trade, Alert) ...
class WatchlistItem(db.Model):
    __tablename__ = 'watchlist_item'
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint('user_id', 'symbol', name='uq_user_symbol'),)

    def __repr__(self):
        return f'<WatchlistItem Symbol:{self.symbol} UserID:{self.user_id}>'

class Holding(db.Model):
    __tablename__ = 'holding'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<Holding {self.symbol} Qty:{self.quantity} UserID:{self.user_id}>'

class Trade(db.Model):
    __tablename__ = 'trade'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    pnl = db.Column(db.Float, nullable=True)
    trade_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    asset_class = db.Column(db.String(50), nullable=True)
    setup_reason = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"Trade('{self.trade_date}', '{self.symbol}', P&L: '{self.pnl}')"

class Alert(db.Model):
    __tablename__ = 'alert'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    target_price = db.Column(db.Float, nullable=False)
    condition = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    triggered_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        status = 'Active' if self.is_active else f'Triggered at {self.triggered_at}'
        return f'<Alert for {self.symbol} {self.condition} {self.target_price} - {status}>'
