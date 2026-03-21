# indicadores.py
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator
from config import params
try:
    from scipy.signal import find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

def calc_vwap(df):
    """Calcula el Volume Weighted Average Price (VWAP) - OPTIMIZADO con NumPy"""
    # Optimización: Usar NumPy para operaciones vectorizadas
    tp = (df['high'].values + df['low'].values + df['close'].values) / 3
    cum_vol_price = np.cumsum(tp * df['volume'].values)
    cum_vol = np.cumsum(df['volume'].values)
    return pd.Series(cum_vol_price / cum_vol, index=df.index)

def aplicar_indicadores(df):
    """
    Aplica todos los indicadores técnicos necesarios.
    """
    MIN_PERIODS = 14
    if len(df) < MIN_PERIODS:
        raise ValueError(f"Se requieren al menos {MIN_PERIODS} períodos para calcular indicadores")
    
    # --- Indicadores institucionales ---
    df['VWAP'] = calc_vwap(df)
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # --- Indicadores de tendencia ---
    try:
        df["ADX"] = ADXIndicator(df["high"], df["low"], df["close"], window=14).adx().bfill()
    except Exception as e:
        df["ADX"] = 0.0
    
    # --- Indicadores de momentum ---
    try:
        df["RSI"] = RSIIndicator(df["close"], window=14).rsi().bfill()
        # Dual RSI para mejor detección de momentum (M5 optimization)
        df["RSI_fast"] = RSIIndicator(df["close"], window=7).rsi().bfill()
        df["RSI_slow"] = RSIIndicator(df["close"], window=21).rsi().bfill()
    except Exception as e:
        df["RSI"] = 50.0
        df["RSI_fast"] = 50.0
        df["RSI_slow"] = 50.0
    
    # --- Indicadores volatilidad (Bollinger Bands) - Configurable ---
    try:
        bb_window = params.get("BB_WINDOW", 30)
        bb_std = params.get("BB_STD", 2.5)
        bb = BollingerBands(df["close"], window=bb_window, window_dev=bb_std)
        df["BB_High"] = bb.bollinger_hband().bfill()
        df["BB_Low"] = bb.bollinger_lband().bfill()
        df["BB_Middle"] = bb.bollinger_mavg().bfill()
    except Exception as e:
        df["BB_High"], df["BB_Low"], df["BB_Middle"] = df["close"], df["close"], df["close"]

    # --- Indicador de volatilidad (ATR) ---
    try:
        atr = AverageTrueRange(df["high"], df["low"], df["close"], window=14)
        df["ATR"] = atr.average_true_range().bfill()
    except Exception:
        df["ATR"] = (df["high"] - df["low"]).rolling(window=14).mean().bfill()
    
    return df

def esta_en_rango(df: pd.DataFrame, umbral: float) -> bool:
    """Devuelve True si ADX < umbral, indicando mercado sin tendencia fuerte"""
    return df["ADX"].iloc[-1] < umbral

# --- Validaciones ---
def validar_vwap(df: pd.DataFrame, umbral_pct: float = 0.005) -> pd.Series:
    """
    Valida si el precio está dentro de un rango aceptable respecto al VWAP.
    umbral_pct: Porcentaje máximo permitido de desviación desde el VWAP
    Devuelve Serie booleana indicando validez de cada vela.
    """
    vwap = df['VWAP']
    price = df['close']
    
    # Calcular umbrales superior e inferior
    upper = vwap * (1 + umbral_pct)
    lower = vwap * (1 - umbral_pct)
    
    return (price >= lower) & (price <= upper)

# --- Detección de Divergencias ---

def detectar_divergencia_rsi(df: pd.DataFrame, lookback: int = 60) -> str:
    """
    Detecta divergencias entre precio y RSI.
    OPTIMIZADO: Usa scipy.signal.find_peaks para detección más precisa.
    
    Divergencia Alcista: Precio hace mínimos más bajos, RSI hace mínimos más altos.
    Divergencia Bajista: Precio hace máximos más altos, RSI hace máximos más bajos.
    
    Returns: 'bullish_div', 'bearish_div', or None
    """
    if len(df) < lookback + 5:
        return None
    
    # Obtener últimas N velas para análisis
    recent = df.tail(lookback).copy()
    
    prices = recent['close'].values
    rsi_vals = recent['RSI'].values if 'RSI' in recent.columns else None
    
    if rsi_vals is None or len(prices) < 10:
        return None
    
    # OPTIMIZACIÓN: Usar scipy para encontrar picos y valles
    if SCIPY_AVAILABLE:
        # Encontrar mínimos (valles) en precio y RSI
        price_lows, _ = find_peaks(-prices, distance=5)
        rsi_lows, _ = find_peaks(-rsi_vals, distance=5)
        
        # Divergencia alcista: necesitamos al menos 2 mínimos
        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            # Comparar los 2 últimos mínimos
            if prices[price_lows[-1]] < prices[price_lows[-2]]:  # Precio nuevo mínimo más bajo
                if rsi_vals[rsi_lows[-1]] > rsi_vals[rsi_lows[-2]]:  # RSI mínimo más alto
                    return 'bullish_div'
        
        # Encontrar máximos (picos) en precio y RSI
        price_highs, _ = find_peaks(prices, distance=5)
        rsi_highs, _ = find_peaks(rsi_vals, distance=5)
        
        # Divergencia bajista: necesitamos al menos 2 máximos
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            if prices[price_highs[-1]] > prices[price_highs[-2]]:  # Precio nuevo máximo más alto
                if rsi_vals[rsi_highs[-1]] < rsi_vals[rsi_highs[-2]]:  # RSI máximo más bajo
                    return 'bearish_div'
    else:
        # Fallback al método original si scipy no está disponible
        min_idx_recent = len(prices) - 1 - prices[::-1].argmin()
        first_half = prices[:len(prices)//2]
        if len(first_half) < 3:
            return None
        min_idx_prev = first_half.argmin()
        
        if prices[min_idx_recent] < prices[min_idx_prev]:
            if rsi_vals[min_idx_recent] > rsi_vals[min_idx_prev]:
                return 'bullish_div'
        
        max_idx_recent = len(prices) - 1 - prices[::-1].argmax()
        max_idx_prev = first_half.argmax()
        
        if prices[max_idx_recent] > prices[max_idx_prev]:
            if rsi_vals[max_idx_recent] < rsi_vals[max_idx_prev]:
                return 'bearish_div'
    
    return None


def detectar_divergencia_macd(df: pd.DataFrame) -> str:
    """
    Detecta divergencias en MACD histogram.
    
    Returns: 'bullish_div', 'bearish_div', or None
    """
    if len(df) < 30:
        return None
    
    # Calcular MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    
    # Tomar las últimas 40 velas para ver estructura
    recent_hist = histogram.tail(40).values
    recent_price = df['close'].tail(40).values
    
    if len(recent_hist) < 10:
        return None
    
    # Buscar mínimos
    hist_min_recent = recent_hist[len(recent_hist)//2:].min()
    hist_min_prev = recent_hist[:len(recent_hist)//2].min()
    price_min_recent = recent_price[len(recent_price)//2:].min()
    price_min_prev = recent_price[:len(recent_price)//2].min()
    
    # Divergencia alcista en histograma
    if price_min_recent < price_min_prev and hist_min_recent > hist_min_prev:
        return 'bullish_div'
    
    # Buscar máximos
    hist_max_recent = recent_hist[len(recent_hist)//2:].max()
    hist_max_prev = recent_hist[:len(recent_hist)//2].max()
    price_max_recent = recent_price[len(recent_price)//2:].max()
    price_max_prev = recent_price[:len(recent_price)//2].max()
    
    # Divergencia bajista
    if price_max_recent > price_max_prev and hist_max_recent < hist_max_prev:
        return 'bearish_div'
    
    return None


def calcular_obv_trend(df: pd.DataFrame, window: int = 10) -> str:
    """
    Calcula la tendencia del On-Balance Volume.
    OPTIMIZADO: Añade filtro de volumen para ignorar señales débiles.
    
    Returns: 'bullish', 'bearish', or 'neutral'
    """
    if len(df) < window + 5:
        return 'neutral'
    
    try:
        obv = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
        obv_recent = obv.tail(window)
        
        # Calcular pendiente del OBV
        obv_slope = obv_recent.iloc[-1] - obv_recent.iloc[0]
        price_slope = df['close'].tail(window).iloc[-1] - df['close'].tail(window).iloc[0]
        
        # OPTIMIZACIÓN: Filtro de volumen - ignorar si volumen promedio es bajo
        avg_volume = df['volume'].tail(window).mean()
        volume_threshold = df['volume'].rolling(50).mean().iloc[-1] * 0.5
        
        if avg_volume < volume_threshold:
            return 'neutral'  # Volumen insuficiente para confiar en OBV
        
        # Si OBV sube con precio = confirmación
        if obv_slope > 0 and price_slope > 0:
            return 'bullish'
        elif obv_slope < 0 and price_slope < 0:
            return 'bearish'
        # Divergencia OBV vs precio
        elif obv_slope > 0 and price_slope < 0:
            return 'bullish'  # Acumulación oculta
        elif obv_slope < 0 and price_slope > 0:
            return 'bearish'  # Distribución oculta
    except Exception:
        pass
    
    return 'neutral'
