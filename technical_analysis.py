"""
AstaBot 2.0 - Indicadores tecnicos y sistema de scoring
EMA 50/200, RSI, ADX, Bollinger, ATR, VWAP + SMC (FVG, Order Blocks)
+ HTF Confirmation + Liquidity Sweep + Volatility Filter
Sistema de scoring 0-8 puntos (score minimo 5)
"""
import os
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange


def calc_vwap(df):
    tp = (df['high'].values + df['low'].values + df['close'].values) / 3
    cum_vol_price = np.cumsum(tp * df['volume'].values)
    cum_vol = np.cumsum(df['volume'].values)
    return pd.Series(cum_vol_price / cum_vol, index=df.index)


def apply_indicators(df):
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['RSI'] = RSIIndicator(df['close'], window=14).rsi().bfill()
    df['ADX'] = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx().bfill()
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['BB_High'] = bb.bollinger_hband().bfill()
    df['BB_Low'] = bb.bollinger_lband().bfill()
    df['BB_Middle'] = bb.bollinger_mavg().bfill()
    df['ATR'] = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().bfill()
    df['VWAP'] = calc_vwap(df)
    return df


def rejection_candle(row):
    body = abs(row['close'] - row['open'])
    if body == 0:
        return ''
    upper_wick = row['high'] - max(row['close'], row['open'])
    lower_wick = min(row['close'], row['open']) - row['low']
    if upper_wick > 2 * body and upper_wick > lower_wick:
        return 'sell'
    if lower_wick > 2 * body and lower_wick > upper_wick:
        return 'buy'
    return ''


def detect_rsi_divergence(df, lookback=40):
    if len(df) < lookback + 5:
        return 0
    recent = df.tail(lookback)
    prices = recent['close'].values
    rsi_vals = recent['RSI'].values
    if len(prices) < 10:
        return 0
    half = len(prices) // 2
    price_lows = [prices[:half].argmin(), half + prices[half:].argmin()]
    rsi_lows = [rsi_vals[:half].argmin(), half + rsi_vals[half:].argmin()]
    if prices[price_lows[1]] < prices[price_lows[0]] and rsi_vals[rsi_lows[1]] > rsi_vals[rsi_lows[0]]:
        return 1
    price_highs = [prices[:half].argmax(), half + prices[half:].argmax()]
    rsi_highs = [rsi_vals[:half].argmax(), half + rsi_vals[half:].argmax()]
    if prices[price_highs[1]] > prices[price_highs[0]] and rsi_vals[rsi_highs[1]] < rsi_vals[rsi_highs[0]]:
        return -1
    return 0


def detect_fvg(df, lookback=20):
    if len(df) < lookback + 3:
        return 0
    recent = df.tail(lookback)
    highs = recent['high'].values
    lows = recent['low'].values
    closes = recent['close'].values
    for i in range(len(recent) - 3, 1, -1):
        prev_high = highs[i - 2]
        next_high = highs[i + 1]
        if prev_high < next_high and closes[i - 1] > next_high:
            return 1
        prev_low = lows[i - 2]
        next_low = lows[i + 1]
        if prev_low > next_low and closes[i - 1] < next_low:
            return -1
    return 0


def detect_order_block(df, lookback=15):
    if len(df) < lookback + 5:
        return 0
    recent = df.tail(lookback)
    for i in range(len(recent) - 5, 0, -1):
        if recent['close'].iloc[i] < recent['open'].iloc[i]:
            if recent['low'].iloc[i] == recent['low'].iloc[i:i+5].min():
                if recent['close'].iloc[i+1] > recent['high'].iloc[i]:
                    return 1
        if recent['close'].iloc[i] > recent['open'].iloc[i]:
            if recent['high'].iloc[i] == recent['high'].iloc[i:i+5].max():
                if recent['close'].iloc[i+1] < recent['low'].iloc[i]:
                    return -1
    return 0


def detect_liquidity_sweep(df, lookback=10):
    """
    Detecta Liquidity Sweep / Stop Hunt (SMC)
    Una vela hace un wick largo que barre liquidez y recupera >70%
    """
    if len(df) < lookback + 3:
        return 0
    recent = df.tail(lookback)
    for i in range(len(recent) - 3, 0, -1):
        candle = recent.iloc[i]
        body = abs(candle['close'] - candle['open'])
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        lower_wick = min(candle['close'], candle['open']) - candle['low']
        total_range = candle['high'] - candle['low']
        if total_range == 0:
            continue
        # Bullish sweep: wick abajo largo, recupera >70%
        if lower_wick > 2 * body and lower_wick > upper_wick:
            recovery = (candle['close'] - candle['low']) / total_range
            if recovery > 0.7:
                return 1
        # Bearish sweep: wick arriba largo, recupera >70%
        if upper_wick > 2 * body and upper_wick > lower_wick:
            recovery = (candle['high'] - candle['close']) / total_range
            if recovery > 0.7:
                return -1
    return 0


def get_htf_trend(df):
    """
    Determina tendencia del timeframe superior usando EMA 50/200
    """
    if len(df) < 200:
        return 0
    u = df.iloc[-1]
    if u['close'] > u['EMA50'] > u['EMA200']:
        return 1
    if u['close'] < u['EMA50'] < u['EMA200']:
        return -1
    return 0


def score_signal(df, htf_trend=0):
    """
    Scoring con confirmacion HTF y Liquidity Sweep
    Score maximo: 8 puntos. Minimo para senal: 5
    """
    u = df.iloc[-1]
    ema50 = u['EMA50']
    ema200 = u['EMA200']
    rsi = u['RSI']
    adx = u['ADX']
    atr = u['ATR']
    vwap = u['VWAP']
    bb_high = u['BB_High']
    bb_low = u['BB_Low']
    price = u['close']
    vol = u['volume']
    avg_vol = df['volume'].rolling(20).mean().iloc[-1]

    # Filtro de volatilidad minima: no operar si ATR < 0.2% del precio
    atr_pct = (atr / price) * 100
    if atr_pct < 0.2:
        return None

    score_buy = 0
    score_sell = 0
    details_buy = []
    details_sell = []

    # === CONFIRMACION HTF (+2 pts si coincide) ===
    if htf_trend == 1:
        score_buy += 2
        details_buy.append('HTF-UP')
    elif htf_trend == -1:
        score_sell += 2
        details_sell.append('HTF-DOWN')

    # === TENDENCIA LTF (+2 pts) ===
    if price > ema50 > ema200:
        score_buy += 2
        details_buy.append('Trend')
    if price < ema50 < ema200:
        score_sell += 2
        details_sell.append('Trend')

    # === LIQUIDITY SWEEP (+2 pts - la confirmacion mas fuerte) ===
    sweep = detect_liquidity_sweep(df)
    if sweep == 1:
        score_buy += 2
        details_buy.append('Sweep')
    elif sweep == -1:
        score_sell += 2
        details_sell.append('Sweep')

    # === ADX (+1 pt) ===
    if adx >= 20:
        score_buy += 1
        score_sell += 1
        details_buy.append('ADX')
        details_sell.append('ADX')

    # === VOLUMEN (+1 pt) ===
    if vol > avg_vol * 1.2:
        score_buy += 1
        score_sell += 1
        details_buy.append('Vol')
        details_sell.append('Vol')

    # === RECHAZO DE VELA (+1 pt) ===
    rej = rejection_candle(u)
    if rej == 'buy':
        score_buy += 1
        details_buy.append('Rechazo')
    elif rej == 'sell':
        score_sell += 1
        details_sell.append('Rechazo')

    # === VWAP (+1 pt) ===
    if abs(price - vwap) / vwap < 0.005:
        score_buy += 1
        score_sell += 1
        details_buy.append('VWAP')
        details_sell.append('VWAP')

    # === RSI (+1 pt) ===
    if rsi < 30:
        score_buy += 1
        details_buy.append('RSI-OS')
    elif rsi > 70:
        score_sell += 1
        details_sell.append('RSI-OB')

    # === BOLLINGER (+1 pt) ===
    if price <= bb_low:
        score_buy += 1
        details_buy.append('BB-Low')
    elif price >= bb_high:
        score_sell += 1
        details_sell.append('BB-High')

    # === DIVERGENCIA RSI (+1 pt) ===
    div = detect_rsi_divergence(df)
    if div == 1:
        score_buy += 1
        details_buy.append('DivRSI')
    elif div == -1:
        score_sell += 1
        details_sell.append('DivRSI')

    # === SMC: FVG (+1 pt) ===
    fvg = detect_fvg(df)
    if fvg == 1:
        score_buy += 1
        details_buy.append('FVG')
    elif fvg == -1:
        score_sell += 1
        details_sell.append('FVG')

    # === SMC: ORDER BLOCK (+1 pt) ===
    ob = detect_order_block(df)
    if ob == 1:
        score_buy += 1
        details_buy.append('OB')
    elif ob == -1:
        score_sell += 1
        details_sell.append('OB')

    # === SCORE MINIMO: 5 de 8 ===
    SCORE_MIN = 5

    if score_buy > score_sell and score_buy >= SCORE_MIN:
        sl = price - atr * float(os.getenv('ATR_SL_MULT', '1.0'))
        tp = price + atr * float(os.getenv('ATR_TP_MULT', '2.0'))
        return {
            'tipo': 'buy',
            'score': score_buy,
            'max_score': 8,
            'details': '+'.join(details_buy),
            'sl': sl,
            'tp': tp,
        }

    if score_sell > score_buy and score_sell >= SCORE_MIN:
        sl = price + atr * float(os.getenv('ATR_SL_MULT', '1.0'))
        tp = price - atr * float(os.getenv('ATR_TP_MULT', '2.0'))
        return {
            'tipo': 'sell',
            'score': score_sell,
            'max_score': 8,
            'details': '+'.join(details_sell),
            'sl': sl,
            'tp': tp,
        }

    return None


def get_setup_name(details, signal_type):
    d = details.split('+')
    if 'Sweep' in d and 'HTF' in ''.join(d):
        return 'Sweep + HTF Confirmado'
    if 'Sweep' in d and 'FVG' in d:
        return 'SMC: Sweep + FVG'
    if 'Sweep' in d and 'OB' in d:
        return 'SMC: Sweep + Order Block'
    if 'Sweep' in d:
        return 'SMC: Liquidity Sweep'
    if 'Trend' in d and 'Rechazo' in d:
        return 'Pullback EMA + Rechazo'
    if 'Trend' in d and 'DivRSI' in d:
        return 'Trend + Divergencia RSI'
    if 'Trend' in d and 'BB' in ''.join(d):
        return 'Trend + Bollinger Bounce'
    if 'DivRSI' in d and 'BB' in ''.join(d):
        return 'Divergencia + Bollinger'
    if 'RSI' in ''.join(d) and 'BB' in ''.join(d):
        return 'RSI + Bollinger Confluence'
    if 'HTF' in ''.join(d) and 'Trend' in d:
        return 'HTF + LTF Alignment'
    if 'Trend' in d and 'ADX' in d:
        return 'Trend Following'
    if 'Rechazo' in d and 'VWAP' in d:
        return 'VWAP Rejection'
    if 'FVG' in d and 'OB' in d:
        return 'SMC: FVG + Order Block'
    if 'FVG' in d:
        return 'SMC: Fair Value Gap'
    if 'OB' in d:
        return 'SMC: Order Block'
    if 'DivRSI' in d:
        return 'Divergencia RSI'
    if 'Trend' in d:
        return 'Trend Continuation'
    return 'Multi-Indicator Confluence'


def get_volatility_label(atr, price):
    pct = (atr / price) * 100
    if pct < 0.3:
        return 'Baja'
    if pct < 0.8:
        return 'Media'
    return 'Alta'


def get_trend_label(price, ema50, ema200):
    if price > ema50 > ema200:
        return 'Alcista'
    if price < ema50 < ema200:
        return 'Bajista'
    return 'Lateral'


def format_signal_pro(symbol_display, signal, price, sl, tp, score, details, atr, timestamp):
    emoji = "\U0001F7E2" if signal == 'buy' else "\U0001F534"
    action = 'LONG' if signal == 'buy' else 'SHORT'
    rr = round(abs(tp - price) / abs(price - sl), 2) if abs(price - sl) > 0 else 0
    sl_pct = round(abs(price - sl) / price * 100, 2)
    tp_pct = round(abs(tp - price) / price * 100, 2)
    max_score = signal.get('max_score', 8)
    bars = '\u2588' * score + '\u2591' * (max_score - score)
    pct = round(score / max_score * 100)
    setup = get_setup_name(details, signal)
    vol_label = get_volatility_label(atr, price)
    time_str = timestamp.strftime('%H:%M') if timestamp else '--:--'

    lines = [
        f'{emoji} {action} | {symbol_display} | {time_str} UTC',
        '\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501',
        f'\U0001F4CA Setup: {setup}',
        f'\U0001F525 Volatilidad: {vol_label}',
        f'\U0001F3AF Confianza: {bars} {pct}%',
        '\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501',
        f'\U0001F4B0 Entrada:  {price:.2f}',
        f'\U0001F6D1 SL:       {sl:.2f} (-{sl_pct}%)',
        f'\U0001F3AF TP:       {tp:.2f} (+{tp_pct}%)',
        f'\U0001F4D0 R:R:      1:{rr}',
        '\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501',
        f'\u26A0\ufe0f Riesgo: 1% | ATR: {atr:.2f}',
        f'\U0001F4A1 "La disciplina es lo que separa a los ganadores del resto."',
    ]
    return '\n'.join(lines)
