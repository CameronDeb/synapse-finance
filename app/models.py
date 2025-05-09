# app/models.py
from app import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
# import traceback # No longer needed if using exc_info=True
import logging # Import logging

logger = logging.getLogger(__name__) # Get logger instance for this module

@login_manager.user_loader
def load_user(user_id):
    logger.debug(f"load_user called with user_id: {user_id} (type: {type(user_id)})") # Use debug level
    try:
        user_id_int = int(user_id)
        user = db.session.get(User, user_id_int)
        logger.debug(f"load_user returning user: {user}") # Use debug level
        return user
    except (TypeError, ValueError):
        logger.warning(f"Invalid user_id format in session: {user_id}")
        return None
    except Exception as e:
        logger.error(f"Exception in load_user for user_id {user_id}", exc_info=True)
        return None

class User(UserMixin, db.Model):
    __tablename__ = 'user' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    subscription_tier = db.Column(db.String(50), nullable=False, default='free')
    watchlist_items = db.relationship('WatchlistItem', backref='owner', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash: return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_pro(self): return self.subscription_tier == 'pro'

    def __repr__(self): return f'<User {self.email} (Tier: {self.subscription_tier})>'

class WatchlistItem(db.Model):
    __tablename__ = 'watchlist_item' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint('user_id', 'symbol', name='uq_user_symbol'),)

    def __repr__(self): return f'<WatchlistItem Symbol:{self.symbol} UserID:{self.user_id}>'