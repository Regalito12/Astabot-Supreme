import pandas as pd
# import yfinance as yf  # MOVIDO A LA FUNCIÓN (Lazy Load) para evitar cuelgues al inicio
import logging
import requests
import time
import os
from requests.adapters import HTTPAdapter
from config import TWELVE_API_KEY

# --- Configuración ---
logger = logging.getLogger(__name__)
# logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO) # REMOVIDO: Uso logger centralizado
REQUEST_TIMEOUT = 10
RETRY_STRATEGY = HTTPAdapter(max_retries=3)
session = requests.Session()
session.mount("https://", RETRY_STRATEGY)

# Caching simple
cache = {}
CACHE_EXPIRY = 300  # 5 minutos

# --- Funciones de obtención de datos ---

def get_candles_alphavantage(symbol: str, interval="5min", outputsize=200) -> pd.DataFrame:
    """Proveedor adicional: Alpha Vantage (gratis limitado)."""
    url = "https://www.alphavantage.co/query"
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY") or "YOUR_ALPHA_VANTAGE_KEY"
    if not api_key or api_key == "YOUR_ALPHA_VANTAGE_KEY":
        logging.error("Alpha Vantage API key no está configurada. Por favor, establece la variable de entorno ALPHA_VANTAGE_API_KEY.")
    try:
        resp = session.get(
            url,
            params={
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol.replace("/", ""),
                "interval": interval,
                "apikey": api_key,
                "outputsize": "compact"
            },
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        j = resp.json()
        key = f"Time Series ({interval})"
        if key not in j:
            raise ValueError("Respuesta de Alpha Vantage inválida")

        df = pd.DataFrame.from_dict(j[key], orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={
            "1. open": "open", "2. high": "high", "3. low": "low", "4. close": "close", "5. volume": "volume"
        }).astype(float)
        df = df.reset_index().rename(columns={"index": "datetime"})
        return df.tail(outputsize)
    except Exception as e:
        logging.warning(f"{symbol} -> Alpha Vantage falló: {e}")
        return pd.DataFrame()

def get_candles_twelvedata(symbol: str, interval="5min", outputsize=200) -> pd.DataFrame:
    cache_key = f"{symbol}_{interval}_{outputsize}"
    if cache_key in cache and (pd.Timestamp.now() - cache[cache_key]['timestamp']).seconds < CACHE_EXPIRY:
        return cache[cache_key]['data']

    url = "https://api.twelvedata.com/time_series"
    try:
        resp = session.get(
            url,
            params={
                "symbol": symbol,
                "interval": interval,
                "apikey": TWELVE_API_KEY,
                "outputsize": outputsize,
            },
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        j = resp.json()
        if "values" not in j:
            raise ValueError(j.get("message", "Respuesta de TwelveData sin 'values'"))

        df = pd.DataFrame(j["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].astype(float)
        if 'volume' in df.columns:
            df['volume'] = df['volume'].astype(float)
        else:
            df['volume'] = 0.0

        cache[cache_key] = {'data': df, 'timestamp': pd.Timestamp.now()}
        return df
    except Exception as e:
        logging.warning(f"{symbol} -> TwelveData falló: {e}")
        return pd.DataFrame()

def get_candles_yfinance(symbol: str, interval="5min", outputsize=200) -> pd.DataFrame:
    import yfinance as yf # Lazy load
    # Mapeo de intervalos: "5min"->"5m", "1day"->"1d", "1h"->"1h"
    interval_map = {"1day": "1d", "5day": "5d", "1week": "1wk", "1month": "1mo"}
    yf_interval = interval_map.get(interval, interval.replace("min", "m"))
    ticker_map = {
        "XAU/USD": "GC=F", 
        "EUR/USD": "EURUSD=X", 
        "BTC/USD": "BTC-USD", 
        "ETH/USD": "ETH-USD", 
        "GBP/USD": "GBPUSD=X", 
        "USD/JPY": "JPY=X",
        # Nuevos activos añadidos
        "AUD/USD": "AUDUSD=X",
        "USD/CAD": "CAD=X",
        "NZD/USD": "NZDUSD=X",
        "LTC/USD": "LTC-USD",
        "BNB/USD": "BNB-USD",
        "ADA/USD": "ADA-USD"
    }
    ticker = ticker_map.get(symbol)
    if not ticker:
        raise ValueError(f"Símbolo {symbol} no soportado en yfinance_map")

    # Para asegurar suficientes datos, pedimos un período más grande y luego cortamos
    period = "7d" if "m" in yf_interval or "h" in yf_interval else "1y"

    try:
        df = yf.Ticker(ticker).history(period=period, interval=yf_interval, auto_adjust=True, actions=False)
        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df = df.rename(columns={
            "Datetime": "datetime", "Date": "datetime",
            "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
        })
        # Asegurar que la columna datetime es timezone-aware (UTC)
        if df['datetime'].dt.tz is None:
            df['datetime'] = df['datetime'].dt.tz_localize('UTC')
        else:
            df['datetime'] = df['datetime'].dt.tz_convert('UTC')

        return df[["datetime","open","high","low","close","volume"]].tail(outputsize)
    except Exception as e:
        logging.warning(f"{symbol} -> yfinance falló: {e}")
        return pd.DataFrame()

def get_candles(symbol: str, interval: str = "5min", output_size: int = 200) -> pd.DataFrame:
    """
    Obtiene velas de múltiples proveedores, con fallback y caching.
    """
    # 1. Intento con TwelveData (preferido por tener más datos)
    if TWELVE_API_KEY:
        df = get_candles_twelvedata(symbol, interval, output_size)
        if not df.empty:
            logging.info(f"Datos para {symbol} obtenidos de TwelveData.")
            return df

    # 2. Fallback a Alpha Vantage
    df = get_candles_alphavantage(symbol, interval, output_size)
    if not df.empty:
        logging.info(f"Datos para {symbol} obtenidos de Alpha Vantage.")
        return df

    # 3. Último fallback a yfinance
    df = get_candles_yfinance(symbol, interval, output_size)
    if not df.empty:
        logging.info(f"Datos para {symbol} obtenidos de yfinance.")
        return df

    logging.error(f"No se pudieron obtener datos para {symbol} de ningún proveedor.")
    return pd.DataFrame()