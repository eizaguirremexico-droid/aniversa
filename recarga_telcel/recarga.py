"""
Recarga Telcel automatizada.

Todo el proceso ocurre dentro de UN SOLO iframe de paymentservice.telcel.com
que va cambiando de pantalla:
    1. numero de telefono  (mdn / confirmMdn)  -> boton Continuar
    2. tipo de pago        (radio paymentType)
    3. datos de tarjeta    (cardNumber, dateExp, CVV, CP, email, tycos)
                                               -> boton Pagar

Las tarjetas de paquetes estan en la pagina principal (no en el iframe)
y tardan bastante en dibujarse. El iframe de pagos solo aparece DESPUES
de presionar 'Lo quiero'.

EN TU PC:
  1. python recarga.py          -> crea datos.txt y se sale
  2. Llena datos.txt en el Bloc de notas
  3. python recarga.py          -> ahora si corre

EN GITHUB ACTIONS:
  Los datos se leen de variables de entorno (los Secrets del repo) y
  el paquete llega por  --paquete "2 Horas"  desde el menu desplegable.

NO subas datos.txt a git: ahi va tu tarjeta. Ya esta en .gitignore.
"""

import os
import sys
import time
import traceback
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

VERSION = "v11 - corre en la PC y en GitHub Actions"

URL = "https://www.telcel.com/personas/amigo/paquetes/internet-por-tiempo"
DOMINIO_PAGO = "paymentservice.telcel.com"

# En GitHub Actions no hay nadie mirando ni escritorio donde dibujar.
EN_SERVIDOR = os.environ.get("CI") == "true"

# Con --auto no se espera ningun ENTER: sirve para el Programador de
# tareas de Windows y para el servidor, donde nadie presiona teclas.
AUTOMATICO = "--auto" in sys.argv or EN_SERVIDOR

# En un Linux sin escritorio no hay donde dibujar una ventana: si se
# intenta, Chromium no arranca. Se detecta por la ausencia de DISPLAY.
SIN_ESCRITORIO = (sys.platform.startswith("linux")
                  and not os.environ.get("DISPLAY")
                  and not os.environ.get("WAYLAND_DISPLAY"))

SIN_VENTANA = "--headless" in sys.argv or EN_SERVIDOR or SIN_ESCRITORIO

# True = cobra de verdad.  False = llena todo pero no paga.
# En GitHub Actions lo decide la variable PAGAR (si / no).
EJECUTAR_PAGO = os.environ.get("PAGAR", "si").strip().lower() in (
    "si", "s", "1", "true", "yes")


def pausa(mensaje):
    """Espera un ENTER, salvo en modo automatico."""
    if AUTOMATICO:
        return
    input(mensaje)


def arg_valor(nombre):
    """Lee '--nombre valor' de la linea de comandos."""
    if nombre in sys.argv:
        i = sys.argv.index(nombre)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(CARPETA, "datos.txt")

PLANTILLA = """\
# Llena cada dato despues del signo =, sin comillas.
# Las lineas que empiezan con # son comentarios.

# Que paquete comprar. Basta con un pedazo del nombre.
# Ejemplos:  4 Horas    2 Horas    1 Hora
PAQUETE=4 Horas

NUMERO=
TARJETA=
EXP=07/31
CVV=
CP=
EMAIL=

# Tipo de pago: 0 = primera opcion, 1 = segunda opcion.
# Verifica en pantalla cual corresponde a tu tarjeta (credito/debito).
TIPO_PAGO=0
"""

REQUERIDAS = ("NUMERO", "TARJETA", "EXP", "CVV", "CP", "EMAIL")


def crear_plantilla():
    """Crea datos.txt y lo abre, cuando hay alguien mirando la pantalla."""
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        f.write(PLANTILLA)
    print("=" * 60)
    print("Se creo el archivo de datos aqui:")
    print("\n   " + ARCHIVO + "\n")
    print("Te lo estoy abriendo en el Bloc de notas.")
    print("Llenalo, guarda con Ctrl+S, y corre este script otra vez.")
    print("=" * 60)
    try:
        os.startfile(ARCHIVO)
    except AttributeError:
        import subprocess
        subprocess.Popen(
            ["open" if sys.platform == "darwin" else "xdg-open", ARCHIVO])
    except Exception as e:
        print(f"(No se pudo abrir solo: {e}. Abrelo a mano.)")
    pausa("\nENTER para salir...")
    sys.exit(0)


def leer_config():
    """
    Los datos salen de datos.txt en tu PC, o de variables de entorno
    en GitHub Actions (donde vienen de los Secrets del repositorio).
    """
    cfg = {}

    if os.path.exists(ARCHIVO):
        origen = "datos.txt"
        with open(ARCHIVO, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                k, _, v = linea.partition("=")
                cfg[k.strip().upper()] = v.strip()
    else:
        origen = "variables de entorno"
        for k in REQUERIDAS + ("PAQUETE", "TIPO_PAGO"):
            v = os.environ.get(k)
            if v:
                cfg[k] = v.strip()

    # El paquete puede venir por linea de comandos y gana sobre lo demas:
    # es lo que elige el menu desplegable del workflow.
    elegido = arg_valor("--paquete")
    if elegido:
        cfg["PAQUETE"] = elegido

    if not cfg and not AUTOMATICO:
        crear_plantilla()

    faltan = [k for k in REQUERIDAS if not cfg.get(k)]
    if faltan:
        print("=" * 60)
        print(f"Faltan estos datos (origen: {origen}):")
        for f_ in faltan:
            print("   -", f_)
        if origen == "datos.txt":
            print("\nEditalo en:  " + ARCHIVO)
        else:
            print("\nRevisa los Secrets del repositorio en GitHub.")
        print("=" * 60)
        pausa("\nENTER para salir...")
        sys.exit(1)

    cfg.setdefault("TIPO_PAGO", "0")
    cfg.setdefault("PAQUETE", "1 Hora")
    print(f"Datos leidos de {origen}: OK")
    print(f"Paquete solicitado: {cfg['PAQUETE']!r}")
    print(f"Cobrar de verdad: {'SI' if EJECUTAR_PAGO else 'NO'}")
    return cfg


def solo_digitos(texto):
    """
    Los campos con mascara (dateExp, cardNumber) ponen ellos mismos la
    diagonal y los espacios. Si les mandamos esos caracteres, se duplican
    y el valor queda roto. Asi que se envian unicamente los digitos:
    "07/31" -> "0731"
    """
    return "".join(c for c in texto if c.isdigit())


def limpiar(campo):
    """Vacia el campo. Los inputs de React no siempre obedecen fill('')."""
    try:
        campo.click()
        campo.press("Control+a")
        campo.press("Delete")
    except Exception:
        pass
    try:
        campo.fill("")
    except Exception:
        pass


def escribir(campo, texto, etiqueta="campo", intentos=3):
    """
    Escribe y VERIFICA que haya quedado completo.

    Estos campos saltan el foco solos cuando se llenan, asi que las
    teclas restantes se van al campo siguiente y el primero queda corto.
    Por eso se relee el valor y, si falta algo, se reescribe mas lento.
    """
    # El email no es numerico: ahi se compara el texto completo.
    es_numerico = texto.isdigit()
    esperado = len(texto)
    for intento in range(1, intentos + 1):
        demora = 120 + (intento - 1) * 130      # 120, 250, 380 ms

        limpiar(campo)
        campo.click()
        try:
            campo.press_sequentially(texto, delay=demora)
        except AttributeError:
            campo.type(texto, delay=demora)     # Playwright viejo

        try:
            valor = campo.input_value()
            quedo = len(solo_digitos(valor)) if es_numerico else len(valor.strip())
        except Exception:
            quedo = -1

        if quedo == esperado:
            extra = "" if intento == 1 else f" (intento {intento})"
            unidad = "digitos" if es_numerico else "caracteres"
            print(f"      {etiqueta}: OK, {esperado} {unidad}{extra}")
            return True

        print(f"      {etiqueta}: quedaron {quedo} de {esperado}, "
              f"reintentando mas lento...")

    print(f"      {etiqueta}: NO se pudo completar. Revisa la pantalla.")
    return False


def marcar(marco, campo, etiqueta="checkbox"):
    """
    Marca un checkbox o radio probando varias estrategias.

    Muchos formularios ocultan el <input> real y dibujan encima un
    <span> o un <label>. El clic normal choca contra ese adorno, asi
    que hay que intentar por otros caminos y VERIFICAR el resultado.
    """
    def ya_esta():
        try:
            return campo.is_checked()
        except Exception:
            return False

    if ya_esta():
        print(f"      {etiqueta}: ya estaba marcado.")
        return True

    intentos = [
        ("check normal", lambda: campo.check(timeout=5_000)),
        ("check forzado", lambda: campo.check(timeout=5_000, force=True)),
        ("clic forzado", lambda: campo.click(timeout=5_000, force=True)),
        ("evento click", lambda: campo.dispatch_event("click")),
    ]

    for nombre, accion in intentos:
        try:
            accion()
            if ya_esta():
                print(f"      {etiqueta}: marcado ({nombre}).")
                return True
        except Exception:
            pass

    # Ultimo recurso: clic sobre la etiqueta <label> asociada.
    try:
        ident = campo.get_attribute("id")
        if ident:
            etiq = marco.locator(f"label[for='{ident}']")
            if etiq.count():
                etiq.first.click(timeout=5_000, force=True)
                if ya_esta():
                    print(f"      {etiqueta}: marcado (via label).")
                    return True
    except Exception:
        pass

    print(f"      {etiqueta}: NO se pudo marcar.")
    return False


def esperar_habilitado(page, boton, segundos=15):
    """Espera a que un boton deshabilitado se active."""
    for _ in range(segundos * 2):
        try:
            if boton.is_enabled():
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def cerrar_cookies(page):
    """El aviso de cookies puede tapar los botones."""
    for sel in (".acepto-cookies", "a:has-text('Acepto las Cookies')",
                "button:has-text('Acepto')"):
        try:
            b = page.locator(sel)
            if b.count() and b.first.is_visible():
                b.first.click(timeout=5_000)
                print("      Aviso de cookies cerrado.")
                return
        except Exception:
            pass


JS_HAY_BOTON = """() => {
    const SEL = 'a, button, input[type=button], [role=button], [class*=btn]';
    return [...document.querySelectorAll(SEL)].some(e =>
        ((e.innerText || e.value || '').replace(/\s+/g, ' ').trim().toLowerCase())
            .includes('lo quiero'));
}"""

JS_DIAGNOSTICO = """() => {
    const txt = (document.body ? document.body.innerText : '') || '';
    const SEL = 'a, button, input[type=button], [role=button], [class*=btn]';
    const clicables = [...document.querySelectorAll(SEL)]
        .map(e => (e.innerText || e.value || '').replace(/\s+/g, ' ').trim())
        .filter(t => t)
        .slice(0, 25);
    return {
        largo: txt.length,
        // El texto mismo, no solo su tamaño: si el sitio devuelve un
        // bloqueo o una verificacion, la respuesta esta escrita ahi.
        texto: txt.replace(/\s+/g, ' ').trim().slice(0, 400),
        titulo: document.title || '',
        tieneQuiero: txt.toLowerCase().includes('quiero'),
        tienePaquete: txt.toLowerCase().includes('internet por tiempo'),
        clicables: clicables
    };
}"""


def buscar_marco_con_paquetes(page, limite=150):
    """
    Busca el boton 'Lo quiero' en CUALQUIER marco, usando JavaScript.

    No se usa el selector text= de Playwright: en el sitio real no
    encontraba los botones ni estando visibles en pantalla. Preguntarle
    al DOM directamente evita esas sutilezas del motor de selectores.

    Devuelve en cuanto lo encuentra; el limite es solo el tope.
    """
    transcurrido = 0
    while transcurrido < limite:
        for f in page.frames:
            try:
                if f.evaluate(JS_HAY_BOTON):
                    donde = ("marco principal" if f is page.main_frame
                             else f"iframe: {(f.url or '(sin url)')[:70]}")
                    print(f"      [{transcurrido:3}s] Botones encontrados "
                          f"en el {donde}")
                    return f
            except Exception:
                pass

        if transcurrido % 15 == 0:
            print(f"      [{transcurrido:3}s] esperando las tarjetas... "
                  f"({len(page.frames)} marcos)")
        page.wait_for_timeout(3_000)
        transcurrido += 3

    return None


def diagnosticar_marcos(page):
    """Si no se hallaron los botones, reportar que SI hay en cada marco."""
    print("\n      === Que contiene cada marco ===")
    for i, f in enumerate(page.frames):
        url = (f.url or "(sin url)")[:65]
        try:
            d = f.evaluate(JS_DIAGNOSTICO)
        except Exception as e:
            print(f"      [{i}] {url}  -> no se pudo leer ({type(e).__name__})")
            continue

        if not d["largo"]:
            continue
        print(f"      [{i}] {url}")
        print(f"          titulo: {d.get('titulo', '')!r}")
        print(f"          texto={d['largo']} chars, "
              f"dice 'quiero'={d['tieneQuiero']}, "
              f"dice 'internet por tiempo'={d['tienePaquete']}")
        # El contenido literal: si el sitio devolvio un bloqueo o una
        # verificacion, la explicacion esta escrita en este texto.
        if d.get("texto"):
            print(f"          CONTENIDO: {d['texto']}")
        if d["clicables"]:
            print(f"          clicables: {d['clicables'][:12]}")


def elegir_paquete(page, nombre):
    """
    Hace clic en el boton 'Lo quiero' de la tarjeta del paquete pedido.

    Las tarjetas tardan bastante en dibujarse, y todas tienen un boton
    con el mismo texto. Asi que se busca el boton cuyo RECUADRO contenga
    el nombre del paquete.
    """
    print(f"\n[0/3] Buscando el paquete: {nombre!r}")
    print("      (las tarjetas tardan en aparecer, espera...)")

    marco = buscar_marco_con_paquetes(page)
    if marco is None:
        page.screenshot(path="error_sin_paquetes.png", full_page=True)
        print("\n      No aparecio ningun boton 'Lo quiero' en 150s,")
        print("      en ninguno de los marcos. Captura: error_sin_paquetes.png")
        diagnosticar_marcos(page)
        raise RuntimeError("No se encontraron las tarjetas de paquetes")

    page.wait_for_timeout(2_000)
    cerrar_cookies(page)

    handle = marco.evaluate_handle("""(nombre) => {
        const SEL = 'a, button, input[type=button], [role=button]';
        const esLoQuiero = e =>
            ((e.innerText || e.value || '').trim().toLowerCase()) === 'lo quiero';
        const objetivo = nombre.trim().toLowerCase();
        const botones = [...document.querySelectorAll(SEL)].filter(esLoQuiero);

        for (const b of botones) {
            let n = b.parentElement;
            for (let i = 0; i < 8 && n; i++, n = n.parentElement) {
                // Si este contenedor ya abarca varios botones 'Lo quiero',
                // significa que salimos de la tarjeta: dejar de subir.
                // Sin esto se llega al <body>, que contiene TODOS los
                // paquetes, y cualquier nombre coincidiria.
                const dentro = [...n.querySelectorAll(SEL)].filter(esLoQuiero).length;
                if (dentro > 1) break;
                if ((n.innerText || '').toLowerCase().includes(objetivo)) return b;
            }
        }
        return null;
    }""", nombre)

    elemento = handle.as_element()
    if elemento is None:
        # No se hallo: mostrar que paquetes SI hay, para corregir datos.txt
        print(f"\n      No encontre un paquete que diga {nombre!r}.")
        print("      Los paquetes disponibles en la pagina son:")
        try:
            titulos = marco.evaluate("""() => {
                const SEL = 'a, button, input[type=button], [role=button]';
                const esLoQuiero = e =>
                    ((e.innerText || e.value || '').trim().toLowerCase()) === 'lo quiero';
                return [...document.querySelectorAll(SEL)].filter(esLoQuiero).map(b => {
                    let n = b.parentElement, mejor = '(sin titulo)';
                    for (let i = 0; i < 8 && n; i++, n = n.parentElement) {
                        const dentro = [...n.querySelectorAll(SEL)].filter(esLoQuiero).length;
                        if (dentro > 1) break;
                        const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
                        if (t.length > 15) mejor = t.slice(0, 90);
                    }
                    return mejor;
                });
            }""")
            for t in titulos:
                print("         -", t)
        except Exception:
            pass
        print("\n      Corrige la linea PAQUETE= en datos.txt")
        raise RuntimeError(f"Paquete no encontrado: {nombre}")

    elemento.scroll_into_view_if_needed()
    elemento.click()
    print("      'Lo quiero' presionado.")
    page.wait_for_timeout(3_000)


def paso_numero(page, pago, cfg):
    print("\n[1/3] Pantalla del numero de telefono...")
    mdn = pago.locator("input[name='mdn']")
    mdn.wait_for(state="visible", timeout=150_000)   # la pagina tarda mucho

    numero = solo_digitos(cfg["NUMERO"])
    confirm = pago.locator("input[name='confirmMdn']")

    escribir(mdn, numero, "mdn")
    # El segundo se limpia primero: puede traer teclas que se le colaron
    # del primero cuando el foco salto.
    escribir(confirm, numero, "confirmMdn")

    # El primero se revisa OTRA VEZ: al escribir en el segundo, el foco
    # pudo haber regresado y ensuciado el valor anterior.
    try:
        if len(solo_digitos(mdn.input_value())) != len(numero):
            print("      mdn se altero al llenar el segundo. Rehaciendo...")
            escribir(mdn, numero, "mdn (2a pasada)")
    except Exception:
        pass

    boton = pago.locator("button:has-text('Continuar')")
    boton.wait_for(state="visible", timeout=120_000)

    if not esperar_habilitado(page, boton):
        print("\n      El boton Continuar sigue deshabilitado.")
        print("      Contenido real de los campos:")
        for nombre in ("mdn", "confirmMdn"):
            try:
                v = solo_digitos(
                    pago.locator(f"input[name='{nombre}']").input_value())
                print(f"        {nombre}: {len(v)} digitos")
            except Exception as e:
                print(f"        {nombre}: no se pudo leer ({e})")
        raise RuntimeError("Continuar no se habilito")

    boton.click()
    print("      Continuar presionado.")
    page.wait_for_timeout(3_000)


def paso_tipo_pago(page, pago, cfg):
    print("\n[2/3] Pantalla de tipo de pago...")
    radios = pago.locator("input[name='paymentType']")
    radios.first.wait_for(state="visible", timeout=120_000)

    indice = int(cfg.get("TIPO_PAGO", "0"))
    marcar(pago, radios.nth(indice), f"paymentType[{indice}]")
    page.wait_for_timeout(2_000)


def paso_tarjeta(page, pago, cfg):
    print("\n[3/3] Pantalla de datos de tarjeta...")
    tarjeta = pago.locator("input[name='cardNumber']")
    tarjeta.wait_for(state="visible", timeout=120_000)

    escribir(tarjeta, solo_digitos(cfg["TARJETA"]), "cardNumber")
    escribir(pago.locator("input[name='dateExp']"), solo_digitos(cfg["EXP"]), "dateExp")
    escribir(pago.locator("input[name='CVV']"), solo_digitos(cfg["CVV"]), "CVV")
    escribir(pago.locator("input[name='CP']"), solo_digitos(cfg["CP"]), "CP")
    escribir(pago.locator("input[name='email']"), cfg["EMAIL"], "email")
    print("      Datos de tarjeta capturados.")

    marcar(pago, pago.locator("input[name='tycos']"), "tycos (terminos)")

    # Verificar que las mascaras no hayan deformado los valores.
    # Se compara solo la LONGITUD, nunca se imprime el dato.
    print("\n      Verificacion de lo que quedo escrito:")
    esperado = {
        "cardNumber": len(solo_digitos(cfg["TARJETA"])),
        "dateExp": len(solo_digitos(cfg["EXP"])),
        "CP": len(solo_digitos(cfg["CP"])),
    }
    for campo, n_digitos in esperado.items():
        try:
            valor = pago.locator(f"input[name='{campo}']").input_value()
            reales = len(solo_digitos(valor))
            marca = "OK " if reales == n_digitos else "MAL"
            print(f"        [{marca}] {campo}: {reales} digitos "
                  f"(se esperaban {n_digitos})")
        except Exception as e:
            print(f"        [ ? ] {campo}: no se pudo leer ({e})")

    page.screenshot(path="antes_de_pagar.png", full_page=True)
    print("      Captura previa: antes_de_pagar.png")

    if EJECUTAR_PAGO:
        print("\n      Enviando el pago...")
        boton_pagar = pago.locator("button:has-text('Pagar')")
        if not esperar_habilitado(page, boton_pagar):
            print("      El boton Pagar sigue deshabilitado. Se detiene aqui.")
            return
        boton_pagar.click()
        print("      Pago enviado. Observando que responde el sitio...")

        # Vigilar 2 minutos: aqui aparece el 3D Secure del banco si lo hay.
        visto = set()
        # Ya se comprobo que el banco no pide 3D Secure, asi que
        # en modo automatico basta una vigilancia corta.
        vigilar = 15 if AUTOMATICO else 120
        for seg in range(0, vigilar, 5):
            page.wait_for_timeout(5_000)
            for f in page.frames:
                url = f.url or ""
                if any(x in url for x in ("online-metrix", "doubleclick",
                                          "adsrvr", "demdex")):
                    continue
                try:
                    txt = f.evaluate(
                        "() => (document.body ? document.body.innerText : '')"
                        ".replace(/\\s+/g,' ').trim().slice(0, 200)")
                except Exception:
                    continue
                if txt and txt not in visto:
                    visto.add(txt)
                    print(f"      [{seg:3}s] {url[:45]}")
                    print(f"             {txt[:150]}")
            # Sin full_page: en esta pagina tarda varios segundos
            # y aqui solo interesa el aviso de confirmacion.
            try:
                page.screenshot(path=f"resultado_{seg:03}s.png")
            except Exception:
                pass

        print("\n      Se guardaron capturas resultado_XXXs.png")
        print("      Revisa si el banco pidio codigo o si el cargo paso.")
    else:
        print("\n      *** EJECUTAR_PAGO = False -> NO se envio el pago. ***")
        print("      *** Revisa el navegador: todo deberia estar lleno. ***")


def registrar_bitacora(texto):
    """Deja constancia de cada corrida, util cuando corre solo."""
    try:
        with open(os.path.join(CARPETA, "bitacora.txt"), "a",
                  encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {texto}\n")
    except Exception:
        pass


def main():
    print("=" * 60)
    print("  recarga.py  " + VERSION)
    print("=" * 60)

    if EJECUTAR_PAGO and not AUTOMATICO:
        print("\n  *** ATENCION: EJECUTAR_PAGO esta en True. ***")
        print("  *** Este script VA A COBRAR a tu tarjeta.  ***")
        print("\n  Para cancelar, cierra esta ventana ahora.")
        print("  Para desactivarlo, pon EJECUTAR_PAGO = False arriba.")
        for queda in range(10, 0, -1):
            print(f"    continuando en {queda}...", end="\r", flush=True)
            time.sleep(1)
        print("    continuando...          ")

    cfg = leer_config()

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=SIN_VENTANA)
        page = navegador.new_context().new_page()

        try:
            print("Abriendo pagina de paquetes...")
            page.goto(URL, wait_until="domcontentloaded", timeout=90_000)

            cerrar_cookies(page)
            elegir_paquete(page, cfg.get("PAQUETE", "4 Horas"))

            # El mismo iframe sirve para las 3 pantallas.
            pago = page.frame_locator(f"iframe[src*='{DOMINIO_PAGO}']")

            paso_numero(page, pago, cfg)
            paso_tipo_pago(page, pago, cfg)
            paso_tarjeta(page, pago, cfg)
            registrar_bitacora(
                f"OK paquete={cfg.get('PAQUETE')} "
                f"pago={'SI' if EJECUTAR_PAGO else 'NO'}")

        except PWTimeout as e:
            print("\nTIMEOUT: un elemento no aparecio a tiempo.")
            print("Puede que la pantalla haya cambiado de forma.")
            print(e)
            try:
                page.screenshot(path="error.png", full_page=True)
                print("Captura del error en error.png")
            except Exception:
                pass
        except Exception:
            print("\n--- FALLO ---")
            print(traceback.format_exc())
            registrar_bitacora("FALLO: ver error.png")
            try:
                page.screenshot(path="error.png", full_page=True)
            except Exception:
                pass
        finally:
            pausa("\nENTER para cerrar...")
            # Cerrar el contexto antes que el navegador: deja menos
            # procesos hijos sueltos, que son los que mantenian abierta
            # la tuberia de salida y bloqueaban a quien nos invoco.
            try:
                page.context.close()
            except Exception:
                pass
            try:
                navegador.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
    pausa("Fin. ENTER para salir...")
