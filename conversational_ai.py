# conversational_ai.py - IA Conversacional Avanzada para Astabot
import openai
import speech_recognition as sr
import pyttsx3
import logging
from datetime import datetime, timedelta
import json
import re
from typing import Dict, List, Optional, Tuple
import threading
import time

from config import OPENAI_API_KEY
from analytics import AnalyticsEngine
from advanced_ml import predict_advanced_signal, get_ml_insights
from live_trading import get_live_trading_manager
from data_fetch import get_candles
from models import db, User, Signal, Trade

logger = logging.getLogger(__name__)

class ConversationalAI:
    """IA Conversacional Avanzada con integración ChatGPT"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API key required")

        openai.api_key = self.api_key

        # Configurar voz
        self.voice_engine = pyttsx3.init()
        self.voice_engine.setProperty('rate', 180)
        self.voice_engine.setProperty('volume', 0.9)

        # Configurar reconocimiento de voz
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

        # Historial de conversación
        self.conversation_history = []

        # Contexto del usuario
        self.user_context = {}

        # Comandos disponibles
        self.commands = {
            'analyze': self.analyze_market,
            'predict': self.predict_with_ml,
            'report': self.generate_report,
            'suggest': self.suggest_strategy,
            'trade': self.execute_trade,
            'status': self.get_system_status,
            'help': self.get_help
        }

    def chat_with_ai(self, user_message: str, user_id: int = None) -> str:
        """Conversación principal con ChatGPT"""

        # Añadir contexto del usuario
        if user_id:
            self._load_user_context(user_id)

        # Preparar prompt con contexto
        system_prompt = self._build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            *self.conversation_history[-10:],  # Últimos 10 mensajes
            {"role": "user", "content": user_message}
        ]

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )

            ai_response = response.choices[0].message.content

            # Guardar en historial
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": ai_response})

            # Procesar comandos si los hay
            command_result = self._process_commands(user_message, user_id)
            if command_result:
                ai_response += f"\n\n{command_result}"

            return ai_response

        except Exception as e:
            logger.error(f"Error en chat GPT: {str(e)}")
            return "Lo siento, tuve un problema procesando tu mensaje. ¿Puedes intentarlo de nuevo?"

    def voice_command(self, user_id: int = None) -> Tuple[str, str]:
        """Procesar comando de voz"""

        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)
            print("Escuchando...")

            try:
                audio = self.recognizer.listen(source, timeout=5)
                text = self.recognizer.recognize_google(audio, language='es-ES')

                print(f"Comando de voz: {text}")

                # Procesar comando
                response = self.chat_with_ai(text, user_id)

                # Responder por voz
                self.speak_response(response)

                return text, response

            except sr.WaitTimeoutError:
                return "", "No escuché ningún comando"
            except sr.UnknownValueError:
                return "", "No pude entender el audio"
            except sr.RequestError as e:
                return "", f"Error en servicio de reconocimiento: {e}"

    def speak_response(self, text: str):
        """Convertir texto a voz"""

        # Limpiar texto para voz
        clean_text = re.sub(r'[^\w\s.,!?]', '', text)
        clean_text = clean_text[:200]  # Limitar longitud

        try:
            self.voice_engine.say(clean_text)
            self.voice_engine.runAndWait()
        except Exception as e:
            logger.error(f"Error en síntesis de voz: {str(e)}")

    def analyze_market(self, params: Dict) -> str:
        """Análisis de mercado conversacional"""

        symbol = params.get('symbol', 'XAU/USD')

        try:
            # Obtener datos recientes
            df = get_candles(symbol, interval="1h", outputsize=50)

            if df.empty:
                return f"No pude obtener datos para {symbol}"

            latest = df.iloc[-1]

            # Análisis básico
            analysis = f"""
📊 Análisis de {symbol}:

Precio actual: ${latest['close']:.4f}
Cambio 24h: {((latest['close'] - df.iloc[-24]['close']) / df.iloc[-24]['close'] * 100):.2f}%

Indicadores técnicos:
• RSI: {latest.get('RSI', 'N/A'):.1f}
• MACD: {latest.get('MACD', 'N/A'):.4f}
• ADX: {latest.get('ADX', 'N/A'):.1f}

Tendencia: {'Alcista' if latest.get('close', 0) > latest.get('EMA200', 0) else 'Bajista'}
"""

            return analysis

        except Exception as e:
            return f"Error analizando {symbol}: {str(e)}"

    def predict_with_ml(self, params: Dict) -> str:
        """Predicción con ML"""

        symbol = params.get('symbol', 'XAU/USD')

        try:
            prediction = predict_advanced_signal(symbol)

            if 'error' in prediction:
                return f"Error en predicción: {prediction['error']}"

            response = f"""
🤖 Predicción ML para {symbol}:

Señal: {prediction['signal'].upper()}
Confianza: {prediction['confidence']}%
Fuerza: {prediction['strength']}

Probabilidades:
• Compra: {prediction['probabilities']['buy']}%
• Venta: {prediction['probabilities']['sell']}%

Modelo usado: {prediction['model']}
"""

            return response

        except Exception as e:
            return f"Error en predicción ML: {str(e)}"

    def generate_report(self, params: Dict) -> str:
        """Generar reporte automatizado"""

        user_id = params.get('user_id')
        period = params.get('period', '7d')

        try:
            # Obtener analytics
            analytics = AnalyticsEngine.get_performance_dashboard(user_id, days=self._parse_period(period))

            # Obtener insights ML
            insights = get_ml_insights('XAU/USD')  # Ejemplo

            report = f"""
📈 Reporte Automatizado - Período: {period}

📊 Rendimiento General:
• Señales Totales: {analytics.get('total_signals', 0)}
• Win Rate: {analytics.get('win_rate', 0):.1%}
• Profit Factor: {analytics.get('profit_factor', 0):.2f}
• Max Drawdown: {analytics.get('max_drawdown', 0):.1%}

🤖 Insights de Machine Learning:
• Mejor Modelo: {insights.get('best_model', 'N/A')}
• Features Importantes: RSI, Momentum, Volume

💡 Recomendaciones:
• {'Aumentar' if analytics.get('win_rate', 0) < 0.5 else 'Mantener'} frecuencia de trading
• {'Revisar' if analytics.get('max_drawdown', 0) > 0.15 else 'Continuar'} gestión de riesgo
• Considerar {insights.get('best_model', 'ensemble')} para predicciones
"""

            return report

        except Exception as e:
            return f"Error generando reporte: {str(e)}"

    def suggest_strategy(self, params: Dict) -> str:
        """Sugerencias de estrategia basadas en ML"""

        symbol = params.get('symbol', 'XAU/USD')
        risk_level = params.get('risk', 'medium')

        try:
            # Obtener predicción ML
            prediction = predict_advanced_signal(symbol)

            # Obtener analytics
            analytics = AnalyticsEngine.get_performance_dashboard(params.get('user_id'))

            # Generar sugerencias
            suggestions = []

            if prediction['confidence'] > 70:
                if prediction['signal'] == 'buy':
                    suggestions.append(f"Considerar entrada larga en {symbol} con alta confianza")
                elif prediction['signal'] == 'sell':
                    suggestions.append(f"Considerar entrada corta en {symbol} con alta confianza")

            if analytics.get('win_rate', 0) > 0.6:
                suggestions.append("Tu estrategia actual está funcionando bien, continuar")
            else:
                suggestions.append("Considerar ajustar parámetros o cambiar timeframe")

            if risk_level == 'low':
                suggestions.append("Usar stop loss más amplio y position size reducido")
            elif risk_level == 'high':
                suggestions.append("Considerar scalping o day trading con stops ajustados")

            response = f"""
🎯 Sugerencias de Estrategia para {symbol}:

{chr(10).join(f"• {s}" for s in suggestions)}

Parámetros recomendados:
• Risk por trade: {1 if risk_level == 'low' else 2 if risk_level == 'medium' else 5}%
• Timeframe: {'4h' if risk_level == 'low' else '1h' if risk_level == 'medium' else '15m'}
• Stop Loss: {2 if risk_level == 'low' else 1.5 if risk_level == 'medium' else 1}%
"""

            return response

        except Exception as e:
            return f"Error generando sugerencias: {str(e)}"

    def execute_trade(self, params: Dict) -> str:
        """Ejecutar trade por voz/comando"""

        user_id = params.get('user_id')
        account_id = params.get('account_id')
        symbol = params.get('symbol')
        side = params.get('side')
        quantity = params.get('quantity')

        if not all([user_id, account_id, symbol, side, quantity]):
            return "Faltan parámetros para ejecutar trade"

        try:
            trading_manager = get_live_trading_manager()
            result = trading_manager.place_order(
                user_id=user_id,
                account_id=account_id,
                symbol=symbol,
                order_type='market',
                side=side,
                quantity=float(quantity)
            )

            if 'order_id' in result:
                return f"✅ Trade ejecutado exitosamente! Order ID: {result['order_id']}"
            else:
                return f"❌ Error ejecutando trade: {result.get('error', 'Unknown error')}"

        except Exception as e:
            return f"Error ejecutando trade: {str(e)}"

    def get_system_status(self, params: Dict) -> str:
        """Estado del sistema"""

        try:
            # Verificar conexiones
            trading_manager = get_live_trading_manager()
            active_accounts = len(trading_manager.active_accounts)

            status = f"""
🔍 Estado del Sistema Astabot:

🤖 IA Conversacional: ✅ Activa
📊 Analytics Engine: ✅ Operativo
🤖 Machine Learning: ✅ Modelos cargados
💰 Trading Live: {'✅' if active_accounts > 0 else '⚠️'} {active_accounts} cuentas activas

📈 Rendimiento Reciente:
• Señales del día: {Signal.query.filter(Signal.created_at >= datetime.utcnow().date()).count()}
• Trades ejecutados: {Trade.query.filter(Trade.created_at >= datetime.utcnow().date()).count()}

💡 Sistema funcionando correctamente
"""

            return status

        except Exception as e:
            return f"Error obteniendo status: {str(e)}"

    def get_help(self, params: Dict) -> str:
        """Ayuda y comandos disponibles"""

        help_text = """
🆘 Ayuda - Comandos Disponibles:

🎯 Análisis:
• "analiza XAU/USD" - Análisis técnico
• "predice EUR/USD" - Predicción con ML
• "¿cómo está el mercado?" - Estado general

📊 Reportes:
• "genera reporte semanal" - Reporte automático
• "muestra estadísticas" - Analytics detallados

💡 Sugerencias:
• "sugiere estrategia conservadora" - Recomendaciones
• "qué debo hacer ahora" - Advice personalizado

💰 Trading:
• "compra 0.01 XAU/USD" - Ejecutar trade
• "vende 100 EUR/USD" - Cerrar posición

🔊 Voz:
• Di "Astabot" + comando para activar voz

📞 Soporte:
• Pregunta cualquier cosa sobre trading, análisis o sistema
"""

        return help_text

    def _process_commands(self, message: str, user_id: int) -> Optional[str]:
        """Procesar comandos en mensajes"""

        message_lower = message.lower()

        # Patrones de comandos
        patterns = {
            'analyze': r'analiz[ae]\s+(\w+/\w+)',
            'predict': r'predi[cs]e?\s+(\w+/\w+)',
            'report': r'(?:genera|muestra)\s+reporte\s+(\w+)',
            'suggest': r'sugiere\s+estrategia\s+(\w+)',
            'trade_buy': r'compra\s+([\d.]+)\s+(\w+/\w+)',
            'trade_sell': r'vende\s+([\d.]+)\s+(\w+/\w+)',
        }

        for command, pattern in patterns.items():
            match = re.search(pattern, message_lower)
            if match:
                params = {'user_id': user_id}

                if command in ['analyze', 'predict']:
                    params['symbol'] = match.group(1).upper()
                elif command == 'report':
                    params['period'] = match.group(1)
                elif command == 'suggest':
                    params['risk'] = match.group(1)
                elif command in ['trade_buy', 'trade_sell']:
                    params.update({
                        'quantity': match.group(1),
                        'symbol': match.group(2).upper(),
                        'side': 'buy' if command == 'trade_buy' else 'sell'
                    })
                    # Obtener account_id del usuario (lógica simplificada)
                    params['account_id'] = self._get_user_default_account(user_id)

                return self.commands[command.split('_')[0]](params)

        return None

    def _build_system_prompt(self) -> str:
        """Construir prompt del sistema"""

        prompt = """
Eres Astabot, un asistente de IA avanzado especializado en trading automatizado.

Tus capacidades incluyen:
- Análisis técnico de mercados financieros
- Predicciones usando machine learning avanzado
- Generación de reportes automatizados
- Sugerencias de estrategias de trading
- Ejecución de trades en vivo
- Análisis de rendimiento y estadísticas

Comandos disponibles:
- Análisis: "analiza XAU/USD", "¿cómo está el mercado?"
- Predicciones: "predice EUR/USD", "qué va a pasar?"
- Reportes: "genera reporte semanal", "muestra estadísticas"
- Sugerencias: "sugiere estrategia", "qué debo hacer?"
- Trading: "compra 0.01 XAU/USD", "vende 100 EUR/USD"

Sé conversacional, útil y preciso. Si no entiendes algo, pide aclaración.
Proporciona insights accionables basados en datos reales.
"""

        return prompt

    def _load_user_context(self, user_id: int):
        """Cargar contexto del usuario"""

        try:
            user = User.query.get(user_id)
            if user:
                self.user_context = {
                    'name': user.username,
                    'risk_level': getattr(user, 'risk_level', 'medium'),
                    'preferred_symbols': getattr(user, 'preferred_symbols', ['XAU/USD']),
                    'total_trades': Trade.query.filter_by(user_id=user_id).count(),
                    'win_rate': self._calculate_user_win_rate(user_id)
                }
        except Exception as e:
            logger.error(f"Error cargando contexto usuario: {str(e)}")

    def _calculate_user_win_rate(self, user_id: int) -> float:
        """Calcular win rate del usuario"""

        trades = Trade.query.filter_by(user_id=user_id).all()
        if not trades:
            return 0.0

        winning_trades = sum(1 for trade in trades if trade.pnl and trade.pnl > 0)
        return winning_trades / len(trades)

    def _parse_period(self, period_str: str) -> int:
        """Parsear período a días"""

        period_map = {
            'diario': 1, 'semanal': 7, 'mensual': 30,
            'day': 1, 'week': 7, 'month': 30
        }

        return period_map.get(period_str.lower(), 7)

    def _get_user_default_account(self, user_id: int) -> Optional[str]:
        """Obtener cuenta por defecto del usuario"""

        from models import TradingAccount
        account = TradingAccount.query.filter_by(user_id=user_id, is_active=True).first()
        return account.account_id if account else None

# Instancia global
conversational_ai = ConversationalAI()

def get_conversational_ai():
    return conversational_ai

# Funciones de utilidad
def chat_with_ai(message: str, user_id: int = None) -> str:
    """Función de conveniencia para chat"""
    return conversational_ai.chat_with_ai(message, user_id)

def voice_command(user_id: int = None) -> Tuple[str, str]:
    """Función de conveniencia para voz"""
    return conversational_ai.voice_command(user_id)

if __name__ == "__main__":
    # Ejemplo de uso
    ai = ConversationalAI()

    # Chat de texto
    response = ai.chat_with_ai("¿Cómo está el mercado de oro?")
    print("Respuesta:", response)

    # Comando de voz (requiere micrófono)
    # text, response = ai.voice_command()
    # print(f"Comando: {text}")
    # print(f"Respuesta: {response}")