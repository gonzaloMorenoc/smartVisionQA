# Configuration reference

All paths are relative to the config file. Unknown keys are rejected.

```yaml
viewports:                     # at least one; names must be unique
  - name: desktop
    width: 1280                # 1..7680
    height: 800
    device_scale_factor: 1     # 0 < x <= 4

capture:
  full_page: true
  disable_animations: true     # freezes CSS animations/transitions, hides the caret
  timeout_ms: 30000            # navigation / wait timeout
  wait_for_selector: null      # wait until this selector is visible before capturing
  extra_wait_ms: 0             # last resort for pages that settle late (max 30000)
  mask: []                     # CSS selectors painted out in every capture
  mask_color: "#FF00FF"

diff:
  pixel_threshold: 0.1         # max per-channel distance (0-1) still considered equal
  max_diff_ratio: 0.0          # share of significant changed pixels tolerated
  min_region_area: 1           # clusters with fewer changed pixels are ignored (noise)
  cell_size: 8                 # clustering grid; clusters <= 2 cells apart merge
  max_regions: 10              # regions kept for reports / AI

ai:
  enabled: true
  model: qwen2.5vl:7b          # or set $SVQA_MODEL; --model wins over both
  host: null                   # defaults to $OLLAMA_HOST or http://localhost:11434
  timeout_s: 180
  temperature: 0
  seed: 42
  max_retries: 2               # extra attempts when the output fails validation
  max_regions: 6               # regions explained per check (largest first)
  crop_padding: 24
  crop_max_side: 1024

pages:                         # checked against baselines
  - name: home
    target: demo/page_v1.html  # file path or http(s) URL
    viewports: [desktop]       # optional subset
    mask: [".clock"]           # added to capture.mask

comparisons:                   # before vs after, no baseline needed
  - name: v1-vs-v2
    before: demo/page_v1.html
    after: demo/page_v2.html

baseline_dir: baselines
output_dir: results
```

## Choosing a model

Run `smartvisionqa evaluate --model <name>` for each candidate and compare category
accuracy and macro F1 in `results/evaluation.md`. Smaller models (e.g. `qwen2.5vl:3b`) are
much faster on CPU-only CI runners.
