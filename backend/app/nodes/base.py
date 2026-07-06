import abc
import json
import time
from functools import cached_property
from typing import Any, Dict, List, Optional, Union, Set
from pydantic import BaseModel, Field, ConfigDict, PrivateAttr
try:
    from jinja2.nativetypes import NativeTemplate
except ImportError:
    # Fallback to standard Template if nativetypes is unavailable
    from jinja2 import Template as NativeTemplate
import structlog
from app.nodes.properties import property_entries_to_dict
from app.core.types.common import NodeInput,NodeOutput
from app.nodes.contracts import validate_input_contract as validate_contract

class JinjaFallbackDict(dict):
    def __init__(self, fallback_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallback_value = fallback_value
        self._protected = {
            'range', 'dict', 'lipsum', 'cycler', 'joiner', 'namespace',
            'true', 'false', 'none', 'True', 'False', 'None',
            'context', 'metadata', 'config', 'loop', 'self'
        }

    def _should_fallback(self, key: str) -> bool:
        if key in self._protected:
            return False
        # Avoid overriding python built-ins
        import builtins
        if hasattr(builtins, key):
            return False
        return isinstance(self.fallback_value, (str, int, float))

    def __getitem__(self, key):
        if key in self:
            return super().__getitem__(key)
        if self._should_fallback(key):
            return self.fallback_value
        raise KeyError(key)

    def get(self, key, default=None):
        if key in self:
            return super().get(key)
        if self._should_fallback(key):
            return self.fallback_value
        return default

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        return self._should_fallback(key)

class BaseNode(BaseModel, abc.ABC):
    """
    Standardized Base Class for all Enterprise LLM Gateway nodes.

    --- DISTINCTION BETWEEN PROPERTIES AND CONTRACTS ---
    1. User Properties (properties ):
       Business logic settings configured by users in the Workflow Builder.
       Example: 'system_prompt', 'temperature', 'table_name'.

    2. System Properties (system_properties):
       Infrastructure settings configured by Admins in the Node Registry.
       Example: 'port', 'host', 'worker_count', 'timeout_ms'.

    3. Contracts (input_contract & output_contract):
       These define the DATA PAYLOAD structure (Run-time).
       Example: 'user_query', 'document_text', 'extracted_entities'.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "base_node"       # Machine identifier
    label: str = "Base Node"      # UI-facing display name (matches frontend 'label')
    description: str = "Standard node base"
    version: str = "1.0.0"
    category: str = "Custom"       # Internal functional category
    node_type: str = "default"     # trigger, tool, connector, or default
    group: str = "Custom"          # UI grouping (matches frontend 'group')

    # Contract and Envelope definitions
    input_contract: Dict[str, Any] = Field(default_factory=dict) # e.g. {"user_id": {"required": True}}
    output_contract: Dict[str, Any] = Field(default_factory=dict) # e.g. {"result": {"type": "string"}}

    # Visual properties for the UI (aligned with frontend BaseNodeData)
    icon: str = "bot"              # Name of the icon to be mapped in frontend
    color: str = "#5E0CEC"         # Brand color (hex code)
    badge: Optional[str] = "Node"  # Optional badge text (e.g., "Model")
    sub_label: Optional[str] = None # Optional sub-label
    user_properties: Dict[str, Any] = Field(default_factory=dict) # Default configuration values
    system_properties: Dict[str, Any] = Field(default_factory=dict) # Admin-only infra settings
    properties: Dict[str, Any] = Field(default_factory=dict) # Unified properties list

    @cached_property
    def logger(self):
        """
        Returns a logger named after the node class with the node name bound to it.
        This allows all inheriting nodes to use self.logger without manual setup.
        """
        return structlog.get_logger(self.__class__.__name__).bind(node_name=self.name)

    def get_label(self) -> str:
        return self.label

    def get_name(self) -> str:
        return self.name

    def get_description(self) -> str:
        return self.description

    def get_properties(self) -> List[Dict[str, Any]]:
        """Returns the property schema definition for the UI."""
        return getattr(self, "user_properties")

    async def _get_db_node_data(self) -> Dict[str, Any]:
        """Fetches properties for this node type from the global catalog in the DB."""
        import sys
        if "pytest" in sys.modules:
            return {}
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.db_models import NodeDB
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                stmt = select(NodeDB).where(NodeDB.name == self.name)
                result = await session.execute(stmt)
                db_node = result.scalar_one_or_none()
                if db_node:
                    return {
                        "user_properties": db_node.user_properties or {},
                        "system_properties": db_node.system_properties or {},
                        "input_contract": db_node.input_contract or {},
                        "output_contract": db_node.output_contract or {},

                    }
        except Exception as e:
            self.logger.warning("db_properties_fetch_failed", error=str(e))
        return {}

    @abc.abstractmethod
    async def init(self) -> None:
        """
        Initializes the node. Default implementation loads properties from DB.
        Should be called during registration/discovery.
        """
        self.logger.info(f"Initiating node start {self.name}")

        user_props_dict = property_entries_to_dict(self.user_properties)
        system_props_dict = property_entries_to_dict(self.system_properties)

        db_data = await self._get_db_node_data()
        if db_data:
            if db_data.get("user_properties"):
                user_props_dict.update(property_entries_to_dict(db_data.get("user_properties")))
            if db_data.get("system_properties"):
                system_props_dict.update(property_entries_to_dict(db_data.get("system_properties")))
            if db_data.get("input_contract"):
                self.input_contract = db_data.get("input_contract")
            if db_data.get("output_contract"):
                self.output_contract = db_data.get("output_contract")

        self.user_properties = user_props_dict
        self.system_properties = system_props_dict

        # Unified merge: User properties override System properties
        self.properties = {**self.system_properties, **self.user_properties}
        self.logger.info(f"Initiating node ended {self.name}")

    def _resolve_dotted_path(self, dotted_path: str, obj: Any) -> Any:
        """Helper to navigate a dotted path (e.g. 'foo.bar') within a dict/object."""
        parts = [p.strip() for p in dotted_path.split('.') if p.strip()]
        current = obj
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
        return current

    def _extract_list_values(self, expr: str, context: Dict[str, Any]) -> Optional[List[Any]]:
        """
        Extracts values from lists using json-path-like syntax (e.g. 'root[].date').
        """
        # Strip outer quotes if any
        path = expr.strip().strip("'\"")

        if '[]' not in path:
            return None

        left_part, right_part = path.split('[]', 1)
        left_part = left_part.strip()
        right_part = right_part.strip()

        # Get field name to extract from list items (e.g. "date")
        if right_part.startswith('.'):
            field_name = right_part[1:]
        else:
            field_name = right_part

        target_list = None

        # 1. Try to resolve left_part in context
        if left_part:
            target_list = self._resolve_dotted_path(left_part, context)
            if target_list is None:
                # Try context["input_data"] or context["data"]
                for candidate in ["input_data", "data"]:
                    cand_ctx = context.get(candidate)
                    if cand_ctx:
                        target_list = self._resolve_dotted_path(left_part, cand_ctx)
                        if target_list is not None:
                            break

        # 2. If target_list is still None, search standard roots
        if target_list is None or not isinstance(target_list, list):
            for candidate in ["input_data", "data"]:
                cand_ctx = context.get(candidate)
                if isinstance(cand_ctx, list):
                    target_list = cand_ctx
                    break
                elif isinstance(cand_ctx, dict):
                    if left_part and left_part in cand_ctx and isinstance(cand_ctx[left_part], list):
                        target_list = cand_ctx[left_part]
                        break
                    elif 'data' in cand_ctx and isinstance(cand_ctx['data'], list):
                        target_list = cand_ctx['data']
                        break
                    elif 'root' in cand_ctx and isinstance(cand_ctx['root'], list):
                        target_list = cand_ctx['root']
                        break

        # 3. If target_list is still None, try check context directly
        if target_list is None or not isinstance(target_list, list):
            if isinstance(context, list):
                target_list = context
            elif isinstance(context, dict):
                for v in context.values():
                    if isinstance(v, list):
                        target_list = v
                        break

        if not isinstance(target_list, list):
            return None

        # 4. Extract values from list items
        result = []
        for item in target_list:
            if isinstance(item, dict):
                if field_name:
                    val = self._resolve_dotted_path(field_name, item)
                    result.append(val)
                else:
                    result.append(item)
            else:
                result.append(item)
        return result

    def _resolve_single_expression(self, expr: str, context: Dict[str, Any]) -> Any:
        """
        Resolves a single template expression against the given context.
        """
        expr = expr.strip()
        lookup_expr = self._normalize_lookup_expression(expr)

        # Support root[].field or similar path extraction
        if '[]' in lookup_expr:
            resolved = self._extract_list_values(lookup_expr, context)
            if resolved is not None:
                return resolved

        # Try to resolve directly via dotted path lookup first
        # (e.g. input_data.text or user_question)
        if '.' in lookup_expr or lookup_expr in context:
            if not any(c in lookup_expr for c in ['"', "'", '(', ')']):
                resolved = self._resolve_dotted_path(lookup_expr, context)
                if resolved is not None:
                    return resolved

        # Otherwise, fall back to standard Jinja NativeTemplate render
        try:
            from jinja2.nativetypes import NativeTemplate
            from jinja2 import Undefined
            tpl = NativeTemplate(f"{{{{ {expr} }}}}")
            rendered = tpl.render(**context)
            if isinstance(rendered, Undefined):
                return None
            return rendered
        except Exception as e:
            self.logger.warning("jinja_expression_render_failed", expr=expr, error=str(e))
            return None

    def _normalize_lookup_expression(self, expr: str) -> str:
        """
        Treat quoted field references like "stock_token" as stock_token.
        Literal strings still fall back to Jinja rendering if no matching field exists.
        """
        import re

        stripped = expr.strip()
        if len(stripped) < 2 or stripped[0] != stripped[-1] or stripped[0] not in {"'", '"'}:
            return stripped

        unquoted = stripped[1:-1].strip()
        if re.match(r"^[A-Za-z_]\w*(?:\[\])?(?:\.[A-Za-z_]\w*(?:\[\])?)*$", unquoted):
            return unquoted
        return stripped

    def transpose_resolved_value(self, val: Any) -> Any:
        """
        Transposes resolved list/dict template values if they refer to list attributes.
        """
        if isinstance(val, dict):
            # Check if this dict should be transposed
            db_keys = {"query", "query_type", "sql_query", "table_name"}
            if db_keys.intersection(val.keys()):
                return val

            # Check if we have values that are lists of the same length N > 0
            list_values = [v for v in val.values() if isinstance(v, list)]
            if list_values and len(set(len(x) for x in list_values)) == 1:
                n = len(list_values[0])
                if n > 0:
                    keys = list(val.keys())
                    transposed = []
                    for i in range(n):
                        item = {}
                        for k in keys:
                            v = val[k]
                            if isinstance(v, list) and len(v) == n:
                                item[k] = v[i]
                            else:
                                item[k] = v
                        transposed.append(item)
                    return transposed

        elif isinstance(val, list) and val:
            # Check if all elements are lists of the same length N > 0
            if all(isinstance(x, list) for x in val) and len(set(len(x) for x in val)) == 1:
                n = len(val[0])
                if n > 0:
                    return [list(x) for x in zip(*val)]

        return val

    def _resolve_variables(self, template: Any, data: Dict[str, Any]) -> Any:
        """
        Recursively resolves variables using simple {{ key }} replacement.
        """
        import re
        if isinstance(template, dict):
            return {k: self._resolve_variables(v, data) for k, v in template.items()}
        elif isinstance(template, list):
            if len(template) == 1:
                item_tpl = template[0]
                resolved_item = self._resolve_variables(item_tpl, data)
                if isinstance(resolved_item, dict):
                    db_keys = {"query", "query_type", "sql_query", "table_name"}
                    if not db_keys.intersection(resolved_item.keys()):
                        list_values = [v for v in resolved_item.values() if isinstance(v, list)]
                        if list_values and len(set(len(x) for x in list_values)) == 1:
                            n = len(list_values[0])
                            if n > 0:
                                keys = list(resolved_item.keys())
                                transposed = []
                                for i in range(n):
                                    item = {}
                                    for k in keys:
                                        v = resolved_item[k]
                                        if isinstance(v, list) and len(v) == n:
                                            item[k] = v[i]
                                        else:
                                            item[k] = v
                                    transposed.append(item)
                                return transposed
                elif isinstance(resolved_item, list) and resolved_item:
                    if all(isinstance(x, list) for x in resolved_item) and len(set(len(x) for x in resolved_item)) == 1:
                        n = len(resolved_item[0])
                        if n > 0:
                            return [list(x) for x in zip(*resolved_item)]
                return [resolved_item]
            else:
                return [self._resolve_variables(i, data) for i in template]
        elif isinstance(template, str) and self._has_template(template):
            # Match exactly {{key}}
            match = re.match(r"^\{\{\s*(.*?)\s*\}\}$", template.strip())
            if match:
                expr = match.group(1)
                resolved = self._resolve_single_expression(expr, data)
                if resolved is not None:
                    return resolved
                return template

            # Match mixed strings like "q={{key}}"
            pattern = re.compile(r"\{\{\s*(.*?)\s*\}\}")
            def replace_match(m):
                expr = m.group(1)
                resolved = self._resolve_single_expression(expr, data)
                if resolved is not None:
                    if isinstance(resolved, (list, dict)):
                        return json.dumps(resolved)
                    return str(resolved)
                return m.group(0)
            return pattern.sub(replace_match, template)
        return template

    def _has_template(self, val: Any) -> bool:
        """Recursively checks if a value contains a template string."""
        if isinstance(val, str):
            return "{{" in val and "}}" in val
        elif isinstance(val, dict):
            return any(self._has_template(v) for v in val.values())
        elif isinstance(val, list):
            return any(self._has_template(i) for i in val)
        return False

    def is_jinja_template(text: str) -> bool:
        """Check if string contains Jinja2 template syntax"""
        return "{{" in text and "}}" in text

    def _render_template_sets(template: List[str], render_context: List[Dict[str, Any]]) -> List[Set[Any]]:
        result = []
        for context in render_context:
            row_set: Set[Any] = set()
            
            for tmpl_str in template:
                if is_jinja_template(tmpl_str):
                    # Render with Jinja2
                    t = Template(tmpl_str)
                    resolved = t.render(**context)
                    # Try to convert to proper type (e.g. "25" → 25)
                    try:
                        if resolved.isdigit():
                            resolved = int(resolved)
                        elif resolved.replace('.', '', 1).isdigit():
                            resolved = float(resolved)
                    except:
                        pass
                else:
                    # Static value - keep as is
                    resolved = tmpl_str
                
                row_set.add(resolved)
            
            result.append(row_set)
    
  
    def _resolve_jinja_templates(self, template: Any, render_context: Dict[str, Any]) -> Any:
        """
        Recursively resolves variables using Jinja2 NativeTemplate to preserve types.
        """
        if isinstance(template, dict):
            return {k: self._resolve_jinja_templates(v, render_context) for k, v in template.items()}
        elif isinstance(template, list):
            values = self._render_template_sets(template, render_context)
            return values
        elif isinstance(template, str) and "{{" in template and "}}" in template:
            import re
            match = re.match(r"^\{\{\s*(.*?)\s*\}\}$", template.strip())
            if match:
                expr = match.group(1)
                resolved = self._resolve_single_expression(expr, render_context)
                if resolved is not None:
                    return resolved
                return template

            # Match mixed strings
            pattern = re.compile(r"\{\{\s*(.*?)\s*\}\}")
            def replace_match(m):
                expr = m.group(1)
                resolved = self._resolve_single_expression(expr, render_context)
                if resolved is not None:
                    if isinstance(resolved, (list, dict)):
                        return json.dumps(resolved)
                    return str(resolved)
                return m.group(0)
            try:
                return pattern.sub(replace_match, template)
            except Exception as e:
                self.logger.warning("jinja_template_render_failed", template=template, error=str(e))
                return template
        return template



    async def validate_input_contract(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Validates if the input matches the defined input_contract.
        Checks mandatory fields and data types in the JSON body passed to the node.
        Returns a NodeOutput with failure status if validation fails, otherwise None.
        """
        self.logger.info("Starting validate_input_contract", name= self.name)
        schema = inp.input_schema if getattr(inp, "input_schema", None) is not None else self.input_contract
        if not schema:
            self.logger.debug("No schema found", name= self.name, schema=schema)
            return None

        errors = validate_contract(schema, inp, self.name)

        if errors:
            self.logger.error(f"Ending validation of validate_input_contract",name= self.name, inp_data=inp.data,errors= "; ".join(errors))
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message="; ".join(errors),
                error_code=400,
                violations=["contract_violation"]
            )

        return None

    async def validate_output_contract(self, inp: NodeInput, output: NodeOutput) -> Optional[NodeOutput]:
        """
        Validates if the output matches the defined output_contract.
        Checks mandatory fields and data types in the JSON body returned by the node.
        """
        self.logger.info("Starting validate_output_contract", name=self.name)
        schema = inp.output_schema if getattr(inp, "output_schema", None) is not None else self.output_contract
        if not schema:
            self.logger.debug("No output schema found", name=self.name, schema=schema)
            return None

        from app.nodes.contracts import validate_output_contract

        errors = validate_output_contract(
            schema,
            output,
            self.name,
            context_nodes=inp.context.get("nodes", {})
        )

        if errors:
            self.logger.error(f"Ending validation of validate_output_contract", name=self.name, out_data=output.data, errors="; ".join(errors))
            output.status = "failure"
            output.error_message = "; ".join(errors)
            output.error_code = 400
            if "contract_violation" not in output.violations:
                output.violations.append("contract_violation")

        return None

    def get_input_data(self, inp: NodeInput) -> Any:
        """
        Extracts the inner value of the 'data' parameter from the incoming payload.
        Handles both wrapped JSON structures and raw inputs gracefully.
        """
        if not inp.data:
            return None
        try:
            parsed = json.loads(inp.data)
            if isinstance(parsed, dict) and "data" in parsed:
                return parsed["data"]
            return parsed
        except Exception:
            return inp.data

    def set_output_data(self, inp: NodeInput, new_data: Any) -> str:
        """
        Wraps the output value inside the 'data' parameter key, preserving
        any other top-level keys in the envelope if they exist.
        """
        try:
            parsed = json.loads(inp.data)
            if isinstance(parsed, dict) and "data" in parsed:
                parsed["data"] = new_data
                return json.dumps(parsed)
        except Exception:
            pass
        return json.dumps({"data": new_data})

    def transform_strings(self, val: Any, func) -> Any:
        """
        Recursively traverses a JSON-compatible structure (dict, list, string)
        and transforms all string values using the provided function.
        """
        if isinstance(val, str):
            return func(val)
        elif isinstance(val, dict):
            return {k: self.transform_strings(v, func) for k, v in val.items()}
        elif isinstance(val, list):
            return [self.transform_strings(item, func) for item in val]
        return val

    def collect_strings(self, val: Any) -> List[str]:
        """
        Recursively traverses a JSON-compatible structure (dict, list, string)
        and collects all string values in a flat list.
        """
        strings = []
        def _collect(v):
            if isinstance(v, str):
                strings.append(v)
            elif isinstance(v, dict):
                for val_item in v.values():
                    _collect(val_item)
            elif isinstance(v, list):
                for item in v:
                    _collect(item)
        _collect(val)
        return strings

    @abc.abstractmethod
    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """
        Optional validation logic. Can be overridden by nodes to perform
        pre-execution checks.
        """
        return None

    @abc.abstractmethod
    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        The core logic implementation for the node.
        This is the single abstract method to be implemented by child classes.
        """
        pass

    async def run(self, inp: NodeInput) -> NodeOutput:
        """
        The standardized execution lifecycle for every node in the system.

        Execution Steps:
        1. Property Resolution: Merges static node properties with runtime workflow config.
        2. Validation: Executes pre-flight checks (validate_input).
        3. Execution: Runs the core business logic (execute).
        4. Observability: Captures latency, start/end times, and status.
        5. Error Handling: Gracefully catches exceptions and returns a failure NodeOutput.

        Returns:
            NodeOutput: The standardized result containing content, status, and metadata.
        """
        self.logger.info("node_run_started", name = self.name, trace_id=inp.trace_id)
        start_ts = time.time()
        try:
            # Store trace_id in context for observability
            if inp.context is None:
                inp.context = {}

            # 0. Resolve properties: (Registry Defaults enriched by init) < Workflow Config
            inp.config = {**self.properties, **inp.config}

            # 0.05 Parse input_data
            input_data = {}
            if inp.data:
                try:
                    input_data = json.loads(inp.data)
                except Exception:
                    input_data = inp.data

            # 0.06 Get mappings from config
            mapping_config = inp.config.get("mapping_template") or inp.config.get("input_mappings")
            if mapping_config:
                if isinstance(mapping_config, str):
                    try:
                        mapping_config = json.loads(mapping_config)
                    except Exception:
                        pass

            if isinstance(mapping_config, dict):
                mapping_config = {k: v for k, v in mapping_config.items() if not k.startswith('_')}

            # Determine mapped_data (before template resolution)
            mapped_data = mapping_config if mapping_config else input_data

            # 0.07 Check for mandatory fields defined in contract
            schema = inp.input_schema if getattr(inp, "input_schema", None) is not None else self.input_contract
            from app.nodes.contracts import normalize_contract, _required_fields
            normalized_schema = normalize_contract(schema) if schema else {}
            required_fields = _required_fields(normalized_schema) if normalized_schema else []

            if required_fields:
                if not isinstance(mapped_data, dict):
                    missing = required_fields
                else:
                    check_data = mapped_data
                    if "data" in mapped_data and isinstance(mapped_data["data"], dict) and "data" not in normalized_schema.get("properties", {}):
                        check_data = mapped_data["data"]
                    elif "input_data" in mapped_data and isinstance(mapped_data["input_data"], dict) and "input_data" not in normalized_schema.get("properties", {}):
                        check_data = mapped_data["input_data"]
                    
                    missing = [f for f in required_fields if f not in check_data]

                if missing:
                    errors = [f"$.{f} is mandatory" for f in missing]
                    return NodeOutput(
                        trace_id=inp.trace_id,
                        data=inp.data,
                        status="failure",
                        error_message="; ".join(errors),
                        error_code=400,
                        violations=["contract_violation"]
                    )

            # 0.08 If mappings exist and mandatory fields are present, replace templates with the input_data
            if mapping_config:
                try:
                    render_context = {
                        "data": input_data,
                        "input_data": input_data,
                        **(input_data if isinstance(input_data, dict) else {}),
                        "nodes": inp.context.get("nodes", {}),
                        "state": inp.context.get("state", {}),
                    }

                    # find and replace all templates in mapping_config
                    resolved_mapped_data = self._resolve_jinja_templates(mapping_config, render_context)

                    # find and replace all templates in properties / config
                    resolved_config = self._resolve_jinja_templates(inp.config, render_context)
                    inp.data = json.dumps(resolved_mapped_data)
                    inp.config = resolved_config
                except Exception as e:
                    self.logger.error("failed_to_resolve_mapping_templates", error=str(e))

            # 0.1 Input Contract Validation
            contract_output = await self.validate_input_contract(inp)
            if contract_output:
                return contract_output


            # 2. Execution logic
            self.logger.info(f"Node execution started {self.name}",trace_id=inp.trace_id)
            output = await self.execute(inp)

            end_ts = time.time()
            self.logger.info(f"Node execution completed {self.name}",trace_id=inp.trace_id)
            # Enrich output with tracking data
            output.start_time = start_ts
            output.end_time = end_ts
            output.latency_ms = round((end_ts - start_ts) * 1000, 2)

            # # 3. Apply Output Envelope if execution was successful
            # if not output.error_message and not output.violations:
            #     output.output_data = self.apply_output_envelope(output.output_data, inp)

            # Output Contract Validation
            if not output.error_message and not output.violations:
                await self.validate_output_contract(inp, output)

            output.status = "failure" if output.error_message or output.violations else "success"

            self.logger.info(
                "node_run_completed",
                name=self.name,
                status=output.status, function_name=__name__,
                latency_ms=output.latency_ms,
                #output=output.model_dump()
            )
            return output

        except Exception as e:
            end_ts = time.time()
            self.logger.error(
                "node_run_exception",
                name=self.name,
                error=str(e),
                trace_id=inp.trace_id,
                input=inp.model_dump()
            )
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                error_code=500,
                status="failure",
                error_message=str(e),
                start_time=start_ts,
                end_time=end_ts,
                latency_ms=round((end_ts - start_ts) * 1000, 2)
            )

class TriggerNode(BaseNode, abc.ABC):
    """
    A specialized node type that sits at the start of a workflow graph.

    Unlike standard nodes, TriggerNodes:
    1. Are "activated" on system startup to listen for external events.
    2. Can initiate the WorkflowExecutor when an event (Webhook/Timer/Email) occurs.
    3. Manage an internal registry of workflow configurations they are responsible for.
    """
    node_type: str = "TRIGGER"

    async def init(self) -> None:
        """Triggers should still load their properties from the database."""
        self.logger.info(
                        "Trigger node init started",
                        name=self.name
                    )
        await super().init()
        self.logger.info(
                        "Trigger node init ended",
                        name=self.name,
                    )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """Default trigger execution just passes the input payload through."""
        self.logger.info(
                        "Trigger node execution  started",
                        name=self.name,
                        trace_id=inp.trace_id,
                    )
        return NodeOutput(trace_id=inp.trace_id, data=inp.data)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        # Triggers can choose to implement validation if needed, but by default they don't block execution
        return None

    # Internal registry to map specific node instances (by agent_node_id)
    # to their parent workflow configurations.
    _workflows: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]) -> None:
        """
        Registers a specific workflow instance to this trigger agent.

        This method is critical for triggers (like Webhooks or Schedulers) to know
        which workflow graph to execute when an external event occurs.

        Args:
            agent_node_id: The unique ID of the trigger node within the specific workflow.
            workflow_config: The full JSON definition of the workflow to be executed.
        """
        self.logger.info(
                        "Trigger node  activation started",
                        name=self.name
                    )
        self._workflows[agent_node_id] = workflow_config

        # Global node properties are loaded in init()
        # Instance properties should be resolved using _get_node_config() when needed
        self.logger.debug("workflow_registered_to_trigger",
                          name=self.name,
                         workflow_id=workflow_config.get("id"))

    async def execute_dynamic_agent(self, agent_node_id: str, payload: Any, trace_id: Optional[str] = None):
        """
        Unified implementation for all triggers to initiate workflow execution.
        This method builds the langgraph flow via the executor and starts it.
        It retrieves the workflow_config from the internal _workflows registry.
        """
        from app.workflows.executor import WorkflowExecutor
        # Generate a trace ID if not provided, prefixed by node name for observability

        self.logger.debug("execute_dynamic_agent started",
                          name=self.name,
                         workflow_id=agent_node_id)

        t_id = trace_id or f"{self.name}-{int(time.time())}"

        # Retrieve the workflow config for this specific agent_node_id
        workflow_config = self._workflows.get(agent_node_id)
        if not workflow_config:
            self.logger.warning("dynamic_agent_execution_failed_no_workflow_config", agent_node_id=agent_node_id, trace_id=t_id)
            return None

        # Trigger the workflow execution via the central executor logic
        try:
            self.logger.debug("WorkflowExecutor started",
                          name=self.name,
                         workflow_id=workflow_config.get("id"))

            executor = WorkflowExecutor(workflow_config)

            # Ensure payload is wrapped under the "data" key to conform to standard input envelope
            wrapped_payload = None
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict) and "data" in parsed:
                        wrapped_payload = parsed
                    else:
                        wrapped_payload = {"data": parsed}
                except Exception:
                    wrapped_payload = {"data": payload}
            elif isinstance(payload, dict):
                if "data" in payload:
                    wrapped_payload = payload
                else:
                    wrapped_payload = {"data": payload}
            else:
                wrapped_payload = {"data": payload}

            content = json.dumps(wrapped_payload)
            self.logger.debug("WorkflowExecutor ended",
                          name=self.name,
                         workflow_id=workflow_config.get("id"))

            return await executor.execute_async(content, t_id)
        except Exception as e:
            self.logger.error("dynamic_agent_execution_crashed",name=self.name, error=str(e), trace_id=t_id)
            return None
