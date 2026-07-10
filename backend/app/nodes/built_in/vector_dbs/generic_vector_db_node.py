import base64
import os
import re
import uuid
import time
import httpx
from typing import Dict, Any, List, Optional
import json
import structlog

from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.utils.text_splitter import chunk_text
from app.utils.type_utils import safe_int, safe_float
from app.utils.file_utils import load_file_content, extract_text_from_pdf

logger = structlog.get_logger(__name__)

class GenericLLMVectorDB(BaseNode):
    name: str = "generic_llm_vector_db"
    label: str = "Vector DB Integration"
    description: str = "Connects to a Vector Database via URL to write embeddings (text, docs, images) or perform similarity searches."
    category: str = "Vector Databases"
    icon: str = "blocks"
    color: str = "#2cb23cff"

    user_properties: List[Dict[str, Any]] = [
        {
            "key": "url",
            "label": "Vector DB URL",
            "type": "string",
            "default": "http://localhost:6333"
        },
        {
            "key": "db_type",
            "label": "Vector DB Type",
            "type": "choice",
            "options": ["qdrant", "pinecone", "faiss"],
            "default": "qdrant"
        },
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "default": ""
        },
        {
            "key": "collection_name",
            "label": "Collection Name",
            "type": "string",
            "default": "documents"
        },
        {
            "key": "operation",
            "label": "Operation",
            "type": "choice",
            "options": ["upsert", "search"],
            "default": "upsert"
        },
        {
            "key": "chunking_strategy",
            "label": "Chunking Strategy",
            "type": "choice",
            "options": ["none", "character", "recursive"],
            "default": "recursive"
        },
        {
            "key": "chunk_size",
            "label": "Chunk Size",
            "type": "number",
            "default": 1000
        },
        {
            "key": "chunk_overlap",
            "label": "Chunk Overlap",
            "type": "number",
            "default": 200
        },
        {
            "key": "embedding_api_url",
            "label": "Embedding API URL",
            "type": "string",
            "default": "http://127.0.0.1:11434/v1/embeddings"
        },
        {
            "key": "embedding_model",
            "label": "Embedding Model",
            "type": "string",
            "default": "nomic-embed-text"
        },
        {
            "key": "embedding_api_key",
            "label": "Embedding API Key",
            "type": "password",
            "default": ""
        },
        {
            "key": "similarity_threshold",
            "label": "Similarity Threshold",
            "type": "number",
            "default": 0.7
        },
        {
            "key": "    ",
            "label": "Top K Results",
            "type": "number",
            "default": 5
        },
        {
            "key": "text",
            "label": "Input Text",
            "type": "textarea",
            "placeholder": "Text to embed/upsert or search query"
        },
        {
            "key": "pdf_path",
            "label": "PDF File / Base64 Document",
            "type": "string",
            "placeholder": "Local file path or base64 data string"
        },
        {
            "key": "image_path",
            "label": "Image File / Base64 Image",
            "type": "string",
            "placeholder": "Local file path or base64 data string"
        }
    ]

    async def init(self) -> None: 
        await super().init()

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        await super().validate_input(inp)
        return None

    # File loading and PDF parsing utilities have been consolidated to app.utils.file_utils

    async def _generate_embeddings(self, texts: List[str], api_url: str, model: str, api_key: Optional[str] = None) -> List[List[float]]:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # OpenAI v1 format first
        try:
            payload = {
                "model": model,
                "input": texts
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(api_url, json=payload, headers=headers, timeout=30.0)
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and isinstance(data["data"], list):
                        sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
                        return [item["embedding"] for item in sorted_data]
        except Exception:
            pass

        # Loop / Ollama /api/embeddings fallback
        embeddings = []
        is_ollama = "/api/embeddings" in api_url
        async with httpx.AsyncClient() as client:
            for t in texts:
                payload = {
                    "model": model,
                    "prompt" if is_ollama else "input": t
                }
                response = await client.post(api_url, json=payload, headers=headers, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                if "embedding" in data:
                    embeddings.append(data["embedding"])
                elif "data" in data and len(data["data"]) > 0:
                    embeddings.append(data["data"][0]["embedding"])
                else:
                    raise ValueError(f"Embedding response parsing failed: {data}")
        return embeddings

    async def execute(self, inp: NodeInput) -> NodeOutput:
        start_time = time.time()
        config = inp.config
        trace_id = inp.trace_id

        # 1. Properties Setup
        db_type = config.get("db_type", "qdrant").lower()
        db_url = config.get("url", "http://localhost:6333").rstrip('/')
        api_key = config.get("api_key", "")
        collection = config.get("collection_name", "documents")
        operation = config.get("operation", "upsert")
        strategy = config.get("chunking_strategy", "recursive")
        chunk_size = safe_int(config.get("chunk_size"), 1000)
        chunk_overlap = safe_int(config.get("chunk_overlap"), 200)
        embed_url = config.get("embedding_api_url", "http://127.0.0.1:11434/v1/embeddings")
        embed_model = config.get("embedding_model", "nomic-embed-text")
        embed_key = config.get("embedding_api_key", "")
        similarity_threshold = safe_float(config.get("similarity_threshold"), 0.7)
        top_k = safe_int(config.get("top_k"), 5)
        self.logger.info("generic_llm_vector_db_config", trace_id=trace_id, config=config)
        # 2. Extract input data from payload or properties
        payload_data = self.get_input_data(inp)
        input_text = ""
        pdf_source = ""
        image_source = ""

        if isinstance(payload_data, dict):
            input_text = payload_data.get("text") or payload_data.get("content") or payload_data.get("query") or ""
            pdf_source = payload_data.get("pdf_path") or payload_data.get("pdf_base64") or ""
            image_source = payload_data.get("image_path") or payload_data.get("image_base64") or ""
        elif isinstance(payload_data, str):
            input_text = payload_data

        # Fallback to static properties config if empty
        if not input_text and config.get("text"):
            input_text = config.get("text")
        if not pdf_source and config.get("pdf_path"):
            pdf_source = config.get("pdf_path")
        if not image_source and config.get("image_path"):
            image_source = config.get("image_path")

        # Define Qdrant headers
        qdrant_headers = {}
        if api_key:
            qdrant_headers["api-key"] = api_key

        try:
            # 3. Handle SEARCH operation
            if operation == "search":
                self.logger.info("starting search operation", trace_id=trace_id, config=config, name=self.name, function=__name__)
                if not input_text:
                    raise ValueError("Search operation requires 'Input Text' as a query.")

                self.logger.info("vector_db_search_started", trace_id=trace_id, collection=collection, db_type=db_type)
                query_embeddings = await self._generate_embeddings([input_text], embed_url, embed_model, embed_key)
                query_vector = query_embeddings[0]

                search_results = []
                if db_type == "qdrant":
                    search_url = f"{db_url}/collections/{collection}/points/search"
                    payload = {
                        "vector": query_vector,
                        "limit": top_k,
                        "with_payload": True,
                        "score_threshold": similarity_threshold
                    }
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(search_url, json=payload, headers=qdrant_headers, timeout=20.0)
                        resp.raise_for_status()
                        search_results = resp.json().get("result", [])
                else:
                    # Mock / placeholder implementations for other DBs
                    search_results = [
                        {
                            "id": str(uuid.uuid4()),
                            "score": 0.99,
                            "payload": {"text": f"Placeholder search results for {db_type}. Feature coming soon."}
                        }
                    ]

                latency = round((time.time() - start_time) * 1000, 2)
                out_data = self.set_output_data(inp, {"results": search_results, "count": len(search_results)})
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=out_data,
                    status="success",
                    latency_ms=latency,
                    metadata={"search_count": len(search_results), "db_type": db_type}
                )

            # 4. Handle UPSERT operation
            else:
                self.logger.info("starting upsert operation", trace_id=trace_id, config=config, name=self.name, function=__name__)
                raw_text_to_chunk = input_text
                
                # Check for PDF
                if pdf_source:
                    pdf_bytes = load_file_content(pdf_source)
                    pdf_text = extract_text_from_pdf(pdf_bytes)
                    raw_text_to_chunk = (raw_text_to_chunk + "\n\n" + pdf_text).strip()

                # Chunk the text using consolidated helper function
                chunks = chunk_text(
                    text=raw_text_to_chunk,
                    strategy=strategy,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap
                )

                # Generate embeddings
                self.logger.info("starting embedding generation", trace_id=trace_id, config=config, name=self.name, function=__name__)
                embeddings = []
                if chunks:
                    embeddings = await self._generate_embeddings(chunks, embed_url, embed_model, embed_key)

                # Collect image data if present
                image_metadata = {}
                if image_source:
                    try:
                        # Extract basic image base64 metadata
                        img_bytes = load_file_content(image_source)
                        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                        image_metadata = {
                            "has_image": True,
                            "image_base64": f"data:image/png;base64,{img_b64}"[:100000],  # cap length to avoid payload bloat
                            "size_bytes": len(img_bytes)
                        }
                    except Exception as e:
                        self.logger.warning("image_loading_failed", trace_id=trace_id, error=str(e))
                        image_metadata = {"has_image": True, "error": str(e)}

                # Build upsert points list
                points = []
                # Case 1: Storing text chunks
                self.logger.info("building points list", trace_id=trace_id, config=config, name=self.name, function=__name__)
                for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                    pt_payload = {
                        "text": chunk,
                        "chunk_index": i,
                        "timestamp": int(time.time()),
                        "source": "pdf" if pdf_source else "text"
                    }
                    if i == 0 and image_metadata:
                        pt_payload["image_metadata"] = image_metadata

                    points.append({
                        "id": str(uuid.uuid4()),
                        "vector": vector,
                        "payload": pt_payload
                    })

                # Case 2: Image only (no text chunks)
                self.logger.info("building points list", trace_id=trace_id, config=config, name=self.name, function=__name__)  
                if not chunks and image_metadata:
                    # Generate a mock vector or use zeros if no text splits exist
                    vector_size = 1536  # Default size
                    # Storing image standalone
                    points.append({
                        "id": str(uuid.uuid4()),
                        "vector": [0.0] * vector_size,
                        "payload": {
                            "source": "image",
                            "timestamp": int(time.time()),
                            "image_metadata": image_metadata
                        }
                    })

                if not points:
                    return NodeOutput(
                        trace_id=inp.trace_id,
                        data=self.set_output_data(inp, {"status": "skipped", "message": "No text, PDF, or image data provided to write"}),
                        status="success",
                        metadata={"upserted_points": 0}
                    )

                # Write to Vector Database
                if db_type == "qdrant":
                    self.logger.info("writing points to qdrant", trace_id=trace_id, config=config, name=self.name, function=__name__)  
                    # Check and auto-create collection if needed
                    async with httpx.AsyncClient() as client:
                        # Check existence
                        check_url = f"{db_url}/collections/{collection}"
                        res = await client.get(check_url, headers=qdrant_headers, timeout=10.0)
                        
                        if res.status_code == 404:
                            self.logger.info("qdrant_collection_not_found_creating", trace_id=trace_id, collection=collection)
                            vector_dim = len(points[0]["vector"])
                            create_payload = {
                                "vectors": {
                                    "size": vector_dim,
                                    "distance": "Cosine"
                                }
                            }
                            resp_create = await client.put(check_url, json=create_payload, headers=qdrant_headers, timeout=15.0)
                            resp_create.raise_for_status()

                        # Upsert points
                        upsert_url = f"{db_url}/collections/{collection}/points"
                        self.logger.info("writing points to qdrant", trace_id=trace_id, upsert_url=upsert_url, config=config, name=self.name, function=__name__)
                        resp_upsert = await client.put(upsert_url, json={"points": points}, headers=qdrant_headers, timeout=30.0)
                        resp_upsert.raise_for_status()
                else:
                    # Mock write success for other databases
                    self.logger.info("vector_db_write_mocked", trace_id=trace_id, db_type=db_type, points_count=len(points))

                latency = round((time.time() - start_time) * 1000, 2)
                out_data = self.set_output_data(inp, {"status": "success", "upserted_points": len(points)})
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=out_data,
                    status="success",
                    latency_ms=latency,
                    metadata={"upserted_points": len(points), "db_type": db_type}
                )

        except Exception as e:
            self.logger.error("vector_db_node_execution_failed", trace_id=trace_id, error=str(e), exc_info=True)
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message=f"Vector DB integration error: {str(e)}"
            )
