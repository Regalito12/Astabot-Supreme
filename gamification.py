# gamification.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class GamificationSystem:
    def __init__(self):
        self.user_points = {}
        self.achievements = {
            'first_trade': {'points': 10, 'description': 'Primer trade exitoso'},
            'win_streak_5': {'points': 50, 'description': 'Racha de 5 wins'},
            'profit_1000': {'points': 100, 'description': 'Ganancia de $1000'},
            'backtest_master': {'points': 25, 'description': 'Completar 10 backtests'},
        }

    def add_points(self, user_id, points, reason):
        if user_id not in self.user_points:
            self.user_points[user_id] = {'total': 0, 'history': []}
        self.user_points[user_id]['total'] += points
        self.user_points[user_id]['history'].append({
            'points': points,
            'reason': reason,
            'timestamp': datetime.now()
        })
        logger.info(f"Usuario {user_id} ganó {points} puntos: {reason}")

    def check_achievements(self, user_id, stats):
        """Verifica logros basados en estadísticas."""
        unlocked = []
        if stats.get('total_trades', 0) >= 1 and 'first_trade' not in self.user_points.get(user_id, {}).get('achievements', []):
            self.add_points(user_id, self.achievements['first_trade']['points'], 'first_trade')
            unlocked.append('first_trade')

        if stats.get('win_streak', 0) >= 5:
            self.add_points(user_id, self.achievements['win_streak_5']['points'], 'win_streak_5')
            unlocked.append('win_streak_5')

        if stats.get('total_pnl', 0) >= 1000:
            self.add_points(user_id, self.achievements['profit_1000']['points'], 'profit_1000')
            unlocked.append('profit_1000')

        return unlocked

    def get_leaderboard(self):
        """Devuelve ranking de usuarios por puntos."""
        sorted_users = sorted(self.user_points.items(), key=lambda x: x[1]['total'], reverse=True)
        return sorted_users[:10]  # Top 10

# Instancia global
gamification = GamificationSystem()

# Integración en backtesting.py y analizador_oro.py
# Después de trade exitoso: gamification.add_points(user_id, 5, 'trade_win')
# Después de backtest: gamification.add_points(user_id, 1, 'backtest_completed')