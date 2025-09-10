#!/usr/bin/env python3
"""
Ejemplo de uso de SmartVisionQA con URLs reales
"""

import asyncio
from pathlib import Path
from smartVisionQA import SmartVisionQA


async def compare_websites():
    """Ejemplo de comparación de sitios web reales"""
    qa = SmartVisionQA()
    
    # Ejemplos de URLs a comparar
    examples = [
        # Comparar dos versiones de un sitio
        ("https://example.com", "https://example.org"),
        
        # Comparar versión móvil vs desktop (descomentar para usar)
        ("https://m.wikipedia.org", "https://wikipedia.org"),
        
        # Comparar competidores (descomentar para usar)
        # ("https://github.com", "https://gitlab.com"),
    ]
    
    for url1, url2 in examples:
        print(f"\n{'='*60}")
        print(f"Comparando: {url1} vs {url2}")
        print('='*60)
        
        try:
            results = await qa.run_url_comparison(url1, url2)
            qa.generate_report(results)
        except Exception as e:
            print(f"Error: {e}")


async def compare_local_vs_production():
    """Comparar versión local vs producción"""
    qa = SmartVisionQA()
    
    # Útil para comparar tu desarrollo local con producción
    local_url = "http://localhost:3000"
    prod_url = "https://tu-sitio.com"
    
    print(f"Comparando local vs producción...")
    
    try:
        results = await qa.run_url_comparison(local_url, prod_url)
        qa.generate_report(results)
    except Exception as e:
        print(f"Error: {e}")
        print("Asegúrate de que tu servidor local esté corriendo")

if __name__ == "__main__":
    # Ejecutar comparación básica de websites
    asyncio.run(compare_websites())
    
    # Otros ejemplos (descomentar para usar):
    # asyncio.run(compare_local_vs_production())