# portfolio_optimization.py
import pandas as pd
import numpy as np
# from pypfopt import EfficientFrontier, risk_models, expected_returns  # Deshabilitado por dependencias
import logging

logger = logging.getLogger(__name__)

def optimize_portfolio(returns_df, risk_free_rate=0.02):
    """
    Optimiza portfolio usando Markowitz (versión simplificada sin pypfopt).
    returns_df: DataFrame con retornos de cada activo (columnas = símbolos).
    """
    try:
        # Versión simplificada: asignación igual ponderada
        n_assets = len(returns_df.columns)
        equal_weight = 1.0 / n_assets
        weights = {col: equal_weight for col in returns_df.columns}

        # Calcular métricas simples
        mu = returns_df.mean() * 252  # Retorno anualizado
        S = returns_df.cov() * 252    # Covarianza anualizada
        expected_return = np.dot(list(weights.values()), mu)
        volatility = np.sqrt(np.dot(list(weights.values()), np.dot(S.values, list(weights.values()))))
        sharpe_ratio = (expected_return - risk_free_rate) / volatility if volatility > 0 else 0

        return {
            'weights': weights,
            'expected_return': expected_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio
        }
    except Exception as e:
        logger.error(f"Error en optimización: {e}")
        return None

def get_historical_returns(symbols, period="1y"):
    """Obtiene retornos históricos para símbolos."""
    from data_fetch import get_candles_yfinance
    returns = {}
    for symbol in symbols:
        df = get_candles_yfinance(symbol, interval="1d", outputsize=365)  # 1 año diario
        if not df.empty:
            df['returns'] = df['close'].pct_change()
            returns[symbol] = df['returns'].dropna()
    return pd.DataFrame(returns)

# Integración en backtesting.py o analizador_oro.py
def allocate_capital(signals, total_capital=10000):
    """Asigna capital basado en optimización."""
    if not signals:
        return {}

    symbols = [s['symbol'] for s in signals]
    returns_df = get_historical_returns(symbols)
    if returns_df.empty:
        # Fallback: asignación igual
        weight = 1 / len(signals)
        return {s['symbol']: total_capital * weight for s in signals}

    opt = optimize_portfolio(returns_df)
    if opt:
        # Ajustar pesos basado en señales activas
        active_weights = {k: v for k, v in opt['weights'].items() if k in symbols}
        total_active = sum(active_weights.values())
        if total_active > 0:
            normalized = {k: (v / total_active) * total_capital for k, v in active_weights.items()}
            return normalized

    # Fallback
    weight = total_capital / len(signals)
    return {s['symbol']: weight for s in signals}