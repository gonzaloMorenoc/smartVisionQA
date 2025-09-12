#!/bin/bash
set -e

echo "Iniciando Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Esperar a que Ollama esté disponible
echo "Esperando a que Ollama esté disponible..."
until curl -s http://localhost:11434/api/version > /dev/null; do
    sleep 2
done

echo "Descargando modelo qwen2.5vl:7b..."
ollama pull qwen2.5vl:7b

echo "Ejecutando SmartVisionQA..."
python3 smartVisionQA.py

# Análisis completado, terminar contenedor
echo "Análisis completado. Resultados en /app/results"