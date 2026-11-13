@echo off
rem Sends the latest agent files from this PC to your Oracle server.
rem 1) Edit the two lines below. 2) Double-click this file. 3) Send /restart to your Telegram bot.
set KEY=C:\keys\oracle.key
set HOST=ubuntu@YOUR_SERVER_IP

cd /d "%~dp0"
echo Sending files to %HOST% ...
scp -i "%KEY%" agent.py captions.py meta_setup.py settings.json requirements.txt %HOST%:~/social-uploader/
scp -i "%KEY%" -r server %HOST%:~/social-uploader/
echo.
echo Done. Now send  /restart  to your Telegram bot so the agent loads the new files.
pause
