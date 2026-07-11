@ECHO OFF
cd /d "%~dp0"
chcp 65001 >nul

echo ========================================
echo   نغمة — نشر الصفحة على الإنترنت
echo ========================================
echo.

python -m pip install -r requirements.txt -q

if not exist "tools" mkdir tools

if not exist "tools\cloudflared.exe" (
  echo Downloading Cloudflare Tunnel...
  powershell -NoProfile -Command ^
    "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'tools\cloudflared.exe'"
  if errorlevel 1 (
    echo Failed to download cloudflared.
    pause
    exit /b 1
  )
)

echo.
echo Starting the website...
echo Keep this window open while the site is online.
echo A public https link will appear below.
echo.

set OPEN_BROWSER=0
start "Naghma Server" cmd /c "python app.py"

timeout /t 3 /nobreak >nul

echo.
echo ========== رابط الموقع العام ==========
tools\cloudflared.exe tunnel --url http://127.0.0.1:5000
pause
