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
    
    def __init__(self, model: str = "llava:7b"):
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
        prompt = """Compare these two webpage screenshots and identify:
        1. Visual differences in layout
        2. Text changes
        3. Color or style differences
        4. Missing or new elements
        
        Format: JSON with keys: layout_changes, text_changes, style_changes, element_changes"""
        
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
            result = json.loads(response['response'])
        except:
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
        
        # Guardar reporte JSON
        report_path = self.results_dir / "comparison_report.json"
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\nReporte guardado en: {report_path}")


async def main():
    qa = SmartVisionQA()
    
    # Casos de prueba
    test_cases = [
        ("page_v1.html", "page_v2.html"),
    ]
    
    for html1, html2 in test_cases:
        try:
            results = await qa.run_comparison(html1, html2)
            qa.generate_report(results)
        except Exception as e:
            print(f"Error en comparación {html1} vs {html2}: {e}")


if __name__ == "__main__":
    asyncio.run(main())