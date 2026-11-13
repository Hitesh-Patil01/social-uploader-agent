@echo off
rem Starts the agent and starts it again if it stops or crashes.
rem To stop it for good: send /stop on Telegram, or press Ctrl+C and answer Y, or close this window.
cd /d "%~dp0"
call venv\Scripts\activate
set AGENT_LOOP=1
:loop
python agent.py
if errorlevel 5 goto end
echo.
echo The agent stopped. Starting again in 10 seconds. Close this window to stop it for good.
timeout /t 10 /nobreak >nul
goto loop
:end
echo The agent was stopped on purpose.
pause
