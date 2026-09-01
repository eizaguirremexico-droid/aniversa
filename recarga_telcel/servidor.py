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

from flask import Flask, Response, jsonify, request

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
}


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
    """Corre el script de compra y guarda el resultado."""
    entorno = os.environ.copy()
    entorno["PAGAR"] = "si" if pagar else "no"
    entorno["CI"] = "true"          # modo sin ventana y sin pausas

    try:
        p = subprocess.run(
            [sys.executable, SCRIPT, "--paquete", paquete],
            capture_output=True, text=True, timeout=600,
            cwd=CARPETA, env=entorno)
        salida = (p.stdout or "") + (p.stderr or "")
        if not pagar:
            ok = "NO se envio el pago" in salida
            resultado = "Prueba completada sin cobrar" if ok else "Termino con dudas"
        else:
            ok = "Pago enviado" in salida
            resultado = "Recarga enviada" if ok else "Termino con dudas"
    except subprocess.TimeoutExpired:
        salida = "Se paso de 10 minutos y se cancelo."
        resultado = "Tardo demasiado"
    except Exception as e:
        salida = str(e)
        resultado = "Fallo"

    with _candado:
        _estado["corriendo"] = False
        _estado["resultado"] = resultado
        _estado["salida"] = salida[-4000:]


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
  #detalle {
    margin-top: 12px; font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 12px; color: #9aa1ad; white-space: pre-wrap;
    max-height: 260px; overflow: auto;
  }
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
    <div id="detalle"></div>
  </div>

<script>
const PAQUETES = __PAQUETES__;
const botones = document.getElementById('botones');
const caja = document.getElementById('estado');
const punto = document.getElementById('punto');
const titulo = document.getElementById('titulo');
const detalle = document.getElementById('detalle');
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
    if (!vigilando) vigilando = setInterval(mirar, 2000);
  } catch (e) {
    punto.className = 'punto mal';
    titulo.textContent = e.message;
    bloquear(false);
  }
}

async function mirar() {
  try {
    const e = await (await fetch('/api/estado')).json();
    if (e.corriendo) {
      punto.className = 'punto trabajando';
      titulo.textContent = `Comprando ${e.paquete}... (${e.segundos||0}s)`;
      bloquear(true);
    } else if (e.resultado) {
      const bien = /enviada|completada/i.test(e.resultado);
      punto.className = 'punto ' + (bien ? 'bien' : 'mal');
      titulo.textContent = e.resultado;
      detalle.textContent = e.salida || '';
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
