@echo off
title Drive to inbox (PC)
rem Moves videos from the Google Drive folder social-inbox into this project's inbox folder, once a minute.
rem Use this only while the agent runs on your PC. Do not run it together with a server that does the same job.
rem Needs rclone with a remote called gdrive (rclone lsd gdrive: must list social-inbox).
cd /d "%~dp0"
if not exist inbox mkdir inbox
echo Watching Google Drive folder social-inbox. Leave this window open. Close it to stop.
:loop
rclone move gdrive:social-inbox "%~dp0inbox" --include "*.mp4" --include "*.mov" --include "*.m4v" --include "*.txt" --min-age 1m
timeout /t 60 /nobreak >nul
goto loop
