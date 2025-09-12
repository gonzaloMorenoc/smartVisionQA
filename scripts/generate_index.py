#!/usr/bin/env python3
"""
Genera índice HTML para todos los reportes generados
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict


def generate_index_html(results_dir: Path) -> None:
    """Genera página de índice con todos los reportes"""
    
    reports = []
    
    # Buscar todos los reportes JSON
    for json_file in results_dir.glob("comparison_*.json"):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Buscar HTML correspondiente
            html_file = json_file.with_name(
                json_file.name.replace("comparison_", "visual_report_").replace(".json", ".html")
            )
            
            if html_file.exists():
                # Contar cambios
                diff = data.get('differences', {})
                total_changes = 0
                
                if isinstance(diff, dict):
                    for key in ['layout_changes', 'text_changes', 'style_changes', 'element_changes']:
                        changes = diff.get(key, [])
                        if isinstance(changes, list):
                            total_changes += len([c for c in changes if c and str(c).strip()])
                
                reports.append({
                    'json_file': json_file.name,
                    'html_file': html_file.name,
                    'file1': data.get('file1', 'Unknown'),
                    'file2': data.get('file2', 'Unknown'),
                    'total_changes': total_changes,
                    'timestamp': json_file.stat().st_mtime
                })
        
        except Exception as e:
            print(f"Error procesando {json_file}: {e}")
    
    # Ordenar por timestamp (más reciente primero)
    reports.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Generar HTML
    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartVisionQA - Reports Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            color: #333;
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}
        
        .subtitle {{
            color: #666;
            font-size: 1.1rem;
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }}
        
        .stat-number {{
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9rem;
        }}
        
        .reports-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }}
        
        .report-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }}
        
        .report-card:hover {{
            transform: translateY(-5px);
        }}
        
        .report-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .comparison-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #333;
        }}
        
        .changes-badge {{
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        
        .changes-badge.no-changes {{
            background: #22c55e;
        }}
        
        .changes-badge.medium {{
            background: #f97316;
        }}
        
        .changes-badge.high {{
            background: #ef4444;
        }}
        
        .comparison-files {{
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 20px;
            line-height: 1.4;
        }}
        
        .actions {{
            display: flex;
            gap: 10px;
        }}
        
        .btn {{
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 600;
            transition: background 0.3s;
            cursor: pointer;
        }}
        
        .btn-primary {{
            background: #667eea;
            color: white;
        }}
        
        .btn-primary:hover {{
            background: #5a6fd8;
        }}
        
        .btn-secondary {{
            background: #f1f5f9;
            color: #64748b;
        }}
        
        .btn-secondary:hover {{
            background: #e2e8f0;
        }}
        
        .timestamp {{
            color: #94a3b8;
            font-size: 0.8rem;
            margin-top: 15px;
        }}
        
        .no-reports {{
            text-align: center;
            background: white;
            border-radius: 15px;
            padding: 60px;
            color: #666;
        }}
        
        .github-info {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            padding: 20px;
            margin-top: 30px;
            text-align: center;
            color: white;
        }}
        
        .github-info a {{
            color: white;
            text-decoration: none;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SmartVisionQA Dashboard</h1>
            <p class="subtitle">Visual Regression Testing Reports</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{len(reports)}</div>
                <div class="stat-label">Total Reports</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{sum(r['total_changes'] for r in reports)}</div>
                <div class="stat-label">Total Changes</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len([r for r in reports if r['total_changes'] == 0])}</div>
                <div class="stat-label">Identical Pages</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len([r for r in reports if r['total_changes'] > 5])}</div>
                <div class="stat-label">High Impact</div>
            </div>
        </div>
        
        {_generate_reports_html(reports)}
        
        <div class="github-info">
            <p>Generated by SmartVisionQA Pipeline • 
            <a href="https://github.com/{{}}/smartVisionQA">View on GitHub</a> • 
            Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
    </div>
</body>
</html>"""
    
    index_path = results_dir / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Índice generado: {index_path}")


def _generate_reports_html(reports: List[Dict]) -> str:
    """Genera HTML para la lista de reportes"""
    
    if not reports:
        return """
        <div class="no-reports">
            <h3>No reports available</h3>
            <p>Run the pipeline to generate visual comparison reports</p>
        </div>
        """
    
    reports_html = """<div class="reports-grid">"""
    
    for report in reports:
        # Determinar severidad
        changes = report['total_changes']
        if changes == 0:
            badge_class = "no-changes"
            badge_text = "No Changes"
        elif changes <= 2:
            badge_class = ""
            badge_text = f"{changes} Changes"
        elif changes <= 5:
            badge_class = "medium"
            badge_text = f"{changes} Changes"
        else:
            badge_class = "high"
            badge_text = f"{changes} Changes"
        
        timestamp = datetime.fromtimestamp(report['timestamp']).strftime('%Y-%m-%d %H:%M')
        
        reports_html += f"""
        <div class="report-card">
            <div class="report-header">
                <div class="comparison-title">Visual Comparison</div>
                <div class="changes-badge {badge_class}">{badge_text}</div>
            </div>
            <div class="comparison-files">
                <strong>V1:</strong> {report['file1']}<br>
                <strong>V2:</strong> {report['file2']}
            </div>
            <div class="actions">
                <a href="{report['html_file']}" class="btn btn-primary">View Report</a>
                <a href="{report['json_file']}" class="btn btn-secondary">JSON Data</a>
            </div>
            <div class="timestamp">Generated: {timestamp}</div>
        </div>
        """
    
    reports_html += """</div>"""
    return reports_html


def main():
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    generate_index_html(results_dir)


if __name__ == "__main__":
    main()