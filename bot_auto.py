# bot_auto.py
import logging
import sys
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import telegram
from datetime import datetime

# --- Setup de Logging Centralizado ---
def setup_logging():
    """Configura el logging para consola y archivo, filtrando ruido."""
    log_format = "{asctime} - {name:<20} - {levelname:<8} - {message}"
    formatter = logging.Formatter(log_format, style='{')

    # Configurar el logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Cambiado a INFO para menos ruido
    # Limpiar handlers existentes para evitar duplicados
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Handler para la consola
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Handler para el archivo
    log_dir = "logs_astabot"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_handler = logging.FileHandler(f"{log_dir}/trading_bot.log", mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Silenciar loggers de librerías muy verbosas
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("telegram.ext").setLevel(logging.ERROR)
    logging.getLogger("telegram.bot").setLevel(logging.ERROR)
    logging.getLogger("apscheduler").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("peewee").setLevel(logging.ERROR)
    logging.getLogger("yfinance").setLevel(logging.ERROR)

    # Integración básica con Sentry (placeholder - instala sentry-sdk si usas)
    # import sentry_sdk
    # sentry_sdk.init(dsn="YOUR_SENTRY_DSN", traces_sample_rate=1.0)

# Llamar a la configuración ANTES de importar cualquier otro módulo
# setup_logging() sera llamado en main()

from config import TELEGRAM_TOKEN, SUPPORTED_ASSETS, reload_config, params
from analizador_oro import analizar_mercado, job, mercado_abierto
from backtesting import run_backtest
from errors import AstabotError, notify_critical_error, retry_on_failure
from realtime_streaming import start_streaming, stop_all_streaming
from reinforcement_learning import load_rl_model
from gamification import gamification
from risk_manager import risk_manager # --- NUEVO: Gestor de Riesgos ---
from models import init_db # --- NUEVO: Inicializador de DB ---

# Inicializar mejoras avanzadas
# load_rl_model() sera llamado en main()

# --- Modificación para paralelizar análisis de activos ---
import asyncio

async def initialize_streaming():
    for symbol in SUPPORTED_ASSETS:
        start_streaming(symbol)

# Llamar a la función asíncrona
# loop = asyncio.get_event_loop()
# loop.run_until_complete(initialize_streaming())

logger = logging.getLogger(__name__)

# --- Definición de Teclados ---
reply_markup = ReplyKeyboardMarkup([['/analizar', '/status'], ['/risk', '/backtest'], ['/config', '/historial']], resize_keyboard=True)

# --- Handlers de Comandos de Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "¡Hola! Soy Astabot. /analizar (manual), /backtest (histórico), /config (ajustes), /historial, /estadisticas."
    
    # Check Kill Switch
    if risk_manager.is_forced_active():
        text = "🛑 CIRCUIT BREAKER ACTIVO. El bot está detenido por seguridad debido a pérdidas diarias."
    elif not mercado_abierto():
        text = "📴 Mercado cerrado. El análisis automático está en pausa."
        
    await update.message.reply_text(text, reply_markup=reply_markup)

async def analizar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check Kill Switch before manual analysis
    if risk_manager.is_forced_active():
        await update.message.reply_text("🛑 No se puede analizar: El Circuit Breaker está ACTIVO para proteger tu capital.")
        return

    buttons = [
        [InlineKeyboardButton(text=name, callback_data=symbol)]
        for symbol, name in SUPPORTED_ASSETS.items()
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Selecciona un activo para analizar:", reply_markup=keyboard)

async def asset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    symbol = query.data
    await query.answer(f"Analizando {symbol}...")

    logger.info(f"Ejecutando análisis manual para {symbol}...")
    loop = asyncio.get_running_loop()
    resultado = await loop.run_in_executor(None, analizar_mercado, symbol, True)
    logger.info(f"Resultado del análisis para {symbol}: {resultado}")

    text_response = ""
    if isinstance(resultado, dict):
        if "message" in resultado:
            text_response = resultado["message"]
        else:
            import random
            frases = [
                "¡El mercado provee, tú pones la disciplina! 🧠💪",
                "Paciencia, gestión de riesgo y ejecución fría. Let's go! 🚀",
                "Los grandes traders no adivinan, reaccionan. ¡A cazar pips! 💰",
                "Un trader supremo protege su capital antes de atacar. 🛡️",
                "¡Concéntrate en el proceso, los profits llegarán solos! 📈✨"
            ]
            emoji_tipo = "🟢 COMPRA (LONG)" if resultado.get('tipo', '').lower() == 'buy' else "🔴 VENTA (SHORT)"
            desc_asset = SUPPORTED_ASSETS.get(symbol, symbol)
            
            mensaje = [
                "⚡ 𝐀𝐒𝐓𝐀𝐁𝐎𝐓 𝐒𝐔𝐏𝐑𝐄𝐌𝐄 (𝗠𝗮𝗻𝘂𝗮𝗹) ⚡",
                "━━━━━━━━━━━━━━━━━━",
                f"🪙 ACTIVO: {desc_asset}",
                f"🎯 ACCIÓN: {emoji_tipo}",
                f"📊 CONFIANZA: {resultado.get('confianza', 'N/A')} 💎",
                "━━━━━━━━━━━━━━━━━━",
                f"📥 ENTRADA (ENTRY): {resultado.get('price', 0):.4f}",
                f"⛔ STOP LOSS (SL): {resultado.get('sl', 0):.4f}",
                f"✅ TAKE PROFIT (TP): {resultado.get('tp', 0):.4f}",
                "━━━━━━━━━━━━━━━━━━",
                f"🧠 Análisis M.L: {resultado.get('regime', 'N/A')}",
                f"🪤 Trampas Ocultas: {resultado.get('trap_signal', 'None') or 'Ninguna'}",
                f"💰 Tamaño Riesgo: {resultado.get('position_size', 0):.4f}",
                "",
                f"💡 Astabot dice:\n«{random.choice(frases)}»"
            ]
            text_response = "\n".join(mensaje)

            # --- Nueva sección: Botones de ajuste SL/TP ---
            sl_tp_buttons = [
                [InlineKeyboardButton("Ajustar SL", callback_data=f"adjust_sl_{symbol}"),
                 InlineKeyboardButton("Ajustar TP", callback_data=f"adjust_tp_{symbol}")]
            ]
            keyboard = InlineKeyboardMarkup(sl_tp_buttons)

            await query.edit_message_text(text=text_response, reply_markup=keyboard)

            # --- Notificación de logros gamificación ---
            user_id = update.effective_user.id
            stats = resultado.get("stats", {})
            unlocked = gamification.check_achievements(user_id, stats)
            if unlocked:
                achievement_messages = [gamification.achievements[a]['description'] for a in unlocked]
                achievement_text = "\n".join([f"🏆 Logro desbloqueado: {msg}" for msg in achievement_messages])
                await context.bot.send_message(chat_id=user_id, text=achievement_text)

    elif isinstance(resultado, str):
        text_response = resultado
    else:
        text_response = f"⏳ No se encontró una señal clara para {symbol} en este momento."

    await query.edit_message_text(text=text_response)

async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"backtest_{symbol}")]
        for symbol, name in SUPPORTED_ASSETS.items()
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Selecciona un activo para backtesting histórico:", reply_markup=keyboard)

async def backtest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    try:
        if data.startswith("backtest_"):
            symbol = data.replace("backtest_", "")
            capital_buttons = [
                [InlineKeyboardButton("$1,000", callback_data=f"capital_1000_{symbol}"),
                 InlineKeyboardButton("$5,000", callback_data=f"capital_5000_{symbol}")],
                [InlineKeyboardButton("$10,000", callback_data=f"capital_10000_{symbol}"),
                 InlineKeyboardButton("$50,000", callback_data=f"capital_50000_{symbol}")]
            ]
            keyboard = InlineKeyboardMarkup(capital_buttons)
            await query.edit_message_text(f"Selecciona capital inicial para {SUPPORTED_ASSETS.get(symbol, symbol)}:", reply_markup=keyboard)

        elif data.startswith("capital_"):
            _, capital_str, symbol = data.split("_", 2)
            capital = int(capital_str)
            period_buttons = [
                [InlineKeyboardButton("3 Meses", callback_data=f"period_3mo_{capital}_{symbol}"),
                 InlineKeyboardButton("6 Meses", callback_data=f"period_6mo_{capital}_{symbol}")],
                [InlineKeyboardButton("1 Año", callback_data=f"period_1y_{capital}_{symbol}"),
                 InlineKeyboardButton("2 Años", callback_data=f"period_2y_{capital}_{symbol}")]
            ]
            keyboard = InlineKeyboardMarkup(period_buttons)
            await query.edit_message_text(f"Selecciona período para {SUPPORTED_ASSETS.get(symbol, symbol)} (Capital: ${capital:,}):", reply_markup=keyboard)

        elif data.startswith("period_"):
            _, period, capital_str, symbol = data.split("_", 3)
            capital = int(capital_str)
            interval_buttons = [
                [InlineKeyboardButton("5 Min", callback_data=f"interval_5min_{period}_{capital}_{symbol}"),
                 InlineKeyboardButton("15 Min", callback_data=f"interval_15min_{period}_{capital}_{symbol}")],
                [InlineKeyboardButton("1 Hora", callback_data=f"interval_1h_{period}_{capital}_{symbol}"),
                 InlineKeyboardButton("1 Día", callback_data=f"interval_1d_{period}_{capital}_{symbol}")]
            ]
            keyboard = InlineKeyboardMarkup(interval_buttons)
            await query.edit_message_text(f"Selecciona intervalo para {SUPPORTED_ASSETS.get(symbol, symbol)} ({period.replace('_', ' ')}, Capital: ${capital:,}):", reply_markup=keyboard)

        elif data.startswith("interval_"):
            _, interval, period, capital_str, symbol = data.split("_", 4)
            capital = int(capital_str)
            
            try:
                await query.answer(f"Ejecutando backtest para {symbol}...")
            except telegram.error.BadRequest as e:
                if "Query is too old" in str(e) or "timeout expired" in str(e):
                    logger.warning(f"Query timeout para {symbol}, ignorando.")
                    return
                else:
                    raise

            logger.info(f"Iniciando backtest para {symbol} via Telegram: {period}, {interval}, capital ${capital}")
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, run_backtest, symbol, period, interval, capital)
                metrics = result.get('metrics', {})
                
                if "error" in metrics:
                    text = f"❌ Error en backtest para {SUPPORTED_ASSETS.get(symbol, symbol)}: {metrics['error']}"
                elif "error" in result:
                    text = f"❌ Error en backtest: {result['error']}"
                else:
                    period_display = period.replace("mo", " meses").replace("y", " años").replace("_", " ")
                    interval_display = interval.replace("min", " min").replace("h", " hora").replace("d", " día")
                    text = [
                        f"📊 Backtest para {SUPPORTED_ASSETS.get(symbol, symbol)} ({period_display}, {interval_display}, Capital: ${capital:,})",
                        f"Trades Totales: {metrics.get('total_trades', 0)}",
                        f"Win Rate: {metrics.get('win_rate', 0):.1%}",
                        f"P&L Total: ${metrics.get('total_pnl', 0):.2f}",
                        f"Capital Final: ${metrics.get('final_capital', 0):.2f}",
                        f"Max Drawdown: {metrics.get('max_drawdown', 0):.1%}",
                        f"Profit Factor: {metrics.get('profit_factor', 0):.2f}"
                    ]
                    text = "\n".join(text)
            except Exception as e:
                logger.error(f"Error en backtest para {symbol}: {e}")
                text = "🚨 Error ejecutando backtest. Revisa logs."

            try:
                await query.edit_message_text(text=text)
            except Exception as e:
                if "Message is not modified" in str(e):
                    logger.info("Mensaje de backtest no modificado, ignorando.")
                else:
                    raise
    except (ValueError, IndexError) as e:
        logger.error(f"Error al procesar callback_data: '{data}'. Error: {e}")
        await query.answer("Hubo un error al procesar la opción seleccionada.")

async def adjust_sl_tp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("adjust_sl_"):
        symbol = data.replace("adjust_sl_", "")
        action = "Stop Loss"
    elif data.startswith("adjust_tp_"):
        symbol = data.replace("adjust_tp_", "")
        action = "Take Profit"
    else:
        return
        
    # Temporal response until a MessageHandler state machine is built for inputs
    await query.edit_message_text(text=f"⚙️ La función para ajustar el {action} de {symbol} directamente desde Telegram está en desarrollo. ¡Pronto disponible!")

async def approve_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    from broker_integration import pending_trades, broker
    import asyncio

    if data.startswith("approve_"):
        trade_id = data.split("_")[1]
        if trade_id in pending_trades:
            trade = pending_trades.pop(trade_id)
            await query.edit_message_text(text=f"⏳ Ejecutando trade {trade['tipo'].upper()} {trade['symbol']}...")
            
            # Execute trade in a thread
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                broker.execute_trade,
                trade["symbol"], trade["tipo"], trade["quantity"],
                trade["price"], trade["tp"], trade["sl"]
            )
            
            if result["status"] == "success":
                await query.edit_message_text(text=f"✅ Trade {trade['tipo'].upper()} {trade['symbol']} EJECUTADO!\nOrden: {result.get('order_id')}")
            else:
                await query.edit_message_text(text=f"❌ Falló ejecución: {result.get('message')}")
        else:
            await query.edit_message_text(text="⚠️ Trade expirado o ya procesado.")
            
    elif data.startswith("reject_"):
        trade_id = data.split("_")[1]
        if trade_id in pending_trades:
            pending_trades.pop(trade_id)
            await query.edit_message_text(text="❌ Trade rechazado por el usuario.")
        else:
            await query.edit_message_text(text="⚠️ Trade ya procesado.")

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("Ajustar Riesgos", callback_data="config_riesgos"),
         InlineKeyboardButton("Ajustar Filtros", callback_data="config_filtros")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Selecciona qué configurar:", reply_markup=keyboard)

async def config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "config_riesgos":
        text = "Parámetros de Riesgos:\n- POSITION_SIZE_PCT: 0.01 (1% capital/trade)\n- TRAILING_STOP_PCT: 0.02 (2% trailing)\nEdita params.json para cambiar."
    elif data == "config_filtros":
        text = "Filtros Activos:\n- Horas: 00:00-21:00 UTC\n- News: Evita 08:00-09:00 UTC\nEdita params.json para ajustar."
    else:
        text = "Opción no válida."
    await query.edit_message_text(text=text)

async def historial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el historial de las últimas señales generadas."""
    import pandas as pd
    from pathlib import Path
    
    log_path = Path("logs/signals_log_simple.csv")
    
    if not log_path.exists():
        await update.message.reply_text("📭 No hay historial de señales todavía.")
        return
    
    try:
        # Leer el CSV sin encabezados
        df = pd.read_csv(log_path, header=None, names=['timestamp', 'symbol', 'type', 'price', 'tp', 'sl', 'score'])
        
        if df.empty:
            await update.message.reply_text("📭 No hay señales registradas aún.")
            return
        
        # Tomar las últimas 10 señales
        df = df.tail(10)
        
        mensajes = ["📈 **Historial de Señales (últimas 10)**\n"]
        for _, row in df.iterrows():
            try:
                ts = str(row['timestamp'])[:16].replace('T', ' ')
                symbol = row['symbol']
                tipo = "🟢 BUY" if row['type'] == 'buy' else "🔴 SELL"
                precio = float(row['price'])
                tp = float(row['tp'])
                sl = float(row['sl'])
                
                msg = f"• {ts}\n  {symbol} | {tipo}\n  📍 {precio:.2f} | TP: {tp:.2f} | SL: {sl:.2f}"
                mensajes.append(msg)
            except Exception:
                continue
        
        if len(mensajes) == 1:
            await update.message.reply_text("📭 No se pudieron leer las señales.")
            return
            
        await update.message.reply_markdown("\n\n".join(mensajes))
        
    except Exception as e:
        logger.error(f"Error leyendo historial: {e}")
        await update.message.reply_text(f"❌ Error al leer historial: {e}")

async def estadisticas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas del sistema basadas en las señales generadas."""
    import pandas as pd
    from pathlib import Path
    from collections import Counter
    
    log_path = Path("logs/signals_log_simple.csv")
    
    if not log_path.exists():
        await update.message.reply_text("📭 No hay datos para estadísticas todavía.")
        return
    
    try:
        # Leer el CSV sin encabezados
        df = pd.read_csv(log_path, header=None, names=['timestamp', 'symbol', 'type', 'price', 'tp', 'sl', 'score'])
        
        if df.empty:
            await update.message.reply_text("📭 No hay datos para estadísticas.")
            return
        
        # Calcular estadísticas
        total_signals = len(df)
        
        # Por símbolo
        by_symbol = df['symbol'].value_counts().to_dict()
        symbol_stats = "\n".join([f"  • {s}: {c} señales" for s, c in by_symbol.items()])
        
        # Por tipo (buy/sell)
        buys = len(df[df['type'] == 'buy'])
        sells = len(df[df['type'] == 'sell'])
        
        # Última señal
        last = df.iloc[-1]
        last_ts = str(last['timestamp'])[:16].replace('T', ' ')
        last_symbol = last['symbol']
        last_type = "BUY" if last['type'] == 'buy' else "SELL"
        
        msg = [
            "📊 **Estadísticas del Sistema**\n",
            f"📈 Total de Señales: {total_signals}",
            f"🟢 Señales BUY: {buys}",
            f"🔴 Señales SELL: {sells}",
            f"\n**Por Activo:**",
            symbol_stats,
            f"\n**Última Señal:**",
            f"  {last_ts}",
            f"  {last_symbol} | {last_type}"
        ]
        
        await update.message.reply_markdown("\n".join(msg))
        
    except Exception as e:
        logger.error(f"Error calculando estadísticas: {e}")
        await update.message.reply_text(f"❌ Error al calcular estadísticas: {e}")

# Note: The 'job' function is imported from analizador_oro.py at the top of the file

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica el estado de los servicios."""
    # Verificación simple
    status_msg = [
        "✅ **Sistema Operativo**",
        "📡 Streaming: Activo",
        "🧠 Modelos ML: Cargados",
        f"📋 Activos soportados: {len(SUPPORTED_ASSETS)}",
        "🕒 Hora servidor: " + datetime.now().strftime("%H:%M UTC")
    ]
    await update.message.reply_markdown("\n".join(status_msg))

async def risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado de riesgo y P&L diario."""
    pnl = risk_manager.get_daily_pnl()
    is_active = risk_manager.is_forced_active()
    max_loss = params.get("MAX_DAILY_LOSS_PCT", 0.05) * 100
    
    status = "🔴 ACTIVADO (Pérdidas excedidas)" if is_active else "🟢 NORMAL (Operativo)"
    
    msg = [
        "🛡️ **Estado de Riesgo Local**",
        f"📊 P&L Diario: ${pnl:.2f}",
        f"🛑 Límite Diario: {max_loss}%",
        f"⚡ Circuit Breaker: {status}",
        "",
        "Usa /reset_risk para limpiar el candado manualmente."
    ]
    await update.message.reply_markdown("\n".join(msg))

async def reset_risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resetea el Kill Switch manualmente."""
    # Podríamos añadir verificación de admin aquí si quisiéramos
    risk_manager.reset_kill_switch()
    await update.message.reply_text("✅ Circuit Breaker reseteado. El bot volverá a analizar en el próximo ciclo.")


async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para recargar la configuración en caliente."""
    try:
        new_params = reload_config()
        await update.message.reply_text(f"✅ Configuración recargada correctamente.\nParámetros activos: {len(new_params)}")
        logger.info("Configuración recargada vía Telegram.")
    except Exception as e:
        logger.error(f"Error recargando configuración: {e}")
        await update.message.reply_text(f"❌ Error al recargar configuración: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    error_msg = f"Error en Telegram: {str(context.error)}"
    await notify_critical_error(error_msg)
    if isinstance(update, Update) and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🚨 Ha ocurrido un error interno. El equipo ya fue notificado."
        )

def is_pid_running(pid):
    """Verifica si un proceso con el PID dado está en curso (multiplataforma)."""
    if pid <= 0: return False
    try:
        if sys.platform == "win32":
            # Usar tasklist en Windows para evitar dependencias externas como psutil
            import subprocess
            output = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"], 
                stderr=subprocess.STDOUT, 
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            return str(pid) in output
        else:
            # Unix-like: os.kill(pid, 0) no mata, solo verifica existencia
            os.kill(pid, 0)
            return True
    except Exception:
        return False

# --- Función Principal ---
def main():
    print("DEBUG: Entrando en main...", flush=True)
    # --- Logging y Base de Datos ---
    setup_logging()
    init_db()
    load_rl_model()
    logger = logging.getLogger(__name__)
    logger.info("Sistema inicializado: Logging, DB y RL cargados.")

    # --- Process Management: Check and Write PID to lockfile ---
    lock_file = "astabot.lock"
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                old_pid = int(f.read().strip())
            
            if is_pid_running(old_pid):
                print(f"❌ Error: Ya hay una instancia de Astabot ejecutándose (PID: {old_pid}).")
                sys.exit(1)
            else:
                logger.warning(f"⚠️ Detectado archivo de bloqueo huérfano (PID: {old_pid}). Limpiando...")
                os.remove(lock_file)
        except Exception as e:
            logger.error(f"Error al verificar lock file: {e}")
            if os.path.exists(lock_file): os.remove(lock_file)

    pid = os.getpid()
    with open(lock_file, "w") as f:
        f.write(str(pid))
    
    logger.info(f"Iniciando Astabot (PID: {pid})...")

    # --- Inicializar Broker (MT5) ---
    from config import ENABLE_AUTOTRADING
    from broker_integration import broker
    
    if ENABLE_AUTOTRADING:
        if broker.initialize_mt5():
            logger.info("Conexión con Broker establecida.")
        else:
            logger.error("No se pudo conectar con el Broker. El bot funcionará solo en modo Señales.")
    else:
        logger.info("Modo de Sólo Señales activo (Autotrading APAGADO). No se abrirá MT5.")

    # --- INICIALIZACIÓN DE COMPONENTES ---
    # application.run_polling() maneja el loop, así que inicializamos componentes dentro del contexto
    # o usamos el loop de la aplicación.

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    from config import params
    scan_interval = params.get("SCAN_INTERVAL_MINUTES", 3) * 60

    job_queue = application.job_queue
    job_queue.run_repeating(job, interval=scan_interval, first=10)
    logger.info(f"Análisis automático programado cada {params.get('SCAN_INTERVAL_MINUTES', 3)} minutos (Modo Rápido).")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analizar", analizar_command))
    application.add_handler(CommandHandler("backtest", backtest_command))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("historial", historial_command))
    application.add_handler(CommandHandler("estadisticas", estadisticas_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("risk", risk_command))
    application.add_handler(CommandHandler("reset_risk", reset_risk_command))
    application.add_handler(CommandHandler("reload", reload_command))

    # Handlers de CallbackQuery con patrones para evitar solapamientos
    # Los más específicos deben ir primero.
    application.add_handler(CallbackQueryHandler(backtest_callback, pattern=r'^(backtest_|capital_|period_|interval_)'))
    application.add_handler(CallbackQueryHandler(adjust_sl_tp_callback, pattern=r'^(adjust_sl_|adjust_tp_)'))
    application.add_handler(CallbackQueryHandler(approve_reject_callback, pattern=r'^(approve_|reject_)'))
    application.add_handler(CallbackQueryHandler(config_callback, pattern=r'^config_'))
    # El handler de asset es el menos específico, por lo que va al final.
    application.add_handler(CallbackQueryHandler(asset_callback))
    
    application.add_error_handler(error_handler)

    logger.info("Astabot está ahora en línea y escuchando...")
    
    async def post_init(application):
        logger.info("Realizando post-inicialización...")
        await initialize_streaming()
        logger.info("Streaming inicializado correctamente.")

    application.post_init = post_init
    
    try:
        application.run_polling()
    except telegram.error.Conflict:
        logger.critical("Conflicto: otro proceso del bot está ejecutándose con este token. Detén instancias previas e intenta de nuevo.")
    except Exception as e:
         logger.critical(f"Error fatal: {e}")
    finally:
        # Cleanup
        if os.path.exists("astabot.lock"):
            os.remove("astabot.lock")
        broker.shutdown()
        stop_all_streaming()
        logger.info("Astabot detenido y recursos liberados.")

if __name__ == "__main__":
    main()
