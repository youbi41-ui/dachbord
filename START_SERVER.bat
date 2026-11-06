@echo off
cd /d "%~dp0"
python server\clinic_server.py --host 127.0.0.1 --port 8080
pause
