Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "python -m waitress --listen=127.0.0.1:5000 app:app", 0, False
