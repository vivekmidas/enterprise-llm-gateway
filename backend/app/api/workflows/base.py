import abc
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from  app.core.types.common import NodeInput, NodeOutput

class BaseAgent(abc.ABC):
    """
    Standardized Base Class for all Enterprise LLM Gateway agents.
    """
    name: str = "base_agent"       # Machine identifier
    label: str = "Base Agent"      # UI-facing display name (matches frontend 'label')
    description: str = "Standard agent base"
    version: str = "1.0.0"
    category: str = "Custom"       # Internal functional category
    group: str = "Custom"          # UI grouping (matches frontend 'group')

    # Visual properties for the UI (aligned with frontend BaseNodeData)
    icon: str = "bot"              # Name of the icon to be mapped in frontend
    color: str = "#7C3AED"         # Brand color (hex code)
    badge: Optional[str] = "Node"  # Optional badge text (e.g., "Model")
    sub_label: Optional[str] = None # Optional sub-label

    def get_name(self) -> str:
        return self.name

    def get_description(self) -> str:
        return self.description

    def get_properties(self) -> List[Dict[str, Any]]:
        """Returns the property schema definition for the UI."""
        return getattr(self, "propertySchema", [])

    @abc.abstractmethod
    async def run(self, inp: NodeInput) -> NodeOutput:
        """
        Core logic to be implemented by child agents.
        Should return content and metadata/violations.
        """
        pass

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        Standard execution wrapper with observability, timing, and error handling.
        """
        start_ts = time.time()
        try:
            # Perform the actual work
            output = await self.run(inp)
            end_ts = time.time()

            # Enrich output with tracking data
            output.start_time = start_ts
            output.end_time = end_ts
            output.latency_ms = round((end_ts - start_ts) * 1000, 2)
            output.status = "failure" if output.error or output.violations else "success"
            return output

        except Exception as e:
            end_ts = time.time()
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error=str(e),
                start_time=start_ts,
                end_time=end_ts,
                latency_ms=round((end_ts - start_ts) * 1000, 2)
            )