# market_regime.py
import pandas as pd
import numpy as np
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class MarketRegime(Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING_STABLE = "RANGING_STABLE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"  # Mercado peligroso/ruidoso
    SQUEEZE = "SQUEEZE"  # Rango muy estrecho, preparación para explosión
    UNCERTAIN = "UNCERTAIN"

class MarketRegimeDetector:
    def __init__(self, df):
        self.df = df
        
    def detect_regime(self) -> dict:
        """
        Analiza el DataFrame y determina el régimen actual del mercado.
        Retorna un diccionario con detalles del régimen.
        """
        if self.df.empty or len(self.df) < 50:
            return {
                "regime": MarketRegime.UNCERTAIN,
                "confidence": 0.0,
                "reason": "Insuficientes datos"
            }
            
        u = self.df.iloc[-1]
        
        # 1. Análisis de Tendencia (ADX + EMAs)
        adx = u.get("ADX", 0)
        ema_short = u.get("EMA50", 0)  # Asumiendo que se calculan en indicadores.py
        ema_long = u.get("EMA200", 0) # Asumiendo que se calculan en indicadores.py
        price = u["close"]
        
        # Pendiente de la EMA corta - OPTIMIZADO: usar np.gradient()
        # Tomamos el promedio de cambio de las últimas 3 velas para suavizar
        if len(self.df) >= 5:
            ema_slope = np.gradient(self.df['EMA50'].tail(5).values).mean()
        else:
            ema_slope = 0
        
        is_trending_strong = adx > 25
        is_trending_weak = adx > 20
        
        is_bullish_alignment = price > ema_short > ema_long
        is_bearish_alignment = price < ema_short < ema_long
        
        # 2. Análisis de Volatilidad (Squeeze & Expansion) - OPTIMIZADO
        bb_high = u.get("BB_High", 0)
        bb_low = u.get("BB_Low", 0)
        bb_width = (bb_high - bb_low) / u["close"] if u["close"] > 0 else 0
        
        # OPTIMIZACIÓN: Cachear avg_bb_width en el DataFrame si no existe
        if 'bb_width' not in self.df.columns:
            self.df['bb_width'] = (self.df['BB_High'] - self.df['BB_Low']) / self.df['close']
        
        avg_bb_width = self.df['bb_width'].rolling(50).mean().iloc[-1] if len(self.df) >= 50 else bb_width
        
        is_squeeze = bb_width < (avg_bb_width * 0.7) and adx < 20  # OPTIMIZADO: Fake squeeze check
        is_high_vol = bb_width > (avg_bb_width * 2.0)
        
        # --- CLASIFICACIÓN (OPTIMIZADO: Sistema de confianza ponderado) ---
        
        regime = MarketRegime.UNCERTAIN
        reason = []
        confidence = 0.3  # Valor por defecto más bajo
        
        # Prioridad 1: Alta Volatilidad (Peligro)
        if is_high_vol:
            regime = MarketRegime.HIGH_VOLATILITY
            reason.append("Volatilidad Extrema (Bollinger Expansion)")
            confidence = 0.85
            
        # Prioridad 2: Squeeze (Preparación) - OPTIMIZADO con fake check
        elif is_squeeze:
            regime = MarketRegime.SQUEEZE
            reason.append("Squeeze Detectado (Baja Volatilidad + ADX bajo)")
            confidence = 0.75
            
        # Prioridad 3: Tendencia Clara
        elif is_trending_strong:
            if is_bullish_alignment and ema_slope > 0:
                regime = MarketRegime.TRENDING_BULLISH
                reason.append(f"Tendencia Alcista Fuerte (ADX={adx:.1f})")
                confidence = 0.9
            elif is_bearish_alignment and ema_slope < 0:
                regime = MarketRegime.TRENDING_BEARISH
                reason.append(f"Tendencia Bajista Fuerte (ADX={adx:.1f})")
                confidence = 0.9
            else:
                # ADX alto pero EMAs cruzadas o precio en retroceso profundo
                regime = MarketRegime.UNCERTAIN
                reason.append("Conflicto: ADX alto pero estructura rota")
                confidence = 0.4
                
        # Prioridad 4: Rango (Ranging)
        elif not is_trending_weak: # ADX < 20
            regime = MarketRegime.RANGING_STABLE
            reason.append(f"Rango Lateral (ADX bajo={adx:.1f})")
            confidence = 0.8
            
        # Default - OPTIMIZADO: Threshold mínimo de confianza
        else:
            regime = MarketRegime.UNCERTAIN
            reason.append("Mercado mixto / Transición")
            confidence = 0.3
        
        # OPTIMIZACIÓN: Si confidence < 0.5, marcar como UNCERTAIN
        if confidence < 0.5 and regime != MarketRegime.HIGH_VOLATILITY:
            regime = MarketRegime.UNCERTAIN
            reason.append("(Confianza baja)")
            
        return {
            "regime": regime,
            "confidence": confidence,
            "reason": ", ".join(reason),
            "details": {
                "adx": adx,
                "bb_width_ratio": bb_width / avg_bb_width if avg_bb_width > 0 else 0,
                "ema_slope": ema_slope
            }
        }
