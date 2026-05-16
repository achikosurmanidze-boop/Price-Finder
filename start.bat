@echo off
chcp 65001 >nul
echo =========================================
echo    ქართული ფასების შემდარებელი
echo =========================================
echo.

if not exist "backend\.env" (
    echo ERROR: backend\.env ფაილი ვერ მოიძებნა!
    echo.
    echo გთხოვ:
    echo   1. backend\.env ფაილი გახსენი ნოუთბუქით
    echo   2. ANTHROPIC_API_KEY= ხაზში ჩაწერე შენი API გასაღები
    echo.
    pause
    exit /b 1
)

echo [1/3] პაკეტების შემოწმება...
py -m pip install -r backend\requirements.txt --quiet

if not exist "backend\site_status.json" (
    echo.
    echo [2/3] პირველი გაშვება — ვამოწმებთ რომელი საიტი ხელმისაწვდომია...
    echo       ^(ეს ერთხელ ხდება, შემდეგ ჩაიწერება^)
    echo.
    cd backend
    py diagnostic.py
    cd ..
) else (
    echo [2/3] საიტის სტატუსი უკვე შემოწმებულია ^(site_status.json^)
)

echo.
echo [3/3] სერვერის გაშვება...
echo.
echo   API:       http://localhost:8000
echo   ფრონტენდი: frontend\index.html ^(გახსენი ბრაუზერით^)
echo   Crawler:   ყოველ 5 წუთში ავტომატურად განახლდება
echo.
echo სერვერის გასაჩერებლად: Ctrl+C
echo.

cd backend
py main.py
