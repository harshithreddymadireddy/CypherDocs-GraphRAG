import sys
import os
import time
import logging
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.neo4j_client import Neo4jClient
from app.extractor import GraphRAGExtractor
from app.rag_engine import GraphRAGEngine

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def test_connectivity():
    logger.info("Initializing Neo4j Client...")
    db = Neo4jClient()
    try:
        db.connect()
        logger.info("Successfully connected to Neo4j database!")
        
        logger.info("Initializing constraints and index...")
        db.init_db()
        
        logger.info("Database Stats before verification:")
        stats = db.get_db_stats()
        logger.info(f"Stats: {stats}")
        return db
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        db.close()
        return None

def test_pipeline(db):
    logger.info("Testing document and graph ingestion...")
    
    # 1. Insert Document
    doc_id = "test-doc-123"
    db.create_document(doc_id, "test_verification_report.txt")
    
    # 2. Insert Chunk
    chunk_id = f"{doc_id}_chunk_0"
    text = "ACME Corporation, led by CEO John Doe, signed a compliance agreement with the regulatory agency SEC in 2026."
    
    # Dummy embedding (768 dimensional)
    dummy_embedding = [0.01] * 768
    db.insert_chunk(doc_id, chunk_id, 0, text, dummy_embedding)
    logger.info("Chunk inserted.")

    # 3. Insert Entities
    db.insert_entity(chunk_id, "ACME Corporation", "ORGANIZATION", "A global enterprise manufacturing widgets.")
    db.insert_entity(chunk_id, "John Doe", "PERSON", "The CEO of ACME Corporation.")
    db.insert_entity(chunk_id, "SEC", "ORGANIZATION", "The Securities and Exchange Commission, a regulatory agency.")
    logger.info("Entities inserted.")

    # 4. Insert Relationships
    db.insert_relationship(chunk_id, "John Doe", "PERSON", "ACME Corporation", "ORGANIZATION", "EMPLOYED_BY", "John Doe is the CEO of ACME.")
    db.insert_relationship(chunk_id, "ACME Corporation", "ORGANIZATION", "SEC", "ORGANIZATION", "REGULATED_BY", "ACME signed a compliance agreement with the SEC.")
    logger.info("Relationships inserted.")
    
    db.update_document_status(doc_id, "completed")
    logger.info("Document status set to completed.")

    # 5. Verify database counts increased
    stats = db.get_db_stats()
    logger.info(f"Stats after ingestion: {stats}")
    if stats["document_count"] > 0 and stats["entity_count"] >= 3:
        logger.info("Database verification check: SUCCESS!")
    else:
        logger.error("Database verification check: FAILED. Expected counts were not met.")
        return False
        
    # 6. Retrieve visualization subgraph
    subgraph = db.get_visualization_subgraph(5)
    logger.info(f"Retrieved subgraph sample: {subgraph}")
    
    # 7. Test Vector search (using same dummy embedding)
    vector_results = db.search_vector(dummy_embedding, top_k=2)
    logger.info(f"Vector search results: {vector_results}")
    
    # 8. Test Graph Traversal
    graph_context = db.get_graph_context_for_chunks([chunk_id])
    logger.info(f"Graph context results: {graph_context}")
    
    return True

if __name__ == "__main__":
    logger.info("Starting GraphRAG verification suite...")
    
    load_dotenv()
    
    db = test_connectivity()
    if not db:
        logger.error("Could not run verification: Neo4j is offline.")
        sys.exit(1)
        
    success = test_pipeline(db)
    db.close()
    
    if success:
        logger.info("All local backend functionality verified successfully!")
        sys.exit(0)
    else:
        logger.error("Verification pipeline encountered errors.")
        sys.exit(1)
