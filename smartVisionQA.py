#!/usr/bin/env python3
"""
smartVisionQA - Visual QA Testing with Ollama
"""

import asyncio
import base64
import json
import logging
import re
from pathlib import Path
from typing import Dict

import ollama
from playwright.async_api import async_playwright
from PIL import Image
import io
from generate_html_report import generate_from_json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def clean_changes_list(changes: list, key: str) -> list:
    """Limpia y filtra una lista de cambios, eliminando entradas vacías o inválidas."""
    return [
        str(c).strip() for c in changes
        if c and str(c).strip() and str(c).strip() != key
        and not str(c).strip().startswith(f'"{key}"')
    ]


class HTMLRenderer:
    """Renderiza HTML a imágenes usando Playwright"""

    async def _render_to_image(self, target: str, is_url: bool = False, output_path: Path = None) -> bytes:
        """Renderiza una página (archivo HTML o URL) a imagen PNG."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                if is_url:
                    await page.goto(target, wait_until="networkidle")
                    await page.wait_for_timeout(2000)
                else:
                    file_url = f"file://{Path(target).absolute()}"
                    await page.goto(file_url)
                    await page.wait_for_load_state("networkidle")

                screenshot = await page.screenshot(full_page=True)

                if output_path:
                    output_path.write_bytes(screenshot)

                return screenshot
            finally:
                await browser.close()

    async def html_to_image(self, html_path: Path, output_path: Path = None) -> bytes:
        return await self._render_to_image(str(html_path), is_url=False, output_path=output_path)

    async def url_to_image(self, url: str, output_path: Path = None) -> bytes:
        """Captura una URL como imagen"""
        return await self._render_to_image(url, is_url=True, output_path=output_path)


class VisionAnalyzer:
    """Analiza y compara imágenes usando Ollama. El modelo más eficaz de los que he probado para imagenes es qwen2.5vl:7b"""
    # tested models: gemma3:4b | gemma3:12b | llava:7b | qwen2.5vl:7b
    def __init__(self, model: str = None):
        import os
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b")
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

        return response.get('response', '')

    def compare_images(self, img1_bytes: bytes, img2_bytes: bytes) -> Dict:
        prompt = """You are analyzing two versions of a webpage: VERSION 1 (V1) vs VERSION 2 (V2).

        V1 is the FIRST/ORIGINAL version, V2 is the SECOND/UPDATED version.

        Compare V1 against V2 and identify ONLY actual visual differences. Be precise and specific.

        Analyze and list specific differences in these categories:

        1. LAYOUT CHANGES: Grid changes, element positioning, spacing, new/removed sections
        2. TEXT CHANGES: Title changes, button text changes, content modifications, statistics changes
        3. STYLE CHANGES: Color scheme differences, font changes, border styles, shadows, gradients
        4. ELEMENT CHANGES: New buttons, badges, banners, missing elements, additional cards

        Rules:
        - Only report differences that actually exist between V1 and V2
        - Use format "V1 has X, V2 has Y" for clarity
        - Ignore minor pixel differences or rendering artifacts
        - If no differences exist in a category, leave the array empty

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
            raw_response = response.get('response', '')
            if not raw_response:
                logger.warning("Respuesta vacía del modelo Ollama")
                return {
                    "layout_changes": [],
                    "text_changes": [],
                    "style_changes": [],
                    "element_changes": []
                }

            # Extraer JSON con regex para manejar texto envolvente
            json_match = re.search(r'\{[\s\S]*\}', raw_response)

            if json_match:
                result = json.loads(json_match.group())

                # Limpiar cada lista de cambios
                for key in ['layout_changes', 'text_changes', 'style_changes', 'element_changes']:
                    if key in result and isinstance(result[key], list):
                        result[key] = clean_changes_list(result[key], key)
            else:
                raise ValueError("No valid JSON found in response")

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("No se pudo parsear JSON de la respuesta: %s", e, exc_info=True)
            result = {
                "raw_response": raw_response,
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
        self.results_dir = Path("results").resolve()
        self.results_dir.mkdir(exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitiza un nombre para usarlo como parte de un nombre de archivo."""
        name = Path(name).stem if name.endswith('.html') else name
        return re.sub(r'[^\w\-.]', '_', name)

    async def run_comparison(self, html1: str, html2: str) -> Dict:
        html1_path = self.demo_dir / html1
        html2_path = self.demo_dir / html2

        if not html1_path.exists() or not html2_path.exists():
            raise FileNotFoundError(f"HTML files not found in {self.demo_dir}")

        logger.info("Renderizando %s...", html1)
        img1 = await self.renderer.html_to_image(
            html1_path,
            self.results_dir / f"{self._sanitize_filename(html1)}_screenshot.png"
        )

        logger.info("Renderizando %s...", html2)
        img2 = await self.renderer.html_to_image(
            html2_path,
            self.results_dir / f"{self._sanitize_filename(html2)}_screenshot.png"
        )

        logger.info("Analizando diferencias con Ollama...")
        differences = self.analyzer.compare_images(img1, img2)

        return {
            "file1": html1,
            "file2": html2,
            "differences": differences
        }

    async def run_url_comparison(self, url1: str, url2: str) -> Dict:
        """Compara dos URLs capturando sus páginas web"""
        logger.info("Capturando %s...", url1)
        img1 = await self.renderer.url_to_image(
            url1,
            self.results_dir / "url1_screenshot.png"
        )

        logger.info("Capturando %s...", url2)
        img2 = await self.renderer.url_to_image(
            url2,
            self.results_dir / "url2_screenshot.png"
        )

        logger.info("Analizando diferencias con Ollama...")
        differences = self.analyzer.compare_images(img1, img2)

        return {
            "file1": url1,
            "file2": url2,
            "differences": differences
        }

    def generate_report(self, results: Dict):
        logger.info("=" * 50)
        logger.info("REPORTE DE DIFERENCIAS VISUALES")
        logger.info("=" * 50)
        logger.info("Comparación: %s vs %s", results['file1'], results['file2'])

        diff = results['differences']

        if 'raw_response' in diff:
            logger.info("Análisis completo:\n%s", diff['raw_response'])
        else:
            for key, changes in diff.items():
                if changes:
                    logger.info("%s:", key.upper().replace('_', ' '))
                    if isinstance(changes, list):
                        for change in changes:
                            logger.info("  - %s", change)
                    else:
                        logger.info("  %s", changes)

        # Guardar reporte JSON único para cada comparación
        file1_name = self._sanitize_filename(results['file1'])
        file2_name = self._sanitize_filename(results['file2'])
        report_filename = f"comparison_{file1_name}_vs_{file2_name}.json"
        report_path = self.results_dir / report_filename
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2)

        # Generar reporte HTML visual
        html_report_path = generate_from_json(report_path, self.results_dir)

        logger.info("Reporte JSON guardado en: %s", report_path)
        logger.info("Reporte HTML guardado en: %s", html_report_path)
        logger.info("Resultados disponibles para CI/CD:")
        logger.info("- JSON: %s", report_path.relative_to(Path.cwd()))
        logger.info("- HTML: %s", html_report_path.relative_to(Path.cwd()))
        logger.info("- Screenshots: %s/*_screenshot.png", self.results_dir.name)


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
            logger.error("Error en comparación %s vs %s: %s", html1, html2, e, exc_info=True)

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
    #         logger.error("Error en comparación %s vs %s: %s", url1, url2, e, exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
