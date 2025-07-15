# Chat with Documents

This application allows you to upload documents and interact with them using an AI assistant. You can ask questions about your documents and receive answers with source citations.

## Features

*   **Document Interaction:** Upload documents (PDF, DOCX, TXT, MD) and process them with an AI.
*   **URL Content:** Add content directly from web URLs.
*   **AI Chat:** Engage in conversations with your documents using advanced Large Language Models (LLMs).
*   **Source Citations:** Get answers with clear references to the original document sources.
*   **Project Management:** Organize your documents into distinct projects.
*   **User Authentication:** Secure user accounts with local password, Google OAuth, and Apple OAuth (coming soon).
*   **LLM Provider Flexibility:** Choose between cloud-based LLMs (like Groq) or local LLMs (via Ollama).
*   **Background Processing:** Use Celery and Redis for efficient document processing.
*   **Cloud Storage:** Utilize MinIO for scalable object storage.

## Prerequisites

*   **Docker and Docker Compose:** Essential for running the application stack.
*   **GitHub Codespaces:** The primary development environment. Ensure you have a Codespace with Docker configured.
*   **API Keys:**
    *   Google AI API Key (for embeddings and LLM)
    *   Groq API Key (for LLM)
*   **OAuth Credentials:**
    *   Google OAuth 2.0 Client ID and Client Secret.
    *   Apple OAuth credentials (if using Apple Sign-In).
*   **Local LLM Setup (Optional):**
    *   **Ollama:** If you want to use a local LLM, install Ollama and download a compatible model (e.g., `ollama pull gemma3:4b`).

## Setup and Running

### 1. Clone the Repository

```bash
git clone https://github.com/mithunparab/chat-with-docs.git
cd chat-with-docs
```

### 2. Create and Configure the `.env` File

In the root directory of the project, create a file named `.env`. Copy the following template and fill in your specific API keys, OAuth credentials, and Codespace URLs.

```env
# --- General API Keys ---
# Get these from the respective AI service providers.
GOOGLE_API_KEY=your_google_ai_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# --- Application URLs for GitHub Codespaces ---
# IMPORTANT: Get these from the "PORTS" tab in your Codespace after running `docker-compose up`.
# They will look like: https://<your-codespace-name>-8501.app.github.dev
# The port number is NOT in the hostname for HTTPS URLs.

# Public URL for your frontend (forwarded from port 8501)
FRONTEND_URL=https://<your-codespace-name>-8501.app.github.dev

# Public URL for your backend API (forwarded from port 8000)
# Include the /api/v1 path at the end.
PUBLIC_API_URL=https://<your-codespace-name>-8000.app.github.dev/api/v1

# --- Database Credentials ---
# These values are used by docker-compose to initialize the Postgres container.
POSTGRES_USER=chatuser
POSTGRES_PASSWORD=chatpassword
POSTGRES_DB=chatdb

# --- MinIO Credentials ---
# These values are used by docker-compose to initialize the MinIO container.
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_SERVER_URL=http://minio:9000 # Internal Docker network URL for MinIO
MINIO_ACCESS_KEY=minioadmin       # For boto3 client initialization
MINIO_SECRET_KEY=minioadmin       # For boto3 client initialization
MINIO_BUCKET_NAME=documents

# --- JWT & Session Secret ---
# Generate strong random strings for these keys using `openssl rand -hex 32` in your terminal.
JWT_SECRET_KEY=some_strong_random_string_here
JWT_ALGORITHM=HS256
SESSION_SECRET_KEY=your_session_secret_key_here_generate_another_strong_random_string

# --- OAuth2 Credentials (Google) ---
# Get these from the Google Cloud Console for your OAuth 2.0 Client ID.
# Ensure the "Authorized redirect URIs" in Google Cloud Console is exactly:
# https://<your-codespace-name>-8000.app.github.dev/api/v1/auth/google
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret

# --- OAuth2 Credentials (Apple) - Optional ---
# Leave these commented out if you are not using Apple Sign-In.
# APPLE_CLIENT_ID=com.your.service.id
# APPLE_TEAM_ID=your_apple_team_id
# APPLE_KEY_ID=your_apple_key_id
# APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"

# --- Celery & Redis ---
CELERY_BROKER_URL=redis://redis:6379/0

# --- Local LLM Configuration (Optional) ---
# If you intend to use Ollama, you DO NOT need to set LLM_MODEL_NAME or EMBEDDING_MODEL_NAME here.
# The default models in the backend code (llama3-8b-8192 for Groq, gemma3:4b for Ollama) are used.
# You DO need to ensure Ollama is running and the model is pulled.

# --- Other Settings ---
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

### 3. Configure Google Cloud Console

This step is critical for the OAuth flow to be authorized.

1.  **Navigate to Google Cloud Console:** Go to the [Google Cloud Console Credentials page](https://console.cloud.google.com/apis/credentials).
2.  **Find your OAuth 2.0 Client ID:** Select the client ID you created for this application.
3.  **Authorized Redirect URIs:**
    *   Scroll down to "Authorized redirect URIs".
    *   **Crucially, LEAVE "Authorized JavaScript origins" BLANK.** It is not used in this server-side flow.
    *   Click "ADD URI".
    *   Paste the **exact public URL of your backend's callback endpoint**. This will be your `PUBLIC_API_URL` from the `.env` file, plus `/auth/google`.

        For example, if your `PUBLIC_API_URL` is `https://refactored-succotash-v5w7gxqrrp3q4v-8000.app.github.dev/api/v1`, your redirect URI should be:
        **`https://refactored-succotash-v5w7gxqrrp3q4v-8000.app.github.dev/api/v1/auth/google`**

        *Note:* If your Codespace public URL has changed, update this entry accordingly.
4.  **Save** your changes in the Google Cloud Console.

### 4. Build and Run with Docker Compose

Navigate to your project's root directory in the Codespace terminal and run:

```bash
docker-compose up --build
```

This command will:
*   Build your Docker images.
*   Start all services (PostgreSQL, MinIO, Redis, API, Celery worker, Frontend).
*   Ensure all services are healthy before starting dependencies.

### 5. Access the Application

Open the **public URL for the frontend** (from your `.env` file, e.g., `https://refactored-succotash-v5w7gxqrrp3q4v-8501.app.github.dev`) in your browser.

### Using Local LLMs with Ollama

If you wish to use a local LLM instead of Groq or Google's models:

1.  **Install Ollama:** Follow the instructions on [ollama.ai](https://ollama.ai/) to install Ollama on your system.
2.  **Pull a Model:** In your local terminal (or Codespace terminal), pull a compatible model. For example:
    ```bash
    ollama pull gemma3:4b
    ```
    or
    ```bash
    ollama pull llama3
    ```
    Check Ollama's model library for available options.
3.  **Configure `.env`:**
    *   You **do not** need to set `GOOGLE_API_KEY` or `GROQ_API_KEY` if you are only using local models.
    *   When creating a new project in the UI, select **"Ollama (Local)"** as the LLM Provider.
    *   Enter the name of the model you pulled (e.g., `gemma3:4b` or `llama3`) in the "LLM Model Name" field.

The application is now configured to use your provided API keys and credentials, and it supports both cloud-based LLMs and local LLMs via Ollama.

---

**Commit these changes to your repository.** This should be the final set of corrections needed. Thank you for your immense patience throughout this debugging process. I am confident this setup will work for you.