# SmartVisionQA

Proof of concept for automated visual testing using local vision models with Ollama.

## Requirements

- Python 3.8+
- Ollama installed and running
- Vision model qwen2.5vl:7b downloaded
- Docker (optional, for containerized execution)

## Installation

1. Install Ollama:
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

2. Download vision model:
```bash
ollama pull qwen2.5vl:7b
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

## Project Structure

```
smartVisionQA/
├── smartVisionQA.py            # Main script
├── generate_html_report.py     # HTML report generator
├── example_url_comparison.py   # URL comparison examples
├── demo/                       # Example HTML files
│   ├── page_v1.html           # Version 1 (original)
│   ├── page_v2.html           # Version 2 (major changes)
│   ├── page_v3.html           # Version 3 (minor changes)
│   └── simple_test.html       # Simple test page
├── results/                    # Screenshots and reports (auto-generated)
│   ├── comparison_*.json       # JSON reports per comparison
│   ├── visual_report_*.html    # Visual HTML reports
│   └── *_screenshot.png        # Screenshots
└── requirements.txt            # Dependencies
```

## Usage

### Local Execution

Run all comparisons:
```bash
python smartVisionQA.py
```

The script automatically executes:
- page_v1.html vs page_v2.html
- page_v1.html vs page_v3.html  
- page_v2.html vs page_v3.html

For each comparison:
1. Renders HTMLs to images
2. Uses Ollama to analyze visual differences
3. Generates unique JSON and HTML reports

### Docker Execution

Build and run with Docker:
```bash
docker build -t smartvisionqa .
docker run --rm -v $(pwd)/results:/app/results smartvisionqa
```

### GitHub Actions Pipeline

The repository includes a GitHub Actions workflow for automated visual testing.

#### Setup

1. Enable GitHub Pages in repository settings
2. Set Pages source to "GitHub Actions"
3. Ensure Actions have write permissions for Pages

#### Running the Pipeline

1. Go to repository **Actions** tab
2. Select **SmartVisionQA Analysis** workflow
3. Click **Run workflow**
4. Choose whether to publish results to GitHub Pages

#### Pipeline Features

- **Containerized execution**: Runs analysis in isolated Docker environment
- **Artifact storage**: Results saved for 30 days as downloadable artifacts
- **GitHub Pages publishing**: Optional web dashboard with visual reports
- **Automatic cleanup**: Docker resources cleaned after execution

#### Accessing Results

**Via Artifacts:**
- Go to workflow run page
- Download `visual-qa-results` artifact
- Contains all JSON reports, HTML dashboards, and screenshots

**Via GitHub Pages (if enabled):**
- Automatic deployment to `https://username.github.io/repository-name`
- Interactive dashboard with all comparison results
- Direct links to HTML reports and screenshots

## Customization

### Comparing Different HTML Files

Modify in `smartVisionQA.py` at **line 300** - test cases list:
```python
test_cases = [
    ("your_file1.html", "your_file2.html"),
]
```

### Changing Ollama Model

Modify in `smartVisionQA.py` at **line 59** - model initialization:
```python
def __init__(self, model: str = "qwen2.5vl:7b"): 
```

## HTML Reports

The system automatically generates visual HTML reports:

```bash
python smartVisionQA.py  # Generates JSON + HTML automatically
```

To generate HTML report from existing JSON:
```bash
python generate_simple_report.py results/comparison_page_v1_vs_page_v2.json
```

## Real Website Comparison

For comparing live websites:

```bash
python example_url_comparison.py
```

You can modify URLs in the `example_url_comparison.py` file.

## CI/CD Integration

### GitHub Actions

The workflow provides CI/CD integration:
- Triggered manually or via API
- Results available as artifacts
- Optional web publishing
- No external dependencies required

## Extension

To integrate with Selenium/Playwright for live websites:

**In HTMLRenderer class (line 18)**, add method:
```python
async def url_to_image(self, url: str) -> bytes:
    # Implement real URL capture
    pass
```

## Notes

- Requires ~6GB for qwen2.5vl:7b model
- First execution downloads model (~6GB)
- Screenshots saved in `results/` directory
- Docker execution recommended for consistent environments