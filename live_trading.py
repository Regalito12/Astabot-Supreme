# live_trading.py - Módulo de Trading en Vivo con Brokers
import logging
import time
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import threading
import json

# Imports condicionales para brokers
# Imports condicionales para brokers (movidos a métodos para evitar cuelgues)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

try:
    import alpaca_trade_api as tradeapi
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    tradeapi = None

try:
    from ib_insync import IB, Stock, Forex, util
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False
    IB = None

from models import db, TradingAccount, Trade, Position, Signal, Asset
from errors import AstabotError, notify_critical_error
from config import SUPPORTED_ASSETS

logger = logging.getLogger(__name__)

class BrokerError(AstabotError):
    """Error específico de brokers"""
    pass

class OrderError(BrokerError):
    """Error en órdenes"""
    pass

class ConnectionError(BrokerError):
    """Error de conexión"""
    pass

class BrokerBase(ABC):
    """Clase base abstracta para brokers"""

    def __init__(self, account_data: Dict):
        self.account_data = account_data
        self.connected = False
        self.account_id = account_data.get('account_id')
        self.is_paper_trading = account_data.get('is_paper_trading', True)

    @abstractmethod
    def connect(self) -> bool:
        """Conectar al broker"""
        pass

    @abstractmethod
    def disconnect(self):
        """Desconectar del broker"""
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """Obtener balance de cuenta"""
        pass

    @abstractmethod
    def place_order(self, symbol: str, order_type: str, side: str, quantity: float,
                   price: Optional[float] = None, stop_price: Optional[float] = None) -> Dict:
        """Colocar orden"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancelar orden"""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict]:
        """Obtener posiciones abiertas"""
        pass

    @abstractmethod
    def get_orders(self) -> List[Dict]:
        """Obtener órdenes activas"""
        pass

    def validate_order(self, symbol: str, quantity: float, price: Optional[float] = None) -> bool:
        """Validar orden antes de enviar"""
        if symbol not in SUPPORTED_ASSETS:
            raise OrderError(f"Símbolo {symbol} no soportado")

        if quantity <= 0:
            raise OrderError("Cantidad debe ser positiva")

        balance = self.get_balance()
        if price and (price * quantity) > balance:
            raise OrderError("Fondos insuficientes")

        return True

class MetaTrader5Broker(BrokerBase):
    """Integración con MetaTrader 5"""

    def __init__(self, account_data: Dict):
        super().__init__(account_data)
        if not MT5_AVAILABLE:
            raise BrokerError("MetaTrader5 no está instalado")

        self.login = account_data.get('mt5_login')
        self.password = account_data.get('mt5_password')
        self.server = account_data.get('mt5_server')

    def connect(self) -> bool:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            raise ConnectionError("No se pudo inicializar MT5")

        if not mt5.login(self.login, self.password, self.server):
            raise ConnectionError(f"No se pudo conectar a MT5: {mt5.last_error()}")

        self.connected = True
        logger.info(f"Conectado a MT5 - Cuenta: {self.account_id}")
        return True

    def disconnect(self):
        if self.connected:
            import MetaTrader5 as mt5
            mt5.shutdown()
            self.connected = False
            logger.info("Desconectado de MT5")

    def get_balance(self) -> float:
        if not self.connected:
            raise ConnectionError("No conectado a MT5")

        import MetaTrader5 as mt5
        account_info = mt5.account_info()
        if account_info is None:
            raise BrokerError("No se pudo obtener información de cuenta")

        return account_info.balance

    def place_order(self, symbol: str, order_type: str, side: str, quantity: float,
                   price: Optional[float] = None, stop_price: Optional[float] = None) -> Dict:

        self.validate_order(symbol, quantity, price)

        # Mapear tipos de orden MT5
        order_type_mt5 = {
            'market': mt5.ORDER_TYPE_BUY if side == 'buy' else mt5.ORDER_TYPE_SELL,
            'limit': mt5.ORDER_TYPE_BUY_LIMIT if side == 'buy' else mt5.ORDER_TYPE_SELL_LIMIT,
            'stop': mt5.ORDER_TYPE_BUY_STOP if side == 'buy' else mt5.ORDER_TYPE_SELL_STOP
        }.get(order_type)

        if order_type_mt5 is None:
            raise OrderError(f"Tipo de orden no soportado: {order_type}")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": quantity,
            "type": order_type_mt5,
            "price": price or mt5.symbol_info_tick(symbol).ask if side == 'buy' else mt5.symbol_info_tick(symbol).bid,
            "deviation": 10,
            "magic": 234000,
            "comment": "Astabot Trade",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        if stop_price:
            request["sl"] = stop_price

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise OrderError(f"Error en orden MT5: {result.comment}")

        return {
            'order_id': str(result.order),
            'status': 'filled',
            'price': result.price,
            'quantity': quantity
        }

    def cancel_order(self, order_id: str) -> bool:
        # MT5 no tiene cancelación directa, se cierra la posición
        positions = mt5.positions_get()
        for pos in positions:
            if str(pos.ticket) == order_id:
                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                    "position": pos.ticket,
                    "price": mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask,
                    "deviation": 10,
                }
                result = mt5.order_send(close_request)
                return result.retcode == mt5.TRADE_RETCODE_DONE

        return False

    def get_positions(self) -> List[Dict]:
        positions = mt5.positions_get()
        return [{
            'symbol': pos.symbol,
            'side': 'long' if pos.type == mt5.POSITION_TYPE_BUY else 'short',
            'quantity': pos.volume,
            'avg_entry_price': pos.price_open,
            'current_price': pos.price_current,
            'pnl': pos.profit,
            'order_id': str(pos.ticket)
        } for pos in positions]

    def get_orders(self) -> List[Dict]:
        orders = mt5.orders_get()
        return [{
            'order_id': str(order.ticket),
            'symbol': order.symbol,
            'type': 'limit' if order.type == mt5.ORDER_TYPE_BUY_LIMIT else 'stop',
            'side': 'buy' if 'BUY' in str(order.type) else 'sell',
            'quantity': order.volume_initial,
            'price': order.price_open,
            'status': 'pending'
        } for order in orders]

class AlpacaBroker(BrokerBase):
    """Integración con Alpaca"""

    def __init__(self, account_data: Dict):
        super().__init__(account_data)
        if not ALPACA_AVAILABLE:
            raise BrokerError("Alpaca API no está instalada")

        self.api_key = account_data.get('api_key')
        self.api_secret = account_data.get('api_secret')
        self.base_url = account_data.get('base_url', 'https://paper-api.alpaca.markets')  # Paper trading por defecto

        self.api = tradeapi.REST(self.api_key, self.api_secret, self.base_url)

    def connect(self) -> bool:
        try:
            account = self.api.get_account()
            self.connected = account.status == 'ACTIVE'
            if self.connected:
                logger.info(f"Conectado a Alpaca - Cuenta: {self.account_id}")
            return self.connected
        except Exception as e:
            raise ConnectionError(f"Error conectando a Alpaca: {str(e)}")

    def disconnect(self):
        self.connected = False
        logger.info("Desconectado de Alpaca")

    def get_balance(self) -> float:
        if not self.connected:
            raise ConnectionError("No conectado a Alpaca")

        account = self.api.get_account()
        return float(account.cash)

    def place_order(self, symbol: str, order_type: str, side: str, quantity: float,
                   price: Optional[float] = None, stop_price: Optional[float] = None) -> Dict:

        self.validate_order(symbol, quantity, price)

        try:
            # Mapear símbolos Alpaca
            alpaca_symbol = symbol.replace('/', '')

            order = self.api.submit_order(
                symbol=alpaca_symbol,
                qty=quantity,
                side=side,
                type=order_type,
                time_in_force='gtc',
                limit_price=price if order_type == 'limit' else None,
                stop_price=stop_price if order_type == 'stop' else None
            )

            return {
                'order_id': order.id,
                'status': order.status,
                'price': float(order.limit_price or order.stop_price or 0),
                'quantity': quantity
            }

        except Exception as e:
            raise OrderError(f"Error en orden Alpaca: {str(e)}")

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.api.cancel_order(order_id)
            return True
        except Exception as e:
            logger.error(f"Error cancelando orden Alpaca: {str(e)}")
            return False

    def get_positions(self) -> List[Dict]:
        positions = self.api.list_positions()
        return [{
            'symbol': pos.symbol,
            'side': 'long' if pos.side == 'long' else 'short',
            'quantity': float(pos.qty),
            'avg_entry_price': float(pos.avg_entry_price),
            'current_price': float(pos.current_price),
            'pnl': float(pos.unrealized_pl),
            'order_id': pos.symbol  # Alpaca no tiene order_id directo
        } for pos in positions]

    def get_orders(self) -> List[Dict]:
        orders = self.api.list_orders()
        return [{
            'order_id': order.id,
            'symbol': order.symbol,
            'type': order.type,
            'side': order.side,
            'quantity': float(order.qty),
            'price': float(order.limit_price or order.stop_price or 0),
            'status': order.status
        } for order in orders]

class InteractiveBrokersBroker(BrokerBase):
    """Integración con Interactive Brokers"""

    def __init__(self, account_data: Dict):
        super().__init__(account_data)
        if not IB_AVAILABLE:
            raise BrokerError("IB API no está instalada")

        self.host = account_data.get('ib_host', '127.0.0.1')
        self.port = account_data.get('ib_port', 7497)
        self.client_id = account_data.get('ib_client_id', 1)

        self.ib = IB()

    def connect(self) -> bool:
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self.connected = self.ib.isConnected()
            if self.connected:
                logger.info(f"Conectado a Interactive Brokers - Cuenta: {self.account_id}")
            return self.connected
        except Exception as e:
            raise ConnectionError(f"Error conectando a IB: {str(e)}")

    def disconnect(self):
        if self.connected:
            self.ib.disconnect()
            self.connected = False
            logger.info("Desconectado de Interactive Brokers")

    def get_balance(self) -> float:
        if not self.connected:
            raise ConnectionError("No conectado a IB")

        account = self.ib.managedAccounts()[0]
        summary = self.ib.accountSummary(account)

        for item in summary:
            if item.tag == 'TotalCashValue':
                return float(item.value)

        return 0.0

    def place_order(self, symbol: str, order_type: str, side: str, quantity: float,
                   price: Optional[float] = None, stop_price: Optional[float] = None) -> Dict:

        self.validate_order(symbol, quantity, price)

        try:
            # Crear contrato
            if '/' in symbol:  # Forex
                contract = Forex(symbol.split('/')[0] + symbol.split('/')[1])
            else:  # Stock
                contract = Stock(symbol, 'SMART', 'USD')

            # Crear orden
            from ib_insync import MarketOrder, LimitOrder, StopOrder

            if order_type == 'market':
                order = MarketOrder(side.upper(), quantity)
            elif order_type == 'limit':
                order = LimitOrder(side.upper(), quantity, price)
            elif order_type == 'stop':
                order = StopOrder(side.upper(), quantity, stop_price)
            else:
                raise OrderError(f"Tipo de orden no soportado: {order_type}")

            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(1)  # Esperar confirmación

            return {
                'order_id': str(trade.order.orderId),
                'status': trade.orderStatus.status,
                'price': float(trade.order.lmtPrice or trade.order.auxPrice or 0),
                'quantity': quantity
            }

        except Exception as e:
            raise OrderError(f"Error en orden IB: {str(e)}")

    def cancel_order(self, order_id: str) -> bool:
        try:
            order = self.ib.orders[int(order_id)]
            self.ib.cancelOrder(order)
            return True
        except Exception as e:
            logger.error(f"Error cancelando orden IB: {str(e)}")
            return False

    def get_positions(self) -> List[Dict]:
        positions = self.ib.positions()
        return [{
            'symbol': pos.contract.symbol,
            'side': 'long' if pos.position > 0 else 'short',
            'quantity': abs(pos.position),
            'avg_entry_price': float(pos.avgCost / abs(pos.position)),
            'current_price': 0,  # IB no proporciona precio actual directo
            'pnl': float(pos.unrealizedPNL),
            'order_id': str(pos.contract.conId)
        } for pos in positions]

    def get_orders(self) -> List[Dict]:
        orders = self.ib.orders()
        return [{
            'order_id': str(order.orderId),
            'symbol': order.contract.symbol if hasattr(order.contract, 'symbol') else 'N/A',
            'type': order.orderType.lower(),
            'side': order.action.lower(),
            'quantity': order.totalQuantity,
            'price': float(order.lmtPrice or order.auxPrice or 0),
            'status': 'pending'  # IB no tiene status directo
        } for order in orders]

class LiveTradingManager:
    """Gestor principal de trading en vivo"""

    def __init__(self):
        self.brokers = {}
        self.active_accounts = {}
        self.sync_thread = None
        self.running = False

    def add_broker_account(self, user_id: int, account_data: Dict) -> str:
        """Añadir cuenta de broker para un usuario"""

        broker_type = account_data.get('broker_name', '').lower()

        if broker_type == 'metatrader5':
            broker = MetaTrader5Broker(account_data)
        elif broker_type == 'alpaca':
            broker = AlpacaBroker(account_data)
        elif broker_type == 'interactive brokers':
            broker = InteractiveBrokersBroker(account_data)
        else:
            raise BrokerError(f"Broker no soportado: {broker_type}")

        account_id = account_data.get('account_id')
        self.brokers[f"{user_id}_{account_id}"] = broker

        # Guardar en BD
        trading_account = TradingAccount(
            user_id=user_id,
            broker_name=broker_type,
            account_name=account_data.get('account_name'),
            account_id=account_id,
            api_key=account_data.get('api_key'),
            api_secret=account_data.get('api_secret'),
            is_paper_trading=account_data.get('is_paper_trading', True)
        )

        db.session.add(trading_account)
        db.session.commit()

        return account_id

    def connect_account(self, user_id: int, account_id: str) -> bool:
        """Conectar cuenta de broker"""
        broker_key = f"{user_id}_{account_id}"
        if broker_key not in self.brokers:
            raise BrokerError("Cuenta no encontrada")

        broker = self.brokers[broker_key]
        if broker.connect():
            self.active_accounts[broker_key] = broker
            return True
        return False

    def disconnect_account(self, user_id: int, account_id: str):
        """Desconectar cuenta de broker"""
        broker_key = f"{user_id}_{account_id}"
        if broker_key in self.active_accounts:
            self.active_accounts[broker_key].disconnect()
            del self.active_accounts[broker_key]

    def place_order(self, user_id: int, account_id: str, symbol: str, order_type: str,
                   side: str, quantity: float, price: Optional[float] = None,
                   stop_price: Optional[float] = None, signal_id: Optional[int] = None) -> Dict:
        """Colocar orden en broker"""

        broker_key = f"{user_id}_{account_id}"
        if broker_key not in self.active_accounts:
            raise ConnectionError("Cuenta no conectada")

        broker = self.active_accounts[broker_key]

        # Verificar riesgo
        if not self.check_risk_limits(user_id, symbol, quantity, price):
            raise OrderError("Límite de riesgo excedido")

        order_result = broker.place_order(symbol, order_type, side, quantity, price, stop_price)

        # Guardar en BD
        trade = Trade(
            user_id=user_id,
            trading_account_id=self.get_account_db_id(account_id),
            asset_id=self.get_asset_id(symbol),
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            status='pending',
            signal_id=signal_id
        )

        db.session.add(trade)
        db.session.commit()

        return order_result

    def cancel_order(self, user_id: int, account_id: str, order_id: str) -> bool:
        """Cancelar orden"""
        broker_key = f"{user_id}_{account_id}"
        if broker_key not in self.active_accounts:
            raise ConnectionError("Cuenta no conectada")

        broker = self.active_accounts[broker_key]
        return broker.cancel_order(order_id)

    def get_account_balance(self, user_id: int, account_id: str) -> float:
        """Obtener balance de cuenta"""
        broker_key = f"{user_id}_{account_id}"
        if broker_key not in self.active_accounts:
            raise ConnectionError("Cuenta no conectada")

        return self.active_accounts[broker_key].get_balance()

    def get_account_positions(self, user_id: int, account_id: str) -> List[Dict]:
        """Obtener posiciones de cuenta"""
        broker_key = f"{user_id}_{account_id}"
        if broker_key not in self.active_accounts:
            raise ConnectionError("Cuenta no conectada")

        return self.active_accounts[broker_key].get_positions()

    def sync_positions(self):
        """Sincronizar posiciones con BD"""
        for broker_key, broker in self.active_accounts.items():
            try:
                positions = broker.get_positions()

                for pos_data in positions:
                    # Actualizar o crear posición en BD
                    position = Position.query.filter_by(
                        user_id=int(broker_key.split('_')[0]),
                        asset_id=self.get_asset_id(pos_data['symbol'])
                    ).first()

                    if position:
                        position.quantity = pos_data['quantity']
                        position.avg_entry_price = pos_data['avg_entry_price']
                        position.current_price = pos_data['current_price']
                        position.unrealized_pnl = pos_data['pnl']
                    else:
                        position = Position(
                            user_id=int(broker_key.split('_')[0]),
                            trading_account_id=self.get_account_db_id(broker.account_id),
                            asset_id=self.get_asset_id(pos_data['symbol']),
                            side=pos_data['side'],
                            quantity=pos_data['quantity'],
                            avg_entry_price=pos_data['avg_entry_price'],
                            current_price=pos_data['current_price'],
                            unrealized_pnl=pos_data['pnl']
                        )
                        db.session.add(position)

                db.session.commit()

            except Exception as e:
                logger.error(f"Error sincronizando posiciones para {broker_key}: {e}")

    def check_risk_limits(self, user_id: int, symbol: str, quantity: float, price: Optional[float]) -> bool:
        """Verificar límites de riesgo"""
        # Implementar lógica de risk management
        # Por ahora, check básico
        return quantity > 0 and (price is None or price > 0)

    def start_sync_service(self):
        """Iniciar servicio de sincronización"""
        if self.sync_thread and self.sync_thread.is_alive():
            return

        self.running = True
        self.sync_thread = threading.Thread(target=self._sync_loop)
        self.sync_thread.daemon = True
        self.sync_thread.start()
        logger.info("Servicio de sincronización iniciado")

    def stop_sync_service(self):
        """Detener servicio de sincronización"""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join()
        logger.info("Servicio de sincronización detenido")

    def _sync_loop(self):
        """Loop de sincronización"""
        while self.running:
            try:
                self.sync_positions()
                time.sleep(30)  # Sync cada 30 segundos
            except Exception as e:
                logger.error(f"Error en sync loop: {e}")
                time.sleep(60)

    def get_account_db_id(self, account_id: str) -> int:
        """Obtener ID de BD de cuenta"""
        account = TradingAccount.query.filter_by(account_id=account_id).first()
        return account.id if account else None

    def get_asset_id(self, symbol: str) -> int:
        """Obtener ID de activo"""
        asset = Asset.query.filter_by(symbol=symbol).first()
        return asset.id if asset else None

    def execute_signal(self, signal_id: int, user_id: int, account_id: str):
        """Ejecutar señal automáticamente"""
        signal = Signal.query.get(signal_id)
        if not signal:
            return

        try:
            # Calcular tamaño de posición basado en riesgo
            balance = self.get_account_balance(user_id, account_id)
            risk_amount = balance * 0.01  # 1% de balance
            stop_loss_distance = abs(signal.entry_price - signal.stop_loss)
            position_size = risk_amount / stop_loss_distance if stop_loss_distance > 0 else 0.01

            # Obtener símbolo del activo
            asset = Asset.query.get(signal.asset_id)
            symbol_to_trade = asset.symbol if asset else "Unknown"

            # Ejecutar orden
            order_result = self.place_order(
                user_id=user_id,
                account_id=account_id,
                symbol=symbol_to_trade,
                order_type='market',
                side=signal.signal_type,
                quantity=position_size,
                stop_price=signal.stop_loss,
                signal_id=signal.id
            )

            # Actualizar señal
            signal.executed = True
            signal.executed_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"Señal {signal_id} ejecutada exitosamente")

        except Exception as e:
            logger.error(f"Error ejecutando señal {signal_id}: {e}")
            notify_critical_error(f"Error ejecutando señal: {str(e)}")

# Instancia global
live_trading_manager = LiveTradingManager()

def get_live_trading_manager():
    return live_trading_manager