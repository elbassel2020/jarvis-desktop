@echo off
echo Restarting Jarvis...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
timeout /t 2 >nul
cd /d C:\Users\walid\Documents\Jarvis
start "" wscript.exe start_jarvis_silent.vbs
echo Jarvis restarted (background).
