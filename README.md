# CypherDocs

CypherDocs is an enterprise-grade Graph Retrieval-Augmented Generation (GraphRAG) platform that combines **Knowledge Graphs (Neo4j)**, **Vector Similarity Search**, and **Large Language Models (Gemini)** to enable relationship-aware semantic retrieval from unstructured documents such as financial reports, contracts, legal agreements, compliance documents, and research papers.

The system ingests documents, splits them into overlapping passages, generates embeddings, extracts entity-relationship networks using structured LLM schemas, and builds a unified knowledge graph. At query time, it traverses graph neighbors alongside vector search results to construct highly explainable, context-rich answers.

---

## Key Features

- **Document Processing**: Automatic text extraction from PDF, DOCX, TXT, and Markdown files.
- **LLM-Powered Extraction**: Generates dense vector embeddings (`text-embedding-004`) and performs entity/relationship extraction using Gemini structured output schemas.
- **Hybrid Retrieval Engine**: Melds semantic chunk vector search with query-guided 1-hop graph traversals.
- **Interactive Visualization**: Explores the extracted entity-relationship graph using a premium, glassmorphism-themed dark mode dashboard powered by D3 force-graph.
- **Platform Analytics**: Displays statistics including document status queues, chunk distributions, entity types, and relationship density.



## Installation & Setup

Follow these step-by-step instructions to configure and run CypherDocs on your device.

### Prerequisites
- **Python**: version `3.10` or higher
- **Docker & Docker Compose**: to host the Neo4j instance
- **Google Gemini API Key**: to power extraction and reasoning

---

### Step 1: Clone and Prepare Workspace
Copy or clone the repository to your device and navigate into the root directory:
```bash
cd CypherDocs-graphrag
```

### Step 2: Spin Up Neo4j Database
Start the Neo4j container using Docker. The database container is named **`CypherDocs-graphrag`** and is pre-configured with the **APOC plugin** (Awesome Procedures on Cypher):
```bash
docker compose up -d
```
*This exposes the HTTP Console on `http://localhost:7474` and the Bolt protocol connector on port `7687`.*

#### Accessing and Managing the Container:
- **Neo4j Browser (Web UI)**: Open [http://localhost:7474](http://localhost:7474) in your browser. Connect using username `neo4j` and password `password123`.
- **Cypher Shell CLI**: Execute Cypher queries directly inside the container:
  ```bash
  docker exec -it CypherDocs-graphrag cypher-shell -u neo4j -p password123
  ```
- **Inspect Container Logs**: Track database runtime status:
  ```bash
  docker logs CypherDocs-graphrag
  ```

### Step 3: Create and Activate Virtual Environment
Create a virtual environment named **`CypherDocs-graphrag`** in the project root:
```bash
# Create the environment
python3 -m venv CypherDocs-graphrag

# Activate on macOS / Linux
source CypherDocs-graphrag/bin/activate

# Activate on Windows (Command Prompt)
CypherDocs-graphrag\Scripts\activate

# Activate on Windows (PowerShell)
.\CypherDocs-graphrag\Scripts\Activate.ps1
```

### Step 4: Install Dependencies
With the `CypherDocs-graphrag` virtual environment active, install all required python packages:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 5: Configure Environment Variables
Copy the template `.env.example` file to create your active configuration:
```bash
cp .env.example .env
```
Open `.env` in a text editor and update the parameters:
```env
# Database Credentials
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# Gemini API Key (Insert your actual key here)
GEMINI_API_KEY=AIzaSy...

# Models Configuration
EMBEDDING_MODEL=text-embedding-004
GENERATIVE_MODEL=gemini-1.5-flash
```

---

## Verification & Launch

### Step 6: Run Automated Backend Tests
Run the provided validation script to confirm the database connection, constraint mapping, vector indexing, and graph traversal functionality are operating properly:
```bash
python verify.py
```
*If everything is correct, the script logs `All local backend functionality verified successfully!` and exits.*

### Step 7: Launch the Web Server
Launch the FastAPI backend application:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 8: Access the Application
Open your web browser and navigate to:
```
http://localhost:8000
```

---

## Usage Guide

1. **Upload Documents**: Go to the **Document Ingestion** tab. Select or drag-and-drop multiple documents (PDFs, text reports, legal agreements). The files will queue and display processing statuses.
![Image Alt](https://github.com/harshithreddymadireddy/CypherDocs-GraphRAG/blob/e9ff52ecb96996b914bab030722993eb430f4fb9/Assets/Images%3Avideo/Document_ingestion.jpeg)
2. **Visualize Graph**: Go to the **Graph Explorer** tab. Once status shows `completed`, click **Refresh Graph** to load the force-directed network nodes. Click on individual nodes or relationships to view property details in the inspector.
![Image Alt](https://github.com/harshithreddymadireddy/CypherDocs-GraphRAG/blob/e9ff52ecb96996b914bab030722993eb430f4fb9/Assets/Images%3Avideo/Graph_Explorer_Files.jpeg)
3. **Ask Queries**: Go to the **Query Workspace** tab. Enter questions (e.g. *"Which companies were added to the NIFTY 50 index in 2025?"*). The assistant will generate a synthesized answer, citing document passages under the **Vector Sources** tab and graph connections under the **Graph Links** tab.
![Image Alt](https://github.com/harshithreddymadireddy/CypherDocs-GraphRAG/blob/e9ff52ecb96996b914bab030722993eb430f4fb9/Assets/Images%3Avideo/Query.jpeg)

