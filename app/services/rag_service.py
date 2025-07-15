import tempfile
import json
import hashlib
import redis
from typing import List, Tuple, Dict, Any, Optional, AsyncGenerator
import httpx
import chromadb
import pickle
import io
from langchain_community.document_loaders import (
    PyPDFLoader, UnstructuredURLLoader, UnstructuredWordDocumentLoader,
    UnstructuredMarkdownLoader, TextLoader, UnstructuredFileLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.schema.runnable import Runnable
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain.prompts import ChatPromptTemplate
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.services import storage_service
from app.db.models import Project, User
import logging

logger = logging.getLogger(__name__)

def _ensure_ollama_model_is_available(model_name: str):
    if not settings.OLLAMA_HOST: return
    try:
        client = httpx.Client(base_url=settings.OLLAMA_HOST, timeout=60.0)
        response = client.get("/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        model_base_name = model_name.split(':')[0]
        model_exists = any(m['name'].split(':')[0] == model_base_name for m in models)
        if model_exists: return
        logger.info(f"Ollama model '{model_name}' not found. Pulling it now...")
        pull_response = client.post("/api/pull", json={"name": model_name, "stream": False}, timeout=None)
        pull_response.raise_for_status()
        logger.info(f"Successfully pulled Ollama model '{model_name}'.")
    except Exception as e:
        logger.error(f"Failed to ensure Ollama model '{model_name}' is available: {e}", exc_info=True)
        raise

class RAGService:
    def __init__(self, user: User, project: Project):
        self.user = user
        self.project = project
        self.collection_name = f"proj_{str(project.id).replace('-', '')}"
        
        self.embedding_function = GoogleGenerativeAIEmbeddings(model=settings.EMBEDDING_MODEL_NAME)

        llm_model_name = self.project.llm_model_name
        if self.project.llm_provider == "ollama" and settings.OLLAMA_HOST:
            self.llm = ChatOllama(base_url=settings.OLLAMA_HOST, model=llm_model_name, temperature=0.2)
        else:
            self.llm = ChatGroq(groq_api_key=settings.GROQ_API_KEY, model_name=llm_model_name, temperature=0.2)
            
        try:
            self.redis_client: redis.Redis = redis.from_url(settings.CELERY_BROKER_URL)
            self.redis_client.ping()
        except Exception:
            self.redis_client = None

        chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PATH, settings=ChromaSettings(anonymized_telemetry=False))
        self.vectorstore = Chroma(client=chroma_client, collection_name=self.collection_name, embedding_function=self.embedding_function)

    def _get_bm25_retriever_storage_key(self) -> str:
        """Returns the MinIO storage key for the project's BM25 retriever."""
        return f"_internal/{self.project.id}/bm25_retriever.pkl"

    def _get_loader(self, file_path, file_type, url=None):
        if url: return UnstructuredURLLoader(urls=[url], headers={"User-Agent": "Mozilla/5.0"})
        if file_type == "application/pdf": return PyPDFLoader(file_path)
        if file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document": return UnstructuredWordDocumentLoader(file_path)
        if file_type == "text/markdown": return UnstructuredMarkdownLoader(file_path)
        if file_type.startswith("text/"): return TextLoader(file_path)
        logger.warning(f"Unknown file type '{file_type}'. Using generic UnstructuredFileLoader as fallback.")
        return UnstructuredFileLoader(file_path)

    def _invalidate_query_cache(self):
        """Invalidates all query caches related to a project."""
        if not self.redis_client: return
        try:
            rag_query_keys = [k.decode('utf-8') for k in self.redis_client.scan_iter(f"rag_cache:{self.project.id}:*")]
            if rag_query_keys: self.redis_client.delete(*rag_query_keys)
            logger.info(f"Invalidated query caches for project {self.project.id}.")
        except Exception as e:
            logger.error(f"Failed to clear Redis query cache for project {self.project.id}: {e}", exc_info=True)

    def process_document(self, storage_key, file_type, file_name, document_id, url=None):
        if self.project.llm_provider == "ollama":
            _ensure_ollama_model_is_available(self.project.llm_model_name)
            
        logger.info(f"Processing document: {file_name}")
        if url:
            docs = self._get_loader(None, file_type, url=url).load()
        else:
            with tempfile.NamedTemporaryFile(delete=True, suffix=f"_{file_name}") as tmp:
                storage_service.download_file(storage_key, tmp.name)
                docs = self._get_loader(tmp.name, file_type).load()
        
        if not docs: return
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
        chunks = text_splitter.split_documents(docs)
        if not chunks: return

        for chunk in chunks:
            chunk.metadata['document_id'] = document_id
            chunk.metadata.setdefault('source', url or file_name)

        self.vectorstore.add_documents(documents=chunks)
        self._invalidate_query_cache()
        logger.info(f"Added {len(chunks)} chunks for document {document_id}. Caches invalidated.")
    
    def delete_document_chunks(self, document_id: str):
        logger.info(f"Preparing to delete chunks for document_id: {document_id}")
        try:
            collection = self.vectorstore._collection
            chunks_to_delete = collection.get(where={"document_id": document_id}, include=[])
            ids_to_delete = chunks_to_delete['ids']

            if not ids_to_delete:
                logger.info(f"No chunks found for document_id: {document_id}. Nothing to delete.")
                return

            logger.info(f"Found {len(ids_to_delete)} chunks to delete. Deleting now...")
            self.vectorstore.delete(ids=ids_to_delete)
            self._invalidate_query_cache()
            logger.info(f"Successfully deleted chunks for doc {document_id} and invalidated query caches.")
        except Exception as e:
            logger.error(f"Error during chunk deletion for document {document_id}: {e}", exc_info=True)

    def _get_all_project_docs_from_chroma(self) -> List[Document]:
        """Loads all documents for a project from ChromaDB."""
        try:
            logger.info(f"Loading all project documents from ChromaDB for project {self.project.id}...")
            results = self.vectorstore.get(include=["metadatas", "documents"])
            all_docs = [Document(page_content=text, metadata=meta or {}) for text, meta in zip(results['documents'] or [], results['metadatas'] or [])]
            logger.info(f"Loaded {len(all_docs)} documents from ChromaDB.")
            return all_docs
        except Exception as e:
            logger.error(f"Failed to load all project documents from Chroma: {e}", exc_info=True)
            return []

    def rebuild_and_persist_bm25_index(self):
        """Rebuilds the BM25 index from all docs in Chroma and saves it to MinIO."""
        logger.info(f"BM25_TASK: Starting BM25 index rebuild for project {self.project.id}")
        all_docs = self._get_all_project_docs_from_chroma()
        storage_key = self._get_bm25_retriever_storage_key()

        if not all_docs:
            logger.warning(f"BM25_TASK: No documents found for project {self.project.id}. Deleting any existing BM25 index.")
            storage_service.delete_file(storage_key)
            return

        logger.info(f"BM25_TASK: Building new index from {len(all_docs)} documents.")
        bm25_retriever = BM25Retriever.from_documents(all_docs, k=5)
        pickled_retriever = pickle.dumps(bm25_retriever)
        
        if storage_service.upload_in_memory_object(storage_key, pickled_retriever):
            logger.info(f"BM25_TASK: Successfully rebuilt and persisted BM25 index to MinIO.")
        else:
            logger.error(f"BM25_TASK: FAILED to upload persisted BM25 index to MinIO.")

    def _load_bm25_retriever(self) -> Optional[BM25Retriever]:
        """Loads the persisted BM25Retriever from MinIO."""
        storage_key = self._get_bm25_retriever_storage_key()
        logger.info(f"QUERY_TIME: Attempting to load BM25 index from MinIO: {storage_key}")
        try:
            retriever_bytes = storage_service.download_in_memory_object(storage_key)
            if retriever_bytes:
                logger.info(f"QUERY_TIME: Successfully loaded BM25 index from MinIO.")
                return pickle.loads(retriever_bytes)
        except Exception as e:
            logger.error(f"QUERY_TIME: Could not load/unpickle BM25 index: {e}", exc_info=True)
        
        logger.warning(f"QUERY_TIME: BM25 index not found or failed to load. Query will rely on vector search only.")
        return None

    def _get_retriever(self) -> Runnable:
        """Constructs the final retriever, loading the persisted BM25 index."""
        bm25_retriever = self._load_bm25_retriever()
        vector_retriever = self.vectorstore.as_retriever(search_kwargs={"k": 5})

        if bm25_retriever:
            return EnsembleRetriever(retrievers=[bm25_retriever, vector_retriever], weights=[0.5, 0.5])
        else:
            return vector_retriever

    def _get_rag_chain(self) -> Runnable:
        """Creates the RAG chain for answering questions."""
        # --- ** THE FIX IS HERE ** ---
        # This simpler, more direct prompt is more robust and works better with smaller, local LLMs.
        prompt_template = """
Answer the question based *only* on the following context.
If the context does not contain the answer, say "The provided documents do not contain an answer to this question."

Context:
{context}

Question:
{question}
"""
        rag_prompt = ChatPromptTemplate.from_template(prompt_template)
        return rag_prompt | self.llm

    async def stream_query(self, message: str) -> Tuple[AsyncGenerator[str, None], List[Dict[str, Any]]]:
        """Handles a streaming query, yielding sources first, then LLM tokens."""
        retriever = self._get_retriever()
        rag_chain = self._get_rag_chain()
        
        hyde_prompt = ChatPromptTemplate.from_template("Write a short hypothetical doc for this question: {question}")
        hypothetical_doc_runnable = hyde_prompt | self.llm
        hypothetical_doc = await hypothetical_doc_runnable.ainvoke({"question": message})
        
        final_docs = await retriever.ainvoke(hypothetical_doc.content)
        
        if not final_docs:
            async def empty_generator():
                yield "I couldn't find relevant information in your documents to answer the query."
            return empty_generator(), []

        context_text = "\n\n---\n\n".join([doc.page_content for doc in final_docs])
        
        unique_sources: Dict[str, Dict[str, Any]] = {}
        for doc in final_docs:
            source_info = {"content": doc.page_content, "source": doc.metadata.get("source", "Unknown")}
            unique_sources[doc.page_content] = source_info
        
        sources = list(unique_sources.values())
        
        response_generator = (chunk.content async for chunk in rag_chain.astream({"context": context_text, "question": message}))
        
        return response_generator, sources

    def query(self, message: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Handles a non-streaming query."""
        cache_key = f"rag_cache:{self.project.id}:{hashlib.sha256(message.encode()).hexdigest()}"
        if self.redis_client and (cached_result := self.redis_client.get(cache_key)):
            return json.loads(cached_result)['answer'], json.loads(cached_result)['sources']

        retriever = self._get_retriever()
        rag_chain = self._get_rag_chain()

        hyde_prompt = ChatPromptTemplate.from_template("Write a short hypothetical doc for this question: {question}")
        hypothetical_doc = (hyde_prompt | self.llm).invoke({"question": message}).content
        final_docs = retriever.invoke(hypothetical_doc)
        
        if not final_docs:
            return "I couldn't find relevant information in your documents to answer the query.", []

        context_text = "\n\n---\n\n".join([doc.page_content for doc in final_docs])
        answer = rag_chain.invoke({"context": context_text, "question": message}).content
        
        unique_sources: Dict[str, Dict[str, Any]] = {}
        for doc in final_docs:
            source_info = {"content": doc.page_content, "source": doc.metadata.get("source", "Unknown")}
            unique_sources[doc.page_content] = source_info
        
        sources = list(unique_sources.values())
        
        if self.redis_client:
            result_to_cache = {"answer": answer, "sources": sources}
            self.redis_client.set(cache_key, json.dumps(result_to_cache), ex=3600)

        return answer, sources