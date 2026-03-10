#!/bin/bash
set -e

echo "Iniciando Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Esperar a que Ollama esté disponible con timeout
echo "Esperando a que Ollama esté disponible..."
MAX_RETRIES=30
RETRY=0
until curl -s http://localhost:11434/api/version > /dev/null; do
    RETRY=$((RETRY+1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "ERROR: Ollama no arrancó tras $MAX_RETRIES intentos"
        exit 1
    fi
    sleep 2
done

echo "Descargando modelo ${OLLAMA_MODEL:-qwen2.5vl:7b}..."
ollama pull "${OLLAMA_MODEL:-qwen2.5vl:7b}"

echo "Ejecutando SmartVisionQA..."
python3 smartVisionQA.py

# Mantener contenedor activo para copiar resultados
echo "Análisis completado. Resultados en /app/results"
wait $OLLAMA_PID
