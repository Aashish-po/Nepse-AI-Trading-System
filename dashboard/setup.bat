@echo off
REM Quick-start setup for NEPSE AI Trading Dashboard (Windows)

echo.
echo  NEPSE AI Trading Dashboard - Quick Start Setup (Windows)
echo ===========================================================
echo.

REM Check Python version
echo ✓ Checking Python version...
python --version >nul 2>&1 || (
    echo ❌ Python not found. Install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

REM Create virtual environment
echo.
echo ✓ Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo   Created: venv\
) else (
    echo   Already exists: venv\
)

REM Activate virtual environment
echo.
echo ✓ Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo ✓ Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo ✓ Installing dependencies...
pip install -r requirements-dashboard.txt

REM Create Streamlit directory
echo.
echo ✓ Setting up Streamlit configuration...
if not exist ".streamlit" mkdir .streamlit

REM Create secrets.toml if it doesn't exist
if not exist ".streamlit\secrets.toml" (
    (
        echo # NEPSE AI Trading System API Configuration
        echo API_BASE = "http://localhost:8000"
    ) > .streamlit\secrets.toml
    echo   Created: .streamlit\secrets.toml
    echo     Edit this file to configure your backend URL
) else (
    echo   Already exists: .streamlit\secrets.toml
)

REM Copy config.toml
if not exist ".streamlit\config.toml" (
    copy .streamlit_config.toml .streamlit\config.toml >nul 2>&1 || (
        echo    Run: copy .streamlit_config.toml .streamlit\config.toml
    )
)

echo.
echo ===========================================================
echo  Setup Complete!
echo.
echo  Next Steps:
echo 1. Start the backend API:
echo    cd ..\backend
echo    python -m uvicorn app.main:app --reload
echo.
echo 2. In another terminal, start the dashboard:
echo    streamlit run app.py
echo.
echo 3. Open your browser to http://localhost:8501
echo.
echo  Documentation: See dashboard/README.md
echo ===========================================================
echo.
pause