# advanced_ml.py - Machine Learning Avanzado para Astabot
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectKBest, f_classif
import xgboost as xgb
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
import joblib
import os
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Imports para Reinforcement Learning
try:
    import gym
    from stable_baselines3 import PPO, A2C, SAC
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold
    RL_AVAILABLE = True
except ImportError:
    RL_AVAILABLE = False
    gym = None

from data_fetch import get_candles
from indicadores import aplicar_indicadores
from config import SUPPORTED_ASSETS

logger = logging.getLogger(__name__)

class AdvancedMLPredictor:
    """Motor de Machine Learning Avanzado para predicción de señales de trading"""

    def __init__(self, symbol: str, model_dir: str = "models"):
        self.symbol = symbol
        self.model_dir = model_dir
        self.models = {}
        self.scalers = {}
        self.feature_importance = {}
        self.best_params = {}

        # Crear directorio de modelos
        os.makedirs(model_dir, exist_ok=True)

        # Inicializar modelos ensemble
        self._initialize_models()

    def _initialize_models(self):
        """Inicializar modelos ensemble avanzados"""
        self.models = {
            'random_forest': RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1
            ),
            'xgboost': xgb.XGBClassifier(
                n_estimators=100,  # Aumentado para mayor capacidad
                max_depth=5,       # Reducido para evitar overfitting
                learning_rate=0.05, # Más lento para mejor precisión
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                use_label_encoder=False,
                eval_metric='logloss'
            ),
            'gradient_boosting': GradientBoostingClassifier(
                n_estimators=50,  # OPTIMIZADO: Reducido de 100 a 50
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42
            ),
            'neural_network': MLPClassifier(
                hidden_layer_sizes=(50, 25),  # OPTIMIZADO: Reducido de (100, 50, 25)
                activation='relu',
                solver='adam',
                alpha=0.001,
                learning_rate='adaptive',
                max_iter=500,
                random_state=42
            )
        }

        # Ensemble voting classifier
        estimators = [
            ('rf', self.models['random_forest']),
            ('xgb', self.models['xgboost']),
            ('gb', self.models['gradient_boosting']),
            ('nn', self.models['neural_network'])
        ]

        self.models['ensemble'] = VotingClassifier(
            estimators=estimators,
            voting='soft',  # Probabilidades
            weights=[0.3, 0.3, 0.2, 0.2]
        )

    def advanced_feature_engineering(self, df: pd.DataFrame) -> pd.DataFrame:
        """Feature engineering avanzado para señales de trading"""

        # Features básicas de precio
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

        # Momentum features
        for period in [5, 10, 20, 50]:
            df[f'momentum_{period}'] = df['close'] / df['close'].shift(period) - 1
            df[f'roc_{period}'] = ((df['close'] - df['close'].shift(period)) / df['close'].shift(period)) * 100

        # Volatility features
        df['volatility_20'] = df['returns'].rolling(20).std()
        df['volatility_50'] = df['returns'].rolling(50).std()
        df['volatility_ratio'] = df['volatility_20'] / df['volatility_50']

        # Volume features
        df['volume_ma_20'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma_20']
        df['volume_trend'] = df['volume'].pct_change(5)

        # Price patterns
        df['high_low_ratio'] = (df['high'] - df['low']) / df['close']
        df['open_close_ratio'] = (df['close'] - df['open']) / df['open']
        df['body_size'] = abs(df['close'] - df['open']) / (df['high'] - df['low'])

        # Trend strength
        df['trend_strength'] = abs(df['close'] - df['close'].shift(20)) / df['volatility_20']

        # Mean reversion
        df['zscore_20'] = (df['close'] - df['close'].rolling(20).mean()) / df['close'].rolling(20).std()
        df['zscore_50'] = (df['close'] - df['close'].rolling(50).mean()) / df['close'].rolling(50).std()

        # Bollinger Bands features - NUEVO
        if 'BB_High' in df.columns and 'BB_Low' in df.columns:
            df['bb_width'] = (df['BB_High'] - df['BB_Low']) / df['BB_Middle']
            df['bb_pct_b'] = (df['close'] - df['BB_Low']) / (df['BB_High'] - df['BB_Low'])
            df['bb_squeeze'] = (df['bb_width'] < df['bb_width'].rolling(100).mean()).astype(int)
        
        # Volatility Regime - NUEVO
        if 'ATR' in df.columns:
            df['atr_sma_20'] = df['ATR'].rolling(20).mean()
            df['volatility_regime'] = (df['ATR'] > df['atr_sma_20']).astype(int)

        # Technical indicators avanzados - OPTIMIZADO: Manejo de campos faltantes
        if 'RSI' in df.columns:
            df['rsi_divergence'] = df['RSI'] - df['RSI'].shift(10)
        if 'MACD' in df.columns and 'MACD_Signal' in df.columns:
            df['macd_signal_diff'] = df['MACD'] - df['MACD_Signal']
        # Removido: Stoch_K y Stoch_D no existen en indicadores.py

        # Volume-price analysis - OPTIMIZADO: Manejo seguro de VWAP
        if 'VWAP' in df.columns:
            df['vwap_deviation'] = (df['close'] - df['VWAP']) / df['VWAP']
        else:
            df['vwap_deviation'] = 0
        df['volume_price_trend'] = df['returns'] * df['volume_ratio']

        # Lagged features - OPTIMIZADO: Solo lags útiles [1, 3, 5]
        for lag in [1, 3, 5]:  # Removido lag=2 para reducir features
            df[f'returns_lag_{lag}'] = df['returns'].shift(lag)
            df[f'volume_lag_{lag}'] = df['volume_ratio'].shift(lag)

        # Rolling statistics
        for window in [5, 10, 20]:
            df[f'returns_mean_{window}'] = df['returns'].rolling(window).mean()
            df[f'returns_std_{window}'] = df['returns'].rolling(window).std()
            df[f'returns_skew_{window}'] = df['returns'].rolling(window).skew()
            df[f'returns_kurt_{window}'] = df['returns'].rolling(window).kurt()

        # Target variable: señal futura
        df['future_return_5'] = df['close'].shift(-5) / df['close'] - 1
        df['target'] = (df['future_return_5'] > 0.001).astype(int)  # Buy signal if > 0.1%

        # Limpiar NaN
        df = df.dropna()

        return df

    def prepare_data(self, df: pd.DataFrame, test_size: int = 0.2) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """Preparar datos para entrenamiento"""

        # Features a excluir
        exclude_cols = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'future_return_5']
        feature_cols = [col for col in df.columns if col not in exclude_cols]

        X = df[feature_cols]
        y = df['target']

        # Split temporal
        split_idx = int(len(X) * (1 - test_size))
        X_train = X[:split_idx]
        X_test = X[split_idx:]
        y_train = y[:split_idx]
        y_test = y[split_idx:]

        return X_train, X_test, y_train, y_test

    def optimize_hyperparameters(self, X_train: pd.DataFrame, y_train: pd.Series,
                               model_name: str, n_trials: int = 50) -> Dict:
        """Optimización de hiperparámetros con Optuna"""

        def objective(trial):
            if model_name == 'xgboost':
                params = {
                'n_estimators': trial.suggest_int('n_estimators', 30, 150),  # OPTIMIZADO: Rango reducido
                    'max_depth': trial.suggest_int('max_depth', 3, 10),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
                    'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                    'min_child_weight': trial.suggest_int('min_child_weight', 1, 10)
                }
                model = xgb.XGBClassifier(**params, random_state=42, n_jobs=-1)

            elif model_name == 'random_forest':
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 300),
                    'max_depth': trial.suggest_int('max_depth', 5, 20),
                    'min_samples_split': trial.suggest_int('min_samples_split', 2, 10),
                    'min_samples_leaf': trial.suggest_int('min_samples_leaf', 1, 5),
                    'max_features': trial.suggest_categorical('max_features', ['sqrt', 'log2', None])
                }
                model = RandomForestClassifier(**params, random_state=42, n_jobs=-1)

            elif model_name == 'neural_network':
                params = {
                    'hidden_layer_sizes': trial.suggest_categorical('hidden_layer_sizes',
                        [(50,), (100,), (50, 25), (100, 50), (100, 50, 25)]),
                    'alpha': trial.suggest_float('alpha', 1e-5, 1e-1, log=True),
                    'learning_rate_init': trial.suggest_float('learning_rate_init', 1e-4, 1e-1, log=True)
                }
                model = MLPClassifier(**params, max_iter=300, random_state=42)

            else:
                return 0.5  # Default score

            # Cross-validation
            tscv = TimeSeriesSplit(n_splits=3)
            scores = cross_val_score(model, X_train, y_train, cv=tscv, scoring='f1')
            return scores.mean()

        study = optuna.create_study(
            direction='maximize',
            sampler=TPESampler(),
            pruner=MedianPruner()
        )

        study.optimize(objective, n_trials=n_trials)

        self.best_params[model_name] = study.best_params
        logger.info(f"Best params for {model_name}: {study.best_params}")

        return study.best_params

    def train_models(self, df: pd.DataFrame, optimize: bool = True) -> Dict[str, float]:
        """Entrenar todos los modelos"""

        # Feature engineering
        df_features = self.advanced_feature_engineering(df)

        # Preparar datos
        X_train, X_test, y_train, y_test = self.prepare_data(df_features)

        # Scaling
        self.scalers['robust'] = RobustScaler()
        X_train_scaled = self.scalers['robust'].fit_transform(X_train)
        X_test_scaled = self.scalers['robust'].transform(X_test)

        results = {}

        for model_name, model in self.models.items():
            try:
                logger.info(f"Training {model_name}...")

                # Optimización si está habilitada
                if optimize and model_name in ['xgboost', 'random_forest', 'neural_network']:
                    best_params = self.optimize_hyperparameters(X_train, y_train, model_name)
                    model.set_params(**best_params)

                # Entrenamiento
                if model_name == 'neural_network':
                    model.fit(X_train_scaled, y_train)
                else:
                    model.fit(X_train, y_train)

                # Predicciones
                if model_name == 'neural_network':
                    y_pred = model.predict(X_test_scaled)
                    y_pred_proba = model.predict_proba(X_test_scaled)
                else:
                    y_pred = model.predict(X_test)
                    y_pred_proba = model.predict_proba(X_test)

                # Métricas
                accuracy = accuracy_score(y_test, y_pred)
                precision = precision_score(y_test, y_pred)
                recall = recall_score(y_test, y_pred)
                f1 = f1_score(y_test, y_pred)
                auc = roc_auc_score(y_test, y_pred_proba[:, 1])

                results[model_name] = {
                    'accuracy': accuracy,
                    'precision': precision,
                    'recall': recall,
                    'f1': f1,
                    'auc': auc
                }

                # Feature importance para modelos que lo soportan
                if hasattr(model, 'feature_importances_'):
                    self.feature_importance[model_name] = dict(zip(X_train.columns, model.feature_importances_))

                # Guardar modelo
                model_path = os.path.join(self.model_dir, f"{self.symbol}_{model_name}.joblib")
                joblib.dump(model, model_path)

                logger.info(f"{model_name} trained - F1: {f1:.4f}, AUC: {auc:.4f}")

            except Exception as e:
                logger.error(f"Error training {model_name}: {str(e)}")
                results[model_name] = {'error': str(e)}

        return results

    def predict_with_confidence(self, df: pd.DataFrame, model_name: str = 'ensemble') -> Dict:
        """Predicción con scores de confianza"""

        try:
            # Cargar modelo si existe
            model_path = os.path.join(self.model_dir, f"{self.symbol}_{model_name}.joblib")
            if os.path.exists(model_path):
                model = joblib.load(model_path)
            else:
                model = self.models.get(model_name)
                if not model:
                    return {'error': f'Model {model_name} not found'}

            # Feature engineering
            df_features = self.advanced_feature_engineering(df)
            latest_data = df_features.iloc[-1:]

            # Excluir columnas no features
            exclude_cols = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'target', 'future_return_5']
            feature_cols = [col for col in df_features.columns if col not in exclude_cols]
            X_pred = latest_data[feature_cols]

            # Scaling si es neural network
            if model_name == 'neural_network':
                X_pred_scaled = self.scalers['robust'].transform(X_pred)
                prediction = model.predict(X_pred_scaled)
                probabilities = model.predict_proba(X_pred_scaled)
            else:
                prediction = model.predict(X_pred)
                probabilities = model.predict_proba(X_pred)

            # Confidence score
            confidence = max(probabilities[0]) * 100

            # Decisión basada en confidence
            if confidence > 70:
                signal = 'buy' if prediction[0] == 1 else 'sell'
                strength = 'strong' if confidence > 85 else 'moderate'
            elif confidence < 30:
                signal = 'sell' if prediction[0] == 0 else 'buy'
                strength = 'strong' if confidence < 15 else 'moderate'
            else:
                signal = 'hold'
                strength = 'weak'

            return {
                'signal': signal,
                'confidence': round(confidence, 2),
                'strength': strength,
                'probabilities': {
                    'buy': round(probabilities[0][1] * 100, 2),
                    'sell': round(probabilities[0][0] * 100, 2)
                },
                'model': model_name,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in prediction: {str(e)}")
            return {'error': str(e)}

    def get_feature_importance(self, model_name: str) -> Dict:
        """Obtener importancia de features"""
        return self.feature_importance.get(model_name, {})

    def get_model_performance(self) -> Dict:
        """Obtener rendimiento de modelos"""
        return {
            'best_model': max(self.models.keys(), key=lambda x: self.models[x].get('f1', 0)),
            'feature_importance': self.feature_importance,
            'best_params': self.best_params
        }

class ReinforcementLearningTrader:
    """Trading con Reinforcement Learning"""

    def __init__(self, symbol: str, initial_balance: float = 10000):
        if not RL_AVAILABLE:
            raise ImportError("Stable Baselines3 not available for RL")

        self.symbol = symbol
        self.initial_balance = initial_balance
        self.model = None
        self.env = None

    def create_trading_env(self):
        """Crear entorno de trading personalizado"""

        class TradingEnv(gym.Env):
            def __init__(self, symbol, initial_balance):
                super().__init__()
                self.symbol = symbol
                self.initial_balance = initial_balance
                self.balance = initial_balance
                self.position = 0
                self.current_step = 0

                # Espacio de acciones: Hold, Buy, Sell
                self.action_space = gym.spaces.Discrete(3)

                # Espacio de observaciones: precio, indicadores, posición
                self.observation_space = gym.spaces.Box(
                    low=-np.inf, high=np.inf, shape=(10,), dtype=np.float32
                )

                # Cargar datos históricos
                self.data = self._load_data()

            def _load_data(self):
                df = get_candles(self.symbol, interval="1h", output_size=1000)
                df = aplicar_indicadores(df)
                return df

            def reset(self):
                self.balance = self.initial_balance
                self.position = 0
                self.current_step = 0
                return self._get_observation()

            def step(self, action):
                if self.current_step >= len(self.data) - 1:
                    done = True
                    reward = 0
                else:
                    done = False

                    current_price = self.data.iloc[self.current_step]['close']
                    next_price = self.data.iloc[self.current_step + 1]['close']

                    # Ejecutar acción
                    if action == 1 and self.position == 0:  # Buy
                        self.position = self.balance / current_price
                        self.balance = 0
                    elif action == 2 and self.position > 0:  # Sell
                        self.balance = self.position * current_price
                        self.position = 0

                    # Calcular reward
                    portfolio_value = self.balance + (self.position * next_price)
                    reward = portfolio_value - self.initial_balance

                    self.current_step += 1

                return self._get_observation(), reward, done, {}

            def _get_observation(self):
                if self.current_step >= len(self.data):
                    return np.zeros(10)

                row = self.data.iloc[self.current_step]
                return np.array([
                    row['close'],
                    row['RSI'] or 50,
                    row['MACD'] or 0,
                    row['ADX'] or 25,
                    row['returns'] or 0,
                    self.position,
                    self.balance,
                    row['volatility_20'] or 0,
                    row['volume_ratio'] or 1,
                    row['trend_strength'] or 0
                ], dtype=np.float32)

        self.env = DummyVecEnv([lambda: TradingEnv(self.symbol, self.initial_balance)])

    def train_rl_model(self, total_timesteps: int = 100000):
        """Entrenar modelo RL"""

        if not self.env:
            self.create_trading_env()

        # Usar PPO (Proximal Policy Optimization)
        self.model = PPO(
            "MlpPolicy",
            self.env,
            verbose=1,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01
        )

        # Callback para detener cuando alcance buen rendimiento
        callback = StopTrainingOnRewardThreshold(reward_threshold=1000, verbose=1)

        self.model.learn(total_timesteps=total_timesteps, callback=callback)

        # Guardar modelo
        self.model.save(f"rl_model_{self.symbol}")

    def predict_rl_action(self, observation: np.array) -> int:
        """Predecir acción con modelo RL"""
        if not self.model:
            return 0  # Hold por defecto

        action, _ = self.model.predict(observation)
        return action

# Funciones de utilidad
def train_advanced_ml(symbol: str, optimize: bool = True) -> Dict:
    """Entrenar ML avanzado para un símbolo"""
    predictor = AdvancedMLPredictor(symbol)
    df = get_candles(symbol, interval="1h", output_size=2000)
    results = predictor.train_models(df, optimize=optimize)
    return results

def predict_advanced_signal(symbol: str, model_name: str = 'ensemble') -> Dict:
    """Predecir señal con ML avanzado"""
    predictor = AdvancedMLPredictor(symbol)
    df = get_candles(symbol, interval="1h", output_size=100)
    prediction = predictor.predict_with_confidence(df, model_name)
    return prediction

def get_ml_insights(symbol: str) -> Dict:
    """Obtener insights de ML"""
    predictor = AdvancedMLPredictor(symbol)
    return predictor.get_model_performance()

# Función principal para ejecutar desde línea de comandos
if __name__ == "__main__":
    # Ejemplo de uso
    symbol = "XAU/USD"

    # Entrenar modelos
    print("Training advanced ML models...")
    results = train_advanced_ml(symbol, optimize=True)
    print("Training results:", results)

    # Hacer predicción
    print("Making prediction...")
    prediction = predict_advanced_signal(symbol)
    print("Prediction:", prediction)

    # Insights
    insights = get_ml_insights(symbol)
    print("ML Insights:", insights)