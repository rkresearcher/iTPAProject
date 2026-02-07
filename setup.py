from setuptools import setup, find_packages
import os

# Helper to read requirements.txt
def parse_requirements(filename):
    with open(filename, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="iTPAEngine",
    version="0.1.0",
    packages=find_packages(),
    # Now it reads from your requirements.txt file
    install_requires=parse_requirements("requirements.txt"),
    python_requires=">=3.12",
    description="Automated Claim Assessment Engine using OCR and GPT-Vision",
    author="Your Name",
)
