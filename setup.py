from setuptools import setup, find_packages

setup(
    name="biolit_autominer",
    version="1.0.0",
    author="Ji Qiu",
    author_email="jq2430@columbia.edu",
    description="Automated Biomedical Literature Mining Pipeline",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "biopython>=1.83",
        "beautifulsoup4>=4.12.0",
        "requests>=2.31.0",
        "pandas>=2.1.0",
        "openpyxl>=3.1.0",
        "google-cloud-aiplatform>=1.38.0",
        "schedule>=1.2.0",
        "python-dotenv>=1.0.0",
        "pymupdf>=1.24.0",
    ],
)
