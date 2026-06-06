' Silent launcher for Work Manager
' Double-click this file to start without a terminal window
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c python main.py", 0, False
Set WshShell = Nothing
