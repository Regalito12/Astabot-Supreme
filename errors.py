# errors.py
import logging
from telegram import Bot
from config import TELEGRAM_TOKEN, CHAT_ID

logger = logging.getLogger(__name__)

class AstabotError(Exception):
    """Excepción base para Astabot."""
    pass

class DataFetchError(AstabotError):
    """Error al obtener datos de mercado."""
    pass

class SignalAnalysisError(AstabotError):
    """Error en análisis de señales."""
    pass

class BacktestError(AstabotError):
    """Error en backtesting."""
    pass

class TelegramError(AstabotError):
    """Error en comunicación con Telegram."""
    pass

async def notify_critical_error(message: str):
    """Notifica errores críticos vía Telegram."""
    try:
        # Ignorar errores de conflicto de Telegram (múltiples instancias)
        if "Conflict" in message and "terminated by other getUpdates" in message:
            logger.debug(f"Ignorando error de conflicto: {message}")
            return
        
        # Ignorar otros errores no críticos de Telegram
        if "Error en Telegram:" in message and any(x in message for x in ["Conflict", "ConflictError", "NetworkError"]):
            logger.warning(f"Error de Telegram no crítico: {message}")
            return
            
        bot = Bot(token=TELEGRAM_TOKEN)
        # Eliminar emojis para evitar problemas de codificación
        safe_message = message.replace("🚨", "").replace("Error Crítico:", "Error Critico:")
        await bot.send_message(chat_id=CHAT_ID, text=f"Error Critico: {safe_message}")
    except Exception as e:
        logger.error(f"Fallo al notificar error: {e}")

def retry_on_failure(max_retries=3, delay=1):
    """Decorador para reintentos automáticos."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Intento {attempt+1} falló: {e}")
                    if attempt < max_retries - 1:
                        import asyncio
                        await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff
                    else:
                        raise e
        return wrapper
    return decorator