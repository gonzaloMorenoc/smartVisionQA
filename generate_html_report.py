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
        
        /* Dashboard Styles */
        .dashboard {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }}
        
        .dashboard-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            border-bottom: 2px solid #f1f5f9;
            padding-bottom: 15px;
        }}
        
        .dashboard-header h3 {{
            color: #1e293b;
            font-size: 1.5rem;
            margin: 0;
        }}
        
        .severity-badge {{
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .severity-badge.low {{
            background: #dcfce7;
            color: #166534;
        }}
        
        .severity-badge.medium {{
            background: #fef3c7;
            color: #92400e;
        }}
        
        .severity-badge.high {{
            background: #fecaca;
            color: #991b1b;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .metric-card {{
            text-align: center;
            padding: 20px;
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }}
        
        .metric-number {{
            font-size: 2rem;
            font-weight: bold;
            color: #3b82f6;
            margin-bottom: 5px;
        }}
        
        .metric-label {{
            color: #64748b;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        
        .distribution-chart {{
            margin-bottom: 30px;
        }}
        
        .distribution-chart h4 {{
            color: #1e293b;
            margin-bottom: 15px;
            font-size: 1.2rem;
        }}
        
        .chart-container {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 20px;
        }}
        
        .chart-item {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
        }}
        
        .chart-bar {{
            height: 20px;
            border-radius: 10px;
            margin-right: 15px;
            min-width: 20px;
            transition: width 0.3s ease;
        }}
        
        .chart-label {{
            color: #374151;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        
        .changes-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
        }}
        
        .change-card {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 20px;
            border-left: 4px solid #e2e8f0;
            transition: transform 0.2s;
        }}
        
        .change-card:hover {{
            transform: translateY(-2px);
        }}
        
        .change-card.layout {{
            border-left-color: #ef4444;
        }}
        
        .change-card.text {{
            border-left-color: #f97316;
        }}
        
        .change-card.style {{
            border-left-color: #3b82f6;
        }}
        
        .change-card.element {{
            border-left-color: #22c55e;
        }}
        
        .card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }}
        
        .card-header h4 {{
            color: #1e293b;
            margin: 0;
            font-size: 1.1rem;
        }}
        
        .card-icon {{
            font-size: 1.2rem;
            margin-right: 10px;
        }}
        
        .change-count {{
            background: #e2e8f0;
            color: #475569;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        
        .card-progress {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .progress-bar {{
            flex: 1;
            height: 8px;
            background: #e2e8f0;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .progress-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }}
        
        .progress-fill.layout {{
            background: #ef4444;
        }}
        
        .progress-fill.text {{
            background: #f97316;
        }}
        
        .progress-fill.style {{
            background: #3b82f6;
        }}
        
        .progress-fill.element {{
            background: #22c55e;
        }}
        
        .percentage {{
            color: #64748b;
            font-size: 0.9rem;
            font-weight: 600;
            min-width: 50px;
        }}
        
        .status-card {{
            display: flex;
            align-items: center;
            padding: 25px;
            border-radius: 12px;
            border: 2px solid #e2e8f0;
        }}
        
        .status-card.success {{
            background: #f0fdf4;
            border-color: #22c55e;
        }}
        
        .status-icon {{
            font-size: 2rem;
            margin-right: 20px;
        }}
        
        .status-content h4 {{
            color: #1e293b;
            margin-bottom: 5px;
            font-size: 1.3rem;
        }}
        
        .status-content p {{
            color: #64748b;
            margin: 0;
        }}
        
        .detailed-analysis {{
            margin-top: 30px;
        }}
        
        .detailed-analysis details {{
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }}
        
        .detailed-analysis summary {{
            padding: 15px 20px;
            cursor: pointer;
            font-weight: 600;
            color: #374151;
            border-radius: 8px;
            transition: background 0.2s;
        }}
        
        .detailed-analysis summary:hover {{
            background: #e2e8f0;
        }}
        
        .detailed-analysis .raw-analysis {{
            margin: 0;
            border-top: 1px solid #e2e8f0;
            border-radius: 0 0 8px 8px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Visual QA Report</h1>
            <div class="comparison-info">
                Comparing: <strong>V1: {results['file1']}</strong> vs <strong>V2: {results['file2']}</strong>
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
        
        file1_name = results['file1'].replace('.html', '')
        file2_name = results['file2'].replace('.html', '')
        report_filename = f"visual_report_{file1_name}_vs_{file2_name}.html"
        report_path = self.results_dir / report_filename
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return report_path
    
    def _generate_changes_html(self, diff: Dict) -> str:
        """Genera HTML para los cambios detectados"""
        
        # Si tenemos datos estructurados JSON, usarlos directamente
        if any(diff.get(key) for key in ['layout_changes', 'text_changes', 'style_changes', 'element_changes']):
            return self._generate_structured_changes(diff)
        
        # Si solo tenemos raw_response, parsearlo
        if 'raw_response' in diff:
            analysis_data = self._parse_raw_analysis(diff['raw_response'])
            return self._create_visual_analysis(analysis_data, diff['raw_response'])
        
        return self._generate_no_changes_dashboard()

    def _generate_structured_changes(self, diff: Dict) -> str:
        """Genera HTML desde datos JSON estructurados"""
        
        change_types = {
            'layout_changes': ('layout', 'Layout Changes', '🏗️'),
            'text_changes': ('text', 'Text Changes', '📝'), 
            'style_changes': ('style', 'Style Changes', '🎨'),
            'element_changes': ('element', 'Element Changes', '🔧')
        }
        
        total_changes = 0
        change_categories = []
        
        for key, (css_class, title, icon) in change_types.items():
            changes = diff.get(key, [])
            
            # Filtrar elementos vacíos o que sean la propia clave
            if changes and isinstance(changes, list):
                # Limpiar la lista de cambios
                clean_changes = []
                for change in changes:
                    # Convertir a string y limpiar
                    change_str = str(change).strip()
                    
                    # Ignorar si es la propia clave, está vacío, o es solo formato JSON
                    if (change_str and 
                        change_str != key and 
                        not change_str.startswith(f'"{key}"') and
                        not change_str.startswith(key + ':') and
                        change_str not in ['[', ']', '{', '}', '[]']):
                        clean_changes.append(change_str)
                
                if clean_changes:  # Solo añadir si hay cambios reales
                    total_changes += len(clean_changes)
                    change_categories.append({
                        'type': css_class,
                        'title': title,
                        'icon': icon,
                        'count': len(clean_changes),
                        'changes': clean_changes
                    })
        
        if total_changes == 0:
            return self._generate_no_changes_dashboard()
        
        # Dashboard con métricas
        dashboard_html = self._generate_changes_dashboard(change_categories, total_changes)
        
        # Añadir sección detallada con cada cambio individual
        details_html = self._generate_detailed_changes(change_categories)
        
        # Si hay raw_response, añadirlo como sección expandible
        if 'raw_response' in diff:
            details_html += self._generate_formatted_analysis(diff['raw_response'])
        
        return dashboard_html + details_html
    
    def _generate_detailed_changes(self, categories: list) -> str:
        """Genera sección HTML con lista detallada de cambios"""
        
        if not categories:
            return ""
        
        details_html = """
        <div class="analysis-section" style="margin-top: 30px;">
            <h2>📋 Detailed Changes</h2>
        """
        
        for category in categories:
            color_map = {
                'layout': '#fef3f2',
                'text': '#fff7ed',
                'style': '#f0f9ff',
                'element': '#f0fdf4'
            }
            
            details_html += f"""
            <div class="change-category {category['type']}" style="background: {color_map.get(category['type'], '#f8fafc')};">
                <h3>
                    <span style="margin-right: 10px;">{category['icon']}</span>
                    {category['title']} 
                    <span style="background: #e2e8f0; padding: 2px 8px; border-radius: 12px; font-size: 0.9rem; margin-left: 10px;">
                        {category['count']} change{'s' if category['count'] > 1 else ''}
                    </span>
                </h3>
                <ul class="change-list">
        """
            
            # Mostrar cada cambio individual
            for i, change in enumerate(category['changes'], 1):
                change_text = change if isinstance(change, str) else str(change)
                details_html += f"""
                    <li style="display: flex; align-items: start;">
                        <span style="color: #64748b; min-width: 25px; font-weight: 600;">{i}.</span>
                        <span style="flex: 1; color: #374151;">{change_text}</span>
                    </li>
                """
            
            details_html += """
                </ul>
            </div>
            """
        
        details_html += """
        </div>
        """
        
        return details_html

    def _parse_raw_analysis(self, raw_text: str) -> Dict:
        """Extrae insights categorizados del análisis de texto libre"""
        
        categories = {
            'layout': {
                'keywords': ['layout', 'position', 'grid', 'flex', 'alignment', 'structure', 'spacing', 'moved'],
                'changes': []
            },
            'text': {
                'keywords': ['text', 'font', 'typography', 'content', 'heading', 'paragraph', 'title', 'label'],
                'changes': []
            },
            'style': {
                'keywords': ['color', 'background', 'border', 'shadow', 'gradient', 'style', 'theme', 'dark'],
                'changes': []
            },
            'element': {
                'keywords': ['button', 'element', 'component', 'widget', 'card', 'section', 'badge', 'banner'],
                'changes': []
            }
        }
        
        # Dividir por líneas o frases
        lines = raw_text.replace('. ', '.\n').split('\n')
        
        for line in lines:
            line_clean = line.strip()
            
            # Ignorar líneas que son formato JSON o están vacías
            if (not line_clean or 
                len(line_clean) < 10 or
                line_clean in ['[', ']', '{', '}'] or
                any(line_clean.startswith(f'"{key}_changes"') for key in categories.keys()) or
                any(line_clean.startswith(f'{key}_changes:') for key in categories.keys())):
                continue
                
            # Asignar cada línea a la categoría más relevante
            best_match = None
            best_score = 0
            
            for cat_name, cat_data in categories.items():
                score = sum(1 for keyword in cat_data['keywords'] 
                        if keyword.lower() in line_clean.lower())
                if score > best_score:
                    best_score = score
                    best_match = cat_name
            
            if best_match and best_score > 0:
                # Limpiar y capitalizar la línea
                clean_line = line_clean.strip('.-,[]"\' ')
                if clean_line and not clean_line[0].isupper():
                    clean_line = clean_line[0].upper() + clean_line[1:]
                
                # No añadir si es una clave JSON
                if not any(clean_line.lower().endswith('_changes') for _ in categories.keys()):
                    categories[best_match]['changes'].append(clean_line)
        
        # Contar cambios detectados
        detected_changes = {cat: len(data['changes']) 
                        for cat, data in categories.items()}
        
        return {
            'categories': categories,
            'detected_changes': detected_changes,
            'total_changes': sum(detected_changes.values())
        }
    
    def _create_visual_analysis(self, analysis_data: Dict, raw_text: str) -> str:
        """Crea análisis visual desde datos parseados"""
        
        change_types = {
            'layout': ('layout', 'Layout Changes', '🏗️'),
            'text': ('text', 'Text Changes', '📝'),
            'style': ('style', 'Style Changes', '🎨'),
            'element': ('element', 'Element Changes', '🔧')
        }
        
        categories = []
        total_changes = analysis_data['total_changes']
        
        # Usar los cambios categorizados específicos
        for key, (css_class, title, icon) in change_types.items():
            if key in analysis_data.get('categories', {}):
                changes = analysis_data['categories'][key]['changes']
                if changes:
                    categories.append({
                        'type': css_class,
                        'title': title,
                        'icon': icon,
                        'count': len(changes),
                        'changes': changes  # Cambios específicos por categoría
                    })
        
        if not categories:
            return self._generate_no_changes_dashboard()
        
        # Dashboard con métricas
        dashboard_html = self._generate_changes_dashboard(categories, total_changes)
        
        # Detalles de cambios
        details_html = self._generate_detailed_changes(categories)
        
        # Análisis formateado (no JSON crudo)
        details_html += self._generate_formatted_analysis(raw_text)
        
        return dashboard_html + details_html
    
    def _generate_formatted_analysis(self, raw_text: str) -> str:
        """Genera versión formateada del análisis AI"""
        
        # Formatear el texto para mejor legibilidad
        formatted_lines = []
        for line in raw_text.split('\n'):
            line = line.strip()
            if line:
                # Detectar y formatear secciones
                if any(marker in line.upper() for marker in ['LAYOUT', 'TEXT', 'STYLE', 'ELEMENT']):
                    formatted_lines.append(f"<strong>{line}</strong>")
                elif line.startswith('-') or line.startswith('•') or line.startswith('*'):
                    formatted_lines.append(f"  {line}")
                else:
                    formatted_lines.append(line)
        
        formatted_text = '<br>'.join(formatted_lines)
        
        return f"""
        <div class="detailed-analysis" style="margin-top: 30px;">
            <details>
                <summary style="cursor: pointer; padding: 15px; background: #f8fafc; border-radius: 8px; font-weight: 600;">
                    🤖 View AI Analysis Summary
                </summary>
                <div style="padding: 20px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 0 0 8px 8px; margin-top: -1px;">
                    <div style="font-family: 'Segoe UI', sans-serif; line-height: 1.8; color: #374151;">
                        {formatted_text}
                    </div>
                </div>
            </details>
        </div>
        """
        
    def _generate_no_changes_dashboard(self) -> str:
        """Dashboard cuando no hay cambios"""
        return """
        <div class="dashboard">
            <div class="dashboard-header">
                <h3>📊 Analysis Dashboard</h3>
            </div>
            <div class="status-card success">
                <div class="status-icon">✅</div>
                <div class="status-content">
                    <h4>No Visual Changes Detected</h4>
                    <p>The pages appear to be visually identical</p>
                </div>
            </div>
        </div>
        """
    
    def _generate_changes_dashboard(self, categories: list, total_changes: int) -> str:
        """Genera dashboard visual con métricas"""
        
        # Calcular severidad
        severity = "Low" if total_changes <= 2 else "Medium" if total_changes <= 5 else "High"
        severity_class = severity.lower()
        
        # Generar gráfico de distribución
        chart_html = self._generate_distribution_chart(categories, total_changes)
        
        # Generar tarjetas de cambios
        cards_html = ""
        for category in categories:
            percentage = (category['count'] / total_changes) * 100
            cards_html += f"""
            <div class="change-card {category['type']}">
                <div class="card-header">
                    <span class="card-icon">{category['icon']}</span>
                    <h4>{category['title']}</h4>
                    <span class="change-count">{category['count']}</span>
                </div>
                <div class="card-progress">
                    <div class="progress-bar">
                        <div class="progress-fill {category['type']}" style="width: {percentage}%"></div>
                    </div>
                    <span class="percentage">{percentage:.1f}%</span>
                </div>
            </div>
            """
        
        return f"""
        <div class="dashboard">
            <div class="dashboard-header">
                <h3>📊 Analysis Dashboard</h3>
                <div class="severity-badge {severity_class}">{severity} Impact</div>
            </div>
            
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-number">{total_changes}</div>
                    <div class="metric-label">Total Changes</div>
                </div>
                <div class="metric-card">
                    <div class="metric-number">{len(categories)}</div>
                    <div class="metric-label">Categories Affected</div>
                </div>
                <div class="metric-card">
                    <div class="metric-number">{severity}</div>
                    <div class="metric-label">Impact Level</div>
                </div>
            </div>
            
            {chart_html}
            
            <div class="changes-grid">
                {cards_html}
            </div>
        </div>
        """
    
    def _generate_distribution_chart(self, categories: list, total: int) -> str:
        """Genera gráfico de distribución simple con CSS"""
        if not categories:
            return ""
        
        chart_items = ""
        colors = {'layout': '#ef4444', 'text': '#f97316', 'style': '#3b82f6', 'element': '#22c55e'}
        
        for category in categories:
            percentage = (category['count'] / total) * 100
            color = colors.get(category['type'], '#6b7280')
            chart_items += f"""
            <div class="chart-item">
                <div class="chart-bar" style="width: {percentage}%; background: {color};"></div>
                <span class="chart-label">{category['title']}: {category['count']}</span>
            </div>
            """
        
        return f"""
        <div class="distribution-chart">
            <h4>📈 Change Distribution</h4>
            <div class="chart-container">
                {chart_items}
            </div>
        </div>
        """
    
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
