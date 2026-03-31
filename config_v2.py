"""
AstaBot 2.0 - Configuracion limpia
Solo indicadores tecnicos: EMA 50/200, RSI, ADX, Bollinger, ATR, VWAP
Soporte multi-par: XAU/USD + BTC/USDT
"""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Falta TELEGRAM_TOKEN en variables de entorno")

SYMBOLS = [
    {"symbol": "XAUUSD", "display": "Oro (XAU/USD)", "atr_sl": 1.0, "atr_tp": 2.0},
    {"symbol": "BTC/USD", "display": "Bitcoin (BTC/USD)", "atr_sl": 1.5, "atr_tp": 3.0},
]

INTERVAL = "5min"
CANDLE_COUNT = 200

SCORE_MIN = 4

SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))

ATR_WINDOW = 14

RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "30"))

SPREAD_MAX_PIPS = float(os.getenv("SPREAD_MAX_PIPS", "3.0"))

SIGNAL_LOG_FILE = "signals_log.csv"

NEWS_ALERT_MINUTES = 30

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

WEEKEND_ALERT_HOUR = 20
WEEKEND_ALERT_DAY = 4

BRIEFING_HOUR = 7
BRIEFING_MINUTE = 0

SESSIONS = {
    "asia": {"start": 0, "end": 7, "name": "Asia", "emoji": "\U0001F30F"},
    "londres": {"start": 7, "end": 12, "name": "Londres", "emoji": "\U0001F3DB\ufe0f"},
    "ny": {"start": 13, "end": 17, "name": "Nueva York", "emoji": "\U0001F5FD"},
    "cierre": {"start": 17, "end": 24, "name": "Cierre", "emoji": "\U0001F319"},
}
