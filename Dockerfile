# Dockerfile

# Start with the official, reliable python slim image.
FROM python:3.12-slim

# Install the absolute minimum system libraries needed at RUNTIME.
# ADD netcat-openbsd for the startup script in docker-compose.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install a modern version of poetry
RUN pip install poetry

# Copy only the files needed to resolve and install dependencies
COPY pyproject.toml poetry.lock* ./

# Configure poetry to not use virtualenvs
RUN poetry config virtualenvs.create false

# Install production dependencies. This will now be much faster and smaller.
RUN poetry install --no-root

# Copy the application code
COPY ./app ./app

# Expose the port
EXPOSE 8000

# Set the run command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]