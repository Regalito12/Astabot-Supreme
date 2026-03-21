# ml_model.py
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import joblib
from data_fetch import get_candles_yfinance
from indicadores import aplicar_indicadores
from config import SUPPORTED_ASSETS

MODEL_FILE = "trading_model.pkl"

def prepare_data(symbol, period="1y"):
    """Preparar datos históricos para ML."""
    df = get_candles_yfinance(symbol, interval="1h", outputsize=1000)
    if df.empty:
        return pd.DataFrame()

    df = aplicar_indicadores(df)

    # Crear target: 1 si precio sube en 4 horas, 0 si baja
    df['target'] = (df['close'].shift(-4) > df['close']).astype(int)

    # Features
    features = ['close', 'volume', 'ADX', 'ATR', 'EMA200']
    df = df.dropna()
    return df[features + ['target']]

def train_model(symbol):
    """Entrenar modelo de ML."""
    df = prepare_data(symbol)
    if df.empty:
        return None

    X = df.drop('target', axis=1)
    y = df['target']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    print(f"Precisión del modelo para {symbol}: {accuracy:.2f}")

    joblib.dump(model, MODEL_FILE)
    return model

def predict_signal(symbol):
    """Predecir señal usando modelo entrenado."""
    try:
        model = joblib.load(MODEL_FILE)
    except:
        print("Modelo no encontrado, entrenando...")
        model = train_model(symbol)
        if not model:
            return None

    df = prepare_data(symbol, period="1mo")  # Datos recientes
    if df.empty:
        return None

    latest = df.iloc[-1].drop('target').values.reshape(1, -1)
    prediction = model.predict(latest)[0]
    return "buy" if prediction == 1 else "sell"

if __name__ == "__main__":
    # Entrenar para XAU/USD
    train_model("XAU/USD")