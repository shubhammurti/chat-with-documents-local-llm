"""
Unified Streamlit UI for Chat with Documents

This module handles the complete user experience, including:
- User authentication via password, Google, and Apple (OAuth2).
- Project management with a choice of LLM providers (Cloud vs. Local).
- Document management (upload, URL, status tracking with non-flickering auto-polling).
- Real-time, streaming chat interaction with source citations.
- Deletion of chats and documents.
"""
import streamlit as st
import requests
import pandas as pd
import json
from typing import Dict, Any, List, Optional, Generator
import os
import time

# --- Configuration ---
st.set_page_config(
    page_title="Chat with Your Docs",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🤖"
)

# --- API URL Helpers ---
def get_api_url() -> str:
    return os.getenv("API_URL", "http://localhost:8000/api/v1")

def get_public_api_url() -> str:
    return os.getenv("PUBLIC_API_URL", "http://localhost:8000/api/v1")

API_URL = get_api_url()
PUBLIC_API_URL = get_public_api_url()

# --- Model Selection Options ---
MODEL_OPTIONS = {
    "groq": {
        "Llama 3 8B": "llama3-8b-8192",
        "Llama 3 70B": "llama3-70b-8192",
        "Mixtral 8x7B": "mixtral-8x7b-32768",
        "Gemma 7B": "gemma-7b-it",
    },
    "ollama": {
        "Llama 3": "llama3",
        "Gemma": "gemma",
        "Phi-3": "phi3",
        "Mistral": "mistral",
    }
}

# --- Authentication & Session Management ---

def initialize_session_state():
    """Initializes all required keys in the session state to prevent errors."""
    defaults = {
        "logged_in": False,
        "username": "Guest",
        "token": None,
        "projects": [],
        "current_project_id": None,
        "current_project_name": None,
        "current_chat_id": None,
        "messages": {}, # {chat_id: [messages]}
        "new_project_provider": "groq",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def handle_oauth_token():
    if "token" in st.query_params:
        token = st.query_params["token"]
        st.query_params.clear() 
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = requests.get(f"{API_URL}/auth/users/me", headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                st.session_state.token = token
                st.session_state.username = user_data.get("full_name") or user_data.get("username", "User")
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Login failed: Invalid token received from provider.")
        except requests.RequestException as e:
            st.error(f"Login failed: Could not connect to API to validate token. {e}")

def login_user(username: str, password: str) -> bool:
    try:
        response = requests.post(f"{API_URL}/auth/token", data={"username": username, "password": password})
        if response.status_code == 200:
            token = response.json()["access_token"]
            st.session_state.token = token
            headers = {"Authorization": f"Bearer {token}"}
            user_res = requests.get(f"{API_URL}/auth/users/me", headers=headers)
            if user_res.status_code == 200:
                user_data = user_res.json()
                st.session_state.username = user_data.get("full_name") or user_data.get("username", "User")
            else:
                st.session_state.username = username
            st.session_state.logged_in = True
            return True
        else:
            st.error(f"Login failed: {response.json().get('detail', 'Invalid credentials')}")
            return False
    except requests.RequestException as e:
        st.error(f"Connection to API failed: {e}")
        return False

def signup_user(username: str, email: str, password: str) -> bool:
    try:
        payload = {"username": username, "email": email, "password": password}
        response = requests.post(f"{API_URL}/auth/signup", json=payload)
        if response.status_code == 201:
            st.success("Signup successful! Please log in.")
            return True
        else:
            st.error(f"Signup failed: {response.json().get('detail', 'Unknown error')}")
            return False
    except requests.RequestException as e:
        st.error(f"Connection to API failed: {e}")
        return False

def logout_user():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    initialize_session_state()
    st.query_params.clear()
    st.query_params["logout"] = "true"
    st.rerun()

def auth_page():
    if "logout" in st.query_params:
        st.success("You have been logged out successfully.")
        st.query_params.clear()
    st.title("🤖 Chat with Your Docs")
    st.markdown("Unlock insights from your documents using AI. **Log in or create an account to get started.**")
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                if login_user(username, password):
                    st.rerun()
        st.divider()
        st.markdown("Or sign in with a single click:")
        google_login_url = f"{PUBLIC_API_URL}/auth/login/google"
        st.link_button("Sign in with Google", google_login_url, use_container_width=True)
        st.button("Sign in with Apple (Coming Soon)", use_container_width=True, disabled=True)
    with col2:
        st.subheader("Create an Account")
        with st.form("signup_form"):
            new_username = st.text_input("Username", key="su_u")
            new_email = st.text_input("Email", key="su_e")
            new_password = st.text_input("Password", type="password", key="su_p")
            if st.form_submit_button("Sign Up", use_container_width=True):
                signup_user(new_username, new_email, new_password)

# --- API Helper Functions ---
def get_auth_headers(): 
    return {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}

def api_request(method, endpoint, timeout=60, **kwargs):
    try:
        res = requests.request(method, f"{API_URL}/{endpoint}", headers=get_auth_headers(), timeout=timeout, **kwargs)
        res.raise_for_status()
        return res
    except requests.exceptions.RequestException as e:
        detail = str(e)
        if e.response is not None:
            try:
                detail = e.response.json().get('detail', e.response.text)
            except (AttributeError, json.JSONDecodeError):
                pass
        st.error(f"API Error: {detail}")
        return None

# --- Main Application UI ---
def project_sidebar():
    st.sidebar.title(f"Welcome, {st.session_state.username}!")
    if (projects_res := api_request("GET", "projects/")):
        st.session_state.projects = projects_res.json()
    else:
        st.session_state.projects = []
        
    project_names = [p['name'] for p in st.session_state.projects]
    st.sidebar.header("Projects")
    if project_names:
        if st.session_state.current_project_name not in project_names:
            st.session_state.current_project_name = project_names[0] if project_names else None
            st.session_state.current_chat_id = None
        
        idx = project_names.index(st.session_state.current_project_name) if st.session_state.current_project_name in project_names else 0
        selected_name = st.sidebar.selectbox("Select Project", options=project_names, index=idx)
        
        if selected_name != st.session_state.current_project_name:
            st.session_state.current_project_name = selected_name
            st.session_state.current_chat_id = None
            st.rerun()
            
        current_project = next((p for p in st.session_state.projects if p['name'] == selected_name), {})
        st.session_state.current_project_id = current_project.get('id')
        provider = current_project.get('llm_provider','N/A').upper()
        model_name = current_project.get('llm_model_name', 'N/A')
        st.sidebar.caption(f"Provider: {provider} | Model: {model_name}")
    else:
        st.sidebar.info("Create a project to get started.")

    with st.sidebar.expander("Create New Project"):
        def provider_changed():
            st.session_state.new_project_provider = st.session_state._provider_selector
        provider = st.selectbox("LLM Provider", list(MODEL_OPTIONS.keys()), format_func=lambda x: f"{x.capitalize()} {'(Cloud)' if x=='groq' else '(Local)'}", key="_provider_selector", on_change=provider_changed)
        name = st.text_input("Project Name", key="new_proj_name")
        models = MODEL_OPTIONS.get(st.session_state.new_project_provider, {})
        model_name = st.selectbox("Select Model", list(models.keys()))
        if st.button("Create Project", use_container_width=True):
            if name and model_name:
                payload = {"name": name, "llm_provider": provider, "llm_model_name": models[model_name]}
                if res := api_request("POST", "projects/", json=payload):
                    st.session_state.current_project_name = res.json()['name']
                    st.rerun()

    st.sidebar.header("Profile")
    if st.sidebar.button("Logout", use_container_width=True):
        logout_user()

def chat_history_sidebar():
    st.sidebar.header("Chat History")
    if not st.session_state.current_project_id: return
    
    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        if st.button("➕ New Chat", use_container_width=True):
            st.session_state.current_chat_id = None
            st.rerun()
    with col2:
        if st.session_state.current_chat_id:
            if st.button("🗑️", use_container_width=True, help="Delete current chat"):
                api_request("DELETE", f"chat/sessions/{st.session_state.current_project_id}/{st.session_state.current_chat_id}")
                st.session_state.current_chat_id = None
                st.rerun()

    if sessions_res := api_request("GET", f"chat/sessions/{st.session_state.current_project_id}"):
        for session in sessions_res.json():
            is_selected = st.session_state.current_chat_id == session['id']
            button_type = "primary" if is_selected else "secondary"
            if st.sidebar.button(session['title'], key=f"session_{session['id']}", use_container_width=True, type=button_type):
                if not is_selected:
                    st.session_state.current_chat_id = session['id']
                    st.rerun()

def get_chat_messages(project_id, chat_id):
    if res := api_request("GET", f"chat/sessions/{project_id}/{chat_id}"):
        return res.json()['messages']
    return []



def chat_pane():
    st.header(f"Project: {st.session_state.current_project_name}")

    if 'messages' not in st.session_state:
        st.session_state.messages = {}

    if st.session_state.current_chat_id and st.session_state.current_chat_id not in st.session_state.messages:
        st.session_state.messages[st.session_state.current_chat_id] = get_chat_messages(
            st.session_state.current_project_id, st.session_state.current_chat_id
        )

    for msg in st.session_state.messages.get(st.session_state.current_chat_id, []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    def stream_handler(prompt: str) -> Generator[Dict[str, Any], None, None]:
        payload = {"query": prompt, "chat_id": st.session_state.current_chat_id}
        url = f"{API_URL}/chat/stream/{st.session_state.current_project_id}"
        
        try:
            with requests.post(url, json=payload, headers=get_auth_headers(), stream=True, timeout=300) as response:
                response.raise_for_status()
                event_type = None
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("event:"):
                            event_type = decoded_line[len("event:"):].strip()
                        elif decoded_line.startswith("data:"):
                            data_json = decoded_line[len("data:"):].strip()
                            if data_json and event_type:
                                yield {
                                    "event": event_type,
                                    "data": json.loads(data_json)
                                }
                                event_type = None 
        except requests.RequestException as e:
            st.error(f"Failed to connect to streaming API: {e}")
            yield {"event": "error", "data": "Connection to API failed."}
        except json.JSONDecodeError:
            st.warning("Could not decode stream data.")
            yield {"event": "error", "data": "Invalid data received from stream."}

    if prompt := st.chat_input("Ask a question about your documents..."):
        with st.chat_message("user"):
            st.markdown(prompt)

        st.session_state.messages.setdefault(st.session_state.current_chat_id, []).append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant"):
            with st.expander("Sources", expanded=True):
                sources_placeholder = st.empty()
                sources_placeholder.info("Retrieving sources...")
            response_placeholder = st.empty()
            full_response = ""
            is_new_chat = not st.session_state.current_chat_id

            for event in stream_handler(prompt):
                event_type = event.get("event")
                data = event.get("data")

                if event_type == "start":
                    new_chat_id = data.get('chat_id')
                    if is_new_chat and new_chat_id:
                        st.session_state.messages[new_chat_id] = st.session_state.messages.pop(None, [])
                        st.session_state.current_chat_id = new_chat_id
                
                elif event_type == "sources":
                    sources_placeholder.empty()
                    with sources_placeholder.container():
                        for i, src in enumerate(data):
                            st.info(f"**Source {i+1}: {src.get('source', 'N/A')}**\n\n---\n\n{src.get('content', '')}")
                
                elif event_type == "token":
                    full_response += data
                    response_placeholder.markdown(full_response + "▌")
                
                elif event_type == "error":
                    st.error(data)
            
            response_placeholder.markdown(full_response)
        
        if st.session_state.current_chat_id:
            st.session_state.messages[st.session_state.current_chat_id].append({"role": "assistant", "content": full_response})

        if is_new_chat:
            st.rerun()

def document_manager_pane():
    st.header(f"Manage Documents for '{st.session_state.current_project_name}'")
    c1, c2 = st.columns(2)
    with c1:
        with st.expander("Upload New Documents", expanded=True):
            files = st.file_uploader("Upload files", type=["pdf", "docx", "txt", "md"], accept_multiple_files=True, key=f"uploader_{st.session_state.current_project_id}")
            if files and st.button("Upload Files", use_container_width=True):
                count = sum(1 for f in files if api_request("POST", f"documents/upload/{st.session_state.current_project_id}", files={'file': (f.name, f.getvalue(), f.type)}))
                if count > 0: 
                    st.success(f"{count}/{len(files)} files uploaded. Processing started.")
                    st.cache_data.clear() 
                    st.rerun()

    with c2:
        with st.expander("Add Document from URL", expanded=True):
            url = st.text_input("Enter a URL", key=f"url_input_{st.session_state.current_project_id}")
            if url and st.button("Add URL", use_container_width=True):
                if api_request("POST", f"documents/upload_url/{st.session_state.current_project_id}", json={"url": url}):
                    st.success(f"URL added. Processing started.")
                    st.cache_data.clear() 
                    st.rerun()

    st.markdown("---")
    st.subheader("Project Documents")
    
    placeholder = st.empty()
    
    @st.cache_data(ttl=5) 
    def get_documents(project_id):
        if res := api_request("GET", f"documents/{project_id}"):
            return res.json()
        return []

    docs = get_documents(st.session_state.current_project_id)
    is_processing = any(doc.get('status') in ['PENDING', 'PROCESSING'] for doc in docs)

    with placeholder.container():
        if not docs:
            st.info("No documents have been added to this project yet.")
        else:
            for doc in docs:
                status = doc.get('status', 'UNKNOWN')
                icon = {"PENDING": "⚪️", "PROCESSING": "⏳", "COMPLETED": "✅", "FAILED": "❌"}.get(status, "❓")
                c1, c2 = st.columns([4, 1])
                c1.text(f"{icon} {doc.get('file_name', 'N/A')}")
                if c2.button("Delete", key=f"del_{doc['id']}", use_container_width=True):
                    if api_request("DELETE", f"documents/{st.session_state.current_project_id}/{doc['id']}"):
                        st.cache_data.clear()
                        st.rerun()
    if is_processing:
        time.sleep(5)
        st.rerun()

def main_app():
    st.sidebar.image("https://www.onepointltd.com/wp-content/uploads/2020/03/inno2.png")
    project_sidebar()
    if st.session_state.current_project_id:
        chat_history_sidebar()
        main, docs = st.columns([2, 1])
        with main:
            chat_pane()
        with docs:
            document_manager_pane()
    else:
        st.info("Please create or select a project from the sidebar to begin.")

if __name__ == "__main__":
    initialize_session_state()
    handle_oauth_token()
    if st.session_state.logged_in:
        main_app()
    else:
        auth_page()