@echo off
chcp 65001 >nul
echo =====================================
echo  საიტების გადამოწმება...
echo =====================================
echo.
cd /d "%~dp0backend"
py diagnostic.py
echo.
echo დასრულდა! შედეგი ზემოთ ჩანს.
echo ახლა start.bat გაუშვი.
echo.
pause
