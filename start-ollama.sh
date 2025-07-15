#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Start the Ollama server in the background
ollama serve &
# Get the process ID of the server
PID=$!

echo "Ollama server started with PID: $PID"
echo "Waiting for Ollama server to be ready..."

while ! ollama list > /dev/null 2>&1; do
  echo "Polling Ollama server..."
  sleep 1
done

echo "Ollama server is ready."
echo "--- Pulling llama3 model (this may take several minutes) ---"
ollama pull llama3

echo "--- Pulling gemma model (this may take several minutes) ---"
ollama pull gemma

# Add other popular models to pre-pull
echo "--- Pulling phi3 model ---"
ollama pull phi3

echo "--- Ollama models are ready ---"

# Bring the server process to the foreground and wait for it.
wait $PID