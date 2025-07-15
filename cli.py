"""
Command-line interface for interacting with the Chat with Documents SaaS backend.
Provides commands to add documents, trigger processing, and chat with the document corpus.

TODO:
- Consider migrating synchronous I/O to asynchronous patterns for improved scalability.
"""

import requests
import argparse
import sys
import os
import shutil
from typing import Any, Dict

API_BASE_URL: str = "http://127.0.0.1:8000/api/v1"
LOCAL_DATA_PATH: str = "data/books"  # Path mapped to Docker volume for document storage

def check_server_health() -> bool:
    """
    Check if the backend server is running and healthy.

    Returns:
        bool: True if the server responds with a healthy status, False otherwise.

    Notable:
        Prints error messages to stderr if the server is unreachable.
    """
    try:
        response: requests.Response = requests.get("http://127.0.0.1:8000/health", timeout=3)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException:
        print("❌ Error: Cannot connect to the backend server.")
        print("   Please ensure the application is running with 'docker-compose up'.")
        return False

def process_documents() -> None:
    """
    Trigger the backend endpoint to process all added documents.

    Returns:
        None

    Notable:
        Prints the server's response message and advises monitoring Docker logs for progress.
    """
    print("Document processing instructions ...")
    try:
        response: requests.Response = requests.post(f"{API_BASE_URL}/documents/process", timeout=60)
        response.raise_for_status()
        print(f"✅ Success: {response.json().get('message')}")
        print("   You can monitor the docker logs for processing progress.")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error during processing request: {e}")

def ask_question(query: str) -> None:
    """
    Send a question to the chat API and print the response.

    Args:
        query (str): The user's question to be answered by the backend.

    Returns:
        None

    Notable:
        Prints the answer and any referenced sources. Handles HTTP errors gracefully.
    """
    print(f"💬 Asking: {query}")
    try:
        payload: Dict[str, str] = {"query": query}
        response: requests.Response = requests.post(f"{API_BASE_URL}/chat/", json=payload, timeout=90)
        response.raise_for_status()

        data: Dict[str, Any] = response.json()
        print("\n🤖 Answer:")
        print("-" * 10)
        print(data.get("answer", "No answer found.").strip())
        print("-" * 10)

        sources = data.get("sources")
        if sources:
            print("\n📚 Sources:")
            for source in sources:
                print(f"- {source}")
        print()

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"\n❌ Not Found: The documents do not contain a relevant answer.")
        else:
            print(f"\n❌ HTTP Error: {e.response.status_code} - {e.response.text}")

def main() -> None:
    """
    Entry point for the CLI application.

    Parses command-line arguments and dispatches to the appropriate command handler.

    Returns:
        None

    Notable:
        Exits with status 1 if the backend server is unreachable.
        Supports 'add', 'process', and 'chat' commands.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="A CLI for interacting with the Chat with Documents SaaS.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command: Add a local PDF to be processed.
    parser_add = subparsers.add_parser("add", help="Add a local PDF to be processed.")
    parser_add.add_argument("filepath", type=str, help="The local path to the PDF file.")

    # Process command: Tell the server to process all added documents.
    subparsers.add_parser("process", help="Tell the server to process all added documents.")

    # Chat command: Start a chat session or ask a single question.
    parser_chat = subparsers.add_parser("chat", help="Start a chat session or ask a single question.")
    parser_chat.add_argument("question", nargs='?', type=str, help="A single question to ask.")

    args = parser.parse_args()

    if not check_server_health():
        sys.exit(1)

    if args.command == "add":
        if not os.path.exists(args.filepath):
            print(f"❌ Error: File not found at '{args.filepath}'")
            return
            
        os.makedirs(LOCAL_DATA_PATH, exist_ok=True)
        # TODO: Implement per-user storage for uploaded documents
        shutil.copy(args.filepath, LOCAL_DATA_PATH)
        print(f"✅ File '{os.path.basename(args.filepath)}' added to the processing queue.")
        print("   Run the 'process' command next.")

    elif args.command == "process":
        process_documents()

    elif args.command == "chat":
        if args.question:
            ask_question(args.question)
        else:
            print("Entering interactive chat mode. Press Ctrl+C to exit.")
            try:
                while True:
                    question: str = input("\n> ")
                    if question.strip():
                        ask_question(question)
            except KeyboardInterrupt:
                print("\nExiting chat.")

if __name__ == "__main__":
    main()