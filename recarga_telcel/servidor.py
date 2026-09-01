"""
Interfaz web para disparar la recarga desde el telefono.

Sirve una pagina con un boton por paquete. Corre en el VPS (Dokploy),
asi que funciona desde cualquier lado sin tener la PC encendida.

Configuracion por variables de entorno:
    USUARIO, CLAVE          acceso a la pagina (obligatorios)
    NUMERO, TARJETA, EXP,
    CVV, CP, EMAIL          datos de la compra
    TIPO_PAGO               0 o 1 (por defecto 0)
    PUERTO                  por defecto 8080
"""

import os
import subprocess
import sys
import threading
import time
from functools import wraps

from flask import Flask, Response, jsonify, request, send_file

CARPETA = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(CARPETA, "recarga.py")

USUARIO = os.environ.get("USUARIO", "")
CLAVE = os.environ.get("CLAVE", "")

PAQUETES = [
    {"id": "1 Hora", "titulo": "1 hora", "precio": "$10"},
    {"id": "2 Horas", "titulo": "2 horas", "precio": "$15"},
    {"id": "4 Horas", "titulo": "4 horas", "precio": "$25"},
]

app = Flask(__name__)

# Estado de la corrida en curso. Un candado evita que dos toques
# seguidos lancen dos compras.
_candado = threading.Lock()
_estado = {
    "corriendo": False,
    "paquete": None,
    "pagando": False,
    "inicio": None,
    "resultado": None,
    "salida": "",
    "lineas": [],      # se va llenando en vivo mientras corre
    "paso": "",        # ultima linea con contenido, para el titular
}

LIMITE_SEGUNDOS = 600


def protegido(f):
    """Pide usuario y contrasena. Sin esto, cualquiera podria gastar."""
    @wraps(f)
    def envoltura(*args, **kwargs):
        auth = request.authorization
        if not USUARIO or not CLAVE:
            return Response(
                "El servidor no tiene USUARIO/CLAVE configurados. "
                "Definelos en las variables de entorno.", 500)
        if not auth or auth.username != USUARIO or auth.password != CLAVE:
            return Response(
                "Acceso restringido", 401,
                {"WWW-Authenticate": 'Basic realm="Recarga Telcel"'})
        return f(*args, **kwargs)
    return envoltura


def ejecutar(paquete, pagar):
    """
    Corre el script de compra leyendo su salida LINEA POR LINEA, para
    que la pagina pueda ir mostrando el avance en vez de quedarse dos
    minutos en blanco.

    El '-u' es imprescindible: sin el, Python guarda la salida en un
    buffer cuando no escribe a una terminal, y todos los mensajes
    llegarian de golpe al terminar, que es justo lo que se quiere evitar.
    """
    entorno = os.environ.copy()
    entorno["PAGAR"] = "si" if pagar else "no"
    entorno["CI"] = "true"           # modo sin ventana y sin pausas
    entorno["PYTHONUNBUFFERED"] = "1"

    lineas = []
    proceso = None

    def matar():
        if proceso and proceso.poll() is None:
            proceso.kill()

    try:
        proceso = subprocess.Popen(
            [sys.executable, "-u", SCRIPT, "--paquete", paquete],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=CARPETA, env=entorno)

        # Cortarlo si se pasa del limite, sin bloquear la lectura.
        reloj = threading.Timer(LIMITE_SEGUNDOS, matar)
        reloj.daemon = True
        reloj.start()

        for linea in proceso.stdout:
            linea = linea.rstrip()
            lineas.append(linea)
            if linea.strip():
                with _candado:
                    _estado["lineas"] = lineas[-40:]
                    _estado["paso"] = linea.strip()

        proceso.wait()
        reloj.cancel()

        salida = "\n".join(lineas)
        if proceso.returncode == -9:
            resultado = "Tardo demasiado y se cancelo"
        elif not pagar:
            resultado = ("Prueba completada sin cobrar"
                         if "NO se envio el pago" in salida
                         else "Termino con dudas")
        else:
            resultado = ("Recarga enviada" if "Pago enviado" in salida
                         else "Termino con dudas")
    except Exception as e:
        salida = "\n".join(lineas + [f"Error del servidor: {e}"])
        resultado = "Fallo"

    with _candado:
        _estado["corriendo"] = False
        _estado["resultado"] = resultado
        _estado["salida"] = salida[-6000:]
        _estado["lineas"] = lineas[-40:]


@app.route("/api/recargar", methods=["POST"])
@protegido
def api_recargar():
    datos = request.get_json(silent=True) or {}
    paquete = datos.get("paquete")
    pagar = bool(datos.get("pagar"))

    if paquete not in [p["id"] for p in PAQUETES]:
        return jsonify({"error": "Paquete desconocido"}), 400

    with _candado:
        if _estado["corriendo"]:
            return jsonify({"error": "Ya hay una recarga en curso"}), 409
        _estado.update({
            "corriendo": True, "paquete": paquete, "pagando": pagar,
            "inicio": time.time(), "resultado": None, "salida": "",
            "lineas": [], "paso": "Arrancando...",
        })

    threading.Thread(target=ejecutar, args=(paquete, pagar),
                     daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/estado")
@protegido
def api_estado():
    with _candado:
        e = dict(_estado)
    if e["inicio"]:
        e["segundos"] = int(time.time() - e["inicio"])
    return jsonify(e)


@app.route("/api/captura")
@protegido
def api_captura():
    """
    Devuelve la captura de pantalla mas reciente que dejo el script.

    Sin esto el navegador corre a ciegas dentro del contenedor: si la
    pagina de Telcel devuelve algo inesperado, no habria forma de verlo.
    """
    try:
        pngs = [os.path.join(CARPETA, f) for f in os.listdir(CARPETA)
                if f.lower().endswith(".png")]
        if not pngs:
            return jsonify({"error": "Todavia no hay capturas"}), 404
        recientes = max(pngs, key=os.path.getmtime)
        return send_file(recientes, mimetype="image/png")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/salud")
def salud():
    return "ok", 200


@app.route("/")
@protegido
def inicio():
    return PAGINA


PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#111318">
<title>Recarga Telcel</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 18px 48px;
    font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #111318; color: #e7e9ee;
    max-width: 520px; margin-inline: auto;
  }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #9aa1ad; font-size: 14px; margin-bottom: 26px; }
  .paq {
    display: flex; align-items: center; justify-content: space-between;
    width: 100%; padding: 20px; margin-bottom: 12px;
    background: #1a1e26; color: #e7e9ee;
    border: 1px solid #2a303c; border-radius: 14px;
    font-size: 18px; font-weight: 600; text-align: left;
    cursor: pointer; transition: background .15s, border-color .15s;
  }
  .paq:hover:not(:disabled) { background: #212734; border-color: #3a4354; }
  .paq:disabled { opacity: .4; cursor: not-allowed; }
  .precio { font-size: 20px; color: #7dd3a0; }
  .fila {
    display: flex; align-items: center; gap: 10px;
    margin: 22px 0; padding: 14px 16px;
    background: #1a1e26; border: 1px solid #2a303c; border-radius: 12px;
  }
  .fila label { font-size: 15px; }
  .aviso { color: #f0b866; font-size: 13px; margin-top: 6px; }
  #estado {
    margin-top: 22px; padding: 16px; border-radius: 12px;
    background: #1a1e26; border: 1px solid #2a303c;
    font-size: 15px; display: none;
  }
  #estado.visible { display: block; }
  #paso {
    margin-top: 8px; padding-left: 17px;
    font-size: 14px; color: #c8cdd7;
  }
  #detalle {
    margin-top: 12px; font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 12px; color: #9aa1ad; white-space: pre-wrap;
    max-height: 260px; overflow: auto;
    border-top: 1px solid #2a303c; padding-top: 10px;
  }
  #detalle:empty { display: none; border: 0; padding: 0; }
  #verCaptura {
    display: none; margin-top: 14px; font-size: 14px;
    color: #7aa7f0; text-decoration: underline;
  }
  #verCaptura.visible { display: inline-block; }
  #captura {
    display: none; width: 100%; margin-top: 12px;
    border-radius: 8px; border: 1px solid #2a303c;
  }
  #captura.visible { display: block; }
  .punto {
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    margin-right: 8px; background: #9aa1ad;
  }
  .punto.trabajando { background: #f0b866; animation: latir 1s infinite; }
  .punto.bien { background: #7dd3a0; }
  .punto.mal { background: #e8776f; }
  @keyframes latir { 50% { opacity: .3; } }
</style>
</head>
<body>
  <h1>Recarga Telcel</h1>
  <div class="sub">Elige cuánto tiempo quieres.</div>

  <div id="botones"></div>

  <div class="fila">
    <input type="checkbox" id="pagar">
    <label for="pagar">Cobrar de verdad</label>
  </div>
  <div class="aviso" id="aviso">Sin marcar: llena todo pero no cobra.</div>

  <div id="estado">
    <div><span class="punto" id="punto"></span><span id="titulo"></span></div>
    <div id="paso"></div>
    <div id="detalle"></div>
    <a id="verCaptura" href="#">Ver lo que vio el navegador</a>
    <img id="captura" alt="Captura de la pagina">
  </div>

<script>
const PAQUETES = __PAQUETES__;
const botones = document.getElementById('botones');
const caja = document.getElementById('estado');
const punto = document.getElementById('punto');
const titulo = document.getElementById('titulo');
const detalle = document.getElementById('detalle');
const paso = document.getElementById('paso');
const verCaptura = document.getElementById('verCaptura');
const captura = document.getElementById('captura');

verCaptura.onclick = (ev) => {
  ev.preventDefault();
  // El parametro de tiempo evita que el navegador reuse la captura anterior.
  captura.src = '/api/captura?t=' + Date.now();
  captura.classList.add('visible');
  verCaptura.style.display = 'none';
};
let vigilando = null;

PAQUETES.forEach(p => {
  const b = document.createElement('button');
  b.className = 'paq';
  b.innerHTML = `<span>${p.titulo}</span><span class="precio">${p.precio}</span>`;
  b.onclick = () => pedir(p.id);
  botones.appendChild(b);
});

function bloquear(si) {
  document.querySelectorAll('.paq').forEach(b => b.disabled = si);
}

async function pedir(paquete) {
  const pagar = document.getElementById('pagar').checked;
  if (pagar && !confirm(`Se va a cobrar el paquete de ${paquete}. ¿Continuar?`))
    return;

  bloquear(true);
  caja.classList.add('visible');
  punto.className = 'punto trabajando';
  titulo.textContent = 'Enviando...';
  detalle.textContent = '';

  try {
    const r = await fetch('/api/recargar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({paquete, pagar})
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Error');
    if (!vigilando) vigilando = setInterval(mirar, 1500);
  } catch (e) {
    punto.className = 'punto mal';
    titulo.textContent = e.message;
    bloquear(false);
  }
}

function pintarLog(lineas) {
  if (!lineas || !lineas.length) return;
  const abajo = detalle.scrollTop + detalle.clientHeight >= detalle.scrollHeight - 30;
  detalle.textContent = lineas.join('\\n');
  // Seguir el final solo si el usuario no subio a leer algo.
  if (abajo) detalle.scrollTop = detalle.scrollHeight;
}

async function mirar() {
  try {
    const e = await (await fetch('/api/estado')).json();
    if (e.corriendo) {
      punto.className = 'punto trabajando';
      titulo.textContent = `Comprando ${e.paquete}... (${e.segundos||0}s)`;
      paso.textContent = e.paso || '';
      pintarLog(e.lineas);
      bloquear(true);
    } else if (e.resultado) {
      const bien = /enviada|completada/i.test(e.resultado);
      punto.className = 'punto ' + (bien ? 'bien' : 'mal');
      titulo.textContent = e.resultado;
      paso.textContent = '';
      pintarLog(e.lineas && e.lineas.length ? e.lineas
                                           : (e.salida || '').split('\\n'));
      verCaptura.classList.add('visible');
      bloquear(false);
      clearInterval(vigilando); vigilando = null;
    }
  } catch (_) {}
}

mirar();
</script>
</body>
</html>
"""

PAGINA = PAGINA.replace("__PAQUETES__", str(PAQUETES).replace("'", '"'))


if __name__ == "__main__":
    if not USUARIO or not CLAVE:
        print("AVISO: falta USUARIO y/o CLAVE. La pagina no dejara entrar.")
    puerto = int(os.environ.get("PUERTO", "8080"))
    print(f"Escuchando en el puerto {puerto}")
    app.run(host="0.0.0.0", port=puerto)
