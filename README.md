# Biolit AutoMiner

Automated Biomedical Literature Mining Pipeline

## Installation

```bash
cd ~/Downloads/biolit_autominer
pip install -e .
```

## Usage

```python
from biolit_autominer import EnhancedAutoPipeline

pipeline = EnhancedAutoPipeline(
    email="jq2430@columbia.edu",
    api_key="your_key",
    gemini_project_id="rs-vertexai-czhu",
    output_dir="auto_pipeline_output"
)

result = pipeline.full_workflow("hepatotoxicity AND mitochondrial")
```
