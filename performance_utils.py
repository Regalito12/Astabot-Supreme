# performance_utils.py
import time
import logging
import hashlib
import pickle
from functools import wraps
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)

# Cache global para indicadores
_indicator_cache: Dict[str, Dict[str, Any]] = {}
_cache_timestamps: Dict[str, datetime] = {}

# Configuración de caché
DEFAULT_CACHE_TTL = timedelta(minutes=5)
MAX_CACHE_SIZE = 100


def get_cache_key(symbol: str, interval: str, indicator: str) -> str:
    """Genera una clave única para el caché."""
    return f"{symbol}:{interval}:{indicator}"


def invalidate_cache(symbol: Optional[str] = None):
    """Invalida el caché para un símbolo específico o todo el caché."""
    global _indicator_cache, _cache_timestamps
    
    if symbol:
        keys_to_remove = [k for k in _indicator_cache.keys() if k.startswith(f"{symbol}:")]
        for key in keys_to_remove:
            _indicator_cache.pop(key, None)
            _cache_timestamps.pop(key, None)
        logger.debug(f"Cache invalidated for symbol: {symbol}")
    else:
        _indicator_cache.clear()
        _cache_timestamps.clear()
        logger.debug("Full cache invalidated")


def cached_indicator(ttl: timedelta = DEFAULT_CACHE_TTL):
    """
    Decorador para cachear resultados de indicadores técnicos.
    
    Usage:
        @cached_indicator(ttl=timedelta(minutes=5))
        def calculate_ema(df, period):
            return df['close'].ewm(span=period).mean()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave de caché basada en argumentos
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            cache_key_hash = hashlib.md5(cache_key.encode()).hexdigest()
            
            # Verificar si existe en caché y no ha expirado
            now = datetime.now()
            if cache_key_hash in _indicator_cache:
                timestamp = _cache_timestamps.get(cache_key_hash)
                if timestamp and (now - timestamp) < ttl:
                    logger.debug(f"Cache HIT for {func.__name__}")
                    return _indicator_cache[cache_key_hash]
            
            # Calcular y guardar en caché
            logger.debug(f"Cache MISS for {func.__name__}")
            result = func(*args, **kwargs)
            
            # Limitar tamaño del caché (FIFO simple)
            if len(_indicator_cache) >= MAX_CACHE_SIZE:
                oldest_key = min(_cache_timestamps.items(), key=lambda x: x[1])[0]
                _indicator_cache.pop(oldest_key, None)
                _cache_timestamps.pop(oldest_key, None)
            
            _indicator_cache[cache_key_hash] = result
            _cache_timestamps[cache_key_hash] = now
            
            return result
        return wrapper
    return decorator


def profile_performance(log_level: int = logging.INFO):
    """
    Decorador para medir y loggear el tiempo de ejecución de funciones.
    
    Usage:
        @profile_performance()
        def analizar_mercado(symbol):
            # ... código ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                
                # Extraer nombre del símbolo si está en args o kwargs
                symbol = kwargs.get('symbol', args[0] if args else 'unknown')
                
                logger.log(
                    log_level,
                    f"⏱️ {func.__name__}(symbol={symbol}) took {elapsed_time:.3f}s"
                )
                
                return result
                
            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(
                    f"❌ {func.__name__} failed after {elapsed_time:.3f}s: {str(e)}"
                )
                raise
                
        return wrapper
    return decorator


class PerformanceMonitor:
    """Monitor de rendimiento para tracking de métricas del sistema."""
    
    def __init__(self):
        self.metrics: Dict[str, list] = {
            'analysis_times': [],
            'cache_hits': 0,
            'cache_misses': 0,
            'signals_generated': 0,
            'errors': 0
        }
        self.start_time = datetime.now()
    
    def record_analysis_time(self, symbol: str, duration: float):
        """Registra el tiempo de análisis para un símbolo."""
        self.metrics['analysis_times'].append({
            'symbol': symbol,
            'duration': duration,
            'timestamp': datetime.now()
        })
    
    def record_cache_hit(self):
        """Incrementa contador de cache hits."""
        self.metrics['cache_hits'] += 1
    
    def record_cache_miss(self):
        """Incrementa contador de cache misses."""
        self.metrics['cache_misses'] += 1
    
    def record_signal(self):
        """Incrementa contador de señales generadas."""
        self.metrics['signals_generated'] += 1
    
    def record_error(self):
        """Incrementa contador de errores."""
        self.metrics['errors'] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas de rendimiento."""
        analysis_times = [m['duration'] for m in self.metrics['analysis_times']]
        
        total_cache_ops = self.metrics['cache_hits'] + self.metrics['cache_misses']
        cache_hit_rate = (
            self.metrics['cache_hits'] / total_cache_ops * 100 
            if total_cache_ops > 0 else 0
        )
        
        return {
            'uptime': str(datetime.now() - self.start_time),
            'total_analyses': len(analysis_times),
            'avg_analysis_time': sum(analysis_times) / len(analysis_times) if analysis_times else 0,
            'min_analysis_time': min(analysis_times) if analysis_times else 0,
            'max_analysis_time': max(analysis_times) if analysis_times else 0,
            'cache_hit_rate': round(cache_hit_rate, 2),
            'signals_generated': self.metrics['signals_generated'],
            'errors': self.metrics['errors']
        }
    
    def reset(self):
        """Reinicia todas las métricas."""
        self.__init__()


# Instancia global del monitor
performance_monitor = PerformanceMonitor()


def memoize_dataframe(max_size: int = 50):
    """
    Caché especializado para DataFrames basado en hash del contenido.
    Útil para cachear resultados de apply_indicadores con el mismo DataFrame.
    """
    cache = {}
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(df: pd.DataFrame, *args, **kwargs):
            # Generar hash del DataFrame (usando primeras y últimas filas + shape)
            df_hash = hashlib.md5(
                f"{df.shape}{df.head(5).to_json()}{df.tail(5).to_json()}".encode()
            ).hexdigest()
            
            cache_key = f"{df_hash}:{str(args)}:{str(kwargs)}"
            
            if cache_key in cache:
                logger.debug(f"DataFrame cache HIT for {func.__name__}")
                return cache[cache_key].copy()
            
            logger.debug(f"DataFrame cache MISS for {func.__name__}")
            result = func(df, *args, **kwargs)
            
            # Limitar tamaño del caché
            if len(cache) >= max_size:
                cache.pop(next(iter(cache)))
            
            cache[cache_key] = result.copy() if isinstance(result, pd.DataFrame) else result
            
            return result
        return wrapper
    return decorator


def batch_process(items: list, func: Callable, parallel: bool = False) -> list:
    """
    Procesa una lista de items en batch, opcionalmente en paralelo.
    
    Args:
        items: Lista de items a procesar
        func: Función a aplicar a cada item
        parallel: Si True, usa ProcessPoolExecutor para procesamiento paralelo
    
    Returns:
        Lista de resultados
    """
    if not parallel:
        return [func(item) for item in items]
    
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing
    
    max_workers = min(len(items), multiprocessing.cpu_count())
    results = [None] * len(items)
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(func, item): idx 
            for idx, item in enumerate(items)
        }
        
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.error(f"Error processing item {idx}: {e}")
                results[idx] = None
    
    return results
