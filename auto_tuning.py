# auto_tuning.py
import itertools
import pandas as pd
from backtesting import run_backtest
import logging

logger = logging.getLogger(__name__)

def grid_search_optimization(symbol, param_grid, period="1y", interval="5min"):
    """
    Optimiza parámetros usando grid search basado en backtesting.
    param_grid: dict con listas de valores para cada parámetro.
    """
    best_params = None
    best_score = -float('inf')

    # Genera todas las combinaciones
    keys = param_grid.keys()
    values = param_grid.values()
    combinations = list(itertools.product(*values))

    for combo in combinations:
        params = dict(zip(keys, combo))
        logger.info(f"Probando parámetros: {params}")

        # Actualiza params globales temporalmente
        from config import params
        original_params = params.copy()
        params.update(params)

        # Corre backtest
        result = run_backtest(symbol, period=period, interval=interval)
        if "error" in result:
            continue

        metrics = result['metrics']
        score = metrics['win_rate'] * 0.5 + (1 - metrics['max_drawdown']) * 0.3 + metrics['profit_factor'] * 0.2

        if score > best_score:
            best_score = score
            best_params = params

        # Restaura params originales
        params.update(original_params)

    return best_params, best_score

# Ejemplo de uso
# param_grid = {
#     "ADX_THRESH": [20, 22, 25],
#     "VOL_WINDOW": [15, 20, 25],
#     "TP_ATR_MULT": [1.0, 1.5, 2.0]
# }
# best, score = grid_search_optimization("XAU/USD", param_grid)
# print(f"Mejores parámetros: {best}, Score: {score}")