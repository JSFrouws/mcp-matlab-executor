from setuptools import setup, find_packages

setup(
    name="mcp-matlab-executor",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "mcp>=1.2.0",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "mcp-matlab-executor=mcp_matlab_executor:main",
        ],
    },
)
