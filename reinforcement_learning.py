# reinforcement_learning.py
import numpy as np
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
import gymnasium as gym
from gymnasium import spaces
import logging

logger = logging.getLogger(__name__)

class TradingEnv(gym.Env):
    """Entorno de RL para trading."""
    def __init__(self, df):
        super(TradingEnv, self).__init__()
        self.df = df
        self.current_step = 0
        self.balance = 10000
        self.position = 0  # 0: sin posición, 1: long, -1: short
        self.entry_price = 0

        # Espacios de acción/observación
        self.action_space = spaces.Discrete(3)  # 0: hold, 1: buy, 2: sell
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(10,), dtype=np.float32)

    def reset(self):
        self.current_step = 0
        self.balance = 10000
        self.position = 0
        self.entry_price = 0
        return self._get_obs()

    def step(self, action):
        reward = 0
        done = self.current_step >= len(self.df) - 1

        if action == 1 and self.position == 0:  # Buy
            self.position = 1
            self.entry_price = self.df.iloc[self.current_step]['close']
        elif action == 2 and self.position == 0:  # Sell
            self.position = -1
            self.entry_price = self.df.iloc[self.current_step]['close']
        elif action == 0 and self.position != 0:  # Close position
            pnl = (self.df.iloc[self.current_step]['close'] - self.entry_price) * self.position
            self.balance += pnl
            reward = pnl
            self.position = 0

        self.current_step += 1
        obs = self._get_obs()
        return obs, reward, done, {}

    def _get_obs(self):
        if self.current_step >= len(self.df):
            return np.zeros(10)
        row = self.df.iloc[self.current_step]
        return np.array([
            row['close'], row['volume'], row.get('EMA50', 0), row.get('EMA200', 0),
            row.get('ADX', 0), self.balance, self.position, self.entry_price,
            row.get('ATR', 0), self.current_step / len(self.df)
        ])

def train_rl_model(df, total_timesteps=10000):
    """Entrena modelo RL."""
    env = DummyVecEnv([lambda: TradingEnv(df)])
    model = PPO("MlpPolicy", env, verbose=0)
    model.learn(total_timesteps=total_timesteps)
    model.save("rl_trading_model")
    return model

# --- Nueva función para entrenamiento en tiempo real ---
async def train_rl_model_realtime(new_data_df):
    """Entrena el modelo RL con datos nuevos en tiempo real."""
    global rl_model
    try:
        # Cargar modelo existente
        rl_model = PPO.load("rl_trading_model")
    except:
        logger.warning("Modelo RL no encontrado, creando nuevo modelo.")
        rl_model = None

    if rl_model is None:
        # Entrenar modelo desde cero si no existe
        env = DummyVecEnv([lambda: TradingEnv(new_data_df)])
        rl_model = PPO("MlpPolicy", env, verbose=0)
        rl_model.learn(total_timesteps=10000)
    else:
        # Continuar entrenamiento con nuevos datos
        env = DummyVecEnv([lambda: TradingEnv(new_data_df)])
        rl_model.set_env(env)
        rl_model.learn(total_timesteps=5000, reset_num_timesteps=False)

    rl_model.save("rl_trading_model")
    logger.info("Modelo RL actualizado con nuevos datos.")

def predict_rl_action(model, obs):
    """Predice acción con RL."""
    action, _ = model.predict(obs)
    return action  # 0: hold, 1: buy, 2: sell

# Integración en analizador_oro.py
# Periodicamente llamar a train_rl_model_realtime con nuevos datos
rl_model = None

def load_rl_model():
    global rl_model
    try:
        rl_model = PPO.load("rl_trading_model")
    except:
        logger.warning("Modelo RL no encontrado, usando estrategia base.")

def get_rl_signal(df):
    """Obtiene señal de RL."""
    if rl_model is None:
        return None
    env = TradingEnv(df)
    obs = env._get_obs()
    action = predict_rl_action(rl_model, obs)
    if action == 1:
        return "buy"
    elif action == 2:
        return "sell"
    return None