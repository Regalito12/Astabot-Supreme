# backup_system.py
import os
import shutil
import zipfile
from datetime import datetime
import logging
import schedule
import time

logger = logging.getLogger(__name__)

BACKUP_DIR = "backups"
DB_PATH = "instance/astabot.db"
MODELS_DIR = "models"

def create_backup():
    """Crea backup completo de BD y modelos."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"astabot_backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Backup logs
        if os.path.exists("logs"):
            for root, dirs, files in os.walk("logs"):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, os.path.relpath(file_path, "logs"))

        # Backup BD
        if os.path.exists(DB_PATH):
            zipf.write(DB_PATH, os.path.basename(DB_PATH))

        # Backup modelos
        if os.path.exists(MODELS_DIR):
            for root, dirs, files in os.walk(MODELS_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, os.path.relpath(file_path, MODELS_DIR))

        # Backup configs
        for config_file in ["params.json", "config.py"]:
            if os.path.exists(config_file):
                zipf.write(config_file)

    logger.info(f"Backup creado: {backup_path}")
    return backup_path

def advanced_restore(backup_path):
    """Restaura desde backup con opciones adicionales."""
    try:
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            zipf.extractall(".")
        logger.info(f"Backup restaurado desde: {backup_path}")

        # Validación de restauración
        if os.path.exists(DB_PATH):
            logger.info("Validación: Base de datos restaurada correctamente.")
        else:
            logger.error("Error en restauración: Base de datos no encontrada.")

        if os.path.exists("logs"):
            logger.info("Validación: Logs restaurados correctamente.")
        else:
            logger.warning("Advertencia en restauración: Logs no encontrados.")

    except Exception as e:
        logger.error(f"Error durante la restauración: {e}")

def schedule_backups(interval_hours=24):
    """Programa backups automáticos."""
    schedule.every(interval_hours).hours.do(create_backup)
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Integración en bot_auto.py
# import threading
# backup_thread = threading.Thread(target=schedule_backups, daemon=True)
# backup_thread.start()