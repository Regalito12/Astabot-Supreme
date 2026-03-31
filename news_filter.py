"""
AstaBot 2.0 - Filtro de noticias economicas
Scrapea ForexFactory para eventos USD de alto impacto.
Envia alertas a Telegram antes de noticias que mueven el oro.
"""
import os
import re
import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HIGH_IMPACT_KEYWORDS = [
    "Nonfarm", "NFP", "CPI", "FOMC", "GDP",
    "Federal Funds", "Employment", "Unemployment",
    "Retail Sales", "ISM", "PMI", "PPI",
    "Core PCE", "Consumer Confidence",
]

_CACHE = {'events': [], 'fetched_at': None}


def fetch_forex_factory():
    url = "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"No se pudo acceder a ForexFactory: {e}")
        return None


def parse_events(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.calendar__row")
    events = []
    today = datetime.now(timezone.utc).date()

    for row in rows:
        date_cell = row.select_one("td.calendar__date")
        time_cell = row.select_one("td.calendar__time")
        impact_cell = row.select_one("td.calendar__impact")
        event_cell = row.select_one("td.calendar__event")

        if not all([date_cell, time_cell, impact_cell, event_cell]):
            continue

        date_str = date_cell.get_text(strip=True)
        time_str = time_cell.get_text(strip=True)
        impact = impact_cell.get("title", "").lower()
        event_name = event_cell.get_text(strip=True)

        if "high" not in impact:
            continue

        has_keyword = any(
            kw.lower() in event_name.lower() for kw in HIGH_IMPACT_KEYWORDS
        )
        if not has_keyword:
            continue

        try:
            event_date = datetime.strptime(date_str, "%b %d").replace(
                year=datetime.now(timezone.utc).year, tzinfo=timezone.utc
            )
            if event_date.date() < today:
                event_date = event_date.replace(year=event_date.year + 1)
        except ValueError:
            continue

        actual = row.select_one("td.calendar__actual")
        forecast = row.select_one("td.calendar__forecast")
        previous = row.select_one("td.calendar__previous")

        events.append({
            "date": event_date,
            "time": time_str,
            "name": event_name,
            "actual": actual.get_text(strip=True) if actual else "—",
            "forecast": forecast.get_text(strip=True) if forecast else "—",
            "previous": previous.get_text(strip=True) if previous else "—",
        })

    return events


def get_upcoming_events(minutes_ahead=30):
    global _CACHE
    now = datetime.now(timezone.utc)
    cache_age = _CACHE['fetched_at']
    if cache_age and (now - cache_age) < timedelta(minutes=5):
        events = _CACHE['events']
    else:
        html = fetch_forex_factory()
        events = parse_events(html)
        _CACHE = {'events': events, 'fetched_at': now}

    window_end = now + timedelta(minutes=minutes_ahead)
    upcoming = [
        e for e in events
        if now <= e["date"] <= window_end
    ]
    return upcoming


def format_news_alert(event):
    dt_str = event["date"].strftime("%H:%M")
    lines = [
        "\u26A0\ufe0f **ALERTA NOTICIA ECONOMICA** \u26A0\ufe0f",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        f"\U0001F4C5 {event['name']}",
        f"\u23F0 Hora: {dt_str} UTC",
        f"\U0001F4C8 Forecast: {event['forecast']}",
        f"\U0001F4CA Previous: {event['previous']}",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        "\U0001F6AB Evita operar 15 min antes y despues",
        "\U0001F4A1 El oro se mueve fuerte con noticias USD",
    ]
    return "\n".join(lines)
