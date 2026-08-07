"""
Payload Builder Utility.

Dynamically constructs API request payloads for different LLM providers
(OpenAI, Ollama, Anthropic, vLLM, Grok, Azure, etc.) based on provider capability
and configured payload_structure.
"""
from typing import Any, Dict, List, Optional


def construct_provider_payload(
    provider_key: str,
    model_type: str,
    payload_structure: Optional[Dict[str, Any]],
    model_name: str,
    text_or_messages: Any,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    **extra: Any,
) -> Dict[str, Any]:
    """
    Construct the final JSON payload dictionary for an API request.
    """
    payload_format = (payload_structure or {}).get("payload_format") or provider_key.lower()

    if payload_format == "anthropic_messages" or provider_key.lower() == "anthropic":
        messages: List[Dict[str, Any]] = []
        if isinstance(text_or_messages, list):
            messages = text_or_messages
        elif isinstance(text_or_messages, str):
            messages = [{"role": "user", "content": text_or_messages}]

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        return payload

    elif payload_format == "ollama" or provider_key.lower() == "ollama":
        if model_type == "embedding":
            prompt = text_or_messages if isinstance(text_or_messages, str) else str(text_or_messages)
            return {
                "model": model_name,
                "prompt": prompt,
            }
        else:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if isinstance(text_or_messages, list):
                messages.extend(text_or_messages)
            elif isinstance(text_or_messages, str):
                messages.append({"role": "user", "content": text_or_messages})

            return {
                "model": model_name,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }

    elif payload_format == "gemini" or provider_key.lower() == "gemini":
        if model_type == "embedding":
            prompt = text_or_messages if isinstance(text_or_messages, str) else str(text_or_messages)
            return {
                "model": f"models/{model_name}",
                "content": {
                    "parts": [{"text": prompt}]
                }
            }
        else:
            contents = []
            system_instruction = None
            if system_prompt:
                system_instruction = {"parts": [{"text": system_prompt}]}

            if isinstance(text_or_messages, list):
                for msg in text_or_messages:
                    r = msg.get("role")
                    c = msg.get("content", "")
                    if r == "system":
                        system_instruction = {"parts": [{"text": c}]}
                    else:
                        gem_role = "user" if r == "user" else "model"
                        contents.append({"role": gem_role, "parts": [{"text": c}]})
            elif isinstance(text_or_messages, str):
                contents.append({"role": "user", "parts": [{"text": text_or_messages}]})

            g_payload: Dict[str, Any] = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                }
            }
            if system_instruction:
                g_payload["systemInstruction"] = system_instruction
            return g_payload

    # Standard OpenAI / vLLM / Grok / Azure / default format
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if isinstance(text_or_messages, list):
        messages.extend(text_or_messages)
    elif isinstance(text_or_messages, str):
        messages.append({"role": "user", "content": text_or_messages})

    if model_type == "embedding":
        input_data = text_or_messages if isinstance(text_or_messages, (str, list)) else [str(text_or_messages)]
        return {
            "model": model_name,
            "input": input_data,
        }

    return {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
