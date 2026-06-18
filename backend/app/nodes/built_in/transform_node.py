import json
from typing import Any, Dict, List, Optional, Union
from app.nodes.base import BaseNode, NodeInput, NodeOutput
class TransformNode(BaseNode):
    name: str = "transform_node"
    label: str = "Data Transformer"
    description: str = "Transforms input data using Jinja2 templates to match the next node's contract."
    version: str = "1.0.0"
    category: str = "Data"
    icon: str = "shuffle" # or "exchange", "code"
    color: str = "#FFD700" # Gold color

    property_schema: List[Dict[str, Any]] = [
        {
            "key": "mapping_template",
            "label": "Data Mapping",
            "type": "textarea",
            "default": "{}",
            "description": "Jinja2 template to transform the incoming data. The previous node's output is available as 'input_data'. Example: {'new_key': '{{ input_data.old_key }}'}"
        },
        {
            "key": "output_format",
            "label": "Output Format",
            "type": "choice",
            "options": ["json", "string"],
            "default": "json",
            "description": "The expected format of the resulting data."
        }
    ]

    async def init(self) -> None:
        await super().init()

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        # Basic validation: ensure mapping_template is present
        if not self.properties.get("mapping_template"):
            return NodeOutput(
                trace_id=inp.trace_id,
                output_data=inp.input_data,
                status="failure",
                error_message="'mapping_template' property is required for Transform Node.",
                error_code=400,
                violations=["missing_configuration"]
            )
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        try:
            # 1. Parse the incoming input_data (which is a string, likely JSON)
            parsed_input_data: Any
            try:
                parsed_input_data = json.loads(inp.input_data)
            except json.JSONDecodeError:
                # If not JSON, treat it as a plain string
                parsed_input_data = inp.input_data
            
            # Prepare data for Jinja2 rendering
            template_context = {
                "input_data": parsed_input_data,
                "config": inp.config, # Node's own config
                "context": inp.context, # Workflow context
                "metadata": inp.metadata # Workflow metadata
            }

            # 2. Get the mapping template and output format from node properties
            props = self._get_node_config(inp.trace_id, inp.config) # Ensure we get instance properties
            mapping_template = props.get("mapping_template", "{{ input_data }}")
            output_format = props.get("output_format", "json")

            # 3. Resolve variables using the Jinja2 template
            # If it's a string that looks like a JSON template, try parsing it to a dict first
            # so _resolve_variables can recurse through it.
            try:
                template_obj = json.loads(mapping_template)
            except (json.JSONDecodeError, TypeError):
                template_obj = mapping_template

            transformed_data = self._resolve_variables(template_obj, template_context)

            # 4. Format the output based on the selected output_format
            final_output_data: str
            if output_format == "json":
                if isinstance(transformed_data, (dict, list)):
                    final_output_data = json.dumps(transformed_data)
                else:
                    # If template result is not dict/list, try to JSON serialize it
                    try:
                        final_output_data = json.dumps(transformed_data)
                    except TypeError:
                        final_output_data = str(transformed_data) # Fallback to string
            else: # output_format == "string"
                final_output_data = str(transformed_data)

            return NodeOutput(
                trace_id=inp.trace_id,
                output_data=final_output_data,
                status="success",
                metadata={"transformed_from": inp.input_data}
            )

        except Exception as e:
            self.logger.error("transform_node_execution_failed", error=str(e), trace_id=inp.trace_id)
            return NodeOutput(
                trace_id=inp.trace_id,
                output_data=inp.input_data, # Return original input on failure
                status="failure",
                error_message=f"Data transformation failed: {str(e)}",
                error_code=500
            )