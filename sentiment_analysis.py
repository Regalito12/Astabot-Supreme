# sentiment_analysis.py
import requests
import pandas as pd
# from textblob import TextBlob  # Deshabilitado por dependencias
# import tweepy  # Deshabilitado por dependencias
import logging

logger = logging.getLogger(__name__)

# Config Twitter API (necesitas keys)
TWITTER_API_KEY = "YOUR_TWITTER_API_KEY"
TWITTER_API_SECRET = "YOUR_TWITTER_API_SECRET"
TWITTER_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
TWITTER_ACCESS_SECRET = "YOUR_ACCESS_SECRET"

def get_news_sentiment(symbol):
    """Obtiene sentimiento de noticias usando NewsAPI (versión simplificada sin textblob)."""
    api_key = "YOUR_NEWSAPI_KEY"  # Reemplaza
    url = f"https://newsapi.org/v2/everything?q={symbol}&apiKey={api_key}&language=en&sortBy=publishedAt&pageSize=10"
    try:
        response = requests.get(url)
        articles = response.json().get('articles', [])
        sentiments = []
        for article in articles:
            text = article['title'] + " " + (article.get('description') or "")
            # Análisis simple: contar palabras positivas/negativas
            positive_words = ['bull', 'rise', 'gain', 'up', 'bullish', 'buy']
            negative_words = ['bear', 'fall', 'loss', 'down', 'bearish', 'sell']
            pos_count = sum(1 for word in positive_words if word in text.lower())
            neg_count = sum(1 for word in negative_words if word in text.lower())
            polarity = (pos_count - neg_count) / max(len(text.split()), 1)  # Normalizado
            sentiments.append(polarity)
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        return avg_sentiment
    except Exception as e:
        logger.error(f"Error en sentiment news: {e}")
        return 0

def get_twitter_sentiment(symbol):
    """Obtiene sentimiento de Twitter (versión simplificada sin tweepy)."""
    # Placeholder: simular sentimiento basado en búsquedas web simples
    try:
        # Usar requests para buscar en Twitter/X (limitado sin API)
        # Versión básica: asumir neutral
        return 0  # Neutral por defecto
    except Exception as e:
        logger.error(f"Error en sentiment Twitter: {e}")
        return 0

def get_combined_sentiment(symbol):
    """Combina sentimiento de news y Twitter."""
    news_sent = get_news_sentiment(symbol)
    twitter_sent = get_twitter_sentiment(symbol)
    combined = (news_sent + twitter_sent) / 2  # Promedio
    return combined

# Integración en analizador_oro.py
def adjust_signal_with_sentiment(signal_data, symbol):
    """Ajusta señal basada en sentimiento."""
    sentiment = get_combined_sentiment(symbol)
    if signal_data:
        if sentiment > 0.01 and signal_data['tipo'] == 'buy':
            signal_data['score'] += 1  # Bonus positivo
        elif sentiment < -0.01 and signal_data['tipo'] == 'sell':
            signal_data['score'] += 1
        elif abs(sentiment) > 0.05:  # Sentimiento fuerte opuesto
            signal_data = None  # Descartar señal
    return signal_data