# Imagen oficial de Playwright: ya trae Chromium y todas las
# librerias del sistema que necesita. Instalarlo a mano en una
# imagen limpia es la causa mas comun de fallos raros.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

# Playwright se instala explicitamente: la imagen trae los navegadores,
# pero no garantiza que el modulo de Python sea visible para el mismo
# interprete con el que corre gunicorn. La version debe coincidir con
# la etiqueta de la imagen (v1.49.0) para que encuentre esos navegadores.
RUN pip install --no-cache-dir \
        playwright==1.49.0 \
        flask==3.0.3 \
        gunicorn==22.0.0

# Los navegadores ya vienen en la imagen, aqui.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Falla la construccion si el modulo no quedo importable, en vez de
# descubrirlo hasta que alguien toca un boton.
RUN python -c "from playwright.sync_api import sync_playwright; print('playwright OK')"

COPY recarga.py servidor.py ./

ENV PUERTO=8080
EXPOSE 8080

# Un solo worker y un solo hilo: la compra usa un candado en memoria
# para no lanzar dos a la vez, y con varios workers ese candado no
# serviria de nada. El timeout largo es porque la pagina de Telcel
# tarda mas de un minuto en cargar.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", \
     "--threads", "4", "--timeout", "900", "servidor:app"]
