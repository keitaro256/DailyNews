@echo off
title NewsReader v4
cd /d "%~dp0"
python -c "import requests,bs4,openpyxl,docx" 2>nul || pip install requests beautifulsoup4 lxml openpyxl python-docx --quiet
start "" timeout /t 2 /nobreak >nul && start "" "http://localhost:8765"
python app.py
pause
