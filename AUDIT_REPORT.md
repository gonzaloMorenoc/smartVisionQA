# SmartVisionQA - Informe de Auditoría Completa

**Fecha:** 2026-03-10
**Repositorio:** smartVisionQA
**Alcance:** Análisis integral de arquitectura, calidad, seguridad, testing, rendimiento y mantenibilidad

---

## 1. Arquitectura y Estructura del Proyecto

### Estructura actual

```
smartVisionQA/
├── .github/workflows/visual-qa.yml
├── demo/
│   ├── page_v1.html, page_v2.html, page_v3.html, simple_test.html
├── resources/img/
├── scripts/generate_index.py
├── smartVisionQA.py              (293 líneas - orquestador principal)
├── generate_html_report.py       (910 líneas - generador de reportes)
├── example_url_comparison.py     (61 líneas - ejemplos)
├── Dockerfile
├── docker-entrypoint.sh
├── requirements.txt
└── README.md
```

### Hallazgos

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: Raíz del proyecto
- **Descripción**: Todos los módulos Python están en la raíz sin estructura de paquete. No hay `__init__.py`, no hay separación en directorios por responsabilidad (`src/`, `lib/`, `utils/`). Esto dificulta la escalabilidad cuando el proyecto crezca.
- **Recomendación**: Reorganizar en estructura de paquete:
  ```
  smartVisionQA/
  ├── src/
  │   ├── __init__.py
  │   ├── renderer.py       (HTMLRenderer)
  │   ├── analyzer.py       (VisionAnalyzer)
  │   ├── orchestrator.py   (SmartVisionQA)
  │   └── reporting/
  │       ├── __init__.py
  │       ├── html_report.py
  │       └── index_generator.py
  ├── tests/
  ├── demo/
  ├── scripts/
  └── ...
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `generate_html_report.py` (910 líneas)
- **Descripción**: Archivo monolítico que viola el Principio de Responsabilidad Única (SRP). Contiene: parsing de respuestas AI, limpieza de datos, generación de dashboard HTML, análisis visual, gráficos de distribución — todo en una sola clase.
- **Recomendación**: Separar en al menos 3 módulos: `response_parser.py`, `data_cleaner.py`, `html_builder.py`.

---

## 2. Calidad del Código

### Code Smells y Duplicación

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `smartVisionQA.py:23-55`
- **Descripción**: Los métodos `html_to_image()` y `url_to_image()` comparten ~90% del código. La única diferencia es cómo se navega (`file://` vs URL directa) y un `wait_for_timeout` adicional. Violación clara del principio DRY.
- **Recomendación**:
  ```python
  async def _render_to_image(self, target: str, is_url: bool = False, output_path: Path = None) -> bytes:
      async with async_playwright() as p:
          browser = await p.chromium.launch(headless=True)
          page = await browser.new_page()
          try:
              if is_url:
                  await page.goto(target, wait_until="networkidle")
                  await page.wait_for_timeout(2000)
              else:
                  await page.goto(f"file://{Path(target).absolute()}")
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
      return await self._render_to_image(url, is_url=True, output_path=output_path)
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `smartVisionQA.py:137-145` y `generate_html_report.py:534-546`
- **Descripción**: Lógica de limpieza/filtrado de listas de cambios duplicada en ambos archivos. Ambas realizan: verificar truthy, `isinstance(change, str)`, `strip()`, comparar con nombre de clave, verificar prefijo.
- **Recomendación**: Extraer a una función utilitaria compartida:
  ```python
  def clean_changes_list(changes: list, key: str) -> list:
      return [
          str(c).strip() for c in changes
          if c and str(c).strip() and str(c).strip() != key
          and not str(c).strip().startswith(f'"{key}"')
      ]
  ```

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: `smartVisionQA.py:9,11`
- **Descripción**: Imports no utilizados: `os` nunca se usa (se usa `pathlib.Path` en su lugar), y `List`, `Tuple` de `typing` tampoco se usan.
- **Recomendación**: Eliminar imports no usados:
  ```python
  # Eliminar:
  import os
  # Cambiar:
  from typing import Dict  # Solo Dict se usa
  ```

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: `generate_html_report.py:680`
- **Descripción**: Iteración innecesaria con variable descartada:
  ```python
  if not any(clean_line.lower().endswith('_changes') for _ in categories.keys()):
  ```
  El `for _ in categories.keys()` itera sobre las claves pero nunca las usa — `clean_line` no cambia en cada iteración, así que el resultado es el mismo en cada paso.
- **Recomendación**:
  ```python
  if not clean_line.lower().endswith('_changes'):
  ```

---

## 3. Bugs y Errores Potenciales

---

- **Severidad**: 🔴 Alta
- **Archivo/línea**: `smartVisionQA.py:77,128`
- **Descripción**: Acceso directo a `response['response']` sin verificar que la clave exista. Si la API de Ollama devuelve un error, cambia su formato de respuesta, o hay un timeout, se lanzará un `KeyError` no manejado que interrumpirá toda la ejecución.
- **Recomendación**:
  ```python
  raw_response = response.get('response', '')
  if not raw_response:
      return {"error": "Empty response from model", "layout_changes": [], ...}
  ```

---

- **Severidad**: 🔴 Alta
- **Archivo/línea**: `smartVisionQA.py:24-33,42-50`
- **Descripción**: Si cualquier operación entre `browser = await p.chromium.launch()` y `await browser.close()` lanza una excepción (e.g., timeout de navegación, error de red), el navegador quedará abierto como un proceso zombie. No hay `try/finally` protegiendo el cierre del recurso.
- **Recomendación**:
  ```python
  async with async_playwright() as p:
      browser = await p.chromium.launch(headless=True)
      try:
          page = await browser.new_page()
          # ... operaciones ...
          screenshot = await page.screenshot(full_page=True)
      finally:
          await browser.close()
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `smartVisionQA.py:130-131`
- **Descripción**: El parsing de JSON es frágil. `json_end = raw_response.rfind('}') + 1` devuelve `0` si no hay `}` (ya que `rfind` retorna `-1`). Aunque la condición `json_end > json_start` lo cubre parcialmente, el enfoque `find`/`rfind` fallará con JSON anidados que contengan `}` intermedios del prompt o texto libre.
- **Recomendación**: Usar regex para extraer JSON:
  ```python
  import re
  json_match = re.search(r'\{[\s\S]*\}', raw_response)
  if json_match:
      result = json.loads(json_match.group())
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `smartVisionQA.py:149-156`
- **Descripción**: El bloque `except Exception as e` captura TODAS las excepciones (incluidas `KeyboardInterrupt`, `SystemExit` si se propagan) y solo imprime el mensaje. No se loguea el stack trace, lo que hace imposible debuggear fallos en producción.
- **Recomendación**:
  ```python
  except (json.JSONDecodeError, ValueError, KeyError) as e:
      import traceback
      traceback.print_exc()
      result = { ... }
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `scripts/generate_index.py:281`
- **Descripción**: URL rota en el footer del dashboard:
  ```python
  <a href="https://github.com/{{}}/smartVisionQA">View on GitHub</a>
  ```
  Las dobles llaves `{{}}` son escape de f-string, produciendo `{}` literal en el HTML. El enlace resultante será `https://github.com/{}/smartVisionQA` — URL inválida.
- **Recomendación**: Usar una variable o un placeholder descriptivo:
  ```python
  github_user = os.environ.get('GITHUB_REPOSITORY_OWNER', 'your-username')
  # ... en el f-string:
  <a href="https://github.com/{github_user}/smartVisionQA">View on GitHub</a>
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `docker-entrypoint.sh:10-12`
- **Descripción**: El bucle `until curl ... ; do sleep 2; done` no tiene timeout. Si Ollama no arranca nunca (crash, OOM), el contenedor se quedará en un bucle infinito consumiendo recursos.
- **Recomendación**:
  ```bash
  MAX_RETRIES=30
  RETRY=0
  until curl -s http://localhost:11434/api/version > /dev/null; do
      RETRY=$((RETRY+1))
      if [ $RETRY -ge $MAX_RETRIES ]; then
          echo "ERROR: Ollama no arrancó tras $MAX_RETRIES intentos"
          exit 1
      fi
      sleep 2
  done
  ```

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: `smartVisionQA.py:244-246`
- **Descripción**: `file1_name.replace('.html', '')` es un sanitizado muy básico para nombres de archivo. Si el nombre contiene caracteres especiales, espacios, o la extensión aparece en medio del nombre (e.g., `page.html.bak`), el resultado será inesperado. Además, URLs procesadas por `generate_report` producirán nombres de archivo con `/`, `:` y otros caracteres inválidos.
- **Recomendación**: Usar una función de sanitización apropiada:
  ```python
  import re
  def sanitize_filename(name: str) -> str:
      name = Path(name).stem if name.endswith('.html') else name
      return re.sub(r'[^\w\-.]', '_', name)
  ```

---

## 4. Seguridad

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: No aplica
- **Descripción**: No se detectaron credenciales hardcodeadas, tokens ni API keys. El proyecto no maneja autenticación de usuario ni bases de datos, lo que reduce la superficie de ataque. Las rutas de archivos se manejan con `pathlib.Path` (buena práctica).
- **Recomendación**: Ninguna acción inmediata.

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `generate_html_report.py:611`
- **Descripción**: Potencial XSS almacenado. Los textos de cambios provenientes de la respuesta del modelo AI se insertan directamente en HTML sin escapar:
  ```python
  <span style="flex: 1; color: #374151;">{change_text}</span>
  ```
  Si el modelo genera contenido con `<script>` o atributos maliciosos, se ejecutarían al abrir el reporte.
- **Recomendación**:
  ```python
  from html import escape
  change_text = escape(change_text)
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `Dockerfile:16`
- **Descripción**: `curl -fsSL https://ollama.ai/install.sh | sh` ejecuta un script remoto como root sin verificación de integridad. En entornos de producción esto es un riesgo de cadena de suministro.
- **Recomendación**: Usar una versión pinneada del instalador o instalar desde paquete `.deb` con hash verificado.

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `Dockerfile` (completo)
- **Descripción**: El contenedor ejecuta todo como `root`. Si hay una vulnerabilidad en Playwright/Chromium o Ollama, el atacante tendría privilegios de root dentro del contenedor.
- **Recomendación**:
  ```dockerfile
  RUN useradd -m -s /bin/bash appuser
  USER appuser
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `requirements.txt:1`
- **Descripción**: `ollama==0.3.3` está significativamente desactualizado (versión actual: 0.6.x). Múltiples versiones de diferencia pueden incluir parches de seguridad y correcciones de bugs críticos.
- **Recomendación**: Actualizar a la última versión estable: `ollama>=0.6.0`.

---

## 5. Testing

---

- **Severidad**: 🔴 Alta
- **Archivo/línea**: Todo el proyecto
- **Descripción**: **No existe ningún test en todo el repositorio.** Cobertura: 0%. No hay directorio `tests/`, no hay archivos `test_*.py`, no se importa ningún framework de testing (pytest, unittest). El pipeline de CI/CD tampoco ejecuta tests.
- **Recomendación**: Crear suite de tests mínima:

  **Tests unitarios prioritarios:**
  1. `test_vision_analyzer.py` - Parseo de JSON de respuestas AI (caso éxito, JSON malformado, respuesta vacía)
  2. `test_html_report.py` - Generación de HTML, limpieza de cambios, categorización
  3. `test_html_renderer.py` - Renderizado con mock de Playwright
  4. `test_generate_index.py` - Generación de índice con datos de prueba

  **Tests de integración:**
  5. `test_comparison_pipeline.py` - Flujo completo con mocks de Ollama

  **Ejemplo de test crítico:**
  ```python
  # tests/test_vision_analyzer.py
  import pytest
  from unittest.mock import MagicMock, patch
  from smartVisionQA import VisionAnalyzer

  def test_compare_images_valid_json():
      analyzer = VisionAnalyzer()
      analyzer.client = MagicMock()
      analyzer.client.generate.return_value = {
          'response': '{"layout_changes": ["header moved"], "text_changes": [], "style_changes": [], "element_changes": []}'
      }
      result = analyzer.compare_images(b'\x89PNG...', b'\x89PNG...')
      assert "layout_changes" in result
      assert len(result["layout_changes"]) == 1

  def test_compare_images_malformed_response():
      analyzer = VisionAnalyzer()
      analyzer.client = MagicMock()
      analyzer.client.generate.return_value = {
          'response': 'This is not JSON at all'
      }
      result = analyzer.compare_images(b'\x89PNG...', b'\x89PNG...')
      assert "layout_changes" in result  # Should fallback gracefully

  def test_compare_images_empty_response():
      analyzer = VisionAnalyzer()
      analyzer.client = MagicMock()
      analyzer.client.generate.return_value = {}
      # Should handle KeyError gracefully
      with pytest.raises(KeyError):  # Current behavior - should be fixed
          analyzer.compare_images(b'\x89PNG...', b'\x89PNG...')
  ```

---

## 6. Rendimiento

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `smartVisionQA.py:24-55`
- **Descripción**: Cada llamada a `html_to_image()` o `url_to_image()` lanza una nueva instancia completa de Chromium. Para 3 comparaciones = 6 instancias de navegador creadas y destruidas. El overhead de inicialización de Playwright es significativo (~1-3 segundos por instancia).
- **Recomendación**: Reutilizar la instancia del navegador:
  ```python
  class HTMLRenderer:
      def __init__(self):
          self._playwright = None
          self._browser = None

      async def _get_browser(self):
          if not self._browser:
              self._playwright = await async_playwright().start()
              self._browser = await self._playwright.chromium.launch(headless=True)
          return self._browser

      async def close(self):
          if self._browser:
              await self._browser.close()
          if self._playwright:
              await self._playwright.stop()
  ```

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: `smartVisionQA.py:102-117`
- **Descripción**: Se crea una imagen combinada (apilando V1 y V2 verticalmente) para enviar al modelo. Esto duplica el uso de memoria RAM y el tamaño del payload enviado a Ollama. Para imágenes de página completa, esto puede ser varios MB.
- **Recomendación**: Considerar enviar las dos imágenes por separado al modelo (la API de Ollama soporta múltiples imágenes en el campo `images`):
  ```python
  response = self.client.generate(
      model=self.model,
      prompt=prompt,
      images=[img1_bytes, img2_bytes],  # Dos imágenes separadas
      stream=False
  )
  ```

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: `smartVisionQA.py:248-252`
- **Descripción**: Para cada comparación se escribe un JSON a disco y luego `generate_from_json()` lo vuelve a leer inmediatamente. Esto introduce I/O innecesario cuando los datos ya están en memoria.
- **Recomendación**: Pasar el diccionario directamente al generador HTML:
  ```python
  generator = HTMLReportGenerator(self.results_dir)
  html_report_path = generator.generate_html_report(results)
  ```

---

## 7. Documentación y Mantenibilidad

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: `README.md`
- **Descripción**: El README es razonablemente completo: incluye requisitos, instalación, uso con Docker y CI/CD, y personalización. Sin embargo, le faltan secciones comunes: troubleshooting, contribución, licencia, y la referencia a la línea 300 para modificar test cases es incorrecta (la función `main()` con los test cases está en la línea 262).
- **Recomendación**: Actualizar la referencia de línea y añadir secciones de troubleshooting y contribución.

---

- **Severidad**: 🟡 Media
- **Archivo/línea**: Todos los archivos Python
- **Descripción**: Se usa `print()` en lugar del módulo `logging` estándar de Python. Esto impide: filtrar por nivel de severidad, redirigir a archivos, añadir timestamps automáticos, y desactivar logs en producción.
- **Recomendación**:
  ```python
  import logging

  logging.basicConfig(
      level=logging.INFO,
      format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  )
  logger = logging.getLogger(__name__)

  # Reemplazar:
  # print(f"Renderizando {html1}...")
  logger.info("Renderizando %s...", html1)
  ```

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: `smartVisionQA.py:60-62`
- **Descripción**: El modelo de Ollama está hardcodeado como valor por defecto (`"qwen2.5vl:7b"`). No es configurable por variable de entorno.
- **Recomendación**:
  ```python
  import os
  def __init__(self, model: str = None):
      self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b")
  ```

---

- **Severidad**: 🟢 Baja
- **Archivo/línea**: `.gitignore`
- **Descripción**: Falta excluir patrones comunes: `venv/`, `.venv/`, `.env`, `.idea/`, `.vscode/`, `*.egg-info/`, `dist/`, `build/`.
- **Recomendación**: Ampliar el `.gitignore`:
  ```
  /results/
  .DS_Store
  __pycache__/
  *.pyc
  venv/
  .venv/
  .env
  .idea/
  .vscode/
  *.egg-info/
  dist/
  build/
  ```

---

## Resumen Ejecutivo

### Top 5 Puntos Críticos a Abordar

| # | Severidad | Hallazgo | Impacto |
|---|-----------|----------|---------|
| 1 | 🔴 Alta | **0% cobertura de tests** — No existe ningún test en el proyecto | Cualquier cambio puede romper funcionalidad sin que nadie lo detecte. Bloquea la evolución segura del proyecto. |
| 2 | 🔴 Alta | **KeyError sin manejar en respuestas de Ollama** (`smartVisionQA.py:77,128`) | Crash completo del programa si la API devuelve un formato inesperado. |
| 3 | 🔴 Alta | **Resource leak en Playwright** (`smartVisionQA.py:24-33`) — navegadores no se cierran si hay excepción | Procesos zombie de Chromium, especialmente en Docker donde los recursos son limitados. |
| 4 | 🟡 Media | **XSS potencial en reportes HTML** (`generate_html_report.py:611`) — contenido del modelo AI insertado sin escapar | Un modelo que genere `<script>` inyectaría código ejecutable en los reportes. |
| 5 | 🟡 Media | **Dependencia `ollama` desactualizada** (0.3.3 vs 0.6.x) y **Docker ejecutando como root** | Riesgos de seguridad y compatibilidad acumulados. |

### Estadísticas Generales

| Métrica | Valor |
|---------|-------|
| Líneas de código totales | ~1,615 |
| Hallazgos 🔴 Alta | 3 |
| Hallazgos 🟡 Media | 11 |
| Hallazgos 🟢 Baja | 6 |
| Cobertura de tests | 0% |
| Código duplicado estimado | ~15% |
| Archivos Python | 4 |
| Dependencias | 3 |
