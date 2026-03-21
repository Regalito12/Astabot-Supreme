# realtime_streaming.py
import asyncio
import websockets
import json
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class RealTimeStreamer:
    def __init__(self, symbol, exchange="binance"):
        self.symbol = symbol.replace("/", "").lower()  # ej. btcusdt
        self.exchange = exchange
        self.data = []  # Lista de ticks en tiempo real
        self.is_running = False

    async def connect_binance(self):
        """Conectar a Binance WebSocket para datos en tiempo real."""
        uri = f"wss://stream.binance.com:9443/ws/{self.symbol}@trade"
        async with websockets.connect(uri) as websocket:
            logger.info(f"Conectado a Binance para {self.symbol}")
            while self.is_running:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    tick = {
                        'timestamp': datetime.fromtimestamp(data['T'] / 1000),
                        'price': float(data['p']),
                        'volume': float(data['q'])
                    }
                    self.data.append(tick)
                    # Mantener solo últimos 100 ticks
                    if len(self.data) > 100:
                        self.data.pop(0)
                except Exception as e:
                    logger.error(f"Error en streaming: {e}")
                    from errors import notify_critical_error
                    import asyncio
                    asyncio.create_task(notify_critical_error(f"Fallo crítico en socket de streaming {self.symbol}: {e}"))
                    break

    def get_latest_data(self):
        """Devuelve DataFrame con datos recientes."""
        if not self.data:
            return pd.DataFrame()
        df = pd.DataFrame(self.data)
        df['datetime'] = pd.to_datetime(df['timestamp'])
        df = df[['datetime', 'price', 'volume']].rename(columns={'price': 'close'})
        # Simular OHLC si es necesario
        df['open'] = df['close']
        df['high'] = df['close']
        df['low'] = df['close']
        return df

    async def start(self):
        self.is_running = True
        if self.exchange == "binance":
            await self.connect_binance()

    def stop(self):
        self.is_running = False

# Función para integrar en analizador_oro.py
streamers = {}  # Cache de streamers por símbolo

def get_realtime_data(symbol, exchange="binance"):
    """Obtiene datos en tiempo real si disponible, sino fallback a histórico."""
    if symbol in streamers and streamers[symbol].is_running:
        return streamers[symbol].get_latest_data()
    # Fallback a datos históricos
    from data_fetch import get_candles
    return get_candles(symbol, interval="1min", output_size=50)

def start_streaming(symbol):
    """Inicia streaming para un símbolo."""
    if symbol not in streamers:
        streamers[symbol] = RealTimeStreamer(symbol)
        asyncio.create_task(streamers[symbol].start())

def stop_all_streaming():
    """Detiene todos los streams."""
    for streamer in streamers.values():
        streamer.stop()