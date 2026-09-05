FROM python:3.11-slim

# Evita la scrittura dei file .pyc e abilita log non bufferizzati
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Rome

# Installa certificati SSL e supporto fuso orario
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installa le dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia i file dell'applicazione
COPY config.py checker.py bot.py main.py ./

# Crea la directory per i dati persistenti (stato, log)
RUN mkdir -p /app/data

# Volume per persistenza stato
VOLUME ["/app/data"]

# Comando di avvio
CMD ["python", "main.py"]
