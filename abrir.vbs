' Abre o NTChat sem mostrar a janela preta do console.
' Na primeira vez (ou se faltar algo) abre o instalador.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
arg = ""
If WScript.Arguments.Count > 0 Then arg = " " & WScript.Arguments(0)

If Not fso.FileExists(pasta & "\.venv\Scripts\pythonw.exe") Or Not fso.FileExists(pasta & "\config.json") Then
    ' Ao ligar o PC nao abre o instalador sozinho
    If arg = "" Then sh.Run """" & pasta & "\instalar.bat""", 1, False
    WScript.Quit
End If

sh.Run """" & pasta & "\start.bat""" & arg, 0, False
