import sys
import os
import logging

# Ensure we can import from current directory
sys.path.append(os.getcwd())

from data_fetch import get_candles
from config import TWELVE_API_KEY

logging.basicConfig(level=logging.INFO)

def test_api():
    symbol = "XAU/USD"
    print(f"Testing market data API for {symbol}...")
    print(f"Using TwelveData Key: {TWELVE_API_KEY[:4]}...{TWELVE_API_KEY[-4:]}")
    
    try:
        df = get_candles(symbol, interval="5min", output_size=10)
        if not df.empty:
            print("API SUCCESS: Data received.")
            print(df.tail())
        else:
            print("API FAILURE: No data received.")
    except Exception as e:
        print(f"API EXCEPTION: {e}")

if __name__ == "__main__":
    test_api()
