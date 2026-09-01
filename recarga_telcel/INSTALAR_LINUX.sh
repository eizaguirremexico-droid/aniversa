#!/usr/bin/env bash
#
# Instala el bot de recarga como servicio en Linux.
#
#   sudo bash INSTALAR_LINUX.sh
#
# Deja todo en /opt/recarga y lo arranca solo con el sistema.

set -euo pipefail

DESTINO=/opt/recarga
ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "Correlo con sudo:  sudo bash INSTALAR_LINUX.sh"
    exit 1
fi

# El servicio corre como tu usuario, no como root: no hace falta y
# limita el daño si algo sale mal.
USUARIO="${SUDO_USER:-$USER}"
echo "==> El servicio correra como: $USUARIO"

echo "==> Instalando dependencias del sistema"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

echo "==> Copiando archivos a $DESTINO"
mkdir -p "$DESTINO"
for f in recarga.py bot_telegram.py; do
    if [[ ! -f "$ORIGEN/$f" ]]; then
        echo "FALTA $f en $ORIGEN"
        exit 1
    fi
    cp "$ORIGEN/$f" "$DESTINO/"
done

# datos.txt solo se copia si no existe: nunca pisar el que ya tenga
# los datos buenos.
if [[ -f "$ORIGEN/datos.txt" && ! -f "$DESTINO/datos.txt" ]]; then
    cp "$ORIGEN/datos.txt" "$DESTINO/"
    echo "==> datos.txt copiado"
elif [[ -f "$DESTINO/datos.txt" ]]; then
    echo "==> datos.txt ya existia, no lo toco"
else
    echo "==> OJO: no hay datos.txt. Crealo en $DESTINO/datos.txt"
fi

echo "==> Creando el entorno de Python"
python3 -m venv "$DESTINO/venv"
"$DESTINO/venv/bin/pip" install --quiet --upgrade pip
"$DESTINO/venv/bin/pip" install --quiet requests playwright

echo "==> Descargando Chromium y sus dependencias (tarda un rato)"
"$DESTINO/venv/bin/playwright" install --with-deps chromium

# Los navegadores se descargan en el HOME de quien corre playwright,
# que aqui es root. Se mueven a una ruta comun para que el servicio,
# corriendo como el usuario normal, tambien los encuentre.
if [[ -d /root/.cache/ms-playwright ]]; then
    mkdir -p /opt/ms-playwright
    cp -r /root/.cache/ms-playwright/* /opt/ms-playwright/ 2>/dev/null || true
    chmod -R a+rX /opt/ms-playwright
fi

chown -R "$USUARIO":"$USUARIO" "$DESTINO"
chmod 600 "$DESTINO/datos.txt" 2>/dev/null || true

echo "==> Instalando el servicio"
sed -e "s|CAMBIA_USUARIO|$USUARIO|" "$ORIGEN/bot-recarga.service" \
    > /etc/systemd/system/bot-recarga.service

# Decirle al servicio donde quedaron los navegadores.
if [[ -d /opt/ms-playwright ]]; then
    sed -i '/^ExecStart=/i Environment=PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright' \
        /etc/systemd/system/bot-recarga.service
fi

systemctl daemon-reload
systemctl enable --now bot-recarga

echo
echo "============================================================"
echo "  Listo. El bot arranca solo con el sistema."
echo
echo "  Ver si esta vivo:   systemctl status bot-recarga"
echo "  Ver que hace:       journalctl -u bot-recarga -f"
echo "  Detenerlo:          sudo systemctl stop bot-recarga"
echo "  Que no arranque:    sudo systemctl disable bot-recarga"
echo "============================================================"
