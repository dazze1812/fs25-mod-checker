@echo off
setlocal

cd /d "%~dp0.."

call uv sync --group dev
if errorlevel 1 exit /b %errorlevel%

call uv run pyinstaller --onefile --clean --name "fs25-mod-checker" --add-data "pyproject.toml;." src\fs25_mod_checker\__main__.py
if errorlevel 1 exit /b %errorlevel%

endlocal