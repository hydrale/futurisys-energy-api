# Image de l'API. Sert a deux choses : faire tourner le service en local exactement
# comme en ligne, et alimenter l'hebergement Hugging Face, qui demarre a partir d'un
# Dockerfile place a la racine du depot.

# -slim et non l'image complete : environ 130 Mo au lieu de 1 Go. Le temps de
# telechargement pese sur chaque deploiement.
FROM python:3.11-slim

# Ne pas tourner en root. Si l'API etait compromise, un compte sans privilege limite
# fortement ce qu'un attaquant peut faire dans le conteneur.
RUN useradd --create-home --uid 1000 futurisys

WORKDIR /app

# Les dependances sont copiees et installees AVANT le code : Docker garde en cache
# cette couche tant que requirements.txt ne bouge pas. Une modification du code ne
# declenche donc pas une reinstallation complete.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY models ./models
COPY data ./data

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    APP_ENV=prod

USER futurisys

# 7860 : le port qu'attend Hugging Face Spaces. En local, -p 8000:7860 le ramene
# sur le port habituel.
EXPOSE 7860

# Verification de vie : Docker interroge /health et marque le conteneur en echec si
# la base ou le modele ne repondent plus, au lieu de le laisser tourner a vide.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')"

CMD ["uvicorn", "futurisys.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
