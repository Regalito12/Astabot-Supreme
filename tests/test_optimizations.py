# test_optimizations.py
"""
Script de prueba para validar las optimizaciones del sistema de trading.
Ejecuta tests básicos de rendimiento y calidad de señales.
"""

import time
import sys
from datetime import datetime
from performance_utils import performance_monitor, invalidate_cache
from analizador_oro import analizar_mercado
from config import SUPPORTED_ASSETS

def test_signal_quality():
    """Prueba la generación de señales con los nuevos thresholds."""
    print("=" * 60)
    print("TEST 1: Calidad de Señales")
    print("=" * 60)
    
    symbols = ['XAU/USD', 'BTC/USD']
    results = []
    
    for symbol in symbols:
        print(f"\n🔍 Analizando {symbol}...")
        start = time.time()
        
        try:
            result = analizar_mercado(symbol, is_manual=True)
            elapsed = time.time() - start
            
            if result and 'message' not in result:
                print(f"  ✅ Señal generada:")
                print(f"     - Tipo: {result['tipo'].upper()}")
                print(f"     - Puntuación: {result['confianza']}")
                print(f"     - Régimen: {result.get('regime', 'N/A')}")
                print(f"     - Precio: {result['price']:.4f}")
                print(f"     - TP: {result['tp']:.4f}")
                print(f"     - SL: {result['sl']:.4f}")
                print(f"     - Ratio R:R: {abs((result['tp']-result['price'])/(result['price']-result['sl'])):.2f}")
                print(f"     - Tiempo: {elapsed:.3f}s")
                
                results.append({
                    'symbol': symbol,
                    'score': int(result['confianza'].split('/')[0]),
                    'time': elapsed,
                    'regime': result.get('regime')
                })
            else:
                msg = result.get('message', 'Sin señal') if result else 'Error'
                print(f"  ⏳ {msg}")
                print(f"     - Tiempo: {elapsed:.3f}s")
                
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ Error: {str(e)}")
            print(f"     - Tiempo: {elapsed:.3f}s")
    
    return results


def test_performance():
    """Prueba el rendimiento del sistema con caché."""
    print("\n" + "=" * 60)
    print("TEST 2: Rendimiento y Caché")
    print("=" * 60)
    
    symbol = 'XAU/USD'
    
    # Primera ejecución (sin caché)
    print(f"\n🔄 Primera ejecución (cold cache):")
    invalidate_cache()
    start = time.time()
    result1 = analizar_mercado(symbol, is_manual=True)
    time1 = time.time() - start
    print(f"   Tiempo: {time1:.3f}s")
    
    # Segunda ejecución (con caché)
    print(f"\n🔄 Segunda ejecución (warm cache):")
    start = time.time()
    result2 = analizar_mercado(symbol, is_manual=True)
    time2 = time.time() - start
    print(f"   Tiempo: {time2:.3f}s")
    
    # Calcular mejora
    if time1 > 0 and time2 > 0:
        improvement = ((time1 - time2) / time1) * 100
        print(f"\n📊 Mejora con caché: {improvement:.1f}%")
        if improvement > 10:
            print("   ✅ Caché funcionando correctamente")
        else:
            print("   ⚠️ Mejora de caché menor a lo esperado")
    
    return time1, time2


def test_monitoring():
    """Prueba el sistema de monitoreo de rendimiento."""
    print("\n" + "=" * 60)
    print("TEST 3: Sistema de Monitoreo")
    print("=" * 60)
    
    stats = performance_monitor.get_statistics()
    
    print("\n📈 Estadísticas del Performance Monitor:")
    print(f"   - Uptime: {stats['uptime']}")
    print(f"   - Total análisis: {stats['total_analyses']}")
    print(f"   - Tiempo promedio: {stats['avg_analysis_time']:.3f}s")
    print(f"   - Tiempo mínimo: {stats['min_analysis_time']:.3f}s")
    print(f"   - Tiempo máximo: {stats['max_analysis_time']:.3f}s")
    print(f"   - Cache hit rate: {stats['cache_hit_rate']:.1f}%")
    print(f"   - Señales generadas: {stats['signals_generated']}")
    print(f"   - Errores: {stats['errors']}")
    
    return stats


def test_thresholds():
    """Verifica que los nuevos thresholds están activos."""
    print("\n" + "=" * 60)
    print("TEST 4: Verificación de Thresholds")
    print("=" * 60)
    
    from config import params
    
    print("\n🎯 Parámetros activos:")
    print(f"   - MIN_SCORE_MANUAL: {params.get('MIN_SCORE_MANUAL', 'N/A')} (esperado: 5)")
    print(f"   - MIN_SCORE_AUTO: {params.get('MIN_SCORE_AUTO', 'N/A')} (esperado: 5-6)")
    print(f"   - DIVERGENCE_POINTS: {params.get('DIVERGENCE_POINTS', 'N/A')} (esperado: 3)")
    print(f"   - TP_ATR_MULT: {params.get('TP_ATR_MULT', 'N/A')}")
    print(f"   - SL_ATR_MULT: {params.get('SL_ATR_MULT', 'N/A')}")
    print(f"   - COOLDOWN_MINUTES: {params.get('COOLDOWN_MINUTES', 'N/A')}")


def main():
    """Ejecuta todos los tests."""
    print("\n🔬 SUITE DE PRUEBAS - SISTEMA OPTIMIZADO")
    print(f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # Test 1: Calidad de señales
        signal_results = test_signal_quality()
        
        # Test 2: Rendimiento
        cold_time, warm_time = test_performance()
        
        # Test 3: Monitoreo
        stats = test_monitoring()
        
        # Test 4: Thresholds
        test_thresholds()
        
        # Resumen
        print("\n" + "=" * 60)
        print("📊 RESUMEN DE PRUEBAS")
        print("=" * 60)
        
        if signal_results:
            avg_score = sum(r['score'] for r in signal_results) / len(signal_results)
            avg_time = sum(r['time'] for r in signal_results) / len(signal_results)
            print(f"\n✅ Señales detectadas: {len(signal_results)}")
            print(f"   - Puntuación promedio: {avg_score:.1f}/6")
            print(f"   - Tiempo promedio: {avg_time:.3f}s")
            
            if avg_score >= 5:
                print("   - ✅ Thresholds altos funcionando (score >= 5)")
            else:
                print("   - ⚠️ Puntuación por debajo del nuevo threshold")
        else:
            print("\n⏳ No se generaron señales (normal con thresholds altos)")
        
        if cold_time > 0:
            print(f"\n⚡ Rendimiento:")
            print(f"   - Cold: {cold_time:.3f}s")
            print(f"   - Warm: {warm_time:.3f}s")
            print(f"   - Objetivo: < 2.0s ({'✅' if cold_time < 2.0 else '⚠️'})")
        
        print("\n" + "=" * 60)
        print("✅ PRUEBAS COMPLETADAS")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error durante las pruebas: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
