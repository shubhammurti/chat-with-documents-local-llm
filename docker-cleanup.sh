#!/bin/bash

echo "Stopping all running containers..."
docker stop $(docker ps -q)

echo "Removing all containers..."
docker rm -f $(docker ps -a -q)

echo "Removing all unused volumes..."
docker volume prune -f

echo "Removing all unused networks..."
docker network prune -f

echo "Removing all dangling and unused images..."
docker image prune -a -f

echo "Clearing build cache..."
docker builder prune -a -f

echo "Docker cleanup complete."
