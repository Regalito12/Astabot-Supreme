# fundamental_data.py
import requests
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def get_economic_indicators():
    """Obtiene datos económicos clave (ej. inflación, empleo)."""
    # Usar FRED API (Federal Reserve Economic Data) - gratuita
    api_key = "YOUR_FRED_API_KEY"  # Reemplaza
    indicators = {
        'inflation': 'CPIAUCSL',  # CPI (inflación)
        'unemployment': 'UNRATE',  # Tasa desempleo
        'gdp': 'GDP',  # PIB
        'interest_rate': 'FEDFUNDS'  # Tasa federal
    }

    data = {}
    for name, series_id in indicators.items():
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json"
        try:
            response = requests.get(url)
            observations = response.json().get('observations', [])
            latest = observations[-1] if observations else {}
            data[name] = {
                'value': float(latest.get('value', 0)),
                'date': latest.get('date', '')
            }
        except Exception as e:
            logger.error(f"Error obteniendo {name}: {e}")
            data[name] = {'value': 0, 'date': ''}

    return data

def assess_market_impact(economic_data):
    """Evalúa impacto de datos económicos en mercado."""
    impact = 0

    # Inflación alta -> posible debilidad USD
    if economic_data['inflation']['value'] > 3.0:
        impact -= 0.1  # Bearish para USD pares

    # Desempleo bajo -> fortaleza economía
    if economic_data['unemployment']['value'] < 4.0:
        impact += 0.1

    # Tasa interés alta -> fortaleza USD
    if economic_data['interest_rate']['value'] > 4.0:
        impact += 0.1

    return impact  # -1 a 1

# Integración en analizador_oro.py
# En analizar_mercado:
# economic_data = get_economic_indicators()
# market_impact = assess_market_impact(economic_data)
# if market_impact > 0.1 and signal_data['tipo'] == 'buy':
#     signal_data['score'] += 1  # Bonus por datos fundamentales positivos