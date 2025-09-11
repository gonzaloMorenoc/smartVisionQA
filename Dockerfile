# Dockerfile para SmartVisionQA con Ollama
FROM ubuntu:22.04

# Evitar prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Instalar Ollama
RUN curl -fsSL https://ollama.ai/install.sh | sh

# Cache del modelo
ENV OLLAMA_MODELS=/app/models
RUN mkdir -p /app/models
VOLUME ["/app/models"]

# Configurar directorio de trabajo
WORKDIR /app

# Copiar requirements y instalar dependencias Python
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Instalar Playwright con chromium
RUN playwright install-deps chromium
RUN playwright install chromium

# Copiar código fuente
COPY . .

# Crear directorio de resultados
RUN mkdir -p results

# Script para inicializar Ollama y ejecutar análisis
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 11434

# Punto de entrada
ENTRYPOINT ["/docker-entrypoint.sh"]