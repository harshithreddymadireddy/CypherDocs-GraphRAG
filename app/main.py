import logging
from typing import List
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import config
from app.neo4j_client import Neo4jClient
from app.extractor import GraphRAGExtractor
from app.rag_engine import GraphRAGEngine

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CypherDocs",
    description="Relationship-aware semantic retrieval platform combining Knowledge Graphs and Vector Search",
    version="1.0.0"
)

# Initialize singletons
db_client = Neo4jClient()
extractor = GraphRAGExtractor(db_client)
rag_engine = GraphRAGEngine(db_client, extractor)

@app.on_event("startup")
def startup_event():
    logger.info("Initializing GraphRAG Application...")
    try:
        db_client.init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")

@app.on_event("shutdown")
def shutdown_event():
    db_client.close()
    logger.info("Application shut down.")


# Background task for document processing
def process_document_task(filename: str, file_bytes: bytes):
    try:
        extractor.process_document(filename, file_bytes)
    except Exception as e:
        logger.error(f"Async document processing task failed for {filename}: {e}")


# API Endpoints
class QueryRequest(BaseModel):
    query: str

@app.post("/api/query")
async def query_rag(request: QueryRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        result = rag_engine.answer_query(request.query)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error executing hybrid query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/documents/upload")
async def upload_documents(files: List[UploadFile] = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
        
    uploaded_docs = []
    for file in files:
        try:
            content = await file.read()
            # Queue document ingestion as a background task to prevent request timeouts
            background_tasks.add_task(process_document_task, file.filename, content)
            uploaded_docs.append({"filename": file.filename, "status": "queued"})
        except Exception as e:
            logger.error(f"Failed to read upload file {file.filename}: {e}")
            uploaded_docs.append({"filename": file.filename, "status": "failed", "error": str(e)})
            
    return {"message": f"Successfully queued {len(uploaded_docs)} document(s) for processing.", "files": uploaded_docs}

@app.get("/api/documents")
async def get_documents():
    try:
        docs = db_client.get_all_documents()
        return JSONResponse(content={"documents": docs})
    except Exception as e:
        logger.error(f"Failed to fetch documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    try:
        db_client.delete_document(doc_id)
        return JSONResponse(content={"message": f"Document {doc_id} successfully deleted."})
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/graph/stats")
async def get_graph_stats():
    try:
        stats = db_client.get_db_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        logger.error(f"Failed to fetch graph statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/graph/subgraph")
async def get_subgraph(limit: int = 500, doc_id: str = None):
    try:
        subgraph = db_client.get_visualization_subgraph(limit=limit, doc_id=doc_id)
        return JSONResponse(content=subgraph)
    except Exception as e:
        logger.error(f"Failed to fetch subgraph data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Serve static web interface
@app.get("/")
async def serve_index():
    return FileResponse("app/static/index.html")

# Mount static directory for JS and CSS files
# Wait, make sure we mount it AFTER defining the base root to prevent conflicts
app.mount("/static", StaticFiles(directory="app/static"), name="static")
