' Runs sync_local.ps1 in poll mode with NO visible window (a plain powershell.exe task would flash a window every 5 minutes).
' Usage: wscript.exe //B //Nologo run_hidden.vbs "<path to sync_local.ps1>" "<destination folder>"
Set sh = CreateObject("WScript.Shell")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & WScript.Arguments(0) & """ -OnlyIfChanged -Dest """ & WScript.Arguments(1) & """"
sh.Run cmd, 0, False
