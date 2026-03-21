# backtesting.py
import pandas as pd
import logging
import yfinance as yf
import yfinance as yf
from datetime import datetime, timedelta
from config import params, SUPPORTED_ASSETS
from data_fetch import get_candles_yfinance  # Usamos yfinance para datos históricos largos
from indicadores import aplicar_indicadores
from analizador_oro import decidir_senal, mercado_abierto

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Parámetros de backtesting
INITIAL_CAPITAL = 10000  # Capital inicial en USD
RISK_PER_TRADE = 0.01  # 1% de capital por trade
COMMISSION = 0.0001  # Comisión por trade (0.01%)

def get_historical_data(symbol, period="1y", interval="5min"):
    """
    Obtiene datos históricos largos usando yfinance.
    """
    ticker_map = {
        "XAU/USD": "GC=F",
        "EUR/USD": "EURUSD=X",
        "BTC/USD": "BTC-USD",
        "ETH/USD": "ETH-USD",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "JPY=X"
    }
    ticker = ticker_map.get(symbol)
    if not ticker:
        # Fallback for other forex pairs if not in map
        if "/" in symbol:
            ticker = f"{symbol.replace('/', '')}=X"
        else:
            raise ValueError(f"Símbolo {symbol} no soportado o mapeo no encontrado")

    try:
        # Note: yfinance uses ticker format like 'BTC-USD'
        df = get_candles_yfinance(symbol, interval, outputsize=10000)  # Usa outputsize para más datos históricos
        if df.empty:
            raise ValueError("No se obtuvieron datos históricos")
        return df
    except Exception as e:
        logging.error(f"Error obteniendo datos históricos para {symbol} ({ticker}): {e}")
        return pd.DataFrame()

def simulate_trades(df, symbol):
    """
    Simula trades basados en la estrategia.
    Devuelve lista de trades y métricas.
    """
    trades = []
    capital = INITIAL_CAPITAL
    peak_capital = capital
    max_drawdown = 0
    in_trade = False
    entry_price = 0
    sl = 0
    tp = 0
    trade_type = ""

    for i in range(len(df)):
        vela = df.iloc[i]
        # Para BTC, el mercado nunca cierra. Para otros activos, se comprueba el horario.
        if symbol.upper() != 'BTC/USD' and not mercado_abierto():
            continue

        # Aplicar indicadores en ventana deslizante
        window_df = df.iloc[max(0, i-200):i+1]  # Últimas 200 velas para indicadores
        if len(window_df) < 50:  # Suficientes datos para EMA50
            continue
        window_df = aplicar_indicadores(window_df.copy())
        signal = decidir_senal(window_df)

        if signal and not in_trade:
            # Entrar en trade
            entry_price = vela['close']
            atr = vela.get('ATR', 0)
            if atr == 0: continue # Evitar division por cero si ATR es 0

            if signal['tipo'] == 'buy':
                sl = entry_price - atr * params['SL_ATR_MULT']
                tp = entry_price + atr * params['TP_ATR_MULT']
            else:  # sell
                sl = entry_price + atr * params['SL_ATR_MULT']
                tp = entry_price - atr * params['TP_ATR_MULT']

            if abs(entry_price - sl) == 0: continue # Evitar division por cero

            position_size = (capital * RISK_PER_TRADE) / abs(entry_price - sl)  # Tamaño basado en riesgo
            in_trade = True
            trade_type = signal['tipo']
            entry_time = vela['datetime']
            logging.info(f"Entrada: {trade_type.upper()} en {entry_price:.4f} para {symbol}")

        elif in_trade:
            # Verificar salida
            current_price = vela['close']
            exit_reason = ""
            if trade_type == 'buy':
                if current_price >= tp:
                    exit_price = tp
                    exit_reason = "TP"
                elif current_price <= sl:
                    exit_price = sl
                    exit_reason = "SL"
                else:
                    continue  # No salir aún
            else:  # sell
                if current_price <= tp:
                    exit_price = tp
                    exit_reason = "TP"
                elif current_price >= sl:
                    exit_price = sl
                    exit_reason = "SL"
                else:
                    continue

            # Calcular P&L
            if trade_type == 'buy':
                pnl = (exit_price - entry_price) * position_size
            else:
                pnl = (entry_price - exit_price) * position_size
            pnl -= COMMISSION * position_size * entry_price  # Comisión

            capital += pnl
            peak_capital = max(peak_capital, capital)
            if peak_capital > 0:
                drawdown = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, drawdown)

            trades.append({
                'symbol': symbol,
                'type': trade_type,
                'entry_time': entry_time,
                'exit_time': vela['datetime'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'sl': sl,
                'tp': tp,
                'pnl': pnl,
                'exit_reason': exit_reason,
                'capital_after': capital
            })

            in_trade = False
            logging.info(f"Salida: {exit_reason} en {exit_price:.4f}, P&L: {pnl:.2f}")

    return trades, capital, max_drawdown

def calculate_metrics(trades, final_capital, max_drawdown):
    """
    Calcula métricas de rendimiento.
    """
    if not trades:
        return {"error": "No se realizaron trades"}

    total_trades = len(trades)
    winning_trades = [t for t in trades if t['pnl'] > 0]
    losing_trades = [t for t in trades if t['pnl'] <= 0]
    win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
    total_pnl = sum(t['pnl'] for t in trades)
    avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
    profit_factor = abs(sum(t['pnl'] for t in winning_trades) / sum(t['pnl'] for t in losing_trades)) if losing_trades and sum(t['pnl'] for t in losing_trades) != 0 else float('inf')

    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'final_capital': final_capital,
        'max_drawdown': max_drawdown,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor
    }

def run_backtest(symbol, period="1y", interval="5min", initial_capital=10000):
    """
    Ejecuta el backtest completo para un símbolo.
    initial_capital: Capital inicial en USD (default 10000)
    """
    global INITIAL_CAPITAL
    INITIAL_CAPITAL = initial_capital  # Actualizar variable global

    logging.info(f"Iniciando backtest para {symbol} en período {period} con capital ${initial_capital}")
    df = get_historical_data(symbol, period, interval)
    if df.empty:
        return {"error": "No se pudieron obtener datos históricos"}

    trades, final_capital, max_drawdown = simulate_trades(df, symbol)
    metrics = calculate_metrics(trades, final_capital, max_drawdown)

    # Guardar trades en CSV si hay
    if trades:
        trades_df = pd.DataFrame(trades)
        trades_df.to_csv(f"backtest_trades_{symbol.replace('/', '_')}.csv", index=False)

    return {
        'symbol': symbol,
        'metrics': metrics,
        'trades_count': len(trades)
    }

if __name__ == "__main__":
    # Ejemplo de uso: backtest para XAU/USD
    result = run_backtest("XAU/USD", period="6mo", interval="1h")  # Ajusta período e intervalo
    print("Resultados del Backtest:")
    print(result)