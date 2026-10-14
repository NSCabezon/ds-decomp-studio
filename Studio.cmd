@echo off
rem Double-clic : ouvre DS Decomp Studio dans le navigateur (http://127.0.0.1:8765).
cd /d "%~dp0"
set PY=%~dp0..\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" studio.py %*
pause
