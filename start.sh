#!/bin/bash
cd "$(dirname "$0")"
python3 -c "import requests,bs4,openpyxl,docx" 2>/dev/null || pip3 install requests beautifulsoup4 lxml openpyxl python-docx -q
python3 app.py &
sleep 2
command -v open &>/dev/null && open http://localhost:8765 || xdg-open http://localhost:8765 2>/dev/null
wait
