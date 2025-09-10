#!/usr/bin/env python3
"""
smartVisionQA - Visual QA Testing with Ollama
"""

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import ollama
from playwright.async_api import async_playwright
from PIL import Image
import io
from generate_html_report import generate_from_json


class HTMLRenderer:
    """Renderiza HTML a imágenes usando Playwright"""
    
    async def html_to_image(self, html_path: Path, output_path: Path = None) -> bytes:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            file_url = f"file://{html_path.absolute()}"
            await page.goto(file_url)
            await page.wait_for_load_state("networkidle")
            
            screenshot = await page.screenshot(full_page=True)
            await browser.close()
            
            if output_path:
                output_path.write_bytes(screenshot)
            
            return screenshot

class VisionAnalyzer:
    """Analiza y compara imágenes usando Ollama"""
    # tested models: gemma3:4b | gemma3:12b | llava:7b
    def __init__(self, model: str = "gemma3:4b"):
        self.model = model
        self.client = ollama.Client()
    
    def encode_image(self, image_bytes: bytes) -> str:
        return base64.b64encode(image_bytes).decode('utf-8')
    
    def analyze_single(self, image_bytes: bytes) -> str:
        prompt = "Describe the visual elements in this webpage: layout, colors, text, and components."
        
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            images=[image_bytes],
            stream=False
        )
        
        return response['response']
    
    def compare_images(self, img1_bytes: bytes, img2_bytes: bytes) -> Dict:
        prompt = """Compare these two webpage screenshots systematically. The first image is on top, second on bottom.
        
        Analyze and list specific differences in these categories:
        
        1. LAYOUT CHANGES: Grid changes, element positioning, spacing, new/removed sections
        2. TEXT CHANGES: Title changes, button text changes, content modifications, statistics changes
        3. STYLE CHANGES: Color scheme differences, font changes, border styles, shadows, gradients
        4. ELEMENT CHANGES: New buttons, badges, banners, missing elements, additional cards
        
        Be specific about what changed from the first image to the second image.
        
        Format response as valid JSON with keys: layout_changes, text_changes, style_changes, element_changes
        Each should contain an array of specific change descriptions."""
        
        # Crear imagen combinada para comparación
        img1 = Image.open(io.BytesIO(img1_bytes))
        img2 = Image.open(io.BytesIO(img2_bytes))
        
        # Redimensionar si es necesario
        max_width = max(img1.width, img2.width)
        total_height = img1.height + img2.height
        
        combined = Image.new('RGB', (max_width, total_height))
        combined.paste(img1, (0, 0))
        combined.paste(img2, (0, img1.height))
        
        # Convertir a bytes
        buffer = io.BytesIO()
        combined.save(buffer, format='PNG')
        combined_bytes = buffer.getvalue()
        
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            images=[combined_bytes],
            stream=False
        )
        
        # Intentar parsear como JSON
        try:
            raw_response = response['response']
            # Limpiar el response de posibles caracteres extra antes/después del JSON
            json_start = raw_response.find('{')
            json_end = raw_response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = raw_response[json_start:json_end]
                result = json.loads(json_str)
                
                # Limpiar cada lista de cambios
                for key in ['layout_changes', 'text_changes', 'style_changes', 'element_changes']:
                    if key in result and isinstance(result[key], list):
                        # Filtrar elementos vacíos o inválidos
                        result[key] = [
                            change for change in result[key] 
                            if change and isinstance(change, str) and change.strip() 
                            and change != key and not change.startswith(f'"{key}"')
                        ]
            else:
                raise ValueError("No valid JSON found")
                
        except Exception as e:
            result = {
                "raw_response": response['response'],
                "layout_changes": [],
                "text_changes": [],
                "style_changes": [],
                "element_changes": []
            }
        
        return result


class SmartVisionQA:
    """Orquestador principal de pruebas visuales"""
    
    def __init__(self, demo_dir: Path = Path("demo")):
        self.demo_dir = demo_dir
        self.renderer = HTMLRenderer()
        self.analyzer = VisionAnalyzer()
        self.results_dir = Path("results")
        self.results_dir.mkdir(exist_ok=True)
    
    async def run_comparison(self, html1: str, html2: str) -> Dict:
        html1_path = self.demo_dir / html1
        html2_path = self.demo_dir / html2
        
        if not html1_path.exists() or not html2_path.exists():
            raise FileNotFoundError(f"HTML files not found in {self.demo_dir}")
        
        print(f"Renderizando {html1}...")
        img1 = await self.renderer.html_to_image(
            html1_path, 
            self.results_dir / f"{html1.replace('.html', '')}_screenshot.png"
        )
        
        print(f"Renderizando {html2}...")
        img2 = await self.renderer.html_to_image(
            html2_path,
            self.results_dir / f"{html2.replace('.html', '')}_screenshot.png"
        )
        
        print("Analizando diferencias con Ollama...")
        differences = self.analyzer.compare_images(img1, img2)
        
        return {
            "file1": html1,
            "file2": html2,
            "differences": differences
        }
    
    def generate_report(self, results: Dict):
        print("\n" + "="*50)
        print("REPORTE DE DIFERENCIAS VISUALES")
        print("="*50)
        print(f"\nComparación: {results['file1']} vs {results['file2']}\n")
        
        diff = results['differences']
        
        if 'raw_response' in diff:
            print("Análisis completo:")
            print(diff['raw_response'])
        else:
            for key, changes in diff.items():
                if changes:
                    print(f"\n{key.upper().replace('_', ' ')}:")
                    if isinstance(changes, list):
                        for change in changes:
                            print(f"  - {change}")
                    else:
                        print(f"  {changes}")
        
        # Guardar reporte JSON único para cada comparación
        file1_name = results['file1'].replace('.html', '')
        file2_name = results['file2'].replace('.html', '')
        report_filename = f"comparison_{file1_name}_vs_{file2_name}.json"
        report_path = self.results_dir / report_filename
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        # Generar reporte HTML visual
        html_report_path = generate_from_json(report_path, self.results_dir)
        
        print(f"\nReporte JSON guardado en: {report_path}")
        print(f"Reporte HTML guardado en: {html_report_path}")


async def main():
    qa = SmartVisionQA()
    
    # Casos de prueba con archivos locales
    test_cases = [
        ("page_v1.html", "page_v2.html"),
        ("page_v1.html", "page_v3.html"),
        ("page_v2.html", "page_v3.html"),
    ]
    
    for html1, html2 in test_cases:
        try:
            results = await qa.run_comparison(html1, html2)
            qa.generate_report(results)
        except Exception as e:
            print(f"Error en comparación {html1} vs {html2}: {e}")
    
    # EJEMPLO: Comparar URLs reales (descomentar para usar)
    # url_tests = [
    #     ("https://example.com", "https://example.org"),
    # ]
    # 
    # for url1, url2 in url_tests:
    #     try:
    #         results = await qa.run_url_comparison(url1, url2)
    #         qa.generate_report(results)
    #     except Exception as e:
    #         print(f"Error en comparación {url1} vs {url2}: {e}")


if __name__ == "__main__":
    asyncio.run(main())