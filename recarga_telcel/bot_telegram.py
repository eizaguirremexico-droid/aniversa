"""
Bot de Telegram para disparar la recarga desde el telefono.

Corre en TU PC, no en un servidor: Telcel bloquea con 403 las
peticiones que vienen de un centro de datos, pero acepta las de tu
conexion normal. El telefono manda la orden desde donde sea, con
datos moviles, y la compra sale por tu internet de casa.

CONFIGURACION (una sola vez):

 1. En Telegram, busca:  @BotFather
 2. Mandale:  /newbot
    Te pide un nombre y un usuario (debe terminar en 'bot').
 3. Te devuelve un TOKEN largo. Pegalo en datos.txt:
       TELEGRAM_TOKEN=8123456789:AAF-loquetehayadado
 4. Corre:  python bot_telegram.py
 5. Busca TU bot en Telegram y mandale cualquier mensaje.
    La ventana negra te va a decir tu CHAT_ID.
 6. Pegalo en datos.txt:
       TELEGRAM_CHAT_ID=123456789
 7. Reinicia el bot. Listo.

El CHAT_ID no es un tramite: sin el, cualquiera que encuentre tu bot
podria gastar tu dinero. Con el, el bot ignora a todos menos a ti.

Requiere:  pip install requests
"""

import json
import os
import subprocess
import sys
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
ARCHIVO = os.path.join(CARPETA, "datos.txt")

# El script de compra, con el nombre que tenga en esta carpeta.
CANDIDATOS = ("recarga.py", "PASO2_recarga.py")

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
    for nombre in CANDIDATOS:
        ruta = os.path.join(CARPETA, nombre)
        if os.path.exists(ruta):
            return ruta
    print("ERROR: no encuentro el script de compra en", CARPETA)
    print("Debe llamarse recarga.py o PASO2_recarga.py")
    input("\nENTER para salir...")
    sys.exit(1)


def leer_datos():
    if not os.path.exists(ARCHIVO):
        print("ERROR: no encuentro datos.txt en", CARPETA)
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
            p = subprocess.run(
                [sys.executable, "-u", script, "--auto",
                 "--paquete", paquete],
                capture_output=True, text=True, timeout=600,
                cwd=CARPETA, env=entorno)
            salida = (p.stdout or "") + (p.stderr or "")
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
                print(f"[{hora}] Tu CHAT_ID es: {chat}")
                print(f"         Agrega a datos.txt:  TELEGRAM_CHAT_ID={chat}")
                enviar(chat, f"Tu CHAT_ID es {chat}\n"
                             "Agregalo a datos.txt y reinicia el bot.")
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
