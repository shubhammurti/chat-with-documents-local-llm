#!/bin/bash

cd ~ || exit

# Load the Docker image
docker load < chat-app.tar

# Stop and remove existing container
docker stop chat-app || true
docker rm chat-app || true

# Run the container again
docker run -d --name chat-app -p 3000:3000 chat-app
