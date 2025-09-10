#!/usr/bin/env python3
"""
HTML Report Generator para SmartVisionQA
Convierte reportes JSON en reportes HTML visuales
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict


class HTMLReportGenerator:
    """Genera reportes HTML visuales a partir de resultados JSON"""
    
    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
    
    def generate_html_report(self, results: Dict) -> Path:
        """Genera reporte HTML con imágenes y análisis"""
        
        file1_name = results['file1'].replace('.html', '')
        file2_name = results['file2'].replace('.html', '')
        img1_path = f"{file1_name}_screenshot.png"
        img2_path = f"{file2_name}_screenshot.png"
        
        diff = results['differences']
        
        # Template HTML
        html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visual QA Report - {file1_name} vs {file2_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #f8fafc;
            padding: 20px;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }}
        
        .header h1 {{
            color: #1e293b;
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}
        
        .comparison-info {{
            color: #64748b;
            font-size: 1.1rem;
        }}
        
        .comparison-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .screenshot-panel {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }}
        
        .screenshot-panel h3 {{
            color: #1e293b;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}
        
        .screenshot-panel img {{
            width: 100%;
            height: auto;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }}
        
        .analysis-section {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }}
        
        .analysis-section h2 {{
            color: #1e293b;
            margin-bottom: 25px;
            font-size: 1.8rem;
        }}
        
        .change-category {{
            margin-bottom: 25px;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #e2e8f0;
        }}
        
        .change-category.layout {{
            background: #fef3f2;
            border-color: #ef4444;
        }}
        
        .change-category.text {{
            background: #fff7ed;
            border-color: #f97316;
        }}
        
        .change-category.style {{
            background: #f0f9ff;
            border-color: #3b82f6;
        }}
        
        .change-category.element {{
            background: #f0fdf4;
            border-color: #22c55e;
        }}
        
        .change-category h3 {{
            color: #1e293b;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }}
        
        .change-list {{
            list-style: none;
        }}
        
        .change-list li {{
            padding: 8px 0;
            border-bottom: 1px solid rgba(0,0,0,0.05);
        }}
        
        .change-list li:last-child {{
            border-bottom: none;
        }}
        
        .raw-analysis {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
            font-family: 'Courier New', monospace;
            white-space: pre-wrap;
            border: 1px solid #e2e8f0;
        }}
        
        .timestamp {{
            text-align: center;
            color: #64748b;
            margin-top: 30px;
            font-size: 0.9rem;
        }}
        
        .no-changes {{
            text-align: center;
            color: #22c55e;
            font-size: 1.1rem;
            padding: 20px;
            background: #f0fdf4;
            border-radius: 8px;
            border: 1px solid #22c55e;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Visual QA Report</h1>
            <div class="comparison-info">
                Comparing: <strong>{results['file1']}</strong> vs <strong>{results['file2']}</strong>
            </div>
        </div>
        
        <div class="comparison-grid">
            <div class="screenshot-panel">
                <h3>Version 1: {file1_name}</h3>
                <img src="{img1_path}" alt="Screenshot of {file1_name}">
            </div>
            <div class="screenshot-panel">
                <h3>Version 2: {file2_name}</h3>
                <img src="{img2_path}" alt="Screenshot of {file2_name}">
            </div>
        </div>
        
        <div class="analysis-section">
            <h2>Visual Analysis Results</h2>
            {self._generate_changes_html(diff)}
        </div>
        
        <div class="timestamp">
            Report generated on {self._get_timestamp()}
        </div>
    </div>
</body>
</html>"""
        
        report_path = self.results_dir / "visual_report.html"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return report_path
    
    def _generate_changes_html(self, diff: Dict) -> str:
        """Genera HTML para los cambios detectados"""
        
        if 'raw_response' in diff:
            return f'<div class="raw-analysis">{diff["raw_response"]}</div>'
        
        change_types = {
            'layout_changes': ('layout', 'Layout Changes'),
            'text_changes': ('text', 'Text Changes'), 
            'style_changes': ('style', 'Style Changes'),
            'element_changes': ('element', 'Element Changes')
        }
        
        html_parts = []
        has_changes = False
        
        for key, (css_class, title) in change_types.items():
            changes = diff.get(key, [])
            if changes:
                has_changes = True
                changes_html = ""
                if isinstance(changes, list):
                    changes_html = "<ul class='change-list'>"
                    for change in changes:
                        changes_html += f"<li>{change}</li>"
                    changes_html += "</ul>"
                else:
                    changes_html = f"<p>{changes}</p>"
                
                html_parts.append(f"""
                <div class="change-category {css_class}">
                    <h3>{title}</h3>
                    {changes_html}
                </div>
                """)
        
        if not has_changes:
            return '<div class="no-changes">No significant visual changes detected</div>'
        
        return "".join(html_parts)
    
    def _get_timestamp(self) -> str:
        """Obtiene timestamp formateado"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def generate_from_json(json_path: Path, results_dir: Path = None) -> Path:
    """Función para generar HTML desde archivo JSON"""
    if results_dir is None:
        results_dir = json_path.parent
    
    with open(json_path, 'r') as f:
        results = json.load(f)
    
    generator = HTMLReportGenerator(results_dir)
    return generator.generate_html_report(results)


def main():
    """Script principal para ejecutar desde línea de comandos"""
    if len(sys.argv) < 2:
        print("Uso: python generate_html_report.py <comparison_report.json>")
        print("Ejemplo: python generate_html_report.py results/comparison_report.json")
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    
    if not json_path.exists():
        print(f"Error: No se encontró {json_path}")
        sys.exit(1)
    
    try:
        html_path = generate_from_json(json_path)
        print(f"Reporte HTML generado: {html_path}")
    except Exception as e:
        print(f"Error generando reporte HTML: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
