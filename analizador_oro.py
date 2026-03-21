# analizador_oro.py
import logging
import pandas as pd
from datetime import datetime, time, timezone
import random

# Obtener una instancia del logger para este módulo
logger = logging.getLogger(__name__)

# --- Parámetros de la Estrategia ---
from config import params
# Los parámetros se cargan dinámicamente en cada función para permitir hot-reloading


# --- Importaciones de Librerías y Módulos ---
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import TELEGRAM_TOKEN, CHAT_ID, SUPPORTED_ASSETS
from data_fetch import get_candles
from indicadores import aplicar_indicadores, validar_vwap, detectar_divergencia_rsi, detectar_divergencia_macd, calcular_obv_trend
from registro_signals import registrar_senal
from utils import detectar_soportes_resistencias, verificar_distancia_soporte_resistencia, verificar_volatilidad_extrema, es_vela_cerrada
from config import MIN_DISTANCE_PCT, MAX_ATR_MULT
# Mantuvimos la importación arriba para compatibilidad si algo externo lo usa, 
# pero idealmente usaríamos params.get() abajo.
# actually, let's just remove it if we overwrite usages.
# But wait, config.py has them as module vars. 
# Let's keep the import for now but ignore them in code?
# No, cleaner to remove usage.

from realtime_streaming import get_realtime_data, start_streaming
from reinforcement_learning import get_rl_signal, load_rl_model
from sentiment_analysis import adjust_signal_with_sentiment
from portfolio_optimization import allocate_capital
from fundamental_data import get_economic_indicators, assess_market_impact
from market_regime import MarketRegimeDetector, MarketRegime
from htf_memory import HTFMemory
from performance_utils import cached_indicator, profile_performance, performance_monitor, memoize_dataframe
from advanced_ml import predict_advanced_signal # --- NUEVO: Motor de ML Avanzado ---

# Cache global para instancias de memoria (evitar recargar datos HTF cada vez)
memories = {}

# Importar app para contexto de base de datos
from models import app
from risk_manager import risk_manager
from live_trading import live_trading_manager

# --- Sistema de Cooldown de Señales ---
from datetime import timedelta

# Cache de señales emitidas: {symbol: {'tipo': str, 'timestamp': datetime, 'price': float}}
signal_cooldown = {}

def verificar_cooldown(symbol: str, tipo: str, price: float) -> bool:
    """
    Verifica si se puede emitir una nueva señal según el cooldown.
    Returns True si la señal puede emitirse, False si está en cooldown.
    """
    cooldown_min = params.get("COOLDOWN_MINUTES", 30)
    price_threshold = params.get("PRICE_CHANGE_THRESHOLD", 0.005)
    
    if symbol not in signal_cooldown:
        return True  # Primera señal para este símbolo
    
    last_signal = signal_cooldown[symbol]
    now = datetime.now(timezone.utc)
    
    # Si el tipo de señal cambió (BUY -> SELL o viceversa), permitir
    if last_signal['tipo'] != tipo:
        return True
    
    # Si el precio cambió significativamente, permitir
    price_change = abs(price - last_signal['price']) / last_signal['price']
    if price_change >= price_threshold:
        return True
    
    # Verificar tiempo transcurrido
    time_elapsed = now - last_signal['timestamp']
    if time_elapsed >= timedelta(minutes=cooldown_min):
        return True
    
    logger.debug(f"Cooldown activo para {symbol}: {tipo}. Próxima señal en {cooldown_min - time_elapsed.seconds // 60} min")
    return False

def registrar_cooldown(symbol: str, tipo: str, price: float):
    """Registra una señal en el cache de cooldown."""
    signal_cooldown[symbol] = {
        'tipo': tipo,
        'timestamp': datetime.now(timezone.utc),
        'price': price
    }


# --- Funciones de Soporte de la Estrategia ---

def mercado_abierto() -> bool:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:  # Fin de semana
        return False
    # Horas de trading: Lunes-Viernes, 00:00 - 21:00 UTC (cierra a las 21:00 UTC)
    return 0 <= now.hour < 21

def filtrar_horas(df):
    """Filtra datos fuera de horas de alta volatilidad (ej. evita sesiones asiáticas si es forex)."""
    # Para forex, filtra horas fuera de 00:00-21:00 UTC (sesiones europeas/americanas)
    df = df.copy()  # Crear copia para evitar SettingWithCopyWarning
    df.loc[:, 'hour'] = df['datetime'].dt.hour
    return df[(df['hour'] >= 0) & (df['hour'] <= 21)]

def filtrar_sesion_xau():
    """
    Verifica si estamos en una sesión óptima para operar XAU/USD.
    Solo permite trading en Londres (08-12 UTC) y NY Open (13-17 UTC).
    Returns: True si es buena hora para operar oro.
    """
    if not params.get("XAU_SESSION_FILTER", True):
        return True  # Filtro desactivado
    
    now = datetime.now(timezone.utc)
    hour = now.hour
    
    # Sesiones óptimas para oro:
    # Londres Open: 08:00-12:00 UTC (mejores movimientos direccionales)
    # NY Open: 13:00-17:00 UTC (alta liquidez)
    is_london = 8 <= hour <= 12
    is_ny = 13 <= hour <= 17
    
    if is_london or is_ny:
        return True
    
    logger.debug(f"Fuera de sesión óptima XAU (hora UTC: {hour}). Solo operamos 08-12 y 13-17.")
    return False

def es_retroceso_valido(df, direction="buy"):
    """
    Detecta si estamos en un retroceso saludable dentro de una tendencia.
    Los profesionales operan retrocesos, no extensiones.
    """
    if len(df) < 50:
        return False
    
    # EMA20 para retrocesos de corto plazo
    ema20 = df['close'].ewm(span=20, adjust=False).mean()
    ema50 = df['EMA50'] if 'EMA50' in df.columns else df['close'].ewm(span=50, adjust=False).mean()
    
    price = df['close'].iloc[-1]
    ema20_val = ema20.iloc[-1]
    ema50_val = ema50.iloc[-1]
    
    # Tolerancia del 0.3% para considerar "tocando" la EMA
    tolerance = 0.003
    
    if direction == "buy":
        # Tendencia alcista (EMA20 > EMA50) pero precio retrocedió a EMA20
        in_uptrend = ema20_val > ema50_val
        touched_ema = price <= ema20_val * (1 + tolerance) and price >= ema20_val * (1 - tolerance)
        above_ema50 = price > ema50_val  # No debe estar debajo de EMA50
        return in_uptrend and touched_ema and above_ema50
    else:  # sell
        # Tendencia bajista (EMA20 < EMA50) pero precio rebotó a EMA20
        in_downtrend = ema20_val < ema50_val
        touched_ema = price >= ema20_val * (1 - tolerance) and price <= ema20_val * (1 + tolerance)
        below_ema50 = price < ema50_val
        return in_downtrend and touched_ema and below_ema50

def detectar_momentum_rsi(df):
    """
    Detecta momentum usando el sistema dual RSI (7/21).
    RSI rápido cruzando sobre lento = momentum fuerte.
    Returns: 'bullish', 'bearish', or 'neutral'
    """
    if 'RSI_fast' not in df.columns or 'RSI_slow' not in df.columns:
        return 'neutral'
    
    rsi_fast = df['RSI_fast'].iloc[-1]
    rsi_slow = df['RSI_slow'].iloc[-1]
    rsi_fast_prev = df['RSI_fast'].iloc[-2] if len(df) > 1 else rsi_fast
    rsi_slow_prev = df['RSI_slow'].iloc[-2] if len(df) > 1 else rsi_slow
    
    # Cruce alcista: RSI rápido cruza por encima del lento
    if rsi_fast > rsi_slow and rsi_fast_prev <= rsi_slow_prev:
        return 'bullish'
    
    # Cruce bajista: RSI rápido cruza por debajo del lento
    if rsi_fast < rsi_slow and rsi_fast_prev >= rsi_slow_prev:
        return 'bearish'
    
    # Momentum confirmado (ya cruzado y manteniéndose)
    if rsi_fast > rsi_slow + 5:  # 5 puntos de separación = momentum fuerte
        return 'bullish'
    if rsi_fast < rsi_slow - 5:
        return 'bearish'
    
    return 'neutral'

def filtrar_news(df, news_window=60):
    """
    Filtra señales cerca de eventos de news.
    OPTIMIZADO: Desactivado temporalmente para mayor agresividad.
    """
    return df

def vela_rechazo(u) -> str:
    cuerpo = abs(u["close"] - u["open"])
    if cuerpo == 0: return ""
    sup = u["high"] - max(u["close"], u["open"])
    inf = min(u["close"], u["open"]) - u["low"]
    if sup > 2 * cuerpo and sup > inf:
        return "sell"
    if inf > 2 * cuerpo and inf > sup:
        return "buy"
    return ""

def validar_tendencia(df, direction="buy"):
    """Valida la tendencia principal usando EMAs y MACD. OPTIMIZADO: Cachea cálculos."""
    # OPTIMIZACIÓN: Reutilizar EMAs si ya existen en el DataFrame
    if 'EMA50' not in df.columns:
        df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    if 'EMA200' not in df.columns:
        df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # --- MACD ---
    # OPTIMIZACIÓN: Calcular MACD solo si no existe
    if 'MACD' not in df.columns or 'MACD_Signal' not in df.columns:
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # Obtener últimos valores
    last_ema_corta = df['EMA50'].iloc[-1]
    last_ema_larga = df['EMA200'].iloc[-1]
    last_macd = df['MACD'].iloc[-1]
    last_signal = df['MACD_Signal'].iloc[-1]
    last_price = df['close'].iloc[-1]

    if direction == "buy":
        return all([
            last_ema_corta > last_ema_larga,
            last_macd > last_signal,
            last_price > last_ema_larga
        ])
    else:  # "sell"
        return all([
            last_ema_corta < last_ema_larga,
            last_macd < last_signal,
            last_price < last_ema_larga
        ])

# --- Corazón de la Estrategia: Sistema de Puntuación ---

def decidir_senal(df, symbol="UNKNOWN", capital=10000, in_trade=False, current_sl=0, current_tp=0, trailing_stop=False, regime_info=None, rsi_div=None, macd_div=None, obv_trend='neutral', proximity=None):
    """
    Decide una señal basándose en un sistema de puntuación.
    Adaptado dinámicamente según el régimen de mercado y niveles HTF.
    """
    u = df.iloc[-1]
    regime = regime_info["regime"] if regime_info else MarketRegime.UNCERTAIN

    # Cargar params dinámicos
    ADX_THRESH = params.get("ADX_THRESH", 15)
    VOL_WINDOW = params.get("VOL_WINDOW", 20)
    ATR_WINDOW = params.get("ATR_WINDOW", 14)
    BASE_TP_MULT = params.get("TP_ATR_MULT", 1.5)
    BASE_SL_MULT = params.get("SL_ATR_MULT", 1.0)
    TRAILING_STOP_PCT = params.get("TRAILING_STOP_PCT", 0.02)
    POSITION_SIZE_PCT = params.get("POSITION_SIZE_PCT", 0.01)
    DIVERGENCE_POINTS = params.get("DIVERGENCE_POINTS", 3)  # OPTIMIZADO: Aumentado de 2 a 3


    # --- PUNTOS DINÁMICOS ---
    points_trend = 2
    points_adx = 1
    points_vol = 1
    points_rsi = 1
    points_bb = 1
    points_divergence = DIVERGENCE_POINTS  # Nuevo: puntos por divergencia
    
    # Ajustar pesos según régimen
    if regime == MarketRegime.RANGING_STABLE:
        points_trend = 0  # Ignorar tendencia en rangos
        points_rsi = 2    # RSI vale doble en rangos
        points_bb = 2     # Bollinger vale doble en rangos
        points_divergence = 4  # OPTIMIZADO: Divergencias valen más en rangos
    elif regime in [MarketRegime.TRENDING_BULLISH, MarketRegime.TRENDING_BEARISH]:
        points_trend = 3  # Tendencia es rey
        points_rsi = 0    # Ignorar sobrecompra/sobreventa (dejar correr)
    
    # NOTA: Divergencias ya calculadas y pasadas como parámetros para evitar recalcular
    # Se esperan como kwargs: rsi_div, macd_div, obv_trend
    
    # --- Puntuación de Compra ---
    score_buy = 0
    details_buy = []
    # Lógica de Tendencia Adaptativa
    is_trend_buy = validar_tendencia(df, direction="buy")
    
    # Si estamos en SOPORTE DIARIO, somos más flexibles con la tendencia (buscamos rebote)
    if proximity == 'support' and not is_trend_buy:
        # Permitir compra si precio > EMA50 (recuperación temprana)
        if df['close'].iloc[-1] > df['EMA50'].iloc[-1]:
             score_buy += 2 # Damos los puntos de tendencia por estar en soporte válido
             details_buy.append("Rebound@Supp")
    elif is_trend_buy:
        score_buy += points_trend
        details_buy.append("Trend")

    if u.get("ADX", 0) >= ADX_THRESH: 
        score_buy += points_adx
        details_buy.append("ADX")
    if u["volume"] > df["volume"].rolling(VOL_WINDOW).mean().iloc[-1] * 1.2: 
        score_buy += points_vol
        details_buy.append("Vol")
    if vela_rechazo(u) == "buy": 
        score_buy += 1
        details_buy.append("Rechazo")
    if validar_vwap(df, umbral_pct=0.005).iloc[-1]: 
        score_buy += 1
        details_buy.append("VWAP")

    # RSI (Comprar si está en sobreventa <30)
    if u.get("RSI", 0) < 30: score_buy += points_rsi
    
    # Bollinger Bands (Comprar si rompe la banda baja)
    if u["close"] <= u["BB_Low"]: score_buy += points_bb
    
    # NUEVO: Divergencias alcistas
    if rsi_div == 'bullish_div':
        score_buy += points_divergence
        details_buy.append("DivRSI")
        logger.info(f"🔄 Divergencia RSI alcista detectada (+{points_divergence} pts)")
    if macd_div == 'bullish_div':
        score_buy += 1
        details_buy.append("DivMACD")
        
    # NUEVO: OBV confirma tendencia alcista
    if obv_trend == 'bullish':
        score_buy += 1
        details_buy.append("OBV")
    
    # --- NUEVO: Momentum RSI Dual (7/21) ---
    rsi_momentum = detectar_momentum_rsi(df)
    if rsi_momentum == 'bullish':
        score_buy += 1
        details_buy.append("RSI_Mom")
    
    # --- NUEVO: Bonus por Retroceso válido (profesional) ---
    if es_retroceso_valido(df, direction="buy"):
        score_buy += 1
        details_buy.append("Pullback")

    # --- NUEVO: Motor de Machine Learning Avanzado ---
    try:
        ml_prediction = predict_advanced_signal(symbol)
        if ml_prediction and 'error' not in ml_prediction:
            if ml_prediction['signal'] == 'buy':
                points = 2 if ml_prediction['strength'] == 'strong' else 1
                score_buy += points
                details_buy.append(f"ML({ml_prediction['strength']})")
                logger.debug(f"ML Predictor confirmaciÃ³n BUY: {ml_prediction['confidence']}%")
    except Exception as e:
        logger.error(f"Error en ML Predictor (BUY): {e}")

    # --- Puntuación de Venta ---
    score_sell = 0
    details_sell = []
    # Lógica de Tendencia Adaptativa para Venta
    is_trend_sell = validar_tendencia(df, direction="sell")
    
    # Si estamos en RESISTENCIA DIARIA, somos más flexibles (buscamos rechazo)
    if proximity == 'resistance' and not is_trend_sell:
        if df['close'].iloc[-1] < df['EMA50'].iloc[-1]:
             score_sell += 2
             details_sell.append("Rejection@Res")
    elif is_trend_sell:
        score_sell += points_trend
        details_sell.append("Trend")

    if u.get("ADX", 0) >= ADX_THRESH: 
        score_sell += points_adx
        details_sell.append("ADX")
    if u["volume"] > df["volume"].rolling(VOL_WINDOW).mean().iloc[-1] * 1.2: 
        score_sell += points_vol
        details_sell.append("Vol")
    if vela_rechazo(u) == "sell": 
        score_sell += 1
        details_sell.append("Rechazo")
    if validar_vwap(df, umbral_pct=0.005).iloc[-1]: 
        score_sell += 1
        details_sell.append("VWAP")

    # LOGGING DE DEBUG
    if score_buy > 2 or score_sell > 2:
        logger.info(f"🔍 DEBUG SCORES: Buy={score_buy} ({details_buy}) | Sell={score_sell} ({details_sell}) - Regime: {regime}")

    # RSI (Vender si está en sobrecompra >70)
    if u.get("RSI", 0) > 70: score_sell += points_rsi
    
    # Bollinger Bands (Vender si rompe la banda alta)
    if u["close"] >= u["BB_High"]: score_sell += points_bb
    
    # NUEVO: Divergencias bajistas
    if rsi_div == 'bearish_div':
        score_sell += points_divergence
        details_sell.append("DivRSI")
        logger.info(f"🔄 Divergencia RSI bajista detectada (+{points_divergence} pts)")
    if macd_div == 'bearish_div':
        score_sell += 1
        details_sell.append("DivMACD")
        
    # NUEVO: OBV confirma tendencia bajista
    if obv_trend == 'bearish':
        score_sell += 1
        details_sell.append("OBV")
    
    # --- NUEVO: Momentum RSI Dual (7/21) ---
    if rsi_momentum == 'bearish':
        score_sell += 1
        details_sell.append("RSI_Mom")
    
    # --- NUEVO: Bonus por Retroceso válido (profesional) ---
    if es_retroceso_valido(df, direction="sell"):
        score_sell += 1
        details_sell.append("Pullback")

    # --- NUEVO: Motor de Machine Learning Avanzado ---
    try:
        if 'ml_prediction' not in locals(): # Evitar doble llamada si ya se hizo para buy
             ml_prediction = predict_advanced_signal(symbol)
        
        if ml_prediction and 'error' not in ml_prediction:
            if ml_prediction['signal'] == 'sell':
                points = 2 if ml_prediction['strength'] == 'strong' else 1
                score_sell += points
                details_sell.append(f"ML({ml_prediction['strength']})")
                logger.debug(f"ML Predictor confirmaciÃ³n SELL: {ml_prediction['confidence']}%")
    except Exception as e:
        logger.error(f"Error en ML Predictor (SELL): {e}")

    # --- Gestión de Riesgos ---
    if in_trade and trailing_stop:
        if current_sl > 0 and u["close"] > current_tp * (1 - TRAILING_STOP_PCT):
            new_sl = u["close"] * (1 - TRAILING_STOP_PCT)
            if new_sl > current_sl:
                current_sl = new_sl
        return {"trailing_sl": current_sl} 

    # --- Decisión Final (OPTIMIZADO: thresholds más altos para mejor calidad) ---
    MIN_SCORE_MANUAL = params.get("MIN_SCORE_MANUAL", 5)  # OPTIMIZADO: Aumentado de 4 a 5
    threshold = MIN_SCORE_MANUAL
    
    if regime == MarketRegime.RANGING_STABLE: 
        threshold = 4  # OPTIMIZADO: Era 6, ahora 4 - más agresivo en rangos
    
    # --- Ratio R:R Dinámico según régimen (NUEVO) ---
    TP_MULT = BASE_TP_MULT
    SL_MULT = BASE_SL_MULT
    
    if regime in [MarketRegime.TRENDING_BULLISH, MarketRegime.TRENDING_BEARISH]:
        # En tendencia fuerte: objetivos más amplios - OPTIMIZADO
        TP_MULT = BASE_TP_MULT * 2.0  # OPTIMIZADO: Aumentado de 1.5x a 2.0x (3.0x ATR total)
    elif regime == MarketRegime.RANGING_STABLE:
        # En rango: SL más ajustado
        SL_MULT = BASE_SL_MULT * 0.8
    
    if score_buy > score_sell and score_buy >= threshold:
        tipo = "buy"
        atr = u["ATR"]
        price = u["close"]
        sl = price - atr * SL_MULT
        tp = price + atr * TP_MULT
        position_size = capital * POSITION_SIZE_PCT / abs(price - sl)
        return {"tipo": tipo, "score": score_buy, "position_size": position_size, "sl": sl, "tp": tp, "regime": regime.value, "details": "+".join(details_buy)}

    if score_sell > score_buy and score_sell >= threshold:
        tipo = "sell"
        atr = u["ATR"]
        price = u["close"]
        sl = price + atr * SL_MULT
        tp = price - atr * TP_MULT
        position_size = capital * POSITION_SIZE_PCT / abs(price - sl)
        return {"tipo": tipo, "score": score_sell, "position_size": position_size, "sl": sl, "tp": tp, "regime": regime.value, "details": "+".join(details_sell)}

    return None


# --- Análisis Principal y Orquestación ---

def analizar_mercado(symbol: str, is_manual: bool = False, capital=10000, multi_timeframe=False):
    """Función principal que orquesta el análisis de un símbolo. Soporta multi-timeframe."""
    from errors import DataFetchError, SignalAnalysisError

    # Para BTC, el mercado nunca cierra. Para otros activos, se comprueba el horario.
    if symbol.upper() != 'BTC/USD' and not mercado_abierto() and is_manual:
        return {"message": "📴 Mercado cerrado para este activo."}
    
    # --- FILTRO DE SESIÓN XAU/USD (NUEVO) ---
    # Solo operar oro en sesiones óptimas: Londres (08-12 UTC) y NY (13-17 UTC)
    if symbol.upper() == 'XAU/USD' and not is_manual:
        if not filtrar_sesion_xau():
            logger.debug(f"XAU/USD: Fuera de sesión óptima, saltando análisis automático.")
            return None

    try:
        # Usar datos en tiempo real si disponibles
        df = get_realtime_data(symbol)
        if df.empty:
            df = get_candles(symbol, interval="5min", output_size=200)
        
        atr_window = params.get("ATR_WINDOW", 14)
        if df.empty or len(df) < max(atr_window, 50):
            if is_manual:
                return {"message": f"⛔ Insuficientes velas para {symbol}"}
            return None

        df = aplicar_indicadores(df)

        # BTC no tiene horario de mercado, así que no filtramos por horas.
        if symbol.upper() != 'BTC/USD':
            df = filtrar_horas(df)

        df = filtrar_news(df)
        if df.empty:
            if is_manual:
                return {"message": "⛔ Datos filtrados (fuera de horas/news)."}
            return None

        # --- NUEVOS FILTROS AVANZADOS ---

        # 1. Verificar que la vela esté cerrada
        if not es_vela_cerrada(df):
            if is_manual:
                return {"message": "⏳ Vela actual no cerrada, esperando confirmación."}
            return None

        # 2. Verificar volatilidad extrema
        max_atr_mult = params.get("MAX_ATR_MULT", 2.0)
        if not verificar_volatilidad_extrema(df, max_atr_mult=max_atr_mult):
            if is_manual:
                return {"message": "⚡ Volatilidad extrema detectada, señal descartada."}
            return None

        # 3. Detectar soportes/resistencias y verificar distancia
        # 3. Detectar soportes/resistencias y verificar distancia
        
        # --- NUEVO: DETECCIÓN DE RÉGIMEN DE MERCADO (Brain Module) ---
        regime_detector = MarketRegimeDetector(df)
        regime_info = regime_detector.detect_regime()
        
        # FILTRO MAESTRO: ¿Es seguro operar hoy?
        if regime_info['regime'] == MarketRegime.HIGH_VOLATILITY:
            if is_manual:
                return {
                    "message": f"⛔ ALERTA: Mercado demasiado volátil ({regime_info['reason']}). Operativa pausada."
                }
            logger.info(f"Análisis pausado para {symbol}: High Volatilty detected.")
            return None
            
        # Si estamos en SQUEEZE, solo alertar, no operar (esperar ruptura)
        if regime_info['regime'] == MarketRegime.SQUEEZE:
            if is_manual:
                return {
                    "message": f"⏳ SQUEEZE detectado. Baja volatilidad. Esperando ruptura explosiva."
                }
            return None

        # --- NUEVO: MEMORIA HTF Y DETECCIÓN DE TRAMPAS 🐘🪤 ---
        if symbol not in memories:
            memories[symbol] = HTFMemory(symbol)
        memory = memories[symbol]
        
        try:
            memory.update_memory()
        except Exception as e:
            logger.warning(f"No se pudo actualizar memoria HTF para {symbol}: {e}")

        # Obtener precio actual para usarlo en verificaciones HTF
        price = df.iloc[-1]["close"]

        # 1. Detectar Trampas (Golden Signal)
        trap = memory.detect_liquidity_trap(df)
        golden_signal = None
        
        if trap == 'bear_trap': # Atrapó osos -> Señal ALCISTA fuerte
            logger.info(f"🐻🪤 BEAR TRAP DETECTADA en {symbol}! Posible reversión ALCISTA.")
            golden_signal = "buy"
        elif trap == 'bull_trap': # Atrapó toros -> Señal BAJISTA fuerte
            logger.info(f"🐮🪤 BULL TRAP DETECTADA en {symbol}! Posible reversión BAJISTA.")
            golden_signal = "sell"

        # 2. Verificar Proximidad a Niveles Diarios (Solo si no hay trampa)
        # Si hay trampa, operamos JUSTAMENTE el nivel, así que ignoramos este filtro.
        proximity = None # Inicializar
        if not golden_signal:
            proximity = memory.check_level_proximity(price)
            if proximity == 'resistance':
                # if is_manual: return {"message": "⛔ Precio en RESISTENCIA DIARIA. Compras prohibidas."}
                logger.info(f"Filtro HTF: Precio en resistencia diaria {symbol}. Ignorando setups de compra (pero buscando ventas).")
            elif proximity == 'support':
                # if is_manual: return {"message": "⛔ Precio en SOPORTE DIARIO. Ventas prohibidas."}
                logger.info(f"Filtro HTF: Precio en soporte diario {symbol}. Ignorando setups de venta (pero buscando compras).")

        # Filtro local
        levels = detectar_soportes_resistencias(df)
        min_dist = params.get("MIN_DISTANCE_PCT", 0.005)
        if not golden_signal and not verificar_distancia_soporte_resistencia(price, levels['support'], levels['resistance'], min_distance_pct=min_dist):
            if is_manual:
                return {"message": "📊 Precio cerca de soporte/resistencia local, señal descartada."}
            return None

        # --- CALCULAR DIVERGENCIAS Y OBV (NUEVO) ---
        # Calculamos esto ANTES de decidir la señal para pasarlo como contexto
        rsi_div = detectar_divergencia_rsi(df)
        macd_div = detectar_divergencia_macd(df)
        obv_trend = calcular_obv_trend(df)
        
        signal_data = decidir_senal(
            df,
            symbol=symbol,
            capital=capital, 
            regime_info=regime_info,
            rsi_div=rsi_div,
            macd_div=macd_div,
            obv_trend=obv_trend,
            proximity=proximity if not golden_signal else None # Pasar contexto HTF
        )
        
        # --- INYECTAR GOLDEN SIGNAL ---
        # Si detectamos una trampa, forzamos la señal con puntuación máxima
        if golden_signal:
            signal_data = {
                "tipo": golden_signal,
                "score": 6, # Puntuación máxima "Dios"
                "position_size": 0, # Se calculará abajo
                "sl": 0, "tp": 0 # Se calcularán abajo
            }
            # Calcular SL/TP específicos para trampa (usando ATR o la mecha)
            atr = df["ATR"].iloc[-1]
            if golden_signal == "buy":
                signal_data["sl"] = df["low"].iloc[-1] - atr * 0.5 # SL debajo de la mecha de la trampa
                signal_data["tp"] = price + atr * 3 # Ratio 1:3 mínimo para trampas
            else:
                signal_data["sl"] = df["high"].iloc[-1] + atr * 0.5
                signal_data["tp"] = price - atr * 3
                
            # Calcular position size manualmente aquí porque sobrescribimos signal_data
            _pos_size_pct = params.get("POSITION_SIZE_PCT", 0.01)
            dist_sl = abs(price - signal_data["sl"])
            if dist_sl > 0:
                signal_data["position_size"] = capital * _pos_size_pct / dist_sl
            else:
                signal_data["position_size"] = 0
        
        # Filtrar señales contra tendencia HTF (si no es golden signal)
        if signal_data and not golden_signal:
             proximity = memory.check_level_proximity(price)
             if proximity == 'resistance' and signal_data['tipo'] == 'buy':
                 return None # Bloquear compra en resistencia diario
             if proximity == 'support' and signal_data['tipo'] == 'sell':
                 return None # Bloquear venta en soporte diario

        # Integrar RL si disponible
        rl_signal = get_rl_signal(df)
        if rl_signal and signal_data and signal_data['tipo'] == rl_signal:
            signal_data['score'] += 1  # Bonus por coincidencia RL

        # Ajustar con sentiment analysis
        signal_data = adjust_signal_with_sentiment(signal_data, symbol)

        # --- Nueva sección: Datos fundamentales ---
        try:
            economic_data = get_economic_indicators()
            market_impact = assess_market_impact(economic_data)
            if market_impact > 0.1 and signal_data['tipo'] == 'buy':
                signal_data['score'] += 1  # Bonus por datos fundamentales positivos
            elif market_impact < -0.1 and signal_data['tipo'] == 'sell':
                signal_data['score'] += 1  # Bonus por datos fundamentales negativos
        except Exception as e:
            logger.warning(f"Error procesando datos fundamentales: {e}")

        if multi_timeframe:
            # Análisis en 15min y 1h para confirmar
            df_15m = get_candles(symbol, interval="15min", output_size=100)
            df_1h = get_candles(symbol, interval="1h", output_size=50)
            if not df_15m.empty and not df_1h.empty:
                df_15m = aplicar_indicadores(df_15m)
                df_1h = aplicar_indicadores(df_1h)
                signal_15m = decidir_senal(df_15m, symbol=symbol, capital=capital)
                signal_1h = decidir_senal(df_1h, symbol=symbol, capital=capital)
                # Combinar: requiere señal en al menos 2 timeframes
                confirmations = sum([signal_data is not None, signal_15m is not None, signal_1h is not None])
                if confirmations < 2:
                    signal_data = None
            else:
                # Si no hay datos multi-timeframe, no confirmar
                signal_data = None

        if signal_data is None:
            if is_manual:
                return {"message": "⏳ Sin señal clara (puntuación < 3 o sin confirmación multi-frame)."}
            return None

    except Exception as e:
        logger.error(f"Error en analizar_mercado para {symbol}: {e}")
        raise SignalAnalysisError(f"Análisis falló para {symbol}: {str(e)}")

    # --- Si hay señal, preparar los datos de la operación ---
    u = df.iloc[-1]
    price = u["close"]
    tp = signal_data["tp"]
    sl = signal_data["sl"]
    position_size = signal_data["position_size"]

    confianza_str = f"{signal_data['score']}/6 ({signal_data.get('details', '')})"

    registrar_senal(
        symbol=symbol,
        tipo=signal_data["tipo"],
        precio=price,
        tp=tp,
        sl=sl,
        confianza=confianza_str
    )

    result = {
        "symbol": symbol,
        "tipo": signal_data["tipo"],
        "price": price,
        "tp": tp,
        "sl": sl,
        "position_size": position_size,
        "confianza": confianza_str,
        "adx": u.get("ADX", 0),
        # --- Contexto Nivel Dios ---
        "regime": regime_info['regime'].value,
        "regime_desc": regime_info.get('reason', ''),
        "trap_signal": trap,  # 'bull_trap', 'bear_trap' or None
        "divergences": {
             "rsi": rsi_div,
             "macd": macd_div,
             "obv": obv_trend
        },
        "htf_levels": memory.daily_levels if 'memory' in locals() else None,
        "local_levels": levels if 'levels' in locals() else None
    }
    allocation = allocate_capital([result]) if result else {}
    position_size = allocation.get(symbol, position_size)
    result["position_size"] = position_size
    
    # Para el modo automático, somos más exigentes (puntuación >= MIN_SCORE_AUTO)
    MIN_SCORE_AUTO = params.get("MIN_SCORE_AUTO", 5)
    if not is_manual and signal_data["score"] < MIN_SCORE_AUTO:
        logger.info(f"Señal para {symbol} con puntuación baja ({signal_data['score']}/8) no enviada automáticamente (requiere {MIN_SCORE_AUTO}).")
        return None
    
    # --- Sistema de Cooldown (NUEVO) ---
    if not verificar_cooldown(symbol, signal_data["tipo"], price):
        logger.info(f"Cooldown activo para {symbol}. Señal {signal_data['tipo']} ignorada.")
        return None
    
    # Registrar en cooldown solo si vamos a emitir la señal
    registrar_cooldown(symbol, signal_data["tipo"], price)

    return result

# --- Tarea Programada para el Modo Automático ---

async def job(context: ContextTypes.DEFAULT_TYPE):
    """Tarea programada que se ejecuta cada 5 minutos para analizar todos los activos."""
    import asyncio
    logger.info("--- Iniciando ciclo de análisis programado ---")
    
    # --- CHECK CIRCUIT BREAKER Y CONTEXTO DB ---
    with app.app_context():
        if risk_manager.check_kill_switch(live_trading_manager):
            logger.critical("🚨 Ciclo cancelado: Circuit Breaker activo por pérdidas diarias.")
            return

        loop = asyncio.get_running_loop()
    
    for symbol, description in SUPPORTED_ASSETS.items():
        try:
            logger.info(f"Ejecutando análisis para {symbol}")
            
            # Ejecutar análisis (síncrono/bloqueante) en un thread separado para no congelar el bot
            resultado = await loop.run_in_executor(None, analizar_mercado, symbol, False)
            
            if resultado:
                logger.info(f"¡SEÑAL AUTOMÁTICA ENCONTRADA PARA {symbol}! Puntuación: {resultado['confianza']}")
                import random
                frases = [
                    "¡El mercado provee, tú pones la disciplina! 🧠💪",
                    "Paciencia, gestión de riesgo y ejecución fría. Let's go! 🚀",
                    "Los grandes traders no adivinan, reaccionan. ¡A cazar pips! 💰",
                    "Un trader supremo protege su capital antes de atacar. 🛡️",
                    "¡Concéntrate en el proceso, los profits llegarán solos! 📈✨"
                ]
                emoji_tipo = "🟢 COMPRA (LONG)" if resultado['tipo'].lower() == 'buy' else "🔴 VENTA (SHORT)"
                mensaje = [
                    "⚡ 𝐀𝐒𝐓𝐀𝐁𝐎𝐓 𝐒𝐔𝐏𝐑𝐄𝐌𝐄 𝐒𝐈𝐆𝐍𝐀𝐋 ⚡",
                    "━━━━━━━━━━━━━━━━━━",
                    f"🪙 ACTIVO: {description}",
                    f"🎯 ACCIÓN: {emoji_tipo}",
                    f"📊 CONFIANZA: {resultado['confianza']} 💎",
                    "━━━━━━━━━━━━━━━━━━",
                    f"📥 ENTRADA (ENTRY): {resultado['price']:.4f}",
                    f"⛔ STOP LOSS (SL): {resultado['sl']:.4f}",
                    f"✅ TAKE PROFIT (TP): {resultado['tp']:.4f}",
                    "━━━━━━━━━━━━━━━━━━",
                    f"🧠 Análisis M.L: {resultado.get('regime', 'N/A')}",
                    f"🪤 Trampas Ocultas: {resultado.get('trap_signal', 'None') or 'Ninguna'}",
                    "",
                    f"💡 Astabot dice:\n«{random.choice(frases)}»"
                ]
                await context.bot.send_message(chat_id=CHAT_ID, text="\n".join(mensaje))

                # --- EJECUCIÓN AUTOMÁTICA ---
                from broker_integration import broker
                logger.info(f"Enviando señal de {symbol} al broker para ejecución...")
                await broker.auto_execute(resultado)

            else:
                logger.info(f"No se encontró señal de alta confianza para {symbol} en este ciclo.")
        except Exception as e:
            logger.error(f"Error en el análisis programado para {symbol}: {e}", exc_info=True)
            from errors import notify_critical_error
            import asyncio
            asyncio.create_task(notify_critical_error(f"Fallo crítico en análisis de {symbol}: {str(e)}"))
    logger.info("--- Ciclo de análisis programado finalizado ---")
