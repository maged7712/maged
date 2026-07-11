@ECHO OFF
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   تصدير كوكيز يوتيوب للبرنامج
echo ========================================
echo.
echo تأكد انك مسجل دخول في يوتيوب على المتصفح.
echo.

python -m pip install -r requirements.txt -q

if not exist "data" mkdir data

echo اختر المتصفح:
echo   1^) Chrome
echo   2^) Edge
echo   3^) Firefox
echo.
set /p choice=رقم المتصفح: 

set BROWSER=chrome
if "%choice%"=="2" set BROWSER=edge
if "%choice%"=="3" set BROWSER=firefox

echo.
echo جاري استخراج الكوكيز من %BROWSER% ...
echo اغلق المتصفح تماماً إذا فشل التصدير ثم أعد المحاولة.
echo.

python -m yt_dlp --cookies-from-browser %BROWSER% --cookies "data\cookies.txt" --skip-download "https://www.youtube.com" 2>nul
if not exist "data\cookies.txt" (
  echo فشل التصدير التلقائي. جرب الإضافة يدوياً من المتصفح.
  pause
  exit /b 1
)

for %%A in ("data\cookies.txt") do set SIZE=%%~zA
if "%SIZE%"=="0" (
  echo الملف فارغ. تأكد من تسجيل الدخول في يوتيوب وأغلق المتصفح ثم أعد المحاولة.
  pause
  exit /b 1
)

echo.
echo تم بنجاح: data\cookies.txt
echo.
echo للاستخدام المحلي: شغّل start.bat
echo لرفعها على Render:
echo   1^) افتح data\cookies.txt
echo   2^) انسخ المحتوى كله
echo   3^) في Render ^> Environment أضف:
echo      Key:   YTDLP_COOKIES
echo      Value: ^<الصق المحتوى هنا^>
echo   4^) احفظ ثم Manual Deploy
echo.
pause
