# Imagen oficial de Playwright: ya trae Chromium y todas las
# librerias del sistema que necesita. Instalarlo a mano en una
# imagen limpia es la causa mas comun de fallos raros.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

RUN pip install --no-cache-dir flask==3.0.3 gunicorn==22.0.0

COPY recarga.py servidor.py ./

ENV PUERTO=8080
EXPOSE 8080

# Un solo worker y un solo hilo: la compra usa un candado en memoria
# para no lanzar dos a la vez, y con varios workers ese candado no
# serviria de nada. El timeout largo es porque la pagina de Telcel
# tarda mas de un minuto en cargar.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", \
     "--threads", "4", "--timeout", "900", "servidor:app"]
