import logging
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field

from app.config import config
from app.neo4j_client import Neo4jClient
from app.extractor import GraphRAGExtractor

logger = logging.getLogger(__name__)

# Pydantic schema to extract entities from user query
class QueryEntities(BaseModel):
    entities: List[str] = Field(default_factory=list, description="List of key entities (names of companies, people, regulations, etc.) mentioned in the query.")

class RAGAnswerResponse(BaseModel):
    answer: str = Field(..., description="The comprehensive answer generated using both the document text and graph relationships.")
    evidence_entities: List[str] = Field(default_factory=list, description="Key entities from the graph that supported this answer.")
    evidence_relations: List[str] = Field(default_factory=list, description="Key relationships from the graph that supported this answer.")


class GraphRAGEngine:
    def __init__(self, neo4j_client: Neo4jClient, extractor: GraphRAGExtractor):
        self.db = neo4j_client
        self.extractor = extractor
        
    def _extract_query_entities(self, query: str) -> List[str]:
        """Extracts named entities from the user query to guide graph traversal."""
        if not self.extractor.client:
            return []
            
        prompt = f"""
        Analyze the user's search query and extract any key named entities (people, organizations, products, laws, agreements, locations).
        Return them as a flat list.
        
        Query: "{query}"
        """
        try:
            response_text = self.extractor.execute_generative_with_fallback(
                contents=prompt,
                response_schema=QueryEntities,
                response_mime_type="application/json"
            )
            res = QueryEntities.model_validate_json(response_text)
            return res.entities
        except Exception as e:
            logger.error(f"Failed to extract entities from query: {e}")
            return []

    def _get_graph_context_by_entities(self, entities: List[str]) -> List[Dict[str, Any]]:
        """Finds relationships connected to entities extracted directly from the query."""
        if not entities:
            return []
            
        cypher = """
        MATCH (e:Entity) WHERE toLower(e.name) IN $entities
        MATCH (e)-[r]->(target:Entity)
        RETURN 
            e.name AS source_name, 
            e.type AS source_type, 
            type(r) AS rel_type, 
            coalesce(r.description, '') AS description,
            target.name AS target_name, 
            target.type AS target_type
        LIMIT 30
        """
        entities_lower = [ent.lower() for ent in entities]
        return self.db.query(cypher, {"entities": entities_lower})

    def _fallback_retrieve_context(self, query: str, top_k: int = 5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Fallback keyword-based search on Neo4j for chunks and entity/relationships
        when Gemini client is not initialized/configured.
        """
        import re
        logger.info(f"Using offline-first fallback retrieval for query: {query}")
        
        # Tokenize query to extract words, filter out stopwords
        words = re.findall(r'\b\w+\b', query.lower())
        stopwords = {
            'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', "you're", "you've", "you'll", "you'd",
            'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', "she's", 'her', 'hers',
            'herself', 'it', "it's", 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which',
            'who', 'whom', 'this', 'that', "that'll", 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if',
            'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between',
            'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out',
            'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why',
            'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
            'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', "don't", 'should',
            "should've", 'now', 'd', 'll', 'm', 'o', 're', 've', 'y', 'ain', 'aren', "aren't", 'couldn', "couldn't",
            'didn', "didn't", 'doesn', "doesn't", 'hadn', "hadn't", 'hasn', "hasn't", 'haven', "haven't", 'isn', "isn't",
            'ma', 'mightn', "mightn't", 'mustn', "mustn't", 'needn', "needn't", 'shan', "shan't", 'shouldn', "shouldn't",
            'wasn', "wasn't", 'weren', "weren't", 'won', "won't", 'wouldn', "wouldn't", 'which', 'who', 'what',
            'added', 'removed', 'nifty', 'nifty50', 'company', 'list', 'index', 'year', 'date', 'timeline', 'history',
            'show', 'find', 'get', 'give', 'tell', 'explain', 'who', 'what', 'which', 'when', 'how', 'many'
        }
        keywords = [w for w in words if w not in stopwords and len(w) >= 2]
        if not keywords:
            keywords = [w for w in words if len(w) >= 2]
            
        logger.info(f"Offline fallback keywords extracted: {keywords}")
        
        # 1. Retrieve chunks matching keywords
        if keywords:
            chunks_cypher = """
            MATCH (c:Chunk)
            WITH c, [word IN $keywords WHERE toLower(c.text) CONTAINS word] AS matched
            WHERE size(matched) > 0
            RETURN c.id AS id, c.text AS text, c.doc_id AS doc_id, toFloat(size(matched)) AS score
            ORDER BY score DESC
            LIMIT $top_k
            """
            chunks = self.db.query(chunks_cypher, {"keywords": keywords, "top_k": top_k})
        else:
            chunks_cypher = """
            MATCH (c:Chunk)
            RETURN c.id AS id, c.text AS text, c.doc_id AS doc_id, 1.0 AS score
            LIMIT $top_k
            """
            chunks = self.db.query(chunks_cypher, {"top_k": top_k})
            
        # 2. Retrieve graph context by matching entities containing keywords
        graph_from_query_entities = []
        if keywords:
            entities_cypher = """
            MATCH (e:Entity)
            WITH e, [word IN $keywords WHERE toLower(e.name) CONTAINS word] AS matched
            WHERE size(matched) > 0
            MATCH (e)-[r]->(target:Entity)
            RETURN 
                e.name AS source_name, 
                e.type AS source_type, 
                type(r) AS rel_type, 
                coalesce(r.description, '') AS description,
                target.name AS target_name, 
                target.type AS target_type
            LIMIT 30
            """
            graph_from_query_entities = self.db.query(entities_cypher, {"keywords": keywords})
            
        # 3. Get graph context for retrieved chunks
        chunk_ids = [c["id"] for c in chunks]
        graph_from_chunks = self.db.get_graph_context_for_chunks(chunk_ids)
        
        # 4. Merge graph relationships & deduplicate
        merged_rels = {}
        for rel in graph_from_query_entities + graph_from_chunks:
            key = (rel["source_name"], rel["rel_type"], rel["target_name"])
            merged_rels[key] = rel
            
        return chunks, list(merged_rels.values())

    def _generate_fallback_answer(self, query: str, chunks: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Synthesizes a beautifully formatted Markdown answer programmatically
        from the retrieved hybrid context when offline/no API key.
        """
        import re
        
        # Format chunks
        formatted_chunks = []
        for chunk in chunks:
            doc_name = chunk.get("doc_id", "Unknown")
            res = self.db.query("MATCH (d:Document {id: $doc_id}) RETURN d.filename AS filename", {"doc_id": chunk.get("doc_id")})
            if res:
                doc_name = res[0]["filename"]
            formatted_chunks.append({
                "id": chunk.get("id"),
                "text": chunk.get("text"),
                "document_name": doc_name,
                "score": chunk.get("score", 1.0)
            })

        # Find query words for keyword highlight/extract
        query_words = [w.lower() for w in re.findall(r'\b\w+\b', query) if len(w) > 2]
        
        # Extract facts from relationships
        kb_facts = []
        evidence_entities = set()
        evidence_relations = set()
        
        for rel in relationships:
            src = rel["source_name"]
            tgt = rel["target_name"]
            rtype = rel["rel_type"]
            desc = rel["description"]
            
            evidence_entities.add(src)
            evidence_entities.add(tgt)
            evidence_relations.add(rtype)
            
            desc_str = f" (*{desc}*)" if desc else ""
            kb_facts.append(f"- **{src}** ({rel['source_type']}) → `{rtype}` → **{tgt}** ({rel['target_type']}){desc_str}")

        # Extract relevant snippets from chunks
        snippets = []
        for fc in formatted_chunks:
            text = fc["text"]
            doc_name = fc["document_name"]
            
            # Split text into paragraphs/sentences to find the most relevant parts
            sentences = re.split(r'(?<=[.!?])\s+', text)
            relevant_sentences = []
            for s in sentences:
                s_lower = s.lower()
                if any(qw in s_lower for qw in query_words):
                    relevant_sentences.append(s.strip())
            
            if relevant_sentences:
                snippet = " ... ".join(relevant_sentences[:3])
            else:
                snippet = text[:250] + "..." if len(text) > 250 else text
                
            snippets.append(f"**From `{doc_name}`**:\n> {snippet}")

        # Synthesize markdown answer
        markdown_lines = []
        markdown_lines.append(f"### Search Results: \"{query}\"\n")
        markdown_lines.append("> [!NOTE]")
        markdown_lines.append("> CypherDocs is running in **Offline Mode** (no Gemini API Key configured or online call failed).")
        markdown_lines.append("> Synthesized answer generated using Graph RAG indexing with offline fallback retrieval.\n")
        
        # Core summary
        markdown_lines.append("#### Executive Summary")
        if kb_facts:
            adds = [f for f in kb_facts if "ADD" in f.upper()]
            removes = [f for f in kb_facts if "REMOVE" in f.upper()]
            
            summary_text = (
                f"Based on local database retrieval, we found **{len(relationships)} knowledge graph relationships** "
                f"and **{len(chunks)} relevant document passages** matching the terms in your query."
            )
            if adds or removes:
                summary_text += f" Specifically, detected **{len(adds)} additions** and **{len(removes)} removals** related to your query."
            markdown_lines.append(summary_text)
        else:
            if chunks:
                markdown_lines.append(
                    f"Found relevant information across **{len(chunks)} document passages** in the RAG corpus, "
                    "but no explicit semantic entities or relationships were resolved in the Knowledge Graph for these search terms."
                )
            else:
                markdown_lines.append(
                    "No relevant matches or relationships could be found in the database for the query terms. "
                    "Please make sure your files are uploaded and indexed."
                )
        
        # Knowledge Graph section
        if kb_facts:
            markdown_lines.append("\n#### Knowledge Graph Relationships")
            markdown_lines.append("The following relationships were resolved from the graph:")
            markdown_lines.extend(kb_facts[:15])  # limit to 15 relationships for readability
            if len(kb_facts) > 15:
                markdown_lines.append(f"- *... and {len(kb_facts) - 15} more relationships in the graph.*")
        
        # Document passages section
        if snippets:
            markdown_lines.append("\n#### Supporting Document Passages")
            markdown_lines.append("Excerpts from matching passages:")
            for snip in snippets[:3]:  # top 3 source snippets
                markdown_lines.append(snip + "\n")
                
        answer_text = "\n".join(markdown_lines)
        
        return {
            "answer": answer_text,
            "evidence_entities": list(evidence_entities),
            "evidence_relations": list(evidence_relations),
            "sources": formatted_chunks,
            "graph_relationships": relationships
        }

    def retrieve_hybrid_context(self, query: str, top_k: int = 5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Hybrid retrieval:
        1. Vector search to find top chunks
        2. Query entity extraction -> Graph search to find relationships
        3. Chunk entity reference -> Graph search to find relationships
        4. Merging and deduplicating graph relationships
        """
        # If Gemini API Key is missing or client is None, use fallback retrieval
        if not self.extractor.client:
            return self._fallback_retrieve_context(query, top_k)
            
        # Step 1: Vector Search for Chunks
        query_embedding = self.extractor.get_embedding(query)
        chunks = self.db.search_vector(query_embedding, top_k)
        
        # Step 2: Extract query entities & query graph
        query_entities = self._extract_query_entities(query)
        logger.info(f"Query entities extracted: {query_entities}")
        graph_from_query_entities = self._get_graph_context_by_entities(query_entities)
        
        # Step 3: Get graph context for vector-retrieved chunks
        chunk_ids = [c["id"] for c in chunks]
        graph_from_chunks = self.db.get_graph_context_for_chunks(chunk_ids)
        
        # Step 4: Merge graph relationships & deduplicate
        merged_rels = {}
        for rel in graph_from_query_entities + graph_from_chunks:
            key = (rel["source_name"], rel["rel_type"], rel["target_name"])
            merged_rels[key] = rel
            
        return chunks, list(merged_rels.values())

    def answer_query(self, query: str) -> Dict[str, Any]:
        """
        Retrieves hybrid context and runs the reasoner LLM to generate an explainable answer.
        """
        if not self.extractor.client:
            # No Gemini API key - run fallback offline query retrieval and answer synthesis
            chunks, relationships = self.retrieve_hybrid_context(query)
            return self._generate_fallback_answer(query, chunks, relationships)
            
        # 1. Retrieve context
        chunks, relationships = self.retrieve_hybrid_context(query)
        
        # 2. Format Context
        chunks_str_list = []
        for i, chunk in enumerate(chunks):
            filename = chunk.get("doc_id", "Unknown")
            res = self.db.query("MATCH (d:Document {id: $doc_id}) RETURN d.filename AS filename", {"doc_id": chunk.get("doc_id")})
            if res:
                filename = res[0]["filename"]
            chunks_str_list.append(
                f"[Source Document: {filename}] (Relevance Score: {chunk.get('score', 0):.4f})\n"
                f"Passage:\n{chunk.get('text')}\n"
            )
            
        relationships_str_list = []
        for rel in relationships:
            relationships_str_list.append(
                f"- ({rel['source_name']} : {rel['source_type']}) -[{rel['rel_type']}]-> "
                f"({rel['target_name']} : {rel['target_type']}) | Details: {rel['description']}"
            )
            
        chunks_context = "\n---\n".join(chunks_str_list) if chunks_str_list else "No relevant document passages found."
        graph_context = "\n".join(relationships_str_list) if relationships_str_list else "No relevant graph relationships found."
        
        # 3. Create System & User prompts
        prompt = f"""
        You are an advanced enterprise intelligence assistant. Answer the user's query by synthesizing both semantic text passages (Vector Search) and Knowledge Graph relationships.
        
        Your answer should be accurate, detailed, and directly cite the documents or graph relationships that prove your statements.
        Format your answer in clean Markdown.
        
        User Query:
        "{query}"
        
        ---
        VECTOR SEARCH RETRIEVED PASSAGES:
        {chunks_context}
        
        ---
        KNOWLEDGE GRAPH RETRIEVED RELATIONSHIPS:
        {graph_context}
        ---
        
        Generate the answer. Additionally, specify which exact Entities and Relationships from the knowledge graph context you used as evidence.
        """
        
        try:
            # Generate answering content with structured metadata using fallback chain
            response_text = self.extractor.execute_generative_with_fallback(
                contents=prompt,
                response_schema=RAGAnswerResponse,
                response_mime_type="application/json"
            )
            res = RAGAnswerResponse.model_validate_json(response_text)
            answer_dict = res.model_dump()
                
            formatted_chunks = []
            for chunk in chunks:
                doc_name = chunk.get("doc_id", "Unknown")
                res = self.db.query("MATCH (d:Document {id: $doc_id}) RETURN d.filename AS filename", {"doc_id": chunk.get("doc_id")})
                if res:
                    doc_name = res[0]["filename"]
                formatted_chunks.append({
                    "id": chunk.get("id"),
                    "text": chunk.get("text"),
                    "document_name": doc_name,
                    "score": chunk.get("score")
                })
                
            return {
                "answer": answer_dict.get("answer"),
                "evidence_entities": answer_dict.get("evidence_entities", []),
                "evidence_relations": answer_dict.get("evidence_relations", []),
                "sources": formatted_chunks,
                "graph_relationships": relationships
            }
            
        except Exception as e:
            logger.error(f"RAG generation failed: {e}")
            try:
                raw_text = self.extractor.execute_generative_with_fallback(
                    contents=prompt + "\nGenerate a plain markdown text answer as your response."
                )
                
                formatted_chunks = []
                for chunk in chunks:
                    doc_name = chunk.get("doc_id", "Unknown")
                    doc_id = chunk.get("doc_id")
                    res = self.db.query("MATCH (d:Document {id: $doc_id}) RETURN d.filename AS filename", {"doc_id": doc_id})
                    if res:
                        doc_name = res[0]["filename"]
                    formatted_chunks.append({
                        "id": chunk.get("id"),
                        "text": chunk.get("text"),
                        "document_name": doc_name,
                        "score": chunk.get("score")
                    })
                return {
                    "answer": raw_text,
                    "evidence_entities": [],
                    "evidence_relations": [],
                    "sources": formatted_chunks,
                    "graph_relationships": relationships
                }
            except Exception as inner_e:
                logger.error(f"Fallback generation also failed: {inner_e}")
                return self._generate_fallback_answer(query, chunks, relationships)
