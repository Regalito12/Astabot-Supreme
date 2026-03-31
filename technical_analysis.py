"""
AstaBot 2.0 - Indicadores tecnicos y sistema de scoring
EMA 50/200, RSI, ADX, Bollinger, ATR, VWAP
Sistema de scoring 0-6 puntos
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


def score_signal(df):
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

    score_buy = 0
    score_sell = 0
    details_buy = []
    details_sell = []

    if price > ema50 > ema200:
        score_buy += 2
        details_buy.append('Trend')
    if price < ema50 < ema200:
        score_sell += 2
        details_sell.append('Trend')

    if adx >= 20:
        score_buy += 1
        score_sell += 1
        details_buy.append('ADX')
        details_sell.append('ADX')

    if vol > avg_vol * 1.2:
        score_buy += 1
        score_sell += 1
        details_buy.append('Vol')
        details_sell.append('Vol')

    rej = rejection_candle(u)
    if rej == 'buy':
        score_buy += 1
        details_buy.append('Rechazo')
    elif rej == 'sell':
        score_sell += 1
        details_sell.append('Rechazo')

    if abs(price - vwap) / vwap < 0.005:
        score_buy += 1
        score_sell += 1
        details_buy.append('VWAP')
        details_sell.append('VWAP')

    if rsi < 30:
        score_buy += 1
        details_buy.append('RSI-OS')
    elif rsi > 70:
        score_sell += 1
        details_sell.append('RSI-OB')

    if price <= bb_low:
        score_buy += 1
        details_buy.append('BB-Low')
    elif price >= bb_high:
        score_sell += 1
        details_sell.append('BB-High')

    div = detect_rsi_divergence(df)
    if div == 1:
        score_buy += 1
        details_buy.append('DivRSI')
    elif div == -1:
        score_sell += 1
        details_sell.append('DivRSI')

    if score_buy > score_sell and score_buy >= 4:
        sl = price - atr * float(os.getenv('ATR_SL_MULT', '1.0'))
        tp = price + atr * float(os.getenv('ATR_TP_MULT', '2.0'))
        return {
            'tipo': 'buy',
            'score': score_buy,
            'details': '+'.join(details_buy),
            'sl': sl,
            'tp': tp,
        }

    if score_sell > score_buy and score_sell >= 4:
        sl = price + atr * float(os.getenv('ATR_SL_MULT', '1.0'))
        tp = price - atr * float(os.getenv('ATR_TP_MULT', '2.0'))
        return {
            'tipo': 'sell',
            'score': score_sell,
            'details': '+'.join(details_sell),
            'sl': sl,
            'tp': tp,
        }

    return None
