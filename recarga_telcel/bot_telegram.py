"""
Bot de Telegram para disparar la recarga desde el telefono.

Corre en TU PC, no en un servidor: Telcel responde 403 al servicio del
catalogo cuando la peticion sale de un centro de datos, pero acepta la
misma peticion desde una conexion domestica. El telefono manda la
orden desde donde sea, y la compra sale por tu internet de casa.

COMO USARLO:

 1. Pon este archivo junto a datos.txt (si no, lo busca en Descargas,
    Escritorio y tu carpeta de usuario).
 2. Consigue un token con @BotFather en Telegram: mandale /newbot,
    elige un nombre y un usuario que termine en 'bot'.
 3. Agrega el token a datos.txt:
       TELEGRAM_TOKEN=8123456789:AAF-loquetehayadado
 4. Corre este archivo y deja la ventana abierta.
 5. Buscate tu bot en Telegram y mandale cualquier mensaje.

El primero que le escriba queda registrado como dueño: el bot guarda
ese chat en datos.txt y a partir de ahi ignora a todos los demas. Por
eso conviene escribirle tu, en cuanto lo prendas.

Requiere:  pip install requests
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time

try:
    import requests
except ImportError:
    print("ERROR: falta la libreria requests.")
    print("Corre:  pip install requests")
    input("\nENTER para salir...")
    sys.exit(1)

CARPETA = os.path.dirname(os.path.abspath(__file__))

# El script de compra, con cualquiera de los nombres que ha tenido.
CANDIDATOS = ("recarga.py", "PASO2_recarga.py")


def lugares_probables():
    """Carpetas donde puede estar datos.txt, en orden de preferencia."""
    casa = os.path.expanduser("~")
    return [
        CARPETA,
        os.getcwd(),
        os.path.join(casa, "Downloads"),
        os.path.join(casa, "Descargas"),
        os.path.join(casa, "Desktop"),
        os.path.join(casa, "Escritorio"),
        casa,
    ]


def buscar(nombres):
    """Devuelve la primera ruta existente entre los lugares probables."""
    for carpeta in lugares_probables():
        for nombre in nombres:
            ruta = os.path.join(carpeta, nombre)
            if os.path.exists(ruta):
                return ruta
    return None


ARCHIVO = buscar(["datos.txt"])

PAQUETES = {
    "1 hora - $10": "1 Hora",
    "2 horas - $15": "2 Horas",
    "4 horas - $25": "4 Horas",
}

TECLADO = {
    "keyboard": [[{"text": t}] for t in PAQUETES],
    "resize_keyboard": True,
}

_ocupado = threading.Lock()


def encontrar_script():
    ruta = buscar(CANDIDATOS)
    if ruta:
        return ruta
    print("ERROR: no encuentro el script de compra.")
    print("Debe llamarse recarga.py o PASO2_recarga.py")
    print("\nBusque en estas carpetas:")
    for c in lugares_probables():
        print("   ", c)
    print("\nPon el script en la misma carpeta que este archivo.")
    input("\nENTER para salir...")
    sys.exit(1)


def leer_datos():
    if not ARCHIVO or not os.path.exists(ARCHIVO):
        print("ERROR: no encuentro datos.txt.")
        print("\nBusque en estas carpetas:")
        for c in lugares_probables():
            print("   ", c)
        print("\nPonlo en la misma carpeta que este archivo,")
        print("o arrastra este archivo a donde este datos.txt")
        input("\nENTER para salir...")
        sys.exit(1)
    cfg = {}
    with open(ARCHIVO, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, _, v = linea.partition("=")
                cfg[k.strip().upper()] = v.strip()
    return cfg


def main():
    cfg = leer_datos()
    script = encontrar_script()

    token = cfg.get("TELEGRAM_TOKEN")
    if not token:
        print("Falta TELEGRAM_TOKEN en datos.txt.")
        print("Lee las instrucciones al inicio de este archivo.")
        input("\nENTER para salir...")
        sys.exit(1)

    permitido = cfg.get("TELEGRAM_CHAT_ID", "").strip()
    api = f"https://api.telegram.org/bot{token}"

    def enviar(chat, texto, teclado=False):
        datos = {"chat_id": chat, "text": texto[:4000]}
        if teclado:
            datos["reply_markup"] = json.dumps(TECLADO)
        try:
            requests.post(f"{api}/sendMessage", data=datos, timeout=20)
        except Exception as e:
            print("  (no se pudo responder:", e, ")")

    def comprar(chat, paquete):
        """Lanza la compra y reporta el resultado."""
        hora = time.strftime("%H:%M:%S")
        print(f"[{hora}] Comprando {paquete}...")
        enviar(chat, f"Comprando {paquete}. Tarda unos 3 minutos...")

        entorno = os.environ.copy()
        entorno["PAGAR"] = "si"
        entorno["PYTHONUNBUFFERED"] = "1"

        try:
            # La salida va a un archivo temporal, NO a una tuberia.
            #
            # Con capture_output=True, subprocess espera a que se cierre
            # la tuberia, y Chromium la hereda del proceso de Python: el
            # bot se quedaba bloqueado mientras el navegador siguiera
            # vivo, y nunca llegaba a avisar que la compra habia salido.
            with tempfile.TemporaryFile("w+", encoding="utf-8",
                                        errors="replace") as archivo:
                subprocess.run(
                    [sys.executable, "-u", script, "--auto",
                     "--paquete", paquete],
                    stdout=archivo, stderr=subprocess.STDOUT, timeout=600,
                    cwd=CARPETA, env=entorno)
                archivo.seek(0)
                salida = archivo.read()
            if "Pago enviado" in salida:
                print(f"[{hora}] Listo: {paquete}")
                enviar(chat, f"Listo. Recarga de {paquete} enviada.\n"
                             "Revisa tu correo para el comprobante.")
            else:
                print(f"[{hora}] Termino con dudas")
                enviar(chat, "Termino pero no confirmo el pago.\n\n"
                             + salida[-1200:])
        except subprocess.TimeoutExpired:
            print(f"[{hora}] Se paso de 10 minutos")
            enviar(chat, "Tardo demasiado y lo cancele. Revisa la PC.")
        except Exception as e:
            print(f"[{hora}] Error: {e}")
            enviar(chat, f"Fallo: {e}")
        finally:
            _ocupado.release()

    print("=" * 60)
    print("  Bot de recarga escuchando.")
    print("  Script:", os.path.basename(script))
    if permitido:
        print(f"  Solo respondo al chat {permitido}")
    else:
        print("  [!] TELEGRAM_CHAT_ID NO configurado.")
        print("  [!] Mandale un mensaje al bot para conocer tu ID.")
        print("  [!] Mientras tanto NO ejecuto ninguna recarga.")
    print("  Deja esta ventana abierta. Ctrl+C para detener.")
    print("=" * 60)

    ultimo = 0
    while True:
        try:
            r = requests.get(f"{api}/getUpdates",
                             params={"offset": ultimo + 1, "timeout": 50},
                             timeout=60)
            novedades = r.json().get("result", [])
        except Exception as e:
            print("  Sin conexion, reintento en 10s:", e)
            time.sleep(10)
            continue

        for u in novedades:
            ultimo = u["update_id"]
            msg = u.get("message") or {}
            chat = str((msg.get("chat") or {}).get("id", ""))
            texto = (msg.get("text") or "").strip()
            if not chat:
                continue

            hora = time.strftime("%H:%M:%S")

            if not permitido:
                # El primero que escribe queda registrado como dueño y
                # se guarda en datos.txt, para no obligar a editar el
                # archivo a mano ni a reiniciar el bot.
                permitido = chat
                try:
                    with open(ARCHIVO, "a", encoding="utf-8") as f:
                        f.write(f"\nTELEGRAM_CHAT_ID={chat}\n")
                    print(f"[{hora}] Registrado tu chat: {chat}")
                    print(f"         Guardado en {ARCHIVO}")
                    enviar(chat, "Listo, quedaste registrado. "
                                 "Desde ahora solo yo te respondo a ti.\n\n"
                                 "Elige un paquete:", teclado=True)
                except Exception as e:
                    print(f"[{hora}] Tu CHAT_ID es {chat}, pero no pude "
                          f"guardarlo: {e}")
                    print(f"         Agregalo a mano:  TELEGRAM_CHAT_ID={chat}")
                    enviar(chat, f"Tu CHAT_ID es {chat}. No pude guardarlo "
                                 "solo; agregalo a datos.txt.")
                continue

            if chat != permitido:
                print(f"[{hora}] IGNORADO: chat ajeno ({chat})")
                continue

            paquete = PAQUETES.get(texto)
            if paquete:
                # Solo una compra a la vez: dos toques seguidos no
                # deben convertirse en dos cargos.
                if not _ocupado.acquire(blocking=False):
                    enviar(chat, "Ya hay una recarga en curso, espera.")
                    continue
                threading.Thread(target=comprar, args=(chat, paquete),
                                 daemon=True).start()
            else:
                # Cualquier otro texto solo muestra el teclado: un
                # mensaje suelto no dispara un cargo por accidente.
                enviar(chat, "Elige un paquete:", teclado=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot detenido.")
