@echo off
title AutoMail - Cold Outreach Studio
echo ===================================================
echo Starting AutoMail B2B Cold Outreach Engine...
echo ===================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

echo Checking dependencies...
python -c "import fastapi, uvicorn, groq, pandas, openpyxl, httpx" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installing required packages...
    pip install fastapi uvicorn python-dotenv groq pandas openpyxl httpx
)

echo Launching browser to http://localhost:8000 ...
start http://localhost:8000

echo Starting AutoMail Server (Press Ctrl+C to close)...
python main.py
pause

