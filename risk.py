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


def format_signal_message(symbol_display, signal, price, sl, tp, score, details, atr):
    emoji = "\U0001F7E2 COMPRA (LONG)" if signal == 'buy' else "\U0001F534 VENTA (SHORT)"
    rr = round(abs(tp - price) / abs(price - sl), 2) if abs(price - sl) > 0 else 0

    frases_compra = [
        "\U0001F680 El mercado nos da oportunidad de entrada!",
        "\U0001F4AA Setup limpio, hora de ser preciso.",
        "\U0001F3AF El oro se mueve, aprovechemos con disciplina.",
    ]
    frases_venta = [
        "\U0001F53B Oportunidad de venta detectada!",
        "\U0001F4CA La presion bajista se siente, entremos con cuidado.",
        "\U0001F3AF El mercado cede terreno, vamos con disciplina.",
    ]
    frases = frases_compra if signal == 'buy' else frases_venta
    import random
    frase = random.choice(frases)

    lines = [
        "\U0001F916 ASTABOT 2.0 - Tu asistente de trading \U0001F916",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        f"\U0001FA99 ACTIVO: {symbol_display}",
        f"\U0001F3AF ACCION: {emoji}",
        f"\U0001F4CA SCORE: {score}/6 ({details})",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        f"\U0001F4E5 ENTRADA: {price:.2f}",
        f"\u26D4 STOP LOSS: {sl:.2f}",
        f"\u2705 TAKE PROFIT: {tp:.2f}",
        f"\U0001F4C8 R:R Ratio: 1:{rr}",
        f"\U0001F4C9 ATR: {atr:.2f}",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        frase,
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        "\U0001F6E1\ufe0f Riesgo por operacion: 1% del capital",
        "\U0001F4A1 Recuerda: el SL es tu mejor amigo. Sin excusas.",
        "\U0001F525 La disciplina es lo que separa a los ganadores del resto.",
    ]
    return "\n".join(lines)
