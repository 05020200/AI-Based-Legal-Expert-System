import json
from typing import List, Dict, Any, Optional
from .working_memory import WorkingMemory
from .reasoning_trace import ReasoningTrace


class ForwardChainingEngine:
    """Forward chaining inference engine.

    Parameters
    ----------
    rules: List[dict]
        List of rule dictionaries loaded from ``inference_rules.json``.
    """

    def __init__(self, rules: List[Dict[str, Any]]):
        self.rules = rules

    def _condition_satisfied(self, memory: WorkingMemory, condition: Dict[str, str]) -> bool:
        """Evaluate a single condition against the current working memory.

        Currently only supports the ``==`` operator.
        """
        fact_key = condition["fact_key"]
        operator = condition["operator"]
        expected = condition["expected_value"]
        fact = memory.get_fact(fact_key)
        if fact is None:
            return False
        if operator == "==":
            return fact["value"] == expected
        return False

    def run(self, memory: WorkingMemory, trace: Optional[ReasoningTrace] = None) -> Dict[str, Any]:
        """Execute forward chaining on the supplied ``WorkingMemory``.

        Returns a dictionary containing the initial facts, derived facts, fired rule IDs
        and a list of conclusions.
        """
        # Capture initial facts (only their values)
        initial_facts = {k: v["value"] for k, v in memory.get_all_facts().items()}
        derived_facts: Dict[str, str] = {}
        fired_rules: List[str] = []

        new_fact_added = True
        while new_fact_added:
            new_fact_added = False
            for rule in self.rules:
                rule_id = rule.get("rule_id")
                rule_name = rule.get("rule_name")
                conclusion_key = rule.get("conclusion")
                # Skip if the conclusion already exists with the same value
                if memory.has_fact(conclusion_key, "true"):
                    continue
                conditions = rule.get("conditions", [])
                if all(self._condition_satisfied(memory, cond) for cond in conditions):
                    added = memory.add_derived_fact(conclusion_key, "true")
                    if added:
                        derived_facts[conclusion_key] = "true"
                        fired_rules.append(rule_id)
                        new_fact_added = True
                        if trace is not None:
                            step_conditions = []
                            for cond in conditions:
                                fact_key = cond["fact_key"]
                                fact = memory.get_fact(fact_key)
                                step_conditions.append({
                                    "fact_key": fact_key,
                                    "expected_value": cond["expected_value"],
                                    "actual_value": fact["value"] if fact else None,
                                    "source": fact["source"] if fact else None,
                                })
                            step = {
                                "step": len(trace.get_steps()) + 1,
                                "rule_id": rule_id,
                                "rule_name": rule_name,
                                "conditions": step_conditions,
                                "conclusion": conclusion_key,
                                "explanation": rule.get("explanation", ""),
                            }
                            trace.add_step(step)
        result = {
            "initial_facts": initial_facts,
            "derived_facts": derived_facts,
            "fired_rules": fired_rules,
            "conclusions": list(derived_facts.keys()),
        }
        return result