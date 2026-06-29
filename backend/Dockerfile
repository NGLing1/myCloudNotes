FROM python:3.11-slim

WORKDIR /app

# Installation des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code
COPY app.py .

# Exposition du port
EXPOSE 5000

# Variables d'environnement par défaut
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

# Démarrage de l'application
CMD ["python", "app.py"]