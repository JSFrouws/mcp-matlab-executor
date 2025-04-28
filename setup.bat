@echo off
echo Setting up MATLAB Executor MCP tool...

:: Create virtual environment
uv venv
call .venv\Scripts\activate.bat

:: Install dependencies
uv add "mcp[cli]" python-dotenv

:: Install the package in development mode
uv pip install -e .

echo Setup complete! You can now run the server using:
echo mcp-matlab-executor
