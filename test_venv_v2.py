import time, sys
print(f"Python: {sys.executable}")

def test_m(name):
    t0 = time.time()
    print(f"Loading {name}...", end="", flush=True)
    try:
        __import__(name)
        print(f" OK ({time.time()-t0:.1f}s)")
    except Exception as e:
        print(f" FAILED: {e}")

modules = [
    "pandas",
    "ta",
    "telegram",
    "sklearn",
    "xgboost",
    "optuna",
    "joblib",
    "config",
    "data_fetch",
    "indicadores",
    "registro_signals",
    "utils",
    "realtime_streaming",
    "reinforcement_learning",
    "sentiment_analysis",
    "portfolio_optimization",
    "fundamental_data",
    "market_regime",
    "htf_memory",
    "performance_utils",
    "advanced_ml",
    "models",
    "risk_manager",
    "live_trading",
    "bot_auto"
]

for m in modules:
    test_m(m)

print("ALL IMPORTS OK - Test finished.")
