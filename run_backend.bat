@echo off
REM --- Check if we are in the backend directory or project root ---
if exist backend (
    cd backend
)

REM --- Verify virtual environment existence ---
if not exist venv (
    echo [ERROR] Virtual environment not found in backend directory.
    echo Looking for venv in project root...
    if exist ..\venv (
        set VIRTUAL_ENV=..\venv
    ) else (
        echo [ERROR] No virtual environment found at project root either.
        echo Please run: python -m venv venv
        pause
        exit /b 1
    )
) else (
    set VIRTUAL_ENV=venv
)

echo [SERVER] Activating environment and starting server...
%VIRTUAL_ENV%\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
