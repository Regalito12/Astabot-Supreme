# multi_timeframe_realtime.py - Multi-Timeframe Real-Time Analysis
import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
import logging
import json
import websockets
import requests
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np

from data_fetch import get_candles
from indicadores import aplicar_indicadores
from analizador_oro import decidir_senal
from config import SUPPORTED_ASSETS
from errors import DataFetchError, SignalAnalysisError

logger = logging.getLogger(__name__)

class MultiTimeframeStreamer:
    """Streaming de datos multi-timeframe en tiempo real"""

    def __init__(self, symbols: List[str] = None):
        self.symbols = symbols or list(SUPPORTED_ASSETS.keys())
        self.timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        self.streams = {}  # symbol -> {timeframe: data_stream}
        self.indicators = {}  # symbol -> {timeframe: indicators}
        self.signals = {}  # symbol -> {timeframe: signals}
        self.callbacks = []  # Callbacks para updates
        self.is_running = False
        self.executor = ThreadPoolExecutor(max_workers=10)

        # Swarm intelligence
        self.swarm_agents = {}  # symbol -> swarm_data
        self.consensus_signals = {}  # symbol -> consensus_signal

    def add_callback(self, callback: Callable):
        """Añadir callback para updates en tiempo real"""
        self.callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        """Remover callback"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    async def start_streaming(self):
        """Iniciar streaming multi-timeframe"""
        self.is_running = True
        logger.info(f"Iniciando streaming multi-timeframe para {len(self.symbols)} símbolos")

        # Iniciar streams paralelos
        tasks = []
        for symbol in self.symbols:
            task = asyncio.create_task(self._stream_symbol(symbol))
            tasks.append(task)

        # Iniciar análisis cross-timeframe
        analysis_task = asyncio.create_task(self._cross_timeframe_analysis())

        # Iniciar swarm intelligence
        swarm_task = asyncio.create_task(self._swarm_intelligence_loop())

        try:
            await asyncio.gather(*tasks, analysis_task, swarm_task, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error en streaming: {str(e)}")
        finally:
            self.is_running = False

    def stop_streaming(self):
        """Detener streaming"""
        self.is_running = False
        time.sleep(2)  # Give a moment for async tasks to recognize is_running = False
        self.executor.shutdown(wait=True)
        logger.info("Streaming multi-timeframe detenido")

    async def _stream_symbol(self, symbol: str):
        """Stream de datos para un símbolo específico"""
        while self.is_running:
            try:
                # Obtener datos de todos los timeframes
                for timeframe in self.timeframes:
                    await self._update_timeframe_data(symbol, timeframe)

                # Calcular indicadores en tiempo real
                await self._calculate_realtime_indicators(symbol)

                # Generar señales
                await self._generate_realtime_signals(symbol)

                # Notificar callbacks
                await self._notify_callbacks(symbol)

                # Esperar próximo tick (ajustable por timeframe)
                await asyncio.sleep(1)  # 1 segundo base

            except Exception as e:
                logger.error(f"Error streaming {symbol}: {str(e)}")
                await asyncio.sleep(5)  # Reintentar en 5 segundos

    async def _update_timeframe_data(self, symbol: str, timeframe: str):
        """Actualizar datos de un timeframe específico"""
        try:
            # Obtener datos recientes
            if timeframe not in self.streams.get(symbol, {}):
                self.streams[symbol] = {}
                self.streams[symbol][timeframe] = []

            # Llamada async a get_candles
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                self.executor,
                get_candles,
                symbol,
                timeframe,
                100  # Últimas 100 velas
            )

            if not df.empty:
                # Convertir a lista de dicts para streaming
                latest_data = df.tail(10).to_dict('records')  # Últimas 10 velas

                # Actualizar stream
                self.streams[symbol][timeframe] = latest_data

                # Log update
                logger.debug(f"Updated {symbol} {timeframe}: {len(latest_data)} candles")

        except Exception as e:
            logger.warning(f"Error updating {symbol} {timeframe}: {str(e)}")

    async def _calculate_realtime_indicators(self, symbol: str):
        """Calcular indicadores en tiempo real para todos los timeframes"""
        if symbol not in self.indicators:
            self.indicators[symbol] = {}

        for timeframe in self.timeframes:
            try:
                if timeframe in self.streams.get(symbol, {}):
                    data = self.streams[symbol][timeframe]

                    if len(data) > 20:  # Suficientes datos
                        df = pd.DataFrame(data)

                        # Aplicar indicadores
                        df_indicators = await asyncio.get_event_loop().run_in_executor(
                            self.executor,
                            aplicar_indicadores,
                            df
                        )

                        # Extraer indicadores de la última vela
                        latest_indicators = df_indicators.iloc[-1].to_dict()

                        # Almacenar
                        self.indicators[symbol][timeframe] = {
                            'timestamp': datetime.utcnow().isoformat(),
                            'indicators': latest_indicators,
                            'data': df_indicators.iloc[-1].to_dict()
                        }

            except Exception as e:
                logger.error(f"Error calculating indicators for {symbol} {timeframe}: {str(e)}")

    async def _generate_realtime_signals(self, symbol: str):
        """Generar señales en tiempo real"""
        if symbol not in self.signals:
            self.signals[symbol] = {}

        for timeframe in self.timeframes:
            try:
                if timeframe in self.streams.get(symbol, {}):
                    data = self.streams[symbol][timeframe]

                    if len(data) > 50:  # Suficientes datos para señales
                        df = pd.DataFrame(data)

                        # Aplicar indicadores
                        df_indicators = await asyncio.get_event_loop().run_in_executor(
                            self.executor,
                            aplicar_indicadores,
                            df
                        )

                        # Generar señal
                        signal = await asyncio.get_event_loop().run_in_executor(
                            self.executor,
                            decidir_senal,
                            df_indicators
                        )

                        # Almacenar señal
                        self.signals[symbol][timeframe] = {
                            'timestamp': datetime.utcnow().isoformat(),
                            'signal': signal,
                            'confidence': signal.get('score', 0) / 6 if signal else 0,
                            'data': df_indicators.iloc[-1].to_dict()
                        }

            except Exception as e:
                logger.error(f"Error generating signals for {symbol} {timeframe}: {str(e)}")

    async def _cross_timeframe_analysis(self):
        """Análisis cross-timeframe automático"""
        while self.is_running:
            try:
                for symbol in self.symbols:
                    await self._analyze_cross_timeframe(symbol)

                await asyncio.sleep(5)  # Análisis cada 5 segundos

            except Exception as e:
                logger.error(f"Error in cross-timeframe analysis: {str(e)}")
                await asyncio.sleep(10)

    async def _analyze_cross_timeframe(self, symbol: str):
        """Analizar señales across timeframes"""
        if symbol not in self.signals:
            return

        signals = self.signals[symbol]

        # Contar señales por timeframe
        buy_signals = 0
        sell_signals = 0
        total_signals = 0

        for timeframe, signal_data in signals.items():
            if signal_data.get('signal'):
                signal = signal_data['signal']
                if signal.get('tipo') == 'buy':
                    buy_signals += 1
                elif signal.get('tipo') == 'sell':
                    sell_signals += 1
                total_signals += 1

        # Generar señal cross-timeframe
        cross_signal = None
        confidence = 0

        if total_signals >= 2:  # Al menos 2 timeframes con señales
            if buy_signals > sell_signals and buy_signals >= 2:
                cross_signal = 'buy'
                confidence = buy_signals / total_signals
            elif sell_signals > buy_signals and sell_signals >= 2:
                cross_signal = 'sell'
                confidence = sell_signals / total_signals

        # Almacenar análisis cross-timeframe
        if symbol not in self.consensus_signals:
            self.consensus_signals[symbol] = []

        if cross_signal:
            self.consensus_signals[symbol].append({
                'timestamp': datetime.utcnow().isoformat(),
                'signal': cross_signal,
                'confidence': confidence,
                'timeframes_with_signal': total_signals,
                'buy_signals': buy_signals,
                'sell_signals': sell_signals
            })

            # Mantener solo últimas 10 señales
            if len(self.consensus_signals[symbol]) > 10:
                self.consensus_signals[symbol] = self.consensus_signals[symbol][-10:]

            logger.info(f"Cross-timeframe signal for {symbol}: {cross_signal} (confidence: {confidence:.2f})")

    async def _swarm_intelligence_loop(self):
        """Swarm intelligence para señales confirmadas"""
        while self.is_running:
            try:
                for symbol in self.symbols:
                    await self._update_swarm_intelligence(symbol)

                await asyncio.sleep(10)  # Actualización cada 10 segundos

            except Exception as e:
                logger.error(f"Error in swarm intelligence: {str(e)}")
                await asyncio.sleep(15)

    async def _update_swarm_intelligence(self, symbol: str):
        """Actualizar swarm intelligence para un símbolo"""
        if symbol not in self.swarm_agents:
            # Inicializar swarm agents
            self.swarm_agents[symbol] = {
                'agents': [],
                'consensus': None,
                'confidence': 0
            }

        # Crear agentes basados en diferentes estrategias
        agents = []

        # Agent 1: Trend following
        trend_signal = self._get_trend_agent_signal(symbol)
        if trend_signal:
            agents.append({'strategy': 'trend_following', 'signal': trend_signal})

        # Agent 2: Mean reversion
        mr_signal = self._get_mean_reversion_agent_signal(symbol)
        if mr_signal:
            agents.append({'strategy': 'mean_reversion', 'signal': mr_signal})

        # Agent 3: Momentum
        mom_signal = self._get_momentum_agent_signal(symbol)
        if mom_signal:
            agents.append({'strategy': 'momentum', 'signal': mom_signal})

        # Agent 4: Volume analysis
        vol_signal = self._get_volume_agent_signal(symbol)
        if vol_signal:
            agents.append({'strategy': 'volume', 'signal': vol_signal})

        # Calcular consenso del swarm
        if agents:
            buy_votes = sum(1 for agent in agents if agent['signal'] == 'buy')
            sell_votes = sum(1 for agent in agents if agent['signal'] == 'sell')

            total_votes = len(agents)
            consensus = None
            confidence = 0

            if buy_votes > sell_votes and buy_votes >= total_votes * 0.6:  # 60% consenso
                consensus = 'buy'
                confidence = buy_votes / total_votes
            elif sell_votes > buy_votes and sell_votes >= total_votes * 0.6:
                consensus = 'sell'
                confidence = sell_votes / total_votes

            self.swarm_agents[symbol] = {
                'agents': agents,
                'consensus': consensus,
                'confidence': confidence,
                'timestamp': datetime.utcnow().isoformat()
            }

            if consensus:
                logger.info(f"Swarm consensus for {symbol}: {consensus} (confidence: {confidence:.2f}, agents: {total_votes})")

    def _get_trend_agent_signal(self, symbol: str) -> Optional[str]:
        """Señal del agente trend following"""
        try:
            # Analizar EMA en múltiples timeframes
            trend_score = 0

            for timeframe in ['1h', '4h', '1d']:
                if timeframe in self.indicators.get(symbol, {}):
                    ind = self.indicators[symbol][timeframe]['indicators']

                    # EMA trend
                    if ind.get('close', 0) > ind.get('EMA200', 0):
                        trend_score += 1
                    else:
                        trend_score -= 1

            if trend_score >= 2:
                return 'buy'
            elif trend_score <= -2:
                return 'sell'

        except Exception as e:
            logger.debug(f"Trend agent error for {symbol}: {str(e)}")

        return None

    def _get_mean_reversion_agent_signal(self, symbol: str) -> Optional[str]:
        """Señal del agente mean reversion"""
        try:
            # Analizar RSI y Z-score
            if '1h' in self.indicators.get(symbol, {}):
                ind = self.indicators[symbol]['1h']['indicators']

                rsi = ind.get('RSI', 50)
                zscore = ind.get('zscore_20', 0)

                # Oversold + below mean
                if rsi < 30 and zscore < -1.5:
                    return 'buy'
                # Overbought + above mean
                elif rsi > 70 and zscore > 1.5:
                    return 'sell'

        except Exception as e:
            logger.debug(f"Mean reversion agent error for {symbol}: {str(e)}")

        return None

    def _get_momentum_agent_signal(self, symbol: str) -> Optional[str]:
        """Señal del agente momentum"""
        try:
            # Analizar momentum y MACD
            if '1h' in self.indicators.get(symbol, {}):
                ind = self.indicators[symbol]['1h']['indicators']

                momentum = ind.get('momentum_20', 0)
                macd = ind.get('MACD', 0)
                macd_signal = ind.get('MACD_Signal', 0)

                # Strong momentum + MACD crossover
                if momentum > 0.02 and macd > macd_signal:
                    return 'buy'
                elif momentum < -0.02 and macd < macd_signal:
                    return 'sell'

        except Exception as e:
            logger.debug(f"Momentum agent error for {symbol}: {str(e)}")

        return None

    def _get_volume_agent_signal(self, symbol: str) -> Optional[str]:
        """Señal del agente volume analysis"""
        try:
            # Analizar volume y VWAP
            if '1h' in self.indicators.get(symbol, {}):
                ind = self.indicators[symbol]['1h']['indicators']

                volume_ratio = ind.get('volume_ratio', 1)
                vwap_dev = ind.get('vwap_deviation', 0)

                # High volume + price above VWAP
                if volume_ratio > 1.5 and vwap_dev > 0.005:
                    return 'buy'
                elif volume_ratio > 1.5 and vwap_dev < -0.005:
                    return 'sell'

        except Exception as e:
            logger.debug(f"Volume agent error for {symbol}: {str(e)}")

        return None

    async def _notify_callbacks(self, symbol: str):
        """Notificar callbacks de updates"""
        for callback in self.callbacks:
            try:
                await callback(symbol, self.get_symbol_data(symbol))
            except Exception as e:
                logger.error(f"Error in callback: {str(e)}")

    def get_symbol_data(self, symbol: str) -> Dict:
        """Obtener todos los datos de un símbolo"""
        return {
            'streams': self.streams.get(symbol, {}),
            'indicators': self.indicators.get(symbol, {}),
            'signals': self.signals.get(symbol, {}),
            'consensus_signals': self.consensus_signals.get(symbol, []),
            'swarm_data': self.swarm_agents.get(symbol, {})
        }

    def get_all_data(self) -> Dict:
        """Obtener datos de todos los símbolos"""
        return {symbol: self.get_symbol_data(symbol) for symbol in self.symbols}

# WebSocket server para streaming en tiempo real
class RealtimeWebSocketServer:
    """Servidor WebSocket para streaming de datos en tiempo real"""

    def __init__(self, streamer: MultiTimeframeStreamer, host: str = 'localhost', port: int = 8765):
        self.streamer = streamer
        self.host = host
        self.port = port
        self.connected_clients = set()

    async def websocket_handler(self, websocket, path):
        """Manejador de conexiones WebSocket"""
        self.connected_clients.add(websocket)
        logger.info(f"Cliente WebSocket conectado: {len(self.connected_clients)} total")

        try:
            # Enviar datos iniciales
            await websocket.send(json.dumps({
                'type': 'initial_data',
                'data': self.streamer.get_all_data()
            }))

            # Mantener conexión y enviar updates
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get('type') == 'subscribe':
                        # Cliente solicita datos específicos
                        symbols = data.get('symbols', [])
                        response = {
                            'type': 'subscription_data',
                            'data': {symbol: self.streamer.get_symbol_data(symbol) for symbol in symbols}
                        }
                        await websocket.send(json.dumps(response))

                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Invalid JSON message'
                    }))

        except websockets.exceptions.ConnectionClosed:
            logger.info("Cliente WebSocket desconectado")
        finally:
            self.connected_clients.remove(websocket)

    async def broadcast_update(self, symbol: str, data: Dict):
        """Broadcast update a todos los clientes conectados"""
        if not self.connected_clients:
            return

        message = json.dumps({
            'type': 'realtime_update',
            'symbol': symbol,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        })

        # Enviar a todos los clientes
        disconnected = set()
        for websocket in self.connected_clients:
            try:
                await websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(websocket)

        # Limpiar clientes desconectados
        self.connected_clients -= disconnected

    async def start_server(self):
        """Iniciar servidor WebSocket"""
        server = await websockets.serve(
            self.websocket_handler,
            self.host,
            self.port
        )

        logger.info(f"Servidor WebSocket iniciado en ws://{self.host}:{self.port}")

        # Configurar callback en streamer
        self.streamer.add_callback(self.broadcast_update)

        await server.wait_closed()

# Funciones de utilidad
def start_realtime_streaming(symbols: List[str] = None) -> MultiTimeframeStreamer:
    """Iniciar streaming multi-timeframe"""
    streamer = MultiTimeframeStreamer(symbols)

    def run_async():
        asyncio.run(streamer.start_streaming())

    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()

    return streamer

def start_websocket_server(streamer: MultiTimeframeStreamer, host: str = 'localhost', port: int = 8765):
    """Iniciar servidor WebSocket"""
    server = RealtimeWebSocketServer(streamer, host, port)

    def run_server():
        asyncio.run(server.start_server())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    return server

# Ejemplo de uso
if __name__ == "__main__":
    # Iniciar streaming
    symbols = ['XAU/USD', 'EUR/USD', 'BTC/USD']
    streamer = start_realtime_streaming(symbols)

    # Iniciar WebSocket server
    ws_server = start_websocket_server(streamer)

    print("Multi-timeframe real-time streaming iniciado")
    print(f"WebSocket server: ws://localhost:8765")
    print("Presiona Ctrl+C para detener")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Deteniendo streaming...")
        streamer.stop_streaming()