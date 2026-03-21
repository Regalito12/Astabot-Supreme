# config.py
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()


# logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s') # REMOVIDO: Uso logger centralizado

def load_params(path="params.json"):
    defaults = {
        "EMA_SHORT": 20,
        "EMA_LONG": 50,
        "RSI_HIGH": 60,
        "RSI_LOW": 40,
        "ADX_THRESH": 22,
        "ATR_WINDOW": 14,
        "VOL_WINDOW": 20,
        "TP_ATR_MULT": 1.5,
        "SL_ATR_MULT": 1.0,
        "SL_OUTSIDE_MULT": 1.5,
        "SPIKE_ATR_MULT": 0.8,
        "NEWS_WINDOW_MIN": 60,
        "TRAILING_STOP_PCT": 0.02,
        "POSITION_SIZE_PCT": 0.01,
        "MAX_DAILY_LOSS_PCT": 0.05, # --- NUEVO: Límite de pérdida diaria (5%) ---
        # --- Nuevos parámetros para mejoras de señales ---
        "COOLDOWN_MINUTES": 30,          # Minutos entre señales del mismo tipo
        "PRICE_CHANGE_THRESHOLD": 0.005, # 0.5% cambio para resetear cooldown
        "MIN_SCORE_MANUAL": 4,           # Score mínimo para señales manuales
        "MIN_SCORE_AUTO": 5,             # Score mínimo para señales automáticas
        "DIVERGENCE_LOOKBACK": 60,       # Ventana para detectar divergencias
        "DIVERGENCE_POINTS": 3,          # Puntos por divergencia RSI
        "ENABLE_AUTOTRADING": False,     # --- ACTIVAR PARA TRADING AUTOMÁTICO ---
        "SCAN_INTERVAL_MINUTES": 5,      # Minutos entre escaneos automáticos del mercado
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except Exception as e:
            logging.warning(f"No se pudo leer {path}, usando defaults: {e}")
    return defaults

params = load_params()

def reload_config():
    """Recarga los parámetros desde params.json en caliente."""
    global params
    new_params = load_params()
    params.clear()
    params.update(new_params)
    logging.info("Configuración recargada correctamente.")
    return params

# Nuevos parámetros para filtros avanzados
MIN_DISTANCE_PCT = params.get("MIN_DISTANCE_PCT", 0.005)  # 0.5% distancia mínima a soporte/resistencia
MAX_ATR_MULT = params.get("MAX_ATR_MULT", 2.0)  # 200% del ATR máximo para volatilidad

# Se recomienda encarecidamente usar una variable de entorno para producción
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN environment variable")

_chat_id_raw = os.getenv("TELEGRAM_CHAT_ID")
CHAT_ID = int(_chat_id_raw) if _chat_id_raw else None

# --- API Keys ---
# TwelveData API Key (requerida para datos en tiempo real y algunos históricos)
# Se recomienda encarecidamente usar una variable de entorno para producción
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY", "")

# Alpha Vantage API Key (para datos históricos y fundamentales)
# Se recomienda encarecidamente usar una variable de entorno para producción
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")


SUPPORTED_ASSETS = {
    "XAU/USD": "Oro (XAU/USD)",
    "BTC/USD": "Bitcoin (BTC/USD)",
    "EUR/USD": "Euro vs Dólar (EUR/USD)"
}

# --- MetaTrader 5 Configuration ---
# IMPORTANTE: REEMPLAZA ESTOS VALORES CON TUS DATOS DE EXNESS
MT5_LOGIN = int(os.getenv("MT5_LOGIN", 198043507))  # TU ID DE CUENTA (NUMERO)
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "Jorddy17.") # TU CONTRASEÑA DE TRADING
MT5_SERVER = os.getenv("MT5_SERVER", "Exness-MT5Trial11") # TU SERVIDOR (ej: Exness-MT5Trial, Exness-Real2)
ENABLE_AUTOTRADING = params.get("ENABLE_AUTOTRADING", False)

