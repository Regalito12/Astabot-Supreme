# risk_manager.py
import os
import json
import logging
from datetime import datetime, timezone
from config import params, CHAT_ID
from models import db, Trade, TradingAccount
from sqlalchemy import func

logger = logging.getLogger(__name__)

KILL_SWITCH_FILE = "kill_switch_state.json"

class RiskManager:
    """Gestiona el riesgo global y el estado del Circuit Breaker."""

    @staticmethod
    def get_daily_pnl():
        """Calcula el P&L total acumulado en el día UTC actual."""
        try:
            now = datetime.now(timezone.utc)
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Sumar P&L de trades cerrados hoy
            pnl_sum = db.session.query(func.sum(Trade.pnl)).filter(
                Trade.closed_at >= start_of_day
            ).scalar() or 0.0
            
            return float(pnl_sum)
        except Exception as e:
            logger.error(f"Error calculando P&L diario: {e}")
            return 0.0

    @staticmethod
    def check_kill_switch(broker_manager=None):
        """
        Verifica si se ha superado el límite de pérdida diaria.
        Retorna True si el Kill Switch está activo.
        """
        if RiskManager.is_forced_active():
            return True

        max_loss_pct = params.get("MAX_DAILY_LOSS_PCT", 0.05)
        
        # Necesitamos el balance inicial del día para calcular el %
        # Por ahora, usamos el balance actual del broker principal si está disponible
        # o un balance base configurable.
        try:
            # Intentar obtener balance desde live_trading_manager
            balance = 1000.0 # Default si no hay nada
            if broker_manager:
                # Asumimos que hay una cuenta activa
                accounts = TradingAccount.query.filter_by(is_active=True).all()
                if accounts:
                    balance = broker_manager.get_account_balance(accounts[0].user_id, accounts[0].account_id)
            
            daily_pnl = RiskManager.get_daily_pnl()
            
            # Si la pérdida diaria supera el % del balance
            if daily_pnl < 0 and abs(daily_pnl) >= (balance * max_loss_pct):
                logger.warning(f"⚠️ CIRCUIT BREAKER ACTIVADO: Pérdida diaria {daily_pnl} superó el {max_loss_pct*100}%")
                RiskManager.set_kill_switch(True, f"Pérdida diaria alcanzada: {daily_pnl}")
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error en check_kill_switch: {e}")
            return False

    @staticmethod
    def is_forced_active():
        """Verifica si el Kill Switch fue activado manualmente o persiste."""
        if os.path.exists(KILL_SWITCH_FILE):
            try:
                with open(KILL_SWITCH_FILE, "r") as f:
                    state = json.load(f)
                    
                # Si es del mismo día, sigue activo
                last_active = datetime.fromisoformat(state.get("timestamp"))
                if last_active.date() == datetime.now(timezone.utc).date():
                    return state.get("active", False)
            except Exception:
                pass
        return False

    @staticmethod
    def set_kill_switch(active: bool, reason: str = ""):
        """Activa o desactiva el Kill Switch persistente."""
        state = {
            "active": active,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(KILL_SWITCH_FILE, "w") as f:
            json.dump(state, f)
        
        if active:
            logger.critical(f"🛑 Kill Switch GLOBAL ACTIVADO. Razón: {reason}")
            # Aquí se podría integrar el envío de mensaje a Telegram directamente
            # pero suele hacerse en el bot principal para usar su app/context.

    @staticmethod
    def reset_kill_switch():
        """Resetea el estado del Kill Switch."""
        if os.path.exists(KILL_SWITCH_FILE):
            os.remove(KILL_SWITCH_FILE)
            logger.info("✅ Kill Switch reseteado manualmente.")
            return True
        return False

risk_manager = RiskManager()
