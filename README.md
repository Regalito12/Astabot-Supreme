# Astabot - Sistema de Trading Automatizado

Astabot es un bot de Telegram para análisis y trading automatizado de pares XAU/USD y EUR/USD, utilizando estrategias de confluencia técnica.

## Características

- **Análisis Automático**: Cada 5 minutos analiza el mercado y envía señales de alta confianza.
- **Análisis Manual**: Comando `/analizar` para análisis on-demand.
- **Backtesting**: Simula estrategias históricas con parámetros personalizables.
- **Gestión de Riesgos**: Stop Loss y Take Profit basados en ATR.
- **Configurable**: Parámetros ajustables vía `params.json`.

## Instalación

1. Clona el repositorio.
2. Instala dependencias: `pip install -r requirements.txt`
3. Configura tokens en `config.py`:
   - `TELEGRAM_TOKEN`: Tu token de BotFather.
   - `CHAT_ID`: Tu ID de Telegram.
   - `TWELVE_API_KEY`: API key de TwelveData (opcional, fallback a yfinance).
4. Ejecuta: `python bot_auto.py`

## Uso

### Comandos de Telegram
- `/start`: Inicia el bot.
- `/analizar`: Selecciona activo para análisis manual.
- `/backtest`: Ejecuta backtesting histórico con opciones personalizables.

### Backtesting
- Personaliza capital inicial, período e intervalo.
- Resultados incluyen win rate, P&L, drawdown y profit factor.

### Configuración
Edita `params.json` para ajustar indicadores:
- `ADX_THRESH`: Umbral ADX.
- `ATR_WINDOW`: Ventana ATR.
- etc.

## Dependencias

- python-telegram-bot
- pandas
- yfinance
- ta (technical analysis)
- requests

## Pruebas

Ejecuta tests: `python -m pytest tests.py`

## Estructura del Proyecto

- `analizador_oro.py`: Lógica de estrategia y señales.
- `data_fetch.py`: Obtención de datos de mercado.
- `indicadores.py`: Cálculo de indicadores técnicos.
- `backtesting.py`: Simulación histórica.
- `bot_auto.py`: Interfaz de Telegram.
- `config.py`: Configuraciones y parámetros.
- `registro_signals.py`: Logging de señales.

## Notas de Seguridad

- No uses en producción sin backtesting exhaustivo.
- Gestiona riesgos; el bot no garantiza ganancias.
- Monitorea logs para errores.

## Licencia

MIT License.