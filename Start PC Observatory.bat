@echo off
rem PC Observatory launcher - starts the app with no console window.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" main.py
