@ECHO OFF
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt -q
echo.
echo Starting Naghma (YouTube to MP3)...
echo The browser will open automatically.
echo Downloads folder: %~dp0downloads
echo.
set OPEN_BROWSER=1
python app.py
pause
