# Hôtellerie & Accueil — Monastère Sainte-Marie de Bouaké
# Image volontairement minimale : aucune dépendance à installer.
FROM python:3.12-alpine

LABEL org.opencontainers.image.title="Hotellerie Monastere Bouake"
LABEL org.opencontainers.image.description="Accueil et gestion de l'hotellerie monastique"

WORKDIR /app

# Le code d'abord, les données ensuite : les couches de code restent en cache.
COPY run.py ./
COPY base_connaissances.json ./
COPY hotellerie/ ./hotellerie/

# Le dossier de données existe avant le VOLUME : sinon Docker créerait un
# volume appartenant à root, et l'utilisateur non privilégié ne pourrait
# plus écrire dans sa propre base.
RUN mkdir -p /app/data

# Les données vivent dans un volume : elles survivent aux reconstructions.
ENV HOTELLERIE_DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

VOLUME ["/app/data"]
EXPOSE 8080

# Un utilisateur non privilégié : l'application n'a aucune raison d'être root.
RUN adduser -D -h /app hotellerie && chown -R hotellerie /app
USER hotellerie

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/sante')" || exit 1

CMD ["python", "run.py", "servir", "--hote", "0.0.0.0", "--port", "8080"]
