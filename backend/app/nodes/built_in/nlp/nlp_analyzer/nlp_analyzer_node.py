import json
import re
from typing import Any, Dict, List, Optional
import httpx
import structlog

from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import BaseNode

logger = structlog.get_logger("NLPQueryAnalyzerNode")


class NLPQueryAnalyzerNode(BaseNode):
    """
    Pure LLM-Driven NLP Query Analyzer Node.
    - Model & credentials derived automatically from tenant LLM Profile (llm_profile_id).
    - Takes output JSON schema directly from system prompt or combines output_format.
    - LLM decides 100% of intent, entities, and field values.
    - Output contract is a pure, flexible JSON object for direct downstream branching (Condition Node)
      and SQL query generation (MySQL Node).
    """

    name: str = "nlp_query_analyzer"
    label: str = "NLP Query Analyzer"
    description: str = "Pure LLM-driven NLU: extracts developer-defined JSON fields, intent, and context from user query."
    version: str = "1.2.0"
    category: str = "NLP"
    group: str = "NLP"

    async def init(self) -> None:
        await super().init()
        self.logger.info("nlp_query_analyzer_initialized", name=self.name, version=self.version)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        await super().validate_input(inp)
        query = self._extract_query(inp)
        if not query:
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=400,
                error_message="Missing required field 'query' in input."
            )
        return None

    def _extract_query(self, inp: NodeInput) -> Optional[str]:
        """Strictly extracts 'query' field. No fallback to text or message."""
        data_val = self.get_input_data(inp)
        if isinstance(data_val, str):
            val = data_val.strip()
            return val if val else None
        if isinstance(data_val, dict):
            val = data_val.get("query")
            if isinstance(val, str) and val.strip():
                return val.strip()
            return None
        return None

    def _resolve_customer_id(self, inp: NodeInput) -> Optional[str]:
        """Resolves tenant/customer id from execution context."""
        context = inp.context or {}
        user_data = context.get("user_data") or {}
        return (
            user_data.get("customer_id")
            or context.get("customer_id")
            or context.get("tenant_id")
            or self.customer_id
        )

    async def _resolve_llm_credentials(self, inp: NodeInput) -> tuple[str, str, str]:
        """Derives base_url, api_key, model from llm_profile_id / CustomerDB settings."""
        config = inp.config or {}
        customer_id = self._resolve_customer_id(inp)
        profile_identifier = (
            config.get("llm_profile_id")
            or config.get("profile_id")
            or config.get("profile_name")
            or self.properties.get("llm_profile_id")
            or self.properties.get("profile_name")
        )

        profile_config: Dict[str, Any] = {}
        tenant_settings: Dict[str, Any] = {}

        if customer_id is not None or profile_identifier:
            try:
                from app.core.database import AsyncSessionLocal
                from app.core.profile_resolver import ProfileResolver
                async with AsyncSessionLocal() as session:
                    resolver = ProfileResolver(db=session)
                    resolved = await resolver.resolve_execution_context(
                        profile_id=str(profile_identifier) if profile_identifier else None,
                        customer_id=str(customer_id) if customer_id else "1",
                        model_type="generation"
                    )
                    if resolved:
                        profile_config = resolved
            except Exception as e:
                self.logger.debug("profile_resolution_deferred", error=str(e))

        base_url = (
            config.get("base_url")
            or profile_config.get("base_url")
            or tenant_settings.get("llm_base_url")
            or self.properties.get("base_url")
            or "http://127.0.0.1:11434"
        )
        api_key = (
            config.get("api_key")
            or profile_config.get("api_key")
            or tenant_settings.get("llm_api_key")
            or self.properties.get("api_key")
            or ""
        )
        model = (
            profile_config.get("model_name")
            or config.get("model")
            or config.get("model_name")
            or tenant_settings.get("llm_model")
            or self.properties.get("model")
            or self.properties.get("default_model")
            or "llama3.2"
        )
        return str(base_url).rstrip("/"), str(api_key), str(model)

    def _extract_json_template_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Finds and parses any embedded JSON block in the prompt text."""
        # 1. Try markdown code block ```json ... ```
        code_block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except Exception:
                pass
        # 2. Try raw outer braces {...}
        brace_match = re.search(r"(\{[\s\S]*\})", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except Exception:
                pass
        return None

    def _build_combined_system_prompt(
        self,
        system_prompt: str,
        output_format: Optional[Dict[str, Any]]
    ) -> str:
        """
        Combines system prompt with JSON output format.
        If output_format provided, merges into prompt. If not, enforces JSON output.
        """
        schema_dict = output_format or {}
        if not schema_dict:
            found = self._extract_json_template_from_text(system_prompt)
            if found:
                schema_dict = found

        if schema_dict:
            schema_str = json.dumps(schema_dict, indent=2)
            if schema_str in system_prompt:
                return (
                    f"{system_prompt}\n\n"
                    "STRICT REQUIREMENT: Reply ONLY in valid JSON matching the exact schema above. No prose, no markdown fences."
                )
            else:
                return (
                    f"{system_prompt}\n\n"
                    "You MUST reply strictly in valid JSON matching this exact structure:\n"
                    f"{schema_str}\n\n"
                    "STRICT RULES:\n"
                    "1. Return ONLY the JSON object with the exact keys defined above.\n"
                    "2. For each key, extract or deduce the value from the user query. If absent, set value to null or empty string.\n"
                    "3. Output no other text or explanation."
                )

        return (
            f"{system_prompt}\n\n"
            "STRICT REQUIREMENT: Reply strictly in valid JSON format representing the extracted fields and intent."
        )

    async def execute(self, inp: NodeInput) -> NodeOutput:
        query = self._extract_query(inp) or ""
        config = inp.config or {}
        input_payload = self.get_input_data(inp)

        history: List[Dict[str, str]] = []
        system_prompt_override: Optional[str] = None
        output_format_override = None

        if isinstance(input_payload, dict):
            history = input_payload.get("history") or []
            system_prompt_override = input_payload.get("system_prompt_override")
            output_format_override = input_payload.get("output_format")

        base_system_prompt = (
            system_prompt_override
            or config.get("system_prompt")
            or self.properties.get("system_prompt")
            or "You are an expert NLP Context & Intent Analyzer."
        )

        # Resolve output format if provided
        output_format_raw = (
            output_format_override
            or config.get("output_format")
            or self.properties.get("output_format")
            or {}
        )
        output_format: Dict[str, Any] = {}
        if isinstance(output_format_raw, dict):
            output_format = output_format_raw
        elif isinstance(output_format_raw, list):
            output_format = {str(k): "" for k in output_format_raw}
        elif isinstance(output_format_raw, str) and output_format_raw.strip():
            try:
                parsed_fmt = json.loads(output_format_raw)
                if isinstance(parsed_fmt, dict):
                    output_format = parsed_fmt
                elif isinstance(parsed_fmt, list):
                    output_format = {str(k): "" for k in parsed_fmt}
            except Exception:
                output_format = {x.strip(): "" for x in output_format_raw.split(",") if x.strip()}

        # Combine system prompt with schema
        final_system_prompt = self._build_combined_system_prompt(
            base_system_prompt, output_format
        )

        # Resolve LLM credentials and execute model
        try:
            base_url, api_key, model = await self._resolve_llm_credentials(inp)
            analysis_result = await self._execute_llm_analysis(
                query, final_system_prompt, history, base_url, api_key, model, config
            )
        except Exception as e:
            self.logger.error("nlp_llm_execution_failed", trace_id=inp.trace_id, error=str(e))
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=502,
                error_message=f"LLM execution failed: {str(e)}"
            )

        # Return LLM response as-is in exact format requested by user
        return NodeOutput(
            trace_id=inp.trace_id,
            data=json.dumps(analysis_result, indent=2) if isinstance(analysis_result, (dict, list)) else str(analysis_result),
            status="success"
        )

    async def _execute_llm_analysis(
        self,
        query: str,
        system_instruction: str,
        history: List[Dict[str, str]],
        base_url: str,
        api_key: str,
        model: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Direct LLM execution with JSON format constraint and retries."""
        timeout_seconds = float(config.get("timeout_seconds") or self.properties.get("timeout_seconds") or 15)
        max_retries = int(config.get("max_retries") or self.properties.get("max_retries") or 1)
        user_content = f"User Query:\n\"\"\"{query}\"\"\""

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_instruction}
        ]

        for turn in history:
            if isinstance(turn, dict) and "content" in turn and turn["content"]:
                role = turn.get("role", "user")
                if role not in ("system", "user", "assistant"):
                    role = "user"
                messages.append({"role": role, "content": str(turn.get("content"))})

        messages.append({"role": "user", "content": user_content})

        if "chat/completions" in base_url:
            endpoint = base_url
        elif "api/chat" in base_url:
            endpoint = base_url
        else:
            endpoint = f"{base_url}/api/chat"

        headers = {"Content-Type": "application/json"}
        if api_key and api_key.strip() and api_key not in ("ollama", "EMPTY"):
            headers["Authorization"] = f"Bearer {api_key.strip()}"

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0}
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    resp = await client.post(endpoint, headers=headers, json=payload)
                    resp.raise_for_status()
                    res_json = resp.json()
                    break
            except Exception as e:
                last_error = e
                if attempt == max_retries:
                    raise last_error

        content_str = ""
        if "message" in res_json and "content" in res_json["message"]:
            content_str = res_json["message"]["content"]
        elif "choices" in res_json and len(res_json["choices"]) > 0:
            content_str = res_json["choices"][0].get("message", {}).get("content", "")
        elif "response" in res_json:
            content_str = res_json["response"]

        return json.loads(content_str)
