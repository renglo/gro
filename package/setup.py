"""
Gro Package
Query planner and optimizer handlers for graph workloads.
"""

from setuptools import setup, find_packages

setup(
    name="gro",
    version="1.0.0",
    description="Gro query planner and optimizer handlers",
    author="Renglo Team",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        "requests>=2.32.0",
        "graphforge>=0.4.0",
        "openai>=1.30.0",
    ],
    include_package_data=True,
    package_data={
        "gro": ["blueprints/*.json", "data/*.json"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.12",
    ],
)
