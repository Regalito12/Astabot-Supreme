# htf_memory.py
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from data_fetch import get_candles

logger = logging.getLogger(__name__)

class HTFMemory:
    """
    Memoria de Largo Plazo (Higher Timeframe Memory).
    Gestiona niveles clave (Soportes/Resistencias) de marcos temporales mayores (Daily, 4H).
    Detecta trampas de liquidez (Sweeps).
    """
    def __init__(self, symbol):
        self.symbol = symbol
        self.daily_levels = {'support': [], 'resistance': []}
        self.last_update = None
        self.cache_duration = timedelta(hours=4)  # Actualizar niveles cada 4 horas
        self._cached_df = None  # OPTIMIZADO: Cachear datos daily
        self._cached_df_timestamp = None

    def _fetch_htf_data(self):
        """Obtiene datos diarios/4H con caché optimizado."""
        # OPTIMIZADO: Usar caché si existe y no ha vencido
        now = datetime.now()
        if (self._cached_df is not None and 
            self._cached_df_timestamp is not None and 
            (now - self._cached_df_timestamp) < timedelta(hours=1)):
            return self._cached_df
        
        # Intentar obtener Daily primero
        df_daily = get_candles(self.symbol, interval="1day", output_size=100)
        if df_daily.empty:
            # Fallback a 1h si daily falla (para crypto o forex si proveedores limitados)
            df_daily = get_candles(self.symbol, interval="1h", output_size=200)
        
        # Guardar en caché
        self._cached_df = df_daily
        self._cached_df_timestamp = now
        
        return df_daily

    def _find_swing_levels(self, df, window=5):
        """Encuentra Swing Highs y Lows significativos."""
        if df.empty: return

        # Swing Highs: Máximo local en ventana de 5 velas
        df['is_high'] = df['high'] == df['high'].rolling(window=window*2+1, center=True).max()
        # Swing Lows: Mínimo local
        df['is_low'] = df['low'] == df['low'].rolling(window=window*2+1, center=True).min()

        resistances = df[df['is_high']]['high'].values.tolist()
        supports = df[df['is_low']]['low'].values.tolist()

        # Filtrar niveles muy cercanos (agrupar)
        self.daily_levels['resistance'] = self._cluster_levels(resistances)
        self.daily_levels['support'] = self._cluster_levels(supports)
        
        logger.info(f"[{self.symbol}] HTF Levels actualizados. R: {len(self.daily_levels['resistance'])}, S: {len(self.daily_levels['support'])}")

    def _cluster_levels(self, levels, threshold_pct=0.005):
        """Agrupa niveles cercanos - OPTIMIZADO con mejor algoritmo."""
        if not levels or len(levels) == 0:
            return []
        
        levels_sorted = sorted(levels)
        clustered = []
        current_cluster = [levels_sorted[0]]
        
        for i in range(1, len(levels_sorted)):
            # Si el nivel está dentro del threshold del cluster actual, añadirlo
            cluster_mean = sum(current_cluster) / len(current_cluster)
            if abs(levels_sorted[i] - cluster_mean) / cluster_mean <= threshold_pct:
                current_cluster.append(levels_sorted[i])
            else:
                # Cerrar cluster actual y empezar uno nuevo
                clustered.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [levels_sorted[i]]
        
        # Añadir el último cluster
        if current_cluster:
            clustered.append(sum(current_cluster) / len(current_cluster))
        
        # Quedarse con los 5 más recientes/relevantes
        return clustered[-5:]

    def update_memory(self):
        """Actualiza la memoria si el caché expiró."""
        if self.last_update and datetime.now() - self.last_update < self.cache_duration:
            return

        df = self._fetch_htf_data()
        self._find_swing_levels(df)
        self.last_update = datetime.now()

    def check_level_proximity(self, current_price, threshold_pct=0.003):
        """
        Verifica si el precio actual está en una zona clave.
        Retorna: 'resistance', 'support', o None
        """
        for r in self.daily_levels['resistance']:
            if abs(current_price - r) / current_price < threshold_pct:
                return 'resistance'
        
        for s in self.daily_levels['support']:
            if abs(current_price - s) / current_price < threshold_pct:
                return 'support'
                
        return None

    def detect_liquidity_trap(self, df_lower_tf):
        """
        Detecta patrón de trampa (Sweep) en el timeframe actual (5m) contra niveles HTF.
        OPTIMIZADO: Añade filtro de volumen para confirmar trampas.
        Patrón: Rompe nivel -> Cierra dentro del rango -> Volumen alto.
        Retorna: 'bull_trap' (para vender), 'bear_trap' (para comprar), o None.
        """
        if df_lower_tf.empty or len(df_lower_tf) < 3: 
            return None
        
        last_candle = df_lower_tf.iloc[-1]
        prev_candle = df_lower_tf.iloc[-2]
        
        # OPTIMIZADO: Filtro de volumen - solo detectar trampas con volumen significativo
        avg_volume = df_lower_tf['volume'].rolling(20).mean().iloc[-1] if len(df_lower_tf) >= 20 else df_lower_tf['volume'].mean()
        volume_threshold = avg_volume * 1.5  # Volumen debe ser 1.5x el promedio
        
        if last_candle['volume'] < volume_threshold:
            return None  # Sin volumen suficiente, no es trampa confirmada
        
        # 1. Bear Trap (Cazar Stop Loss de Compradores -> Venta Institucional)
        # Precio rompe resistencia pero cierra ABAJO
        for r in self.daily_levels['resistance']:
            broke_level = last_candle['high'] > r
            closed_below = last_candle['close'] < r
            is_strong_rejection = (last_candle['high'] - last_candle['close']) > (last_candle['close'] - last_candle['low'])
            
            if broke_level and closed_below and is_strong_rejection:
                return 'bull_trap'  # Señal de VENTA (atrapó toros)

        # 2. Bull Trap (Cazar Stop Loss de Vendedores -> Compra Institucional)
        # Precio rompe soporte pero cierra ARRIBA
        for s in self.daily_levels['support']:
            broke_level = last_candle['low'] < s
            closed_above = last_candle['close'] > s
            is_strong_rejection = (last_candle['close'] - last_candle['low']) > (last_candle['high'] - last_candle['close'])
            
            if broke_level and closed_above and is_strong_rejection:
                return 'bear_trap'  # Señal de COMPRA (atrapó osos)

        return None
