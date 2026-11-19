' Arranca el motor sin ninguna ventana y con las herramientas de winget en el PATH
Set sh = CreateObject("WScript.Shell")
carpeta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
Set env = sh.Environment("PROCESS")
env("PATH") = env("PATH") & ";" & sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Microsoft\WinGet\Links"
env("PYTHONUTF8") = "1"
sh.CurrentDirectory = carpeta
sh.Run """" & carpeta & "\.venv\Scripts\pythonw.exe"" """ & carpeta & "\main.py""", 0, False
