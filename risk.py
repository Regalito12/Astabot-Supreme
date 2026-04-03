"""
AstaBot 2.0 - Gestion de riesgo
SL/TP basado en ATR, calculo de posicion, log de senales
"""
import csv
import os
from datetime import datetime, timezone
from config_v2 import RISK_PER_TRADE, SIGNAL_LOG_FILE


def calculate_position_size(capital, entry, sl):
    risk_amount = capital * RISK_PER_TRADE
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return 0
    return risk_amount / sl_distance


def log_signal(signal_type, price, sl, tp, score, details, atr):
    file_exists = os.path.exists(SIGNAL_LOG_FILE)
    with open(SIGNAL_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['timestamp', 'type', 'price', 'sl', 'tp', 'score', 'details', 'atr'])
        writer.writerow([
            datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            signal_type,
            f'{price:.2f}',
            f'{sl:.2f}',
            f'{tp:.2f}',
            score,
            details,
            f'{atr:.2f}',
        ])


def format_signal_message(symbol_display, signal, price, sl, tp, score, details, atr, timestamp=None):
    from technical_analysis import format_signal_pro
    return format_signal_pro(symbol_display, signal, price, sl, tp, score, details, atr, timestamp)
