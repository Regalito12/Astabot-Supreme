from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# Initialize Flask app
app = Flask(__name__)

# Configure Database
# Ensure data folder exists
basedir = os.path.abspath(os.path.dirname(__file__))
data_path = os.path.join(basedir, 'data_astabot')
if not os.path.exists(data_path):
    os.makedirs(data_path)

db_path = os.path.join(data_path, 'astabot.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), default='Unknown')
    asset_type = db.Column(db.String(20), default='Unknown')
    base_currency = db.Column(db.String(3), default='USD')
    quote_currency = db.Column(db.String(3), default='USD')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TradingAccount(db.Model):
    __tablename__ = 'trading_accounts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    broker_name = db.Column(db.String(50), nullable=False)
    account_name = db.Column(db.String(100), nullable=False)
    account_id = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    balance = db.Column(db.Numeric(15, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Trade(db.Model):
    __tablename__ = 'trades'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    trading_account_id = db.Column(db.Integer, db.ForeignKey('trading_accounts.id'), nullable=False)
    asset_id = db.Column(db.Integer, nullable=False)
    side = db.Column(db.String(4), nullable=False) # buy/sell
    quantity = db.Column(db.Numeric(15, 5), nullable=False)
    pnl = db.Column(db.Numeric(15, 2))
    closed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Position(db.Model):
    __tablename__ = 'positions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    trading_account_id = db.Column(db.Integer, nullable=False)
    asset_id = db.Column(db.Integer, nullable=False)
    side = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Numeric(15, 5), nullable=False)
    avg_entry_price = db.Column(db.Numeric(15, 5), nullable=False)
    current_price = db.Column(db.Numeric(15, 5))
    unrealized_pnl = db.Column(db.Numeric(15, 2))
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)

class Signal(db.Model):
    __tablename__ = 'signals'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, nullable=False)
    signal_type = db.Column(db.String(10), nullable=False)
    entry_price = db.Column(db.Numeric(15, 5), nullable=False)
    stop_loss = db.Column(db.Numeric(15, 5))
    take_profit = db.Column(db.Numeric(15, 5))
    executed = db.Column(db.Boolean, default=False)
    executed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_db():
    """Inicializa la base de datos creando las tablas si no existen."""
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            if "already exists" in str(e).lower():
                pass
            else:
                raise

if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada.")
