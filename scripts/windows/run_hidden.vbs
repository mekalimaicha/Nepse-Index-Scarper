' Runs sync_local.ps1 in poll mode with NO visible window (a plain powershell.exe task would flash a window every 5 minutes).
' Usage: wscript.exe //B //Nologo run_hidden.vbs "<sync_local.ps1>" "<Dest>" ["<FundDest>" ["<Python>" ["<StateDir>"]]]
Set a = WScript.Arguments
Set sh = CreateObject("WScript.Shell")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & a(0) & """ -OnlyIfChanged -Dest """ & a(1) & """"
If a.Count > 2 Then
  If a(2) <> "" Then cmd = cmd & " -FundDest """ & a(2) & """"
End If
If a.Count > 3 Then
  If a(3) <> "" Then cmd = cmd & " -Python """ & a(3) & """"
End If
If a.Count > 4 Then
  If a(4) <> "" Then cmd = cmd & " -StateDir """ & a(4) & """"
End If
sh.Run cmd, 0, False
