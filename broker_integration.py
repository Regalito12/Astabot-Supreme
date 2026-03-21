# broker_integration.py
import logging
# import MetaTrader5 as mt5  # --- REMOVIDO: Importación perezosa para evitar cuelgues ---
from config import TELEGRAM_TOKEN, CHAT_ID, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, ENABLE_AUTOTRADING, params
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import uuid

pending_trades = {}

logger = logging.getLogger(__name__)

class BrokerIntegration:
    """Integración con MetaTrader 5 para ejecución automática."""

    def __init__(self):
        self.connected = False
        self.authorized = False

    def initialize_mt5(self):
        """Inicializa la conexiÃ³n con MetaTrader 5 terminal."""
        import MetaTrader5 as mt5 # Lazy import
        if not mt5.initialize():
            logger.critical(f"MT5 initialize() failed, error code = {mt5.last_error()}")
            return False

        logger.info(f"MT5 inicializado. VersiÃ³n: {mt5.version()}")

        # Intentar login si hay credenciales
        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            import MetaTrader5 as mt5
            self.authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
            if self.authorized:
                import MetaTrader5 as mt5
                logger.info(f"Conectado a cuenta {MT5_LOGIN} en servidor {MT5_SERVER}")
                account_info = mt5.account_info()
                if account_info:
                    logger.info(f"Balance: {account_info.balance} {account_info.currency}, Equity: {account_info.equity}")
            else:
                import MetaTrader5 as mt5
                logger.error(f"Fallo al loguear en cuenta {MT5_LOGIN}: {mt5.last_error()}")
        else:
            logger.warning("Credenciales de MT5 no configuradas completamente en config.py")

        self.connected = True
        return True

    def shutdown(self):
        import MetaTrader5 as mt5
        mt5.shutdown()
        self.connected = False
        logger.info("ConexiÃ³n MT5 cerrada.")
    
    def check_spread_xau(self, symbol="XAUUSD"):
        """
        Verifica que el spread de XAU/USD sea aceptable antes de operar.
        Spread alto = trade perdedor desde el inicio.
        """
        max_spread = params.get("XAU_MAX_SPREAD", 0.50)  # Default 0.50 USD
        
        # Convertir sÃ­mbolo al formato MT5 si necesario
        mt5_symbol = symbol.replace("/", "")
        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(mt5_symbol)
        if tick is None:
            logger.warning(f"No se pudo obtener tick para {mt5_symbol}")
            return True  # Permitir si no podemos verificar
        
        spread = tick.ask - tick.bid
        
        if spread > max_spread:
            logger.warning(f"Spread XAU muy alto: {spread:.2f} (máximo: {max_spread}). Trade bloqueado.")
            return False
        
        logger.debug(f"Spread XAU aceptable: {spread:.2f}")
        return True

    async def confirm_trade(self, symbol, tipo, price, tp, sl, quantity):
        """Confirmar trade con usuario antes de ejecutar (si autotrading desactivado)."""
        if ENABLE_AUTOTRADING:
            logger.info("Autotrading activado: Saltando confirmación manual.")
            return True

        bot = Bot(token=TELEGRAM_TOKEN)
        trade_id = str(uuid.uuid4())[:8]
        pending_trades[trade_id] = {
            "symbol": symbol, "tipo": tipo, "quantity": quantity,
            "price": price, "tp": tp, "sl": sl
        }

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Aprobar Trade", callback_data=f"approve_{trade_id}"),
             InlineKeyboardButton("❌ Rechazar", callback_data=f"reject_{trade_id}")]
        ])

        message = f"🚨 CONFIRMACIÓN REQUERIDA 🚨\n¿Ejecutar trade? {tipo.upper()} {symbol} @ {price:.4f}\nTP: {tp:.4f}, SL: {sl:.4f}\n\n⚠️ Autotrading desactivado. Usa los botones para decidir."
        await bot.send_message(chat_id=CHAT_ID, text=message, reply_markup=keyboard)
        logger.info("Solicitud de confirmación enviada a Telegram.")
        return False

    def execute_trade(self, symbol, tipo, quantity, price, tp, sl):
        """Ejecuta una orden en MT5."""
        import MetaTrader5 as mt5  # Lazy import
        if not self.connected or not self.authorized:
            logger.error("No conectado/autorizado en MT5. No se puede operar.")
            return {"status": "error", "message": "MT5 not connected"}
        
        # --- NUEVO: Verificar spread para XAU/USD ---
        if 'XAU' in symbol.upper():
            if not self.check_spread_xau(symbol):
                return {"status": "error", "message": "Spread too high for XAU"}


        action = mt5.TRADE_ACTION_DEAL
        type_order = mt5.ORDER_TYPE_BUY if tipo == "buy" else mt5.ORDER_TYPE_SELL
        
        # Ajustar volumen (lotes) - MT5 usa lotes estándar
        # quantity aquí viene como "tamaño de posición en USD" desde analizador_oro normalmente?
        # Ojo: analizador_oro calcula position_size en USD. Necesitamos convertir a lotes.
        # Simplificación: usaremos 0.01 lotes fijos o una conversión simple si podemos obtener info del símbolo.
        
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logger.error(f"Símbolo {symbol} no encontrado en MT5.")
            return {"status": "error", "message": "Symbol not found"}

        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Falló al seleccionar {symbol}")
                return {"status": "error", "message": "Symbol select failed"}

        # Conversión de unidades a Lotes de MT5
        lot = 0.01 
        if quantity > 0 and symbol_info:
             contract_size = symbol_info.trade_contract_size if hasattr(symbol_info, 'trade_contract_size') else 100000
             if contract_size > 0:
                 calculated_lot = quantity / contract_size
                 
                 step = symbol_info.volume_step if hasattr(symbol_info, 'volume_step') else 0.01
                 min_vol = symbol_info.volume_min if hasattr(symbol_info, 'volume_min') else 0.01
                 max_vol = symbol_info.volume_max if hasattr(symbol_info, 'volume_max') else 100.0
                 
                 lot = round(calculated_lot / step) * step
                 
                 if lot < min_vol:
                     lot = min_vol
                 elif lot > max_vol:
                     lot = max_vol
        
        request = {
            "action": action,
            "symbol": symbol,
            "volume": lot,
            "type": type_order,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": "Astabot Auto",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Enviar orden
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Orden fallida: {result.comment} (Code: {result.retcode})")
            return {"status": "error", "message": result.comment, "retcode": result.retcode}
        
        logger.info(f"Orden ejecutada exitosamente: {result.order}")
        return {"status": "success", "order_id": result.order, "volume": result.volume, "price": result.price}

    async def auto_execute(self, signal_data):
        """Ejecutar automáticamente si configurado."""
        quantity = signal_data.get("position_size", 0.01) # Esto viene en USD
        if not ENABLE_AUTOTRADING:
             await self.confirm_trade(
                signal_data["symbol"], signal_data["tipo"],
                signal_data["price"], signal_data["tp"], signal_data["sl"], quantity
            )
             return {"status": "skipped", "message": "Autotrading disabled"}

        # Autotrading habilitado
        logger.info(f"Iniciando ejecución automática para {signal_data['symbol']} ({signal_data['tipo']})")
        
        # Ejecutar en thread aparte para no bloquear asyncio (mt5.order_send es bloqueante)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, 
            self.execute_trade,
            signal_data["symbol"], signal_data["tipo"], quantity,
            signal_data["price"], signal_data["tp"], signal_data["sl"]
        )
        
        if result["status"] == "success":
             bot = Bot(token=TELEGRAM_TOKEN)
             await bot.send_message(chat_id=CHAT_ID, text=f"✅ ORDINE EJECUTADA: {signal_data['symbol']} {signal_data['tipo'].upper()} @ {result['price']}")
        
        return result

# Instancia global
broker = BrokerIntegration()

if __name__ == "__main__":
    # Test
    asyncio.run(broker.confirm_trade("XAU/USD", "buy", 2000, 2010, 1990, 0.01))