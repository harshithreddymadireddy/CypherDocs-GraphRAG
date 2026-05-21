import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")
    
    # Google Gemini API configurations
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # Models
    # 'gemini-embedding-2' is standard for Gemini embeddings in this environment
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
    # 'gemini-2.5-flash' is fast and supports structured JSON schema outputs
    GENERATIVE_MODEL = os.getenv("GENERATIVE_MODEL", "gemini-2.5-flash")
    
    # Ingestion Parameters
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
    
    # Platform Settings
    PORT = int(os.getenv("PORT", "8000"))
    HOST = os.getenv("HOST", "0.0.0.0")

config = Config()
