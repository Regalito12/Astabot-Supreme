"""
AstaBot 2.0 - Bot principal simplificado
Solo indicadores tecnicos. Sin ML. Sin autotrading.
Multi-par: XAU/USD + BTC/USD.
Features: Simulador PnL, Alertas de Sesion, Resumen Matutino.
"""
import os
import random
import csv
import json
import logging
import threading
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config_v2 import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS,
    INTERVAL, CANDLE_COUNT, SCORE_MIN, SCAN_INTERVAL_MINUTES,
    COOLDOWN_MINUTES, SPREAD_MAX_PIPS, SIGNAL_LOG_FILE,
    NEWS_ALERT_MINUTES, N8N_WEBHOOK_URL,
    WEEKEND_ALERT_HOUR, WEEKEND_ALERT_DAY,
    BRIEFING_HOUR, BRIEFING_MINUTE, SESSIONS,
)
from technical_analysis import apply_indicators, score_signal
from risk import format_signal_message, log_signal
from news_filter import get_upcoming_events, format_news_alert

logging.basicConfig(
    level=logging.INFO,
    format="{asctime} - {name} - {levelname} - {message}",
    style="{",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_last_signals = {}
_alerted_news = set()
_weekend_sent = False
_pnl_file = "pnl_tracker.json"
_briefing_sent = False
_session_alerted = None


def load_pnl_tracker():
    if os.path.exists(_pnl_file):
        try:
            with open(_pnl_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"trades": [], "daily_pnl": {}}


def save_pnl_tracker(data):
    with open(_pnl_file, "w") as f:
        json.dump(data, f, indent=2)


def add_trade_to_pnl(signal):
    tracker = load_pnl_tracker()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trade = {
        "id": len(tracker["trades"]) + 1,
        "date": today,
        "time": datetime.now(timezone.utc).strftime("%H:%M"),
        "symbol": signal["symbol"],
        "type": signal["tipo"],
        "entry": signal["price"],
        "sl": signal["sl"],
        "tp": signal["tp"],
        "score": signal["score"],
        "status": "open",
        "pnl": 0,
    }
    tracker["trades"].append(trade)
    save_pnl_tracker(tracker)
    return trade


def check_open_trades():
    tracker = load_pnl_tracker()
    results = []
    for trade in tracker["trades"]:
        if trade["status"] != "open":
            continue
        try:
            url = "https://api.twelvedata.com/price"
            resp = requests.get(
                url,
                params={"symbol": trade["symbol"], "apikey": os.getenv("TWELVE_API_KEY", "")},
                timeout=10,
            )
            data = resp.json()
            current_price = float(data.get("price", 0))
            if current_price == 0:
                continue

            if trade["type"] == "buy":
                pnl = current_price - trade["entry"]
                if current_price >= trade["tp"]:
                    trade["status"] = "win"
                    trade["exit"] = trade["tp"]
                    trade["pnl"] = round(pnl, 2)
                    results.append(trade)
                elif current_price <= trade["sl"]:
                    trade["status"] = "loss"
                    trade["exit"] = trade["sl"]
                    trade["pnl"] = round(pnl, 2)
                    results.append(trade)
            else:
                pnl = trade["entry"] - current_price
                if current_price <= trade["tp"]:
                    trade["status"] = "win"
                    trade["exit"] = trade["tp"]
                    trade["pnl"] = round(pnl, 2)
                    results.append(trade)
                elif current_price >= trade["sl"]:
                    trade["status"] = "loss"
                    trade["exit"] = trade["sl"]
                    trade["pnl"] = round(pnl, 2)
                    results.append(trade)
        except Exception:
            continue

    if results:
        save_pnl_tracker(tracker)
    return results


def get_daily_pnl_summary():
    tracker = load_pnl_tracker()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_trades = [t for t in tracker["trades"] if t["date"] == today and t["status"] != "open"]
    wins = [t for t in today_trades if t["status"] == "win"]
    losses = [t for t in today_trades if t["status"] == "loss"]
    open_trades = [t for t in tracker["trades"] if t["date"] == today and t["status"] == "open"]
    total_pnl = sum(t["pnl"] for t in today_trades)
    return {
        "total": len(today_trades),
        "wins": len(wins),
        "losses": len(losses),
        "open": len(open_trades),
        "pnl": round(total_pnl, 2),
        "win_rate": round(len(wins) / len(today_trades) * 100, 1) if today_trades else 0,
    }


def get_current_session():
    now = datetime.now(timezone.utc)
    hour = now.hour
    for key, sess in SESSIONS.items():
        if sess["start"] <= hour < sess["end"]:
            return sess
    return SESSIONS["cierre"]


def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_flask, daemon=True).start()


@app.route("/")
def home():
    return "AstaBot 2.0 Online"


@app.route("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


def get_cooldown_key(symbol, tipo):
    return f"{symbol}_{tipo}"


def check_cooldown(symbol, tipo, price):
    key = get_cooldown_key(symbol, tipo)
    if key not in _last_signals:
        return True
    last = _last_signals[key]
    if last['tipo'] != tipo:
        return True
    elapsed = datetime.now(timezone.utc) - last['timestamp']
    if elapsed >= timedelta(minutes=COOLDOWN_MINUTES):
        return True
    price_change = abs(price - last['price']) / last['price']
    if price_change >= 0.005:
        return True
    return False


def register_signal(symbol, tipo, price):
    key = get_cooldown_key(symbol, tipo)
    _last_signals[key] = {
        'tipo': tipo,
        'timestamp': datetime.now(timezone.utc),
        'price': price,
    }


def check_spread(symbol):
    api_key = os.getenv("TWELVE_API_KEY", "")
    if not api_key:
        return True
    try:
        url = "https://api.twelvedata.com/price"
        resp = requests.get(url, params={"symbol": symbol, "apikey": api_key}, timeout=10)
        data = resp.json()
        if "ask" in data and "bid" in data:
            spread_pips = (data["ask"] - data["bid"]) * 10
            if spread_pips > SPREAD_MAX_PIPS:
                logger.warning(f"Spread alto en {symbol}: {spread_pips:.1f} pips")
                return False
        return True
    except Exception as e:
        logger.warning(f"No se pudo verificar spread en {symbol}: {e}")
        return True


def fetch_candles(symbol):
    api_key = os.getenv("TWELVE_API_KEY", "")
    if not api_key:
        logger.error("Falta TWELVE_API_KEY")
        return None

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "outputsize": CANDLE_COUNT,
        "apikey": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "values" not in data or not data["values"]:
            logger.warning(f"Sin datos de Twelve Data para {symbol}: {data.get('message', '')}")
            return None

        df = pd.DataFrame(data["values"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        return df
    except Exception as e:
        logger.error(f"Error fetching candles para {symbol}: {e}")
        return None


def analyze_pair(pair_config):
    symbol = pair_config["symbol"]
    if not check_spread(symbol):
        logger.info(f"Spread alto en {symbol}, saltando")
        return None

    df = fetch_candles(symbol)
    if df is None or len(df) < 50:
        logger.warning(f"Datos insuficientes para {symbol}")
        return None

    df = apply_indicators(df)
    signal = score_signal(df)

    if signal is None:
        logger.info(f"Sin senal en {symbol} (score < 4)")
        return None

    u = df.iloc[-1]
    signal["price"] = u["close"]
    signal["atr"] = u["ATR"]
    signal["symbol"] = symbol
    signal["symbol_display"] = pair_config["display"]

    atr_sl = pair_config.get("atr_sl", 1.0)
    atr_tp = pair_config.get("atr_tp", 2.0)
    if signal["tipo"] == "buy":
        signal["sl"] = signal["price"] - signal["atr"] * atr_sl
        signal["tp"] = signal["price"] + signal["atr"] * atr_tp
    else:
        signal["sl"] = signal["price"] + signal["atr"] * atr_sl
        signal["tp"] = signal["price"] - signal["atr"] * atr_tp

    if not check_cooldown(symbol, signal["tipo"], signal["price"]):
        logger.info(f"Cooldown activo para {symbol} {signal['tipo']}")
        return None

    return signal


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    frases = [
        "\U0001F44B Hola! Soy AstaBot 2.0, tu asistente de trading.",
        "\U0001F44B Bienvenido de vuelta! AstaBot 2.0 listo para operar.",
        "\U0001F916 AstaBot 2.0 activo y analizando el mercado.",
    ]
    pairs_list = "\n".join([f"\u2022 {p['display']}" for p in SYMBOLS])
    text = (
        f"{random.choice(frases)}\n\n"
        f"Analizo {len(SYMBOLS)} pares:\n{pairs_list}\n\n"
        "Sin emociones, sin sobreoperar. Solo senales basadas en datos.\n\n"
        "\U0001F4CB *Comandos disponibles:*\n"
        "/senal - Analiza todos los pares ahora\n"
        "/senal XAUUSD - Analiza solo el Oro\n"
        "/senal BTCUSD - Analiza solo Bitcoin\n"
        "/pnl - Simulador de ganancias/perdidas\n"
        "/status - Mi estado actual\n"
        "/historial - Ultimas 10 senales\n"
        "/noticias - Noticias USD que mueven el mercado\n\n"
        "\U0001F4A1 *Recuerda:* El SL no es negociable. La disciplina es tu mejor arma."
    )
    await update.message.reply_markdown(text)


async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    frases_analizando = [
        "\U0001F50D Analizando el mercado... un momento.",
        "\U0001F4CA Escaneando indicadores... espera.",
        "\U0001F916 Revisando los graficos... dame un segundo.",
    ]
    await update.message.reply_text(random.choice(frases_analizando))

    pair_filter = None
    if context.args:
        arg = context.args[0].upper().replace("/", "")
        for p in SYMBOLS:
            if p["symbol"].upper().replace("/", "") == arg:
                pair_filter = p
                break
        if not pair_filter:
            await update.message.reply_text(
                f"\u274C Par no reconocido. Usa: {', '.join([p['symbol'] for p in SYMBOLS])}"
            )
            return

    pairs_to_check = [pair_filter] if pair_filter else SYMBOLS
    signals_found = 0

    for pair in pairs_to_check:
        signal = analyze_pair(pair)
        if signal is None:
            continue

        signals_found += 1
        register_signal(signal["symbol"], signal["tipo"], signal["price"])
        log_signal(
            signal["tipo"], signal["price"], signal["sl"],
            signal["tp"], signal["score"], signal["details"], signal["atr"],
        )
        add_trade_to_pnl(signal)
        send_to_n8n(signal)

        msg = format_signal_message(
            signal["symbol_display"],
            signal["tipo"],
            signal["price"],
            signal["sl"],
            signal["tp"],
            signal["score"],
            signal["details"],
            signal["atr"],
        )
        await update.message.reply_text(msg)

    if signals_found == 0:
        frases_no = [
            "\U0001F60C Tranquilo, no hay setup claro ahora. Paciencia es clave en trading.",
            "\U0001F440 El mercado no esta dando senal valida. Mejor esperar que perder.",
            "\U0001F6AB Sin senal por ahora. A veces no operar ES operar.",
        ]
        await update.message.reply_text(random.choice(frases_no))


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    closed = check_open_trades()
    for trade in closed:
        emoji = "\U0001F7E2" if trade["status"] == "win" else "\U0001F534"
        resultado = "GANADA" if trade["status"] == "win" else "PERDIDA"
        msg = (
            f"{emoji} Trade #{trade['id']} cerrado: {resultado}\n"
            f"{trade['symbol']} {trade['type'].upper()}\n"
            f"Entrada: {trade['entry']} | Salida: {trade['exit']}\n"
            f"PnL: {trade['pnl']:+.2f}"
        )
        await update.message.reply_text(msg)

    summary = get_daily_pnl_summary()
    pnl_emoji = "\U0001F7E2" if summary["pnl"] >= 0 else "\U0001F534"
    msg = (
        f"\U0001F4CA *Resumen del Simulador (Hoy)*\n\n"
        f"{pnl_emoji} *PnL:* {summary['pnl']:+.2f}\n"
        f"\U0001F4C8 *Trades cerrados:* {summary['total']}\n"
        f"\U0001F7E2 Ganadas: {summary['wins']} | \U0001F534 Perdidas: {summary['losses']}\n"
        f"\u23F3 Abiertas: {summary['open']}\n"
        f"\U0001F4CA *Win Rate:* {summary['win_rate']}%\n\n"
        "\U0001F4A1 *Simulacion:* Si hubieras seguido todas las senales con 1% de riesgo."
    )
    await update.message.reply_markdown(msg)


async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(SIGNAL_LOG_FILE):
        await update.message.reply_text("\U0001F4ED Todavia no hay senales. Paciencia, el mercado premia a quien sabe esperar.")
        return

    try:
        df = pd.read_csv(SIGNAL_LOG_FILE)
        if df.empty:
            await update.message.reply_text("\U0001F4ED Todavia no hay senales. Paciencia, el mercado premia a quien sabe esperar.")
            return

        last10 = df.tail(10)
        buys = len(df[df['type'] == 'buy'])
        sells = len(df[df['type'] == 'sell'])
        avg_score = df['score'].mean()

        lines = [
            "\U0001F4C8 *Tu Historial de Trading*\n",
            f"\U0001F4CA Total senales: {len(df)}",
            f"\U0001F7E2 Compras: {buys} | \U0001F534 Ventas: {sells}",
            f"\U0001F4CA Score promedio: {avg_score:.1f}/6\n",
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        ]
        for _, row in last10.iterrows():
            ts = str(row['timestamp'])[:16].replace('T', ' ')
            tipo = "\U0001F7E2 BUY" if row['type'] == 'buy' else "\U0001F534 SELL"
            lines.append(
                f"\u2022 {ts}\n"
                f"  {tipo} | Score: {row['score']}\n"
                f"  Entrada: {row['price']} | SL: {row['sl']} | TP: {row['tp']}"
            )

        lines.append("\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
        lines.append("\U0001F4A1 Recuerda llenar resultado y PnL en tu Google Sheet!")

        await update.message.reply_markdown("\n".join(lines))
    except Exception as e:
        logger.error(f"Error leyendo historial: {e}")
        await update.message.reply_text(f"Error al leer historial: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    session = get_current_session()

    try:
        news_events = get_upcoming_events(NEWS_ALERT_MINUTES)
        news_count = len(news_events)
    except Exception:
        news_count = 0

    cooldown_info = []
    for key, last in _last_signals.items():
        elapsed = datetime.now(timezone.utc) - last['timestamp']
        remaining = COOLDOWN_MINUTES - elapsed.total_seconds() / 60
        rem = max(0, int(remaining))
        cooldown_info.append(f"  {key}: {rem} min")

    frases_estado = [
        "\U0001F916 Todo listo para la accion!",
        "\U0001F4AA AstaBot trabajando duro por ti.",
        "\U0001F525 Sistema operativo y listo.",
    ]

    pairs_display = "\n".join([f"  \u2022 {p['display']}" for p in SYMBOLS])

    await update.message.reply_text(
        f"{random.choice(frases_estado)}\n\n"
        f"{session['emoji']} *Sesion actual:* {session['name']}\n"
        f"\U0001FA99 *Pares activos:*\n{pairs_display}\n"
        f"\u23F0 *Horario:* 24/7 (Lun-Vie)\n"
        f"\U0001F550 *Hora actual:* {now.strftime('%H:%M')} UTC\n"
        f"\U0001F504 *Scan automatico:* cada {SCAN_INTERVAL_MINUTES} min\n"
        f"\U0001F6E1\ufe0f *Cooldown:* {COOLDOWN_MINUTES} min\n"
        f"\U0001F4F0 *Alerta noticias:* {NEWS_ALERT_MINUTES} min antes\n"
        f"\U0001F4CA *Noticias USD proximas:* {news_count}\n"
        f"\u23F3 *Cooldowns:*\n" + ("\n".join(cooldown_info) if cooldown_info else "  Ninguno activo")
    )


async def cmd_noticias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\U0001F50D Buscando noticias USD de alto impacto...")
    try:
        events = get_upcoming_events(60)
        if not events:
            await update.message.reply_text(
                "\u2705 No hay noticias USD de alto impacto en la proxima hora."
            )
            return
        for event in events:
            msg = format_news_alert(event)
            await update.message.reply_markdown(msg)
    except Exception as e:
        logger.error(f"Error buscando noticias: {e}")
        await update.message.reply_text(f"Error al buscar noticias: {e}")


async def check_news_alerts(context: ContextTypes.DEFAULT_TYPE):
    global _weekend_sent, _briefing_sent, _session_alerted
    try:
        events = get_upcoming_events(NEWS_ALERT_MINUTES)
        for event in events:
            event_key = f"{event['name']}_{event['date'].strftime('%Y%m%d%H%M')}"
            if event_key in _alerted_news:
                continue
            _alerted_news.add(event_key)
            msg = format_news_alert(event)
            try:
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                logger.info(f"Alerta de noticia enviada: {event['name']}")
            except Exception as e:
                logger.error(f"Error enviando alerta: {e}")
    except Exception as e:
        logger.error(f"Error en check_news_alerts: {e}")

    now = datetime.now(timezone.utc)

    if now.weekday() == WEEKEND_ALERT_DAY and now.hour == WEEKEND_ALERT_HOUR:
        if not _weekend_sent:
            _weekend_sent = True
            msg = (
                "\U0001F6A8 *ALERTA FIN DE SEMANA* \U0001F6A8\n\n"
                "\u26A0\ufe0f Son las 20:00 UTC del Viernes.\n"
                "Los mercados cierran pronto.\n\n"
                "\U0001F449 *Cierra todas tus posiciones abiertas.*\n"
                "\U0001F449 No dejes operaciones abiertas al fin de semana.\n\n"
                "\U0001F60E Descansa, recarga energias y vuelve el Lunes con disciplina.\n"
                "\U0001F4AA El trading es una maratón, no un sprint."
            )
            try:
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
                logger.info("Alerta de fin de semana enviada")
            except Exception as e:
                logger.error(f"Error enviando alerta fin de semana: {e}")
    elif now.weekday() != WEEKEND_ALERT_DAY or now.hour != WEEKEND_ALERT_HOUR:
        _weekend_sent = False

    if now.hour == BRIEFING_HOUR and now.minute >= BRIEFING_MINUTE and now.minute < BRIEFING_MINUTE + 5:
        if not _briefing_sent:
            _briefing_sent = True
            await send_morning_briefing(context)
    elif now.hour != BRIEFING_HOUR:
        _briefing_sent = False

    current_session = get_current_session()
    session_key = f"{current_session['name']}_{now.strftime('%Y-%m-%d')}"
    if _session_alerted != session_key:
        _session_alerted = session_key
        if current_session["name"] == "Nueva York":
            msg = (
                f"{current_session['emoji']} *SESION DE NUEVA YORK ABIERTA*\n\n"
                "\U0001F5FD El volumen sube. Los movimientos seran mas fuertes.\n"
                "\U0001F4CA Presta atencion a las noticias de las 13:30 UTC.\n"
                "\U0001F6E1\ufe0f Usa stops mas ajustados. La volatilidad es tu amiga y tu enemiga."
            )
            try:
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
                logger.info("Alerta sesion NY enviada")
            except Exception:
                pass
        elif current_session["name"] == "Londres":
            msg = (
                f"{current_session['emoji']} *SESION DE LONDRES ABIERTA*\n\n"
                "\U0001F3DB\ufe0f El mercado despierta. Empiezan los movimientos reales.\n"
                "\U0001F4CA Buena hora para buscar setups en el Oro.\n"
                "\U0001F50D AstaBot esta escaneando activamente."
            )
            try:
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
                logger.info("Alerta sesion Londres enviada")
            except Exception:
                pass


async def send_morning_briefing(context):
    session = {"emoji": "\U0001F305", "name": "Amanecer"}
    now = datetime.now(timezone.utc)

    prices = {}
    for p in SYMBOLS:
        try:
            url = "https://api.twelvedata.com/price"
            resp = requests.get(
                url,
                params={"symbol": p["symbol"], "apikey": os.getenv("TWELVE_API_KEY", "")},
                timeout=10,
            )
            data = resp.json()
            prices[p["display"]] = data.get("price", "N/A")
        except Exception:
            prices[p["display"]] = "N/A"

    news_count = 0
    try:
        events = get_upcoming_events(480)
        news_count = len(events)
    except Exception:
        pass

    summary = get_daily_pnl_summary()

    frases = [
        "\U0001F305 *Buenos dias! AstaBot 2.0 te da los buenos dias.*",
        "\U0001F305 *Nuevo dia, nuevas oportunidades.*",
        "\U0001F305 *El mercado abrio. Vamos con todo.*",
    ]

    price_lines = "\n".join([f"  \U0001FA99 {k}: ${v}" for k, v in prices.items()])

    tracker = load_pnl_tracker()
    all_closed = [t for t in tracker["trades"] if t["status"] != "open"]
    all_wins = [t for t in all_closed if t["status"] == "win"]
    all_losses = [t for t in all_closed if t["status"] == "loss"]
    total_pnl_all = sum(t["pnl"] for t in all_closed)
    total_wr = round(len(all_wins) / len(all_closed) * 100, 1) if all_closed else 0

    msg = (
        f"{random.choice(frases)}\n\n"
        f"\U0001F550 Hora: {now.strftime('%H:%M')} UTC\n"
        f"\U0001F4CA Precios actuales:\n{price_lines}\n\n"
        f"\U0001F4F0 Noticias USD hoy: {news_count}\n"
        f"\U0001F4CA Trades totales cerrados: {len(all_closed)}\n"
        f"\U0001F7E2 Ganadas: {len(all_wins)} | \U0001F534 Perdidas: {len(all_losses)}\n"
        f"\U0001F4CA PnL acumulado: {total_pnl_all:+.2f} | Win Rate: {total_wr}%\n\n"
        "\U0001F4AA Hoy es un nuevo dia para ser disciplinado.\n"
        "\U0001F6E1\ufe0f Respeta el plan. Confia en el proceso."
    )
    try:
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        logger.info("Resumen matutino enviado")
    except Exception as e:
        logger.error(f"Error enviando resumen matutino: {e}")


def send_to_n8n(signal):
    if not N8N_WEBHOOK_URL:
        return
    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": signal["symbol"],
        "type": signal["tipo"],
        "price": signal["price"],
        "sl": signal["sl"],
        "tp": signal["tp"],
        "score": signal["score"],
        "details": signal["details"],
        "atr": signal["atr"],
    }
    try:
        resp = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Senal enviada a n8n (Trade Journal)")
        else:
            logger.warning(f"n8n respondio {resp.status_code}")
    except Exception as e:
        logger.error(f"Error enviando a n8n: {e}")


async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    logger.info("--- Auto scan multi-par ---")
    for pair in SYMBOLS:
        signal = analyze_pair(pair)
        if signal:
            register_signal(signal["symbol"], signal["tipo"], signal["price"])
            log_signal(
                signal["tipo"], signal["price"], signal["sl"],
                signal["tp"], signal["score"], signal["details"], signal["atr"],
            )
            add_trade_to_pnl(signal)
            send_to_n8n(signal)
            msg = format_signal_message(
                signal["symbol_display"],
                signal["tipo"],
                signal["price"],
                signal["sl"],
                signal["tp"],
                signal["score"],
                signal["details"],
                signal["atr"],
            )
            try:
                await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                logger.info(f"Senal enviada a Telegram: {signal['symbol']}")
            except Exception as e:
                logger.error(f"Error enviando a Telegram: {e}")


def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("senal", cmd_signal))
    application.add_handler(CommandHandler("analizar", cmd_signal))
    application.add_handler(CommandHandler("pnl", cmd_pnl))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("historial", cmd_historial))
    application.add_handler(CommandHandler("noticias", cmd_noticias))

    scan_seconds = SCAN_INTERVAL_MINUTES * 60
    application.job_queue.run_repeating(auto_scan, interval=scan_seconds, first=10)
    logger.info(f"Auto scan cada {SCAN_INTERVAL_MINUTES} min para {len(SYMBOLS)} pares")

    application.job_queue.run_repeating(check_news_alerts, interval=300, first=60)
    logger.info(f"Alertas cada 5 min (noticias, sesiones, briefing)")

    logger.info("AstaBot 2.0 iniciado")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
