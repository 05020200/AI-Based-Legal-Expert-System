import json
from typing import List, Dict, Any

class ReasoningTrace:
    """In‑memory trace of reasoning steps during forward chaining.

    Each step is a dictionary containing at least the following keys:
        - ``step``: sequential step number (starting at 1)
        - ``rule_id``: identifier of the fired rule
        - ``rule_name``: human readable name of the rule (optional)
        - ``conditions``: list of condition dictionaries with ``fact_key``, ``expected_value``, ``actual_value`` and ``source``
        - ``conclusion``: fact key that was concluded
        - ``explanation``: optional textual explanation from the rule
    """

    def __init__(self) -> None:
        self._steps: List[Dict[str, Any]] = []

    def add_step(self, step: Dict[str, Any]) -> None:
        """Record a reasoning step.

        The caller should supply a ``step`` dictionary matching the schema
        described in the class docstring. The step number is not automatically
        generated – the engine passes ``len(self._steps) + 1``.
        """
        self._steps.append(step)

    def get_steps(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the recorded steps in order.
        """
        return list(self._steps)

    # Alias retained for backward compatibility with earlier code that used
    # ``get_all_steps``.
    def get_all_steps(self) -> List[Dict[str, Any]]:
        """Alias for :meth:`get_steps`.
        """
        return self.get_steps()

    def clear(self) -> None:
        """Remove all recorded steps.
        """
        self._steps.clear()

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"ReasoningTrace(steps={self._steps})"
