#!/usr/bin/env python3
"""Setup script for Suno Mastering Agent."""
from setuptools import setup, find_packages

setup(
    name="suno-mastering-agent",
    version="0.1.0",
    description="Automate audio mastering in Suno AI Studio",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "playwright>=1.40.0",
        "pydantic>=2.0.0",
        "rich>=13.0.0",
        "click>=8.0.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "suno-master=main:cli",
        ],
    },
)
