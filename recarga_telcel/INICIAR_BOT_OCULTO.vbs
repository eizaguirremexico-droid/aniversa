' Arranca el bot sin ventana visible.
'
' Para que se prenda solo con Windows:
'   1. Tecla Windows + R
'   2. Escribe:  shell:startup   y Enter
'   3. Copia AQUI este archivo (o un acceso directo, da igual)
'
' Busca INICIAR_BOT.bat en su propia carpeta y, si no esta, en
' Descargas, Escritorio y la carpeta del usuario. Asi funciona tanto
' si pegas el archivo como si pegas un acceso directo.
'
' Para detenerlo: Administrador de tareas, terminar python.exe.
' O usa INICIAR_BOT.bat directamente, que si muestra ventana.

Option Explicit

Dim fso, shell, carpetaPropia, casa, candidatas, ruta, i, encontrada

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

carpetaPropia = fso.GetParentFolderName(WScript.ScriptFullName)
casa = shell.ExpandEnvironmentStrings("%USERPROFILE%")

candidatas = Array( _
    carpetaPropia, _
    casa & "\Downloads", _
    casa & "\Descargas", _
    casa & "\Desktop", _
    casa & "\Escritorio", _
    casa & "\OneDrive\Escritorio", _
    casa)

encontrada = ""
For i = 0 To UBound(candidatas)
    ruta = candidatas(i) & "\INICIAR_BOT.bat"
    If encontrada = "" And fso.FileExists(ruta) Then
        encontrada = ruta
    End If
Next

If encontrada = "" Then
    ' Sin ventana, un fallo silencioso seria invisible: mejor avisar.
    Dim aviso
    aviso = "No encuentro INICIAR_BOT.bat." & vbCrLf & vbCrLf & _
            "Busque en:" & vbCrLf
    For i = 0 To UBound(candidatas)
        aviso = aviso & "   " & candidatas(i) & vbCrLf
    Next
    aviso = aviso & vbCrLf & _
            "Pon INICIAR_BOT.bat en alguna de esas carpetas."
    MsgBox aviso, 48, "Bot de recarga Telcel"
    WScript.Quit 1
End If

' Trabajar desde la carpeta del .bat, para que encuentre el bot,
' datos.txt y el script de compra.
shell.CurrentDirectory = fso.GetParentFolderName(encontrada)

' El 0 oculta la ventana; False es para no esperar, porque el bot
' corre indefinidamente.
shell.Run """" & encontrada & """", 0, False
