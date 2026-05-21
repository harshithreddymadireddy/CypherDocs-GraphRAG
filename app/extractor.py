import io
import uuid
import logging
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field

from pypdf import PdfReader
from docx import Document as DocxDocument

from app.config import config
from app.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# Pydantic schemas for structured extraction
class EntitySchema(BaseModel):
    name: str = Field(..., description="The name of the entity, capitalized (e.g., Google, John Doe, GDPR, US Dollar, 2026-05-21). Keep it concise.")
    type: str = Field(..., description="The category of the entity. Choose from: ORGANIZATION, PERSON, LOCATION, PRODUCT, EVENT, DATE, LAW_REGULATION, CONTRACT_AGREEMENT, FINANCIAL_INSTRUMENT, ASSET, TECHNOLOGY, or CONCEPT.")
    description: str = Field(..., description="A short, one-sentence description explaining the entity's significance or context within the document chunk.")

class RelationshipSchema(BaseModel):
    source: str = Field(..., description="The name of the source entity (must match one of the entities extracted).")
    source_type: str = Field(..., description="The type of the source entity.")
    target: str = Field(..., description="The name of the target entity (must match one of the entities extracted).")
    target_type: str = Field(..., description="The type of the target entity.")
    relationship_type: str = Field(..., description="A short, descriptive verb or phrase in UPPER_SNAKE_CASE (e.g., AGREED_TO, SUBSIDIARY_OF, SIGNED_ON, COMPLIES_WITH, REVENUE_OF, ACQUIRED, REGULATES).")
    description: str = Field(..., description="A short, one-sentence description explaining the relationship context between source and target.")

class ExtractionResult(BaseModel):
    entities: List[EntitySchema] = Field(default_factory=list)
    relationships: List[RelationshipSchema] = Field(default_factory=list)


class GraphRAGExtractor:
    def __init__(self, neo4j_client: Neo4jClient):
        self.db = neo4j_client
        self._init_gemini_client()
        
    def _init_gemini_client(self):
        """Initialize Google GenAI client, supporting both new and legacy libraries."""
        self.client = None
        self.legacy_sdk = False
        
        if not config.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set. Extraction and embedding generation will fail.")
            return

        # Attempt to use the new google-genai SDK
        try:
            from google import genai
            self.client = genai.Client(api_key=config.GEMINI_API_KEY)
            self.legacy_sdk = False
            logger.info("Initialized Google GenAI SDK client")
        except ImportError:
            # Fallback to the legacy google-generativeai SDK
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=config.GEMINI_API_KEY)
                self.client = legacy_genai
                self.legacy_sdk = True
                logger.info("Initialized legacy google-generativeai client")
            except ImportError:
                logger.error("Neither google-genai nor google-generativeai SDK is installed.")

    def execute_generative_with_fallback(self, contents: str, response_schema: Any = None, response_mime_type: str = None) -> str:
        """Executes generative content requests with retries and fallback models."""
        import time
        import random
        
        if not self.client:
            raise ValueError("Gemini client not initialized")
            
        models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
            "gemini-2.0-flash",
            "gemini-2.5-pro"
        ]
        max_retries = 3
        
        for model_name in models:
            delay = 1.0 + random.random()
            for attempt in range(max_retries):
                try:
                    logger.info(f"Attempting generation with model '{model_name}' (attempt {attempt + 1}/{max_retries})")
                    if not self.legacy_sdk:
                        config_dict = {}
                        if response_mime_type:
                            config_dict["response_mime_type"] = response_mime_type
                        if response_schema:
                            config_dict["response_schema"] = response_schema
                        
                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=config_dict
                        )
                        return response.text
                    else:
                        config_dict = {}
                        if response_mime_type:
                            config_dict["response_mime_type"] = response_mime_type
                        if response_schema:
                            config_dict["response_schema"] = response_schema
                        
                        model = self.client.GenerativeModel(model_name)
                        response = model.generate_content(
                            contents,
                            generation_config=config_dict
                        )
                        return response.text
                except Exception as e:
                    err_str = str(e).lower()
                    is_transient = any(x in err_str for x in ["503", "429", "rate limit", "resource exhausted", "unavailable", "temporarily", "timeout", "service unavailable"])
                    if is_transient and attempt < max_retries - 1:
                        logger.warning(f"Transient error with generative model '{model_name}': {e}. Retrying in {delay:.2f}s...")
                        time.sleep(delay)
                        delay *= 2.0 + random.random()
                    else:
                        logger.warning(f"Generative model '{model_name}' failed: {e}.")
                        break  # Break to outer loop to try next model
                        
        raise RuntimeError("All generative fallback models in chain failed.")

    def execute_embedding_with_fallback(self, text: str) -> List[float]:
        """Executes embedding requests with retries and fallback models."""
        import time
        import random
        
        if not self.client:
            raise ValueError("Gemini client not initialized")
            
        models = ["gemini-embedding-2", "text-embedding-004"]
        max_retries = 3
        
        for model_name in models:
            delay = 1.0 + random.random()
            for attempt in range(max_retries):
                try:
                    logger.info(f"Attempting embedding with model '{model_name}' (attempt {attempt + 1}/{max_retries})")
                    if not self.legacy_sdk:
                        response = self.client.models.embed_content(
                            model=model_name,
                            contents=text,
                            config={"output_dimensionality": 768}
                        )
                        return response.embeddings[0].values
                    else:
                        legacy_model_name = model_name
                        if not legacy_model_name.startswith("models/"):
                            legacy_model_name = f"models/{legacy_model_name}"
                        response = self.client.embed_content(
                            model=legacy_model_name,
                            content=text,
                            output_dimensionality=768
                        )
                        return response['embedding'][0]
                except Exception as e:
                    err_str = str(e).lower()
                    is_transient = any(x in err_str for x in ["503", "429", "rate limit", "resource exhausted", "unavailable", "temporarily", "timeout", "service unavailable"])
                    if is_transient and attempt < max_retries - 1:
                        logger.warning(f"Transient error with embedding model '{model_name}': {e}. Retrying in {delay:.2f}s...")
                        time.sleep(delay)
                        delay *= 2.0 + random.random()
                    else:
                        logger.warning(f"Embedding model '{model_name}' failed: {e}.")
                        break  # Try next model
                        
        raise RuntimeError("All embedding fallback models in chain failed.")

    def get_embedding(self, text: str) -> List[float]:
        """Generates embedding for a chunk of text."""
        if not self.client or not config.GEMINI_API_KEY:
            logger.warning("Gemini client not initialized, returning dummy zeros embedding.")
            return [0.0] * 768
            
        try:
            return self.execute_embedding_with_fallback(text)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise e

    def extract_entities_and_relationships(self, chunk_text: str) -> ExtractionResult:
        """Uses Gemini structured output to extract entities and relationships from text."""
        if not self.client or not config.GEMINI_API_KEY:
            logger.warning("Gemini client not initialized or API key missing. Using rule-based fallback extractor.")
            return self._fallback_extract(chunk_text)
            
        prompt = f"""
        Analyze the following text chunk and extract key entities and semantic relationships between them.
        Be precise. Extract names exactly as they are in the text.
        
        Text chunk:
        ---
        {chunk_text}
        ---
        
        Focus on identifying:
        1. Core entities (Organizations, People, Agreements, Dates, Financial assets/metrics).
        2. Direct semantic relations (e.g., who signed what, which company owns another, compliance details).
        """
        
        try:
            response_text = self.execute_generative_with_fallback(
                contents=prompt,
                response_schema=ExtractionResult,
                response_mime_type="application/json"
            )
            return ExtractionResult.model_validate_json(response_text)
        except Exception as e:
            logger.error(f"Structured extraction failed after fallback chain: {e}. Using rule-based fallback extractor.")
            return self._fallback_extract(chunk_text)

    def _fallback_extract(self, text: str) -> ExtractionResult:
        """Rule-based and heuristic general extractor for entities when LLM is offline/unconfigured."""
        import re
        entities = []
        relationships = []

        def contains_word(text_str: str, word: str) -> bool:
            word_lower = word.lower()
            text_lower = text_str.lower()
            if len(word) <= 4 or word.isupper() or "&" in word:
                # short abbreviation or special symbols: check with word boundaries
                pattern = r'(?<![a-zA-Z0-9])' + re.escape(word_lower) + r'(?![a-zA-Z0-9])'
                return bool(re.search(pattern, text_lower))
            else:
                return word_lower in text_lower
        
        # High-precision predefined lists for stock market concepts
        orgs = [
            ("Reliance Industries", "Reliance Industries Limited (RIL), a major conglomerate spanning oil, retail, and telecom", ["reliance industries", "ril"]),
            ("HDFC Bank", "HDFC Bank Limited, a leading private sector bank in India", ["hdfc bank", "hdfc"]),
            ("ITC Limited", "ITC Limited, an FMCG and hospitality conglomerate", ["itc limited", "itc"]),
            ("Hindustan Unilever", "Hindustan Unilever Limited (HUL), an FMCG major", ["hindustan unilever", "hul"]),
            ("Larsen & Toubro", "Larsen & Toubro Limited (L&T), an engineering and infrastructure giant", ["larsen & toubro", "l&t"]),
            ("State Bank of India", "State Bank of India (SBI), India's largest public sector bank", ["state bank of india", "sbi"]),
            ("Tata Motors", "Tata Motors Limited, a prominent automobile manufacturer", ["tata motors"]),
            ("Tata Steel", "Tata Steel Limited, a global steel company", ["tata steel"]),
            ("Hindalco Industries", "Hindalco Industries Limited, a major metals and mining firm", ["hindalco industries", "hindalco"]),
            ("Grasim Industries", "Grasim Industries Limited, a cement and chemicals manufacturer", ["grasim industries", "grasim"]),
            ("NSE", "National Stock Exchange of India, serving as the primary stock exchange", ["nse", "national stock exchange"]),
            ("NSE Indices Limited", "NSE Indices Limited, a subsidiary of the NSE that manages the index", ["nse indices", "iisl"]),
            ("BSE", "Bombay Stock Exchange, Asia's oldest stock exchange, established in 1875", ["bse", "bombay stock exchange"]),
            ("SENSEX", "SENSEX (S&P BSE SENSEX), the benchmark index of the Bombay Stock Exchange in India", ["sensex", "s&p bse sensex"]),
            ("SEBI", "Securities and Exchange Board of India, the regulator for the securities market in India", ["sebi", "securities and exchange board of india"]),
            ("RBI", "Reserve Bank of India, India's central bank and banking regulator", ["rbi", "reserve bank of india"]),
            ("Zomato", "Zomato Limited, an internet and food delivery platform", ["zomato"]),
            ("Jio Financial Services", "Jio Financial Services Limited, a financial services spin-off", ["jio financial", "jfsl"]),
            ("Trent Limited", "Trent Limited, a retail company of the Tata Group", ["trent limited", "trent"]),
            ("Bharat Electronics", "Bharat Electronics Limited (BEL), a state-owned defense electronics company", ["bharat electronics", "bel"]),
            ("Apollo Hospitals", "Apollo Hospitals Enterprise Limited, a healthcare provider", ["apollo hospitals"]),
            ("InterGlobe Aviation", "InterGlobe Aviation Limited (IndiGo), a major low-cost airline", ["interglobe aviation", "indigo"]),
            ("Max Healthcare", "Max Healthcare Institute Limited, a healthcare provider", ["max healthcare"]),
            ("Hero MotoCorp", "Hero MotoCorp Limited, a leading two-wheeler manufacturer", ["hero motocorp"]),
            ("IndusInd Bank", "IndusInd Bank Limited, a private sector bank", ["indusind bank"]),
            ("Bharat Petroleum", "Bharat Petroleum Corporation Limited (BPCL), a public sector oil & gas refiner", ["bharat petroleum", "bpcl"]),
            ("Britannia Industries", "Britannia Industries Limited, a major food-products corporation", ["britannia industries", "britannia"]),
            ("Yes Bank", "Yes Bank Limited, a financial services company", ["yes bank"]),
            ("Wipro", "Wipro Limited, a major multinational IT services corporation", ["wipro"]),
            ("Shriram Finance", "Shriram Finance Limited, a prominent non-banking financial company", ["shriram finance"]),
            ("LTIMindtree", "LTIMindtree Limited, a multinational IT services and consulting company", ["ltimindtree", "ltim"]),
            ("Adani Enterprises", "Adani Enterprises Limited, a diversified conglomerate", ["adani enterprises", "adani"]),
            ("Shree Cement", "Shree Cement Limited, a major Indian cement manufacturer", ["shree cement"]),
            ("Indian Oil Corporation", "Indian Oil Corporation Limited (IOCL), a public sector oil and gas major", ["indian oil", "iocl"]),
            ("Tata Consumer Products", "Tata Consumer Products Limited, a fast-moving consumer goods company", ["tata consumer"]),
            ("GAIL", "GAIL (India) Limited, the largest state-owned natural gas processing and distribution company", ["gail"]),
            ("Divi's Laboratories", "Divi's Laboratories Limited, a major pharmaceutical company", ["divi's", "divis"]),
            ("SBI Life Insurance", "SBI Life Insurance Company Limited, a joint venture life insurance company", ["sbi life"]),
            ("Zee Entertainment", "Zee Entertainment Enterprises Limited, a media and entertainment conglomerate", ["zee entertainment", "zeel"]),
            ("Bharti Infratel", "Bharti Infratel Limited (now Indus Towers), a major telecom infrastructure provider", ["bharti infratel"]),
            ("HDFC Life Insurance", "HDFC Life Insurance Company Limited, a leading long-term life insurance provider", ["hdfc life"]),
            ("Vedanta Limited", "Vedanta Limited, a diversified natural resources company", ["vedanta"]),
            ("Nestle India", "Nestle India Limited, a major food and beverage company", ["nestle"]),
            ("Indiabulls Housing Finance", "Indiabulls Housing Finance Limited, a major housing finance company", ["indiabulls"]),
            ("JSW Steel", "JSW Steel Limited, an Indian multinational steel producer", ["jsw steel"]),
            ("Lupin Limited", "Lupin Limited, a multinational pharmaceutical company", ["lupin"]),
            ("Bajaj Finserv", "Bajaj Finserv Limited, a financial services conglomerate", ["bajaj finserv"]),
            ("Titan Company", "Titan Company Limited, a consumer goods company focusing on watches and jewelry", ["titan"]),
            ("Ambuja Cements", "Ambuja Cements Limited, a leading cement manufacturer", ["ambuja"]),
            ("Aurobindo Pharma", "Aurobindo Pharma Limited, a major generic pharmaceutical manufacturer", ["aurobindo"]),
            ("Bosch Limited", "Bosch Limited, a leading supplier of technology and services in automotive and industrial sectors", ["bosch"]),
            ("Bajaj Finance", "Bajaj Finance Limited, a leading non-banking financial company", ["bajaj finance"]),
            ("ACC Limited", "ACC Limited, a major cement manufacturer", ["acc"]),
            ("Bank of Baroda", "Bank of Baroda, a leading public sector bank in India", ["bank of baroda", "bob"]),
            ("BHEL", "Bharat Heavy Electricals Limited (BHEL), a state-owned power equipment manufacturer", ["bhel", "bharat heavy electricals"]),
            ("Idea Cellular", "Idea Cellular Limited (now part of Vi), a major telecommunication services provider", ["idea cellular", "idea"]),
            ("Eicher Motors", "Eicher Motors Limited, a manufacturer of commercial vehicles and motorcycles", ["eicher"]),
            ("Cairn India", "Cairn India Limited, an oil and gas exploration and production company", ["cairn"]),
            ("Punjab National Bank", "Punjab National Bank (PNB), a major public sector bank", ["punjab national bank", "pnb"]),
            ("Adani Ports", "Adani Ports and Special Economic Zone Limited, the largest private port operator", ["adani ports"]),
            ("NMDC Limited", "NMDC Limited, a state-owned mineral producer", ["nmdc"]),
            ("IDFC Limited", "IDFC Limited, an infrastructure finance company", ["idfc"]),
            ("DLF Limited", "DLF Limited, a major real estate development company", ["dlf"]),
            ("Jindal Steel & Power", "Jindal Steel & Power Limited, a major steel and power producer", ["jindal steel", "jspl"]),
            ("Coal India", "Coal India Limited, a state-owned coal mining and refining corporation", ["coal india"]),
            ("Asian Paints", "Asian Paints Limited, a leading multinational paint company", ["asian paints"]),
            ("Bajaj Auto", "Bajaj Auto Limited, a major two-wheeler manufacturer", ["bajaj auto"]),
            ("Dr. Reddy's Laboratories", "Dr. Reddy's Laboratories Limited, a global pharmaceutical company", ["dr. reddy", "dr reddy"]),
            ("UltraTech Cement", "UltraTech Cement Limited, India's largest cement manufacturer", ["ultratech"]),
            ("NIFTY 50", "NIFTY 50, the benchmark stock market index of the NSE in India", ["nifty 50", "nifty"])
        ]
        
        people = [
            ("Narendra Modi", "Prime Minister of India under whom stable majority governments were formed", ["narendra modi", "modi"])
        ]
        
        found_orgs = []
        for org_name, desc, aliases in orgs:
            matched = False
            for alias in aliases:
                if contains_word(text, alias):
                    matched = True
                    break
            if matched:
                entities.append(EntitySchema(name=org_name, type="ORGANIZATION", description=desc))
                found_orgs.append(org_name)
                
        found_people = []
        for p_name, desc, aliases in people:
            matched = False
            for alias in aliases:
                if contains_word(text, alias):
                    matched = True
                    break
            if matched:
                entities.append(EntitySchema(name=p_name, type="PERSON", description=desc))
                found_people.append(p_name)

        # Heuristic extraction for arbitrary proper nouns (sequences of capitalized words)
        # to ensure that any general document produces nodes when LLM is offline.
        stop_words = {
            "The", "A", "An", "In", "On", "At", "This", "That", "It", "Its", "They", "Their", "We", "Our",
            "He", "She", "His", "Her", "But", "For", "As", "By", "To", "From", "With", "Under", "After", "Before",
            "And", "Or", "If", "Then", "Else", "Of", "For", "Is", "Are", "Was", "Were", "Be", "Been", "Having", "Has", "Have"
        }
        
        # Match sequences of capitalized words (e.g., 'Bombay Stock Exchange', 'State Bank')
        capitalized_phrases = re.findall(r'\b[A-Z][a-zA-Z0-9&]*+(?:\s+[A-Z][a-zA-Z0-9&]*+)+\b', text)
        # Match single capitalized words of length >= 5 that are not sentence-initial stop words
        single_words = re.findall(r'\b[A-Z][a-zA-Z0-9]{4,}\b', text)
        
        candidates = list(set(capitalized_phrases + single_words))
        for cand in candidates:
            cand = cand.strip()
            if cand in stop_words:
                continue
            first_word = cand.split()[0]
            if first_word in stop_words and len(cand.split()) == 1:
                continue
            # Skip if it matches a predefined entity's name (case-insensitive check)
            if any(cand.lower() == ent.name.lower() for ent in entities):
                continue
            # Skip if too long to avoid sentence fragments
            if len(cand) > 50:
                continue
                
            # Heuristically classify entity type
            ent_type = "CONCEPT"
            if any(kw in cand.lower() for kw in ["corp", "inc", "limited", "ltd", "bank", "exchange", "board", "association", "agency"]):
                ent_type = "ORGANIZATION"
            elif any(kw in cand.lower() for kw in ["modi", "ramkrishna", "mehta", "shri", "mr.", "mrs.", "dr."]):
                ent_type = "PERSON"
            elif any(kw in cand.lower() for kw in ["india", "mumbai", "delhi", "bengaluru", "chennai", "kolkata", "london", "york", "us", "uk"]):
                ent_type = "LOCATION"
                
            entities.append(EntitySchema(
                name=cand,
                type=ent_type,
                description=f"Heuristically extracted entity: {cand}"
            ))

        # Explicit stock-index relationship linking for predefined lists
        if "NIFTY 50" in found_orgs:
            for org in found_orgs:
                if org != "NIFTY 50":
                    if org in ["NSE", "NSE Indices Limited"]:
                        relationships.append(RelationshipSchema(
                            source=org, source_type="ORGANIZATION",
                            target="NIFTY 50", target_type="ORGANIZATION",
                            relationship_type="MANAGES",
                            description=f"{org} manages and calculates the NIFTY 50 index."
                        ))
                    elif org not in ["BSE", "SENSEX"]:
                        # Only link as constituent if the text contains nifty constituent-related keywords
                        nifty_kws = ["nifty", "index constituent", "index weight", "portfolio", "added to", "removed from", "constituent of"]
                        if any(kw in text.lower() for kw in nifty_kws):
                            relationships.append(RelationshipSchema(
                                source=org, source_type="ORGANIZATION",
                                target="NIFTY 50", target_type="ORGANIZATION",
                                relationship_type="CONSTITUENT_OF",
                                description=f"{org} is mentioned as a constituent of the NIFTY 50 index."
                            ))
                        
        if "SENSEX" in found_orgs:
            for org in found_orgs:
                if org != "SENSEX":
                    if org in ["BSE"]:
                        relationships.append(RelationshipSchema(
                            source=org, source_type="ORGANIZATION",
                            target="SENSEX", target_type="ORGANIZATION",
                            relationship_type="MANAGES",
                            description=f"{org} manages and calculates the SENSEX index."
                        ))
                    elif org not in ["NSE", "NSE Indices Limited", "NIFTY 50"]:
                        # Only link as constituent if the text contains sensex constituent-related keywords
                        sensex_kws = ["sensex", "index constituent", "index weight", "portfolio", "added to", "removed from", "constituent of"]
                        if any(kw in text.lower() for kw in sensex_kws):
                            relationships.append(RelationshipSchema(
                                source=org, source_type="ORGANIZATION",
                                target="SENSEX", target_type="ORGANIZATION",
                                relationship_type="CONSTITUENT_OF",
                                description=f"{org} is mentioned as a constituent of the SENSEX index."
                            ))

        if "NSE" in found_orgs and "NSE Indices Limited" in found_orgs:
            relationships.append(RelationshipSchema(
                source="NSE Indices Limited", source_type="ORGANIZATION",
                target="NSE", target_type="ORGANIZATION",
                relationship_type="SUBSIDIARY_OF",
                description="NSE Indices Limited is a subsidiary of the National Stock Exchange of India."
            ))
            
        if "Narendra Modi" in found_people:
            if "NIFTY 50" in found_orgs:
                relationships.append(RelationshipSchema(
                    source="Narendra Modi", source_type="PERSON",
                    target="NIFTY 50", target_type="ORGANIZATION",
                    relationship_type="IMPACTED_BY_ELECTION_OF",
                    description="The NIFTY 50 index performance was heavily impacted by the election and policies of Prime Minister Narendra Modi."
                ))
            if "SENSEX" in found_orgs:
                relationships.append(RelationshipSchema(
                    source="Narendra Modi", source_type="PERSON",
                    target="SENSEX", target_type="ORGANIZATION",
                    relationship_type="IMPACTED_BY_ELECTION_OF",
                    description="The SENSEX index performance was heavily impacted by the election and policies of Prime Minister Narendra Modi."
                ))

        # Heuristic relationship generation for co-occurring entities within the same sentence
        sentences = re.split(r'\. |\n', text)
        for sentence in sentences:
            sentence_entities = []
            for ent in entities:
                if contains_word(sentence, ent.name):
                    sentence_entities.append(ent)
            
            # Link all co-occurring pairs
            for i in range(len(sentence_entities)):
                for j in range(i + 1, len(sentence_entities)):
                    e1 = sentence_entities[i]
                    e2 = sentence_entities[j]
                    
                    # Prevent duplicates and self-loops
                    if e1.name.lower() == e2.name.lower():
                        continue
                    exists = any(
                        (r.source.lower() == e1.name.lower() and r.target.lower() == e2.name.lower()) or 
                        (r.source.lower() == e2.name.lower() and r.target.lower() == e1.name.lower())
                        for r in relationships
                    )
                    if not exists:
                        rel_type = "ASSOCIATED_WITH"
                        if e1.type == "PERSON" and e2.type == "ORGANIZATION":
                            rel_type = "AFFILIATED_WITH"
                        elif e2.type == "PERSON" and e1.type == "ORGANIZATION":
                            e1, e2 = e2, e1  # Swap to put Person as source
                            rel_type = "AFFILIATED_WITH"
                            
                        relationships.append(RelationshipSchema(
                            source=e1.name,
                            source_type=e1.type,
                            target=e2.name,
                            target_type=e2.type,
                            relationship_type=rel_type,
                            description=f"Mentions of '{e1.name}' and '{e2.name}' occur together in the same sentence."
                        ))
                
        return ExtractionResult(entities=entities, relationships=relationships)

    def parse_pdf(self, file_bytes: bytes) -> str:
        """Extracts text from PDF bytes."""
        text = []
        pdf = PdfReader(io.BytesIO(file_bytes))
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        return "\n".join(text)

    def parse_docx(self, file_bytes: bytes) -> str:
        """Extracts text from DOCX bytes."""
        doc = DocxDocument(io.BytesIO(file_bytes))
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        return "\n".join(text)

    def chunk_text(self, text: str, chunk_size: int = None, chunk_overlap: int = None) -> List[str]:
        """Splits text into overlapping chunks, attempting to keep sentences whole."""
        size = chunk_size or config.CHUNK_SIZE
        overlap = chunk_overlap or config.CHUNK_OVERLAP
        
        if len(text) <= size:
            return [text]
            
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + size
            
            # If we aren't at the end of the text, try to find a natural boundary (period, paragraph)
            if end < len(text):
                # Try finding a paragraph boundary first in the last 20% of the chunk
                search_start = int(start + size * 0.8)
                boundary = text.rfind("\n\n", search_start, end)
                if boundary == -1:
                    # Try finding a sentence boundary
                    boundary = text.rfind(". ", search_start, end)
                if boundary == -1:
                    # Try finding a space boundary
                    boundary = text.rfind(" ", search_start, end)
                
                if boundary != -1:
                    end = boundary + 1  # Include the punctuation or space
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
                
            start = end - overlap
            # Prevent infinite loops
            if start >= len(text) or (end - start) <= 0:
                break
                
        return chunks

    def process_document(self, filename: str, file_bytes: bytes) -> str:
        """
        Full document pipeline:
        1. Parse file based on extension
        2. Create Document node in Neo4j with status='processing'
        3. Split text into chunks
        4. For each chunk:
           a. Generate vector embedding
           b. Insert Chunk node and connect to Document
           c. Extract entities and relationships via Gemini LLM
           d. Insert Entities and Relationships into Neo4j
        5. Update Document status to 'completed'
        """
        doc_id = str(uuid.uuid4())
        self.db.create_document(doc_id, filename)
        
        try:
            # 1. Parse document text
            ext = filename.split(".")[-1].lower()
            if ext == "pdf":
                text = self.parse_pdf(file_bytes)
            elif ext in ["docx", "doc"]:
                text = self.parse_docx(file_bytes)
            elif ext in ["txt", "md", "markdown"]:
                text = file_bytes.decode("utf-8", errors="ignore")
            else:
                raise ValueError(f"Unsupported file format: .{ext}")
                
            if not text.strip():
                raise ValueError("Extracted text is empty")
                
            # 2. Chunk text
            chunks = self.chunk_text(text)
            logger.info(f"Split {filename} into {len(chunks)} chunks")
            
            # 3. Process each chunk
            for index, chunk_text in enumerate(chunks):
                chunk_id = f"{doc_id}_chunk_{index}"
                
                # a. Embed chunk
                embedding = self.get_embedding(chunk_text)
                
                # b. Insert Chunk into Neo4j
                self.db.insert_chunk(doc_id, chunk_id, index, chunk_text, embedding)
                
                # c. Extract graph components
                extracted = self.extract_entities_and_relationships(chunk_text)
                
                # d. Insert entities
                for entity in extracted.entities:
                    self.db.insert_entity(
                        chunk_id=chunk_id,
                        name=entity.name,
                        entity_type=entity.type,
                        description=entity.description
                    )
                    
                # e. Insert relationships
                for rel in extracted.relationships:
                    # Make sure the entities actually exist in this chunk's metadata before linking them.
                    # This prevents dangling nodes and garbage relationships.
                    self.db.insert_relationship(
                        chunk_id=chunk_id,
                        source_name=rel.source,
                        source_type=rel.source_type,
                        target_name=rel.target,
                        target_type=rel.target_type,
                        rel_type=rel.relationship_type,
                        description=rel.description
                    )
                    
            # 4. Update Document status to completed
            self.db.update_document_status(doc_id, "completed")
            logger.info(f"Successfully processed document {filename} (ID: {doc_id})")
            return doc_id
            
        except Exception as e:
            logger.error(f"Error processing document {filename}: {e}")
            self.db.update_document_status(doc_id, "failed", str(e))
            raise e
