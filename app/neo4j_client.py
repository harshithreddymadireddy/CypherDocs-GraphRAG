from neo4j import GraphDatabase
import logging
from typing import List, Dict, Any, Tuple
from app.config import config

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self):
        self.uri = config.NEO4J_URI
        self.user = config.NEO4J_USER
        self.password = config.NEO4J_PASSWORD
        self.driver = None
        
    def connect(self):
        if not self.driver:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            logger.info("Connected to Neo4j database")
            
    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
            logger.info("Closed Neo4j driver connection")
            
    def query(self, cypher: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        self.connect()
        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def init_db(self):
        """Initialize constraints and vector indexes."""
        self.connect()
        
        # 1. Create uniqueness constraints for Document, Chunk, and Entity
        constraints = [
            "CREATE CONSTRAINT unique_document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT unique_chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT unique_entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE (e.name, e.type) IS UNIQUE"
        ]
        
        for constraint in constraints:
            try:
                self.query(constraint)
                logger.info(f"Initialized constraint: {constraint}")
            except Exception as e:
                logger.warning(f"Error creating constraint: {e}")
                
        # 2. Create Vector Index for Chunk nodes on the 'embedding' property
        # Default dimensions for Gemini's text-embedding-004 is 768.
        vector_index_cypher = """
        CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
        FOR (c:Chunk) ON (c.embedding)
        OPTIONS {indexConfig: {
            `vector.dimensions`: 768,
            `vector.similarity_function`: 'cosine'
        }}
        """
        try:
            self.query(vector_index_cypher)
            logger.info("Initialized vector index 'chunk_embeddings'")
        except Exception as e:
            logger.error(f"Failed to create vector index: {e}")

    def create_document(self, doc_id: str, filename: str, metadata: Dict[str, Any] = None):
        """Creates a Document node."""
        cypher = """
        MERGE (d:Document {id: $doc_id})
        ON CREATE SET d.filename = $filename, d.created_at = timestamp(), d.status = 'processing'
        ON MATCH SET d.status = 'processing'
        """
        self.query(cypher, {"doc_id": doc_id, "filename": filename})

    def update_document_status(self, doc_id: str, status: str, error_message: str = None):
        """Updates the status of a document."""
        cypher = """
        MATCH (d:Document {id: $doc_id})
        SET d.status = $status, d.error = $error_message, d.updated_at = timestamp()
        """
        self.query(cypher, {"doc_id": doc_id, "status": status, "error_message": error_message})

    def insert_chunk(self, doc_id: str, chunk_id: str, index: int, text: str, embedding: List[float]):
        """Inserts a Chunk node and connects it to its parent Document."""
        cypher = """
        MATCH (d:Document {id: $doc_id})
        MERGE (c:Chunk {id: $chunk_id})
        ON CREATE SET 
            c.text = $text, 
            c.index = $index, 
            c.embedding = $embedding,
            c.doc_id = $doc_id
        MERGE (d)-[:HAS_CHUNK]->(c)
        """
        self.query(cypher, {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "index": index,
            "text": text,
            "embedding": embedding
        })

    def insert_entity(self, chunk_id: str, name: str, entity_type: str, description: str):
        """Creates an Entity node if it doesn't exist, and links it to a Chunk."""
        cypher = """
        MERGE (e:Entity {name: $name, type: $entity_type})
        ON CREATE SET e.description = $description, e.created_at = timestamp()
        ON MATCH SET e.description = coalesce(e.description, $description)
        
        WITH e
        MATCH (c:Chunk {id: $chunk_id})
        MERGE (c)-[:MENTIONS]->(e)
        """
        self.query(cypher, {
            "chunk_id": chunk_id,
            "name": name,
            "entity_type": entity_type.upper(),
            "description": description
        })

    def insert_relationship(self, chunk_id: str, source_name: str, source_type: str, 
                            target_name: str, target_type: str, rel_type: str, description: str):
        """Creates a relationship between two Entity nodes, annotated with the source chunk ID."""
        # Sanitize rel_type for Neo4j naming rules (alphanumeric and underscores)
        rel_type_clean = "".join([c if c.isalnum() else "_" for c in rel_type]).upper()
        if not rel_type_clean or rel_type_clean[0].isdigit():
            rel_type_clean = "RELATED_TO"

        # Check if APOC is available to create dynamic relationship type.
        # Otherwise, fall back to a generic 'RELATED_TO' type with a property.
        cypher_check_apoc = "RETURN apoc.version() AS version"
        has_apoc = False
        try:
            res = self.query(cypher_check_apoc)
            if res:
                has_apoc = True
        except Exception:
            pass

        if has_apoc:
            # APOC dynamic relationship creation
            cypher = f"""
            MATCH (source:Entity {{name: $source_name, type: $source_type}})
            MATCH (target:Entity {{name: $target_name, type: $target_type}})
            
            // Create relationship or update properties
            CALL apoc.merge.relationship(source, $rel_type_clean, {{}}, {{description: $description}}, target) YIELD rel
            
            // Add chunk reference to the relationship
            SET rel.chunk_ids = apoc.coll.toSet(coalesce(rel.chunk_ids, []) + $chunk_id)
            """
        else:
            # Fallback Cypher when APOC is not installed/enabled
            cypher = """
            MATCH (source:Entity {name: $source_name, type: $source_type})
            MATCH (target:Entity {name: $target_name, type: $target_type})
            
            MERGE (source)-[r:RELATED_TO {type: $rel_type_clean}]->(target)
            ON CREATE SET r.description = $description, r.chunk_ids = [$chunk_id]
            ON MATCH SET 
                r.description = coalesce(r.description, $description),
                r.chunk_ids = CASE WHEN NOT $chunk_id IN r.chunk_ids THEN r.chunk_ids + $chunk_id ELSE r.chunk_ids END
            """

        self.query(cypher, {
            "chunk_id": chunk_id,
            "source_name": source_name,
            "source_type": source_type.upper(),
            "target_name": target_name,
            "target_type": target_type.upper(),
            "rel_type_clean": rel_type_clean,
            "description": description
        })

    def search_vector(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve most similar Chunk nodes based on embedding similarity."""
        cypher = """
        CALL db.index.vector.queryNodes('chunk_embeddings', $top_k, $query_embedding)
        YIELD node, score
        RETURN node.id AS id, node.text AS text, node.doc_id AS doc_id, score
        """
        try:
            return self.query(cypher, {"query_embedding": query_embedding, "top_k": top_k})
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def get_graph_context_for_chunks(self, chunk_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Traverse the graph: find entities mentioned in the chunks, and retrieve 
        their local relationships up to 1 hop.
        """
        cypher = """
        MATCH (c:Chunk) WHERE c.id IN $chunk_ids
        MATCH (c)-[:MENTIONS]->(e:Entity)
        
        // Find 1-hop relationships for these entities
        MATCH (e)-[r]->(target:Entity)
        RETURN 
            e.name AS source_name, 
            e.type AS source_type, 
            type(r) AS rel_type, 
            coalesce(r.description, '') AS description,
            target.name AS target_name, 
            target.type AS target_type
        LIMIT 50
        """
        return self.query(cypher, {"chunk_ids": chunk_ids})

    def get_all_documents(self) -> List[Dict[str, Any]]:
        cypher = """
        MATCH (d:Document)
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        RETURN 
            d.id AS id, 
            d.filename AS filename, 
            d.status AS status, 
            coalesce(d.error, null) AS error,
            d.created_at AS created_at,
            count(c) AS chunk_count
        ORDER BY d.created_at DESC
        """
        return self.query(cypher)

    def get_db_stats(self) -> Dict[str, Any]:
        """Returns node and edge counts for analytics dashboard."""
        stats = {
            "document_count": 0,
            "chunk_count": 0,
            "entity_count": 0,
            "relationship_count": 0,
            "entity_types": {},
            "relationship_types": {}
        }
        try:
            # 1. Total counts
            counts_cypher = """
            CALL {
                MATCH (d:Document) RETURN count(d) AS doc_count
            }
            CALL {
                MATCH (c:Chunk) RETURN count(c) AS chunk_count
            }
            CALL {
                MATCH (e:Entity) RETURN count(e) AS entity_count
            }
            CALL {
                MATCH ()-[r]->() 
                // Exclude HAS_CHUNK and MENTIONS to count semantic entity relationships
                WHERE NOT type(r) IN ['HAS_CHUNK', 'MENTIONS']
                RETURN count(r) AS rel_count
            }
            RETURN doc_count, chunk_count, entity_count, rel_count
            """
            counts_res = self.query(counts_cypher)
            if counts_res:
                r = counts_res[0]
                stats["document_count"] = r.get("doc_count", 0)
                stats["chunk_count"] = r.get("chunk_count", 0)
                stats["entity_count"] = r.get("entity_count", 0)
                stats["relationship_count"] = r.get("rel_count", 0)

            # 2. Entity types breakdown
            entity_types_res = self.query("""
                MATCH (e:Entity) 
                RETURN e.type AS type, count(e) AS count 
                ORDER BY count DESC
            """)
            for record in entity_types_res:
                t = record.get("type", "UNKNOWN")
                stats["entity_types"][t] = record.get("count", 0)

            # 3. Relationship types breakdown
            rel_types_res = self.query("""
                MATCH ()-[r]->() 
                WHERE NOT type(r) IN ['HAS_CHUNK', 'MENTIONS']
                RETURN type(r) AS type, count(r) AS count 
                ORDER BY count DESC
            """)
            for record in rel_types_res:
                t = record.get("type", "UNKNOWN")
                stats["relationship_types"][t] = record.get("count", 0)
        except Exception as e:
            logger.error(f"Error fetching DB stats: {e}")
            
        return stats

    def delete_document(self, doc_id: str):
        """Deletes a document, its chunks, and any orphaned entities/relationships."""
        self.connect()
        # 1. Delete chunk mentions, chunks, and document node
        cypher = """
        MATCH (d:Document {id: $doc_id})
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        
        // Detach chunk mentions
        WITH d, c
        OPTIONAL MATCH (c)-[m:MENTIONS]->(e:Entity)
        DELETE m
        
        // Delete chunks
        WITH d, c
        DETACH DELETE c
        
        // Delete document
        WITH d
        DETACH DELETE d
        """
        self.query(cypher, {"doc_id": doc_id})
        
        # 2. Clean up orphaned entities (entities not connected to any remaining chunk)
        cleanup_entities_cypher = """
        MATCH (e:Entity)
        WHERE NOT ()-[:MENTIONS]->(e)
        DETACH DELETE e
        """
        self.query(cleanup_entities_cypher)

        # 3. Clean up relationships whose referenced chunks are all deleted
        cleanup_rels_cypher = """
        MATCH (e1:Entity)-[r]->(e2:Entity)
        WHERE NOT type(r) IN ['HAS_CHUNK', 'MENTIONS']
        WITH r
        OPTIONAL MATCH (c:Chunk) WHERE c.id IN r.chunk_ids
        WITH r, count(c) AS active_chunks_count
        WHERE active_chunks_count = 0
        DELETE r
        """
        self.query(cleanup_rels_cypher)
        logger.info(f"Document {doc_id} and its associated elements have been deleted.")

    def get_visualization_subgraph(self, limit: int = 500, doc_id: str = None) -> Dict[str, Any]:
        """Fetch a subset of the graph for rendering in the ForceGraph UI."""
        if doc_id:
            # Nodes Cypher: only entities mentioned by chunks belonging to the document
            nodes_cypher = f"""
            MATCH (d:Document {{id: $doc_id}})-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity)
            RETURN DISTINCT elementId(e) AS id, e.name AS name, e.type AS type, e.description AS description
            LIMIT {limit}
            """
            nodes_res = self.query(nodes_cypher, {"doc_id": doc_id})
        else:
            # Global Nodes Cypher: get representative entities across all documents evenly
            nodes_cypher = f"""
            MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(e:Entity)
            WITH d, e, count(c) as weight
            ORDER BY d.id, weight DESC
            WITH d, collect(e)[0..100] as doc_entities
            UNWIND doc_entities as e
            RETURN DISTINCT elementId(e) AS id, e.name AS name, e.type AS type, e.description AS description
            LIMIT {limit}
            """
            nodes_res = self.query(nodes_cypher)
            
            # Fallback if no documents exist yet, but entities exist
            if not nodes_res:
                nodes_cypher = f"""
                MATCH (e:Entity)
                RETURN elementId(e) AS id, e.name AS name, e.type AS type, e.description AS description
                LIMIT {limit}
                """
                nodes_res = self.query(nodes_cypher)
        
        entity_ids = [n["id"] for n in nodes_res]
        
        if doc_id:
            # Relationships Cypher: only relationships between fetched nodes that are also linked to this doc
            rels_cypher = """
            MATCH (e1:Entity)-[r]->(e2:Entity)
            WHERE elementId(e1) IN $entity_ids AND elementId(e2) IN $entity_ids
              AND any(cid IN r.chunk_ids WHERE cid STARTS WITH $doc_id)
            RETURN 
                elementId(r) AS id,
                elementId(e1) AS source,
                elementId(e2) AS target,
                type(r) AS type,
                coalesce(r.description, '') AS description
            """
            rels_res = self.query(rels_cypher, {"entity_ids": entity_ids, "doc_id": doc_id})
        else:
            # Global Relationships Cypher (only between fetched nodes)
            rels_cypher = """
            MATCH (e1:Entity)-[r]->(e2:Entity)
            WHERE elementId(e1) IN $entity_ids AND elementId(e2) IN $entity_ids
            RETURN 
                elementId(r) AS id,
                elementId(e1) AS source,
                elementId(e2) AS target,
                type(r) AS type,
                coalesce(r.description, '') AS description
            """
            rels_res = self.query(rels_cypher, {"entity_ids": entity_ids})
        
        return {
            "nodes": [{"id": n["id"], "name": n["name"], "label": n["name"], "type": n["type"], "description": n["description"]} for n in nodes_res],
            "links": [{"id": r["id"], "source": r["source"], "target": r["target"], "type": r["type"], "description": r["description"]} for r in rels_res]
        }
