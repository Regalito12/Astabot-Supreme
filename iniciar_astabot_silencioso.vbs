Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Users\Jorddy\OneDrive\Escritorio\PROYECTOS PERSONALESPROGRAMACION\nuevacarpeta"
WshShell.Run "cmd /c .venv\Scripts\pythonw.exe bot_auto.py", 0, False
Set WshShell = Nothing
