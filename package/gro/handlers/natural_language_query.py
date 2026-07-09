from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional, Tuple

from renglo.common import load_config

from gro.handlers.query_parser import QueryParser

DEFAULT_MODEL = "gpt-4o-mini"


class NaturalLanguageQuery:
    """
    Translates plain-English requests into Gro Query Schema v1 JSON.
    """

    def __init__(self):
        self.config = load_config()
        self.query_parser = QueryParser()

    _PROVIDER_TYPE_ALIASES = {
        "dynamo_db": "dynamodb_table",
        "dynamodb": "dynamodb_table",
        "dynamo_db_table": "dynamodb_table",
        "dynamo_table": "dynamodb_table",
        "dynamo": "dynamodb_table",
    }
    _GENERIC_ALIASES = {"from", "to", "source", "target", "left", "right", "a", "b", "s", "v"}

    def _extract_json_text(self, content: str) -> Dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

        fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fence:
            parsed = json.loads(fence.group(1))
            return parsed if isinstance(parsed, dict) else {}

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _build_prompt(self, request_text: str) -> str:
        return (
            "Convert the user request into Gro Query Schema v1 JSON.\n"
            "Return ONLY valid JSON with these top-level keys:\n"
            '{ "version", "match", "where", "return", "options" }\n\n'
            "Schema constraints:\n"
            '- version must be "1.0"\n'
            '- match must include: edge_type, from{ring,alias}, to{ring,alias}, direction(outgoing|incoming|either)\n'
            "- where can include: from, to, edge (objects of predicates)\n"
            "- predicate shape: { op: one of [=, !=, in, not_in, exists, not_exists], value?: any }\n"
            "- return.kind must be node_ids\n"
            "- return.side must be from or to (never both)\n"
            "- options.mode must be graph_only\n"
            "- options.strict_projection must be true\n"
            "- options.trace false unless user asks for debug/trace\n\n"
            "Interpretation rules:\n"
            "- Infer intent from text and choose a single-hop graph pattern.\n"
            "- Use concise aliases (for example: s, v).\n"
            "- If the request asks for one side (sources/subnets/etc), set return.side accordingly.\n"
            "- If user does not specify a limit, omit limit or set null.\n"
            "- For AWS infrastructure requests (subnet/vpc/security group/route table/etc), "
            "prefer ring 'infrastructure_elements' and use where.from/where.to provider_type filters.\n"
            "- For AWS infrastructure connectivity, prefer edge_type "
            "'infrastructure_elements:links:infrastructure_elements:_id'.\n"
            "- Never include explanations, comments, markdown, or extra text.\n\n"
            f"User request:\n{request_text}"
        )

    def _call_llm_translate(self, *, request_text: str, model: str) -> Dict[str, Any]:
        api_key = str(self.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        try:
            from openai import OpenAI
        except Exception as exc:
            raise RuntimeError(f"openai package unavailable: {exc}") from exc

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or DEFAULT_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a translator from natural language to Gro Query Schema v1 JSON. "
                        "Output valid JSON only."
                    ),
                },
                {"role": "user", "content": self._build_prompt(request_text)},
            ],
        )
        content = ((response.choices or [None])[0].message.content or "").strip()
        return self._extract_json_text(content)

    def _normalize_provider_type_token(self, raw: Any) -> Optional[str]:
        token = str(raw or "").strip().lower()
        if not token:
            return None
        token = re.sub(r"[^a-z0-9]+", "_", token)
        token = re.sub(r"_+", "_", token).strip("_")
        if not token:
            return None
        return self._PROVIDER_TYPE_ALIASES.get(token, token)

    def _infer_provider_types_from_request(self, request_text: str) -> Tuple[Optional[str], Optional[str]]:
        text = str(request_text or "").strip().lower()
        if not text:
            return None, None
        text = re.sub(r"[^a-z0-9_ ]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        pattern = re.compile(
            r"find\s+([a-z0-9_ ]+?)\s+nodes?\s+connected\s+to\s+([a-z0-9_ ]+?)\s+nodes?"
        )
        match = pattern.search(text)
        if not match:
            return None, None
        from_type = self._normalize_provider_type_token(match.group(1))
        to_type = self._normalize_provider_type_token(match.group(2))
        return from_type, to_type

    def _enforce_provider_type_filters(self, generated: Dict[str, Any], request_text: str) -> Dict[str, Any]:
        query = dict(generated)
        match_obj = query.get("match")
        if not isinstance(match_obj, dict):
            return query
        from_obj = match_obj.get("from")
        to_obj = match_obj.get("to")
        if not isinstance(from_obj, dict) or not isinstance(to_obj, dict):
            return query
        if str(from_obj.get("ring", "")).strip() != "infrastructure_elements":
            return query
        if str(to_obj.get("ring", "")).strip() != "infrastructure_elements":
            return query

        request_lower = str(request_text or "").strip().lower()
        has_connected_pattern = "connected to" in request_lower
        explicit_incoming = any(token in request_lower for token in (" incoming ", " inbound ", " reverse "))
        explicit_outgoing = any(token in request_lower for token in (" outgoing ", " outbound ", " forward "))
        if has_connected_pattern and not explicit_incoming and not explicit_outgoing:
            # "X connected to Y" is treated as X -> Y by default.
            match_obj["direction"] = "outgoing"
            query["match"] = match_obj

        where_obj = query.get("where")
        if not isinstance(where_obj, dict):
            where_obj = {}
        from_where = where_obj.get("from")
        to_where = where_obj.get("to")
        if not isinstance(from_where, dict):
            from_where = {}
        if not isinstance(to_where, dict):
            to_where = {}

        # Some LLM outputs incorrectly emit side predicates as {"op":"=","value":"x"}.
        # Coerce that shape into the expected field map.
        def _coerce_side_predicate(side_map: Dict[str, Any]) -> Dict[str, Any]:
            op = side_map.get("op")
            has_value = "value" in side_map
            if "provider_type" not in side_map and isinstance(op, str) and has_value:
                return {"provider_type": {"op": op, "value": side_map.get("value")}}
            return side_map

        from_where = _coerce_side_predicate(from_where)
        to_where = _coerce_side_predicate(to_where)

        def _normalize_existing_provider_type(side_map: Dict[str, Any]) -> None:
            existing = side_map.get("provider_type")
            if not isinstance(existing, dict):
                return
            normalized = self._normalize_provider_type_token(existing.get("value"))
            if not normalized:
                return
            op = str(existing.get("op", "=")).strip() or "="
            side_map["provider_type"] = {"op": op, "value": normalized}

        _normalize_existing_provider_type(from_where)
        _normalize_existing_provider_type(to_where)

        from_type, to_type = self._infer_provider_types_from_request(request_text)

        from_alias = self._normalize_provider_type_token(from_obj.get("alias"))
        to_alias = self._normalize_provider_type_token(to_obj.get("alias"))
        if from_alias in self._GENERIC_ALIASES or (from_alias is not None and len(from_alias) <= 2):
            from_alias = None
        if to_alias in self._GENERIC_ALIASES or (to_alias is not None and len(to_alias) <= 2):
            to_alias = None

        if "provider_type" not in from_where:
            candidate = from_type or from_alias
            if candidate:
                from_where["provider_type"] = {"op": "=", "value": candidate}
        if "provider_type" not in to_where:
            candidate = to_type or to_alias
            if candidate:
                to_where["provider_type"] = {"op": "=", "value": candidate}

        where_obj["from"] = from_where
        where_obj["to"] = to_where
        query["where"] = where_obj
        return query

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        request_text = str(payload.get("request_text") or payload.get("text") or "").strip()
        model = str(payload.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        include_raw = bool(payload.get("include_raw", False))

        if not request_text:
            return {
                "success": False,
                "component": "natural_language_query",
                "message": "request_text is required",
            }

        try:
            generated = self._call_llm_translate(request_text=request_text, model=model)
        except Exception as exc:
            return {
                "success": False,
                "component": "natural_language_query",
                "message": str(exc),
            }

        if not isinstance(generated, dict) or not generated:
            return {
                "success": False,
                "component": "natural_language_query",
                "message": "LLM returned no JSON object",
            }

        generated = self._enforce_provider_type_filters(generated, request_text)

        try:
            parsed = self.query_parser.run(generated)
        except Exception as exc:
            return {
                "success": False,
                "component": "natural_language_query",
                "message": f"Generated query did not validate: {exc}",
                "generated_query": generated,
            }

        output: Dict[str, Any] = {
            "success": True,
            "component": "natural_language_query",
            "input": {
                "text_length": len(request_text),
                "model": model,
            },
            "output": {
                "query_v1": parsed.get("query_v1", generated),
                "return_spec": parsed.get("return_spec"),
                "query_pattern": parsed.get("query_pattern"),
            },
        }
        if include_raw:
            output["output"]["llm_generated"] = generated
        return output
