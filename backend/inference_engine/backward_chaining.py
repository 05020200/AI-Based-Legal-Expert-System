import json
from pathlib import Path
from typing import List, Dict, Any, Set

from .working_memory import WorkingMemory

class BackwardChainingEngine:
    """Goal‑directed inference engine.

    It attempts to prove a target fact using the provided inference rules
    and the facts stored in a :class:`WorkingMemory` instance.

    The engine never mutates the working memory – it only reads from it and
    reports which facts are available, which are missing, the rules that were
    considered and a proof path.
    """

    def __init__(self, rules: List[Dict[str, Any]]):
        self.rules = rules

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def query(self, fact_key: str, expected_value: str, memory: WorkingMemory) -> Dict[str, Any]:
        """Attempt to prove ``fact_key == expected_value``.

        Returns a dictionary matching the specification in the Phase 7
        description.
        """
        result = self._prove_goal(
            fact_key=fact_key,
            expected_value=expected_value,
            memory=memory,
            visited=set(),
        )
        # Ensure the top‑level ``goal`` entry is present
        result["goal"] = {"fact_key": fact_key, "expected_value": expected_value}
        return result

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _prove_goal(
        self,
        fact_key: str,
        expected_value: str,
        memory: WorkingMemory,
        visited: Set[str],
    ) -> Dict[str, Any]:
        """Recursively try to prove a single goal.

        ``visited`` holds fact keys that are currently on the recursion stack
        to avoid infinite cycles.
        """
        # Cycle detection
        if fact_key in visited:
            return {
                "goal_satisfied": False,
                "available_facts": [],
                "missing_facts": [],
                "rules_considered": [],
                "proof_path": [],
            }
        visited.add(fact_key)

        # 1. Check if the goal already exists in WorkingMemory
        fact = memory.get_fact(fact_key)
        if fact and fact["value"] == expected_value:
            return {
                "goal_satisfied": True,
                "available_facts": [f"{fact_key}={expected_value}"],
                "missing_facts": [],
                "rules_considered": [],
                "proof_path": [f"{fact_key}={expected_value}"],
            }

        # 2. Find rules that can produce the goal
        matching_rules = [r for r in self.rules if r.get("conclusion") == fact_key]
        if not matching_rules:
            # No rule can produce this fact – it is missing
            return {
                "goal_satisfied": False,
                "available_facts": [],
                "missing_facts": [f"{fact_key}={expected_value}"],
                "rules_considered": [],
                "proof_path": [],
            }

        # 3. Try each matching rule until one succeeds
        aggregate_missing: Set[str] = set()
        aggregate_rules: List[str] = []
        for rule in matching_rules:
            rule_id = rule.get("rule_id")
            conditions = rule.get("conditions", [])
            all_conditions_satisfied = True
            condition_available: List[str] = []
            condition_missing: Set[str] = set()
            sub_rules_used: List[str] = []
            sub_proof_parts: List[str] = []

            for cond in conditions:
                operator = cond.get("operator")
                if operator != "==":
                    # Unsupported operator – treat condition as unsatisfied
                    all_conditions_satisfied = False
                    condition_missing.add(
                        f"{cond.get('fact_key')}={cond.get('expected_value')} (unsupported operator)"
                    )
                    continue
                sub_key = cond.get("fact_key")
                sub_expected = cond.get("expected_value")
                sub_result = self._prove_goal(
                    fact_key=sub_key,
                    expected_value=sub_expected,
                    memory=memory,
                    visited=set(visited),  # copy for independent branch
                )
                if sub_result["goal_satisfied"]:
                    condition_available.extend(sub_result["available_facts"])
                    sub_rules_used.extend(sub_result["rules_considered"])
                    sub_proof_parts.extend(sub_result["proof_path"])
                else:
                    all_conditions_satisfied = False
                    condition_missing.update(sub_result["missing_facts"])
                    # Record any sub‑rules that were attempted even if they failed
                    aggregate_rules.extend(sub_result["rules_considered"])

            if all_conditions_satisfied:
                # Successful proof using this rule
                available = condition_available + [f"{fact_key}={expected_value}"]
                proof = [rule_id] + sub_proof_parts + [f"{fact_key}={expected_value}"]
                return {
                    "goal_satisfied": True,
                    "available_facts": available,
                    "missing_facts": [],
                    "rules_considered": [rule_id] + sub_rules_used,
                    "proof_path": proof,
                }
            else:
                aggregate_missing.update(condition_missing)
                # Include any sub‑rules that were attempted while evaluating this rule
                aggregate_rules.extend(sub_rules_used)
                aggregate_rules = [rule_id] + aggregate_rules

        # No rule could satisfy the goal
        return {
            "goal_satisfied": False,
            "available_facts": [],
            "missing_facts": sorted(aggregate_missing),
            "rules_considered": aggregate_rules,
            "proof_path": [],
        }

# Helper for loading rules in tests (optional, not part of the class)
def load_rules_from_file(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
