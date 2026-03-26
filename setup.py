from setuptools import setup, find_packages

setup(
    name="subtagger",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "subtagger=subtagger.cli:main",
        ],
    },
    python_requires=">=3.11",
)
