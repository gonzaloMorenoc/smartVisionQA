# SmartVisionQA

Prueba de concepto para testing visual automatizado usando Ollama y modelos de visión locales.

## Requisitos

- Python 3.8+
- Ollama instalado y ejecutándose
- Modelo de visión LLaVA descargado

## Instalación

1. Instalar Ollama:
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

2. Descargar modelo de visión:
```bash
ollama pull llava:7b
```

3. Instalar dependencias Python:
```bash
pip install -r requirements.txt
playwright install chromium
```

## Estructura del Proyecto

```
smartVisionQA/
├── smartVisionQA.py      # Script principal
├── demo/                 # HTMLs de ejemplo
│   ├── page_v1.html     # Versión 1
│   └── page_v2.html     # Versión 2 con cambios
├── results/             # Capturas y reportes (generado)
└── requirements.txt     # Dependencias
```

## Uso

Ejecutar comparación básica:
```bash
python smartVisionQA.py
```

El script:
1. Renderiza los HTMLs a imágenes
2. Usa Ollama para analizar diferencias visuales
3. Genera reporte en `results/comparison_report.json`

## Personalización

Para comparar otros HTMLs, modificar en `smartVisionQA.py`:

**Línea 169-171** - Lista de casos de prueba:
```python
test_cases = [
    ("tu_archivo1.html", "tu_archivo2.html"),
]
```

**Línea 52** - Cambiar modelo de Ollama:
```python
def __init__(self, model: str = "llava:13b"):  # Para más precisión
```

## Extensión

Para integrar con Selenium/Playwright para webs reales:

**En la clase HTMLRenderer (línea 18)**, agregar método:
```python
async def url_to_image(self, url: str) -> bytes:
    # Implementar captura de URL real
    pass
```

## Notas

- Requiere ~4GB RAM para modelo llava:7b
- Primera ejecución descarga modelo (~4GB)
- Capturas guardadas en `results/`