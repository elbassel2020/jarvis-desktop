@echo off
echo Stopping Jarvis...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
echo Jarvis stopped.
pause
