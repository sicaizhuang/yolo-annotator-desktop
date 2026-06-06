Option Explicit

Dim shell, files, root, pythonw, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
pythonw = files.BuildPath(root, ".venv\Scripts\pythonw.exe")

If files.FileExists(pythonw) Then
  command = """" & pythonw & """ -m yolo_annotator_desktop"
  shell.Run command, 0, False
Else
  command = """" & files.BuildPath(root, "run_windows.cmd") & """"
  shell.Run command, 1, False
End If
