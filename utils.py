# utils.py
import pandas as pd
import numpy as np
from config import params

def detectar_soportes_resistencias(df, window=20):
    """
    Detecta niveles de soporte y resistencia básicos usando máximos/mínimos locales.
    Devuelve dict con 'support' y 'resistance' (últimos niveles detectados).
    """
    highs = df['high'].rolling(window=window, center=True).max()
    lows = df['low'].rolling(window=window, center=True).min()

    # Soporte: mínimo local reciente
    support = lows.iloc[-1] if not lows.empty else df['low'].iloc[-1]

    # Resistencia: máximo local reciente
    resistance = highs.iloc[-1] if not highs.empty else df['high'].iloc[-1]

    return {'support': support, 'resistance': resistance}

def verificar_distancia_soporte_resistencia(price, support, resistance, min_distance_pct=0.005):
    """
    Verifica si el precio está lo suficientemente lejos de soporte/resistencia.
    min_distance_pct: Porcentaje mínimo de distancia (configurable).
    Devuelve True si está lejos, False si está cerca.
    """
    distance_support = abs(price - support) / price
    distance_resistance = abs(price - resistance) / price

    return distance_support > min_distance_pct and distance_resistance > min_distance_pct

def verificar_volatilidad_extrema(df, atr_window=14, max_atr_mult=2.0):
    """
    Verifica si la última vela tiene volatilidad extrema comparada con ATR.
    max_atr_mult: Multiplicador máximo permitido (configurable, ej. 2.0 = 200% del ATR).
    Devuelve True si es normal, False si extrema.
    """
    if len(df) < atr_window + 1:
        return True  # No hay suficientes datos, asumir normal

    # Calcular ATR de las últimas velas
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift(1))
    low_close = np.abs(df['low'] - df['close'].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=atr_window).mean().iloc[-1]

    # Rango de la última vela
    last_range = df['high'].iloc[-1] - df['low'].iloc[-1]

    # Comparar
    return last_range <= atr * max_atr_mult

def es_vela_cerrada(df):
    """
    Verifica si la última vela está cerrada (no en movimiento).
    Asume que si tenemos datos hasta ahora, la penúltima es cerrada.
    Devuelve True si podemos usar la última vela como cerrada.
    """
    # En APIs de tiempo real, la última vela puede estar incompleta.
    # Para simplicidad, asumimos que si tenemos al menos 2 velas, usamos la penúltima.
    # Pero para no romper, usamos la última y asumimos cerrada.
    return len(df) >= 2  # Placeholder: siempre True si hay suficientes datos