' Arranca el bot sin ventana visible.
'
' Para que se prenda solo con Windows:
'   1. Tecla Windows + R
'   2. Escribe:  shell:startup   y Enter
'   3. Copia un ACCESO DIRECTO de este archivo a esa carpeta
'      (clic derecho sobre el archivo, Copiar; en la carpeta,
'       clic derecho, Pegar acceso directo)
'
' Para detenerlo: Administrador de tareas, terminar el proceso
' python.exe. O usa INICIAR_BOT.bat, que si muestra ventana.

Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = carpeta

' El 0 es lo que oculta la ventana; el False es para no esperar
' a que termine, porque el bot corre indefinidamente.
shell.Run """" & carpeta & "\INICIAR_BOT.bat""", 0, False
