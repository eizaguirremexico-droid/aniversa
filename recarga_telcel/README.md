# Recarga Telcel

Compra un paquete de Internet por tiempo en telcel.com sin intervención manual.

## Cómo funciona la página

Todo el proceso de compra vive dentro de un solo iframe de
`paymentservice.telcel.com`, que va cambiando de pantalla sin que cambie la URL:

| Pantalla | Campos | Botón |
|---|---|---|
| Número | `mdn`, `confirmMdn` | Continuar |
| Tipo de pago | radio `paymentType` | — |
| Tarjeta | `cardNumber`, `dateExp`, `CVV`, `CP`, `email`, `tycos` | Pagar |

Las tarjetas de paquetes, en cambio, están en la página principal y tardan
unos 40 segundos en dibujarse. El iframe de pago **no existe** hasta que se
presiona "Lo quiero".

## Detalles que costaron trabajo

- **`dateExp` es un solo campo `MM/AA`** y pone la diagonal solo. Hay que
  enviarle únicamente dígitos (`0731`), o el valor queda deformado.
- **Los campos saltan el foco** al llenarse, y las teclas restantes se van al
  campo siguiente. Por eso se escribe, se relee el valor y se reintenta más
  lento si quedó corto.
- **El checkbox de términos** está oculto tras un adorno; el clic normal falla.
  Se prueban cinco estrategias hasta que `is_checked()` confirma.
- **Cada tarjeta de paquete** tiene un botón con el mismo texto. La búsqueda
  del contenedor se detiene en cuanto abarca más de un botón, o cualquier
  nombre coincidiría y siempre se compraría el primero.

## Uso en la PC

```
pip install playwright
playwright install chromium
python recarga.py
```

La primera vez crea `datos.txt` y lo abre para que lo llenes. Ese archivo
está en `.gitignore` y no debe subirse: contiene la tarjeta.

Opciones:

- `--auto` no espera ningún ENTER (para el Programador de tareas)
- `--headless` sin ventana
- `--paquete "2 Horas"` elige el paquete

## Uso desde el teléfono

En la app de GitHub: **Actions → Recarga Telcel → Run workflow**, eliges el
paquete del menú y confirmas. No hace falta tener la PC encendida.

Requiere configurar estos Secrets en el repositorio
(Settings → Secrets and variables → Actions):

| Secret | Ejemplo |
|---|---|
| `TELCEL_NUMERO` | 5512345678 |
| `TELCEL_TARJETA` | 1234567812345678 |
| `TELCEL_EXP` | 07/31 |
| `TELCEL_CVV` | 123 |
| `TELCEL_CP` | 12345 |
| `TELCEL_EMAIL` | tu@correo.com |
| `TELCEL_TIPO_PAGO` | 0 |

El workflow arranca con `pagar: no`, que llena todo pero no cobra. Para una
compra real hay que cambiarlo a `si` en el menú.

## Límites conocidos

- El pago no pidió 3-D Secure en las pruebas, pero eso depende del banco y del
  monto; puede cambiar sin aviso.
- La página de pago carga ThreatMetrix (`online-metrix.net`), un sistema
  antifraude que perfila el dispositivo. Ejecutar desde una IP de centro de
  datos como la de GitHub Actions se ve distinto que desde una casa, y podría
  hacer que la transacción se rechace o se marque.
- Los selectores dependen del HTML de Telcel. Si cambian el sitio, hay que
  volver a mapearlo.
