from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


class OntologyMapper:
    """
    Maps AWS provider types and relationship aliases to universal Cypher labels.
    """

    DEFAULT_RESOURCE = "Resource"

    def __init__(self, dictionary_path: Optional[str] = None):
        self.dictionary_path = dictionary_path
        self._provider_to_universal: Dict[str, str] = {}
        self._universal_to_providers: Dict[str, Set[str]] = {}
        self._relationship_aliases: Dict[str, str] = {}
        self._load_dictionary()

    def _load_dictionary(self) -> None:
        payload: Dict[str, Any]
        if self.dictionary_path:
            payload = json.loads(Path(self.dictionary_path).read_text(encoding="utf-8"))
        else:
            raw = resources.files("gro.data").joinpath("aws_universal_types.json").read_text(
                encoding="utf-8"
            )
            payload = json.loads(raw)

        for item in payload.get("type_mappings", []):
            if not isinstance(item, dict):
                continue
            provider_type = str(item.get("provider_type", "")).strip().lower()
            universal_type = str(item.get("universal_type", "")).strip()
            if not provider_type or not universal_type:
                continue
            self._provider_to_universal[provider_type] = universal_type
            self._universal_to_providers.setdefault(universal_type, set()).add(provider_type)

        aliases = payload.get("relationship_aliases", {})
        if isinstance(aliases, dict):
            for alias, canonical in aliases.items():
                alias_key = str(alias).strip().upper()
                canonical_key = str(canonical).strip().upper()
                if alias_key and canonical_key:
                    self._relationship_aliases[alias_key] = canonical_key

    def universal_type_for_provider(self, provider_type: Optional[str]) -> str:
        if not provider_type:
            return self.DEFAULT_RESOURCE
        return self._provider_to_universal.get(str(provider_type).strip().lower(), self.DEFAULT_RESOURCE)

    def provider_types_for_universal(self, universal_type: str) -> Set[str]:
        return set(self._universal_to_providers.get(str(universal_type).strip(), set()))

    def canonical_relationship(self, relationship_label: str) -> str:
        token = str(relationship_label or "").strip().upper()
        if not token:
            return token
        return self._relationship_aliases.get(token, token)

    def expand_relationship_pattern(self, relationship_pattern: str) -> str:
        """
        Expand alias relationship tokens inside a Cypher relationship pattern.
        Example: [:ASSUMES|ASSUMES_ROLE] -> [:ASSUMES|ASSUMES_ROLE] (keeps both)
        while also ensuring canonical labels exist on loaded edges.
        """
        if not relationship_pattern:
            return relationship_pattern

        parts = relationship_pattern.split("|")
        expanded: list[str] = []
        seen: Set[str] = set()
        for part in parts:
            token = part.strip().upper()
            if not token:
                continue
            for candidate in (token, self.canonical_relationship(token)):
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    expanded.append(candidate)
        return "|".join(expanded)

    def labels_for_node(self, *, ring: str, provider_type: Optional[str]) -> list[str]:
        labels = [self.universal_type_for_provider(provider_type), "InfrastructureObject"]
        ring_label = str(ring or "").strip()
        if ring_label:
            labels.append(ring_label)
        deduped: list[str] = []
        seen: Set[str] = set()
        for label in labels:
            if label and label not in seen:
                seen.add(label)
                deduped.append(label)
        return deduped

    @staticmethod
    @lru_cache(maxsize=1)
    def default() -> "OntologyMapper":
        return OntologyMapper()
