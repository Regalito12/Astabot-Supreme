@echo off
echo Asegurándose de que no haya otras instancias de Astabot en ejecución...
call detener_astabot.bat
echo Iniciando Astabot...
cd /d "c:\Users\Jorddy\OneDrive\Escritorio\nuevacarpeta"
call .venv\Scripts\activate.bat
start "Astabot" /B pythonw.exe bot_auto.py
echo Astabot se está ejecutando en segundo plano.