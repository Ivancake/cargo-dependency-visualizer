@echo off
setlocal
rem Запускаем программу и передаём ей все параметры командной строки.
python "%~dp0src\main.py" %*
exit /b %errorlevel%