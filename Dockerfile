FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_MODE=backoffice
WORKDIR /srv/erp
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home erp
COPY --chown=erp:erp app ./app
COPY --chown=erp:erp schema ./schema
RUN mkdir -p /srv/erp/data && chown erp:erp /srv/erp/data
USER erp
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-proxy-headers"]
