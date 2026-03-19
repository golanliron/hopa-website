@echo off
:: מתזמן את הסורק לרוץ כל יום בשעה 08:00
:: הרץ את הקובץ הזה פעם אחת בתור מנהל מערכת (Run as Administrator)

set TASK_NAME=HopaGrantScanner
set SCRIPT_PATH=%~dp0run.bat

echo  מתזמן סריקה יומית ב-08:00...

schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc daily /st 08:00 /f /rl highest

if %errorlevel% == 0 (
    echo  ✓ התזמון הוגדר בהצלחה!
    echo  הסורק ירוץ כל יום ב-08:00 ויעדכן את הדשבורד אוטומטית.
) else (
    echo  שגיאה בהגדרת התזמון. הרץ כ-Administrator.
)

pause
