# tests.py
import unittest
import pandas as pd
from datetime import datetime
import sys
import os

# Añadir el directorio raíz al path para importar módulos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import params
from indicadores import aplicar_indicadores, validar_vwap
from analizador_oro import decidir_senal, validar_tendencia, vela_rechazo
from data_fetch import get_candles_yfinance  # Usar yfinance para tests

class TestIndicadores(unittest.TestCase):
    def setUp(self):
        # Crear datos de prueba
        self.df = pd.DataFrame({
            'datetime': pd.date_range('2023-01-01', periods=50, freq='5min'),
            'open': [100 + i*0.1 for i in range(50)],
            'high': [101 + i*0.1 for i in range(50)],
            'low': [99 + i*0.1 for i in range(50)],
            'close': [100.5 + i*0.1 for i in range(50)],
            'volume': [1000 + i*10 for i in range(50)]
        })

    def test_aplicar_indicadores(self):
        df_result = aplicar_indicadores(self.df.copy())
        self.assertIn('VWAP', df_result.columns)
        self.assertIn('ADX', df_result.columns)
        self.assertIn('ATR', df_result.columns)
        self.assertGreater(len(df_result), 0)

    def test_validar_vwap(self):
        df_ind = aplicar_indicadores(self.df.copy())
        vwap_valid = validar_vwap(df_ind, umbral_pct=0.005)
        self.assertEqual(len(vwap_valid), len(df_ind))
        self.assertTrue(all(isinstance(x, bool) for x in vwap_valid))

class TestAnalizador(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            'datetime': pd.date_range('2023-01-01', periods=200, freq='5min'),
            'open': [100 + i*0.01 for i in range(200)],
            'high': [101 + i*0.01 for i in range(200)],
            'low': [99 + i*0.01 for i in range(200)],
            'close': [100.5 + i*0.01 for i in range(200)],
            'volume': [1000 + i for i in range(200)]
        })
        self.df = aplicar_indicadores(self.df)

    def test_validar_tendencia_buy(self):
        result = validar_tendencia(self.df, direction="buy")
        self.assertIsInstance(result, bool)

    def test_validar_tendencia_sell(self):
        result = validar_tendencia(self.df, direction="sell")
        self.assertIsInstance(result, bool)

    def test_vela_rechazo(self):
        vela = self.df.iloc[-1]
        result = vela_rechazo(vela)
        self.assertIn(result, ["buy", "sell", ""])

    def test_decidir_senal(self):
        signal = decidir_senal(self.df)
        self.assertIsInstance(signal, (dict, type(None)))
        if signal:
            self.assertIn('tipo', signal)
            self.assertIn('score', signal)

class TestDataFetch(unittest.TestCase):
    def test_get_candles_yfinance(self):
        df = get_candles_yfinance("XAU/USD", interval="1h", outputsize=10)
        self.assertIsInstance(df, pd.DataFrame)
        if not df.empty:
            self.assertIn('datetime', df.columns)
            self.assertIn('close', df.columns)

if __name__ == '__main__':
    unittest.main()