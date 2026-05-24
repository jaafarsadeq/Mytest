@echo off
REM Starts the WhatsApp bridge (whatsapp-web.js + ntfy forwarder + HTTP API).
REM Keep this window open. Scan the QR code on first run.
cd /d "%~dp0"
if not exist node_modules (
  echo Installing dependencies...
  call npm install
)
if not exist .env (
  echo .env not found - copying .env.example. Edit it before running again.
  copy .env.example .env
  pause
  exit /b 1
)
node src/bridge.js
pause
