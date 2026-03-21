# registro_signals.py
import csv
import os
from datetime import datetime

LOG_FILE = "signals_log_simple.csv"

def registrar_senal(symbol, tipo, precio, tp, sl, confianza):
    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "tipo": tipo,
        "precio": precio,
        "tp": tp,
        "sl": sl,
        "confianza": confianza
    }
    header = ["timestamp","symbol","tipo","precio","tp","sl","confianza"]
    write_header = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if write_header:
            writer.writeheader()
        writer.writerow(row)