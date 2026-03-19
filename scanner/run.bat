@echo off
echo.
echo  ====================================
echo   Hopa Grant Scanner - מפעיל סורק
echo  ====================================
echo.

cd /d "%~dp0"

:: התקן חבילות אם חסרות
pip install -r requirements.txt -q

echo.
echo  סורק קולות קוראים ושומר ל-Supabase...
echo.

python scanner.py

echo.
echo  לחץ על כל מקש לסגירה...
pause > nul
