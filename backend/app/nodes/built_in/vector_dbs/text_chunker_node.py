from typing import Dict, Any, List, Optional
import json
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput
from app.utils.text_splitter import RecursiveCharacterTextSplitter
from app.nodes.properties import safe_int

class TextChunkerNode(BaseNode):
    name: str = "text_chunker_node"
    label: str = "Text Chunker"
    description: str = "Splits long text or document content into smaller overlapping chunks."
    category: str = "Data Operations"
    icon: str = "blocks"
    color: str = "#06b6d4"

    user_properties: List[Dict[str, Any]] = [
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
            "key": "text",
            "label": "Source Text",
            "type": "textarea",
            "placeholder": "Enter text or use Jinja expression like {{ data.text }}"
        }
    ]

    async def init(self) -> None:
        await super().init()

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        await super().validate_input(inp)
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        config = inp.config
        
        strategy = config.get("chunking_strategy", "recursive")
        chunk_size = safe_int(config.get("chunk_size"), 1000)
        chunk_overlap = safe_int(config.get("chunk_overlap"), 200)

        # Get input text from payload or config
        data_val = self.get_input_data(inp)
        input_text = ""
        
        if isinstance(data_val, dict):
            input_text = data_val.get("text") or data_val.get("content") or data_val.get("data") or ""
        elif isinstance(data_val, str):
            input_text = data_val
        
        # Fallback to config if input data is empty
        if not input_text and config.get("text"):
            input_text = config.get("text")

        if not input_text:
            self.logger.warning("text_chunker_empty_input", trace_id=inp.trace_id)
            return NodeOutput(
                trace_id=inp.trace_id,
                data=self.set_output_data(inp, {"chunks": []}),
                status="success",
                metadata={"chunk_count": 0, "status": "empty"}
            )

        if strategy == "none":
            chunks = [input_text]
        else:
            separators = None
            if strategy == "character":
                separators = [""]
            
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=separators
            )
            chunks = splitter.split_text(input_text)

        out_payload = {
            "chunks": chunks,
            "chunk_count": len(chunks),
            "strategy": strategy,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap
        }

        out_data = self.set_output_data(inp, out_payload)
        return NodeOutput(
            trace_id=inp.trace_id,
            data=out_data,
            status="success",
            metadata={
                "chunk_count": len(chunks),
                "strategy": strategy
            }
        )
