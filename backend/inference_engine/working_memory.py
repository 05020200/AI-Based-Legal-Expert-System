'''Working Memory module for the inference engine.

Provides an in‑memory store for facts of the current case.
'''

from typing import Dict, Optional


class WorkingMemory:
    """In‑memory fact storage for a single legal case.

    Facts are stored as a mapping:
        fact_key -> {"value": <fact_value>, "source": "user"|"derived"}

    The class offers methods to add user facts, derived facts,
    query existence, retrieve values and clear the memory.
    Duplicate insertions are ignored and reported via the return value.
    """

    def __init__(self) -> None:
        """Create an empty working memory."""
        self._facts: Dict[str, Dict[str, str]] = {}

    def add_fact(self, fact_key: str, fact_value: str, source: str = "user") -> bool:
        """Add a fact coming from the user (or an explicit source).

        Returns True if the fact was newly added, False if an identical
        fact already existed.
        """
        existing = self._facts.get(fact_key)
        if existing is not None and existing["value"] == fact_value and existing["source"] == source:
            return False
        # Overwrite if same key with different value or source – treat as new fact
        self._facts[fact_key] = {"value": fact_value, "source": source}
        return True

    def add_derived_fact(self, fact_key: str, fact_value: str) -> bool:
        """Convenient wrapper for adding a derived fact (source = "derived")."""
        return self.add_fact(fact_key, fact_value, source="derived")

    def has_fact(self, fact_key: str, expected_value: Optional[str] = None) -> bool:
        """Check whether a fact exists. If ``expected_value`` is supplied,
        the stored value must match exactly.
        """
        fact = self._facts.get(fact_key)
        if fact is None:
            return False
        if expected_value is not None and fact["value"] != expected_value:
            return False
        return True

    def get_fact(self, fact_key: str) -> Optional[Dict[str, str]]:
        """Retrieve the stored fact information.

        Returns a dict {"value": ..., "source": ...} or ``None`` if
        the fact is not present.
        """
        return self._facts.get(fact_key)

    def get_all_facts(self) -> Dict[str, Dict[str, str]]:
        """Return a shallow copy of all stored facts."""
        return dict(self._facts)

    def clear(self) -> None:
        """Remove all facts from the working memory."""
        self._facts.clear()
