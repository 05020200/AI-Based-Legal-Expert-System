import json
from pathlib import Path

# pyrefly: ignore [missing-import]
import pytest

from backend.inference_engine.working_memory import WorkingMemory
from backend.inference_engine.backward_chaining import BackwardChainingEngine

# Helper to load inference rules
def load_rules() -> list:
    rules_path = Path(__file__).resolve().parents[1] / "knowledge_base" / "inference_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_goal_already_available():
    wm = WorkingMemory()
    wm.add_fact("defective_product_issue", "true")
    engine = BackwardChainingEngine(load_rules())
    result = engine.query("defective_product_issue", "true", wm)
    assert result["goal_satisfied"] is True
    assert result["available_facts"] == ["defective_product_issue=true"]
    assert result["missing_facts"] == []
    assert result["rules_considered"] == []


def test_goal_proved_from_facts():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("product_defective", "true")
    engine = BackwardChainingEngine(load_rules())
    result = engine.query("defective_product_issue", "true", wm)
    assert result["goal_satisfied"] is True
    # Both base facts should be listed as available
    assert set(result["available_facts"]) == {
        "product_purchased=true",
        "product_defective=true",
        "defective_product_issue=true",
    }
    # Rule R1 should be the only rule considered
    assert result["rules_considered"] == ["R1"]
    # Proof path should start with the rule then facts
    assert result["proof_path"][0] == "R1"
    assert "defective_product_issue=true" in result["proof_path"]


def test_missing_fact():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    engine = BackwardChainingEngine(load_rules())
    result = engine.query("defective_product_issue", "true", wm)
    assert result["goal_satisfied"] is False
    assert "product_defective=true" in result["missing_facts"]
    # R1 should be reported as considered even though it fails
    assert "R1" in result["rules_considered"]


def test_recursive_reasoning_success():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("product_defective", "true")
    wm.add_fact("seller_contacted", "true")
    wm.add_fact("seller_denied_or_disputed_claim", "true")
    engine = BackwardChainingEngine(load_rules())
    result = engine.query("potential_consumer_dispute", "true", wm)
    assert result["goal_satisfied"] is True
    # Both R2 and R1 should appear in the rules list (order may vary but R2 first)
    assert result["rules_considered"][0] == "R2"
    assert "R1" in result["rules_considered"]
    # All required base facts should be listed as available
    expected_facts = {
        "product_purchased=true",
        "product_defective=true",
        "seller_contacted=true",
        "seller_denied_or_disputed_claim=true",
        "defective_product_issue=true",
        "potential_consumer_dispute=true",
    }
    assert set(result["available_facts"]) == expected_facts


def test_recursive_missing_fact():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("seller_contacted", "true")
    wm.add_fact("seller_denied_or_disputed_claim", "true")
    engine = BackwardChainingEngine(load_rules())
    result = engine.query("potential_consumer_dispute", "true", wm)
    assert result["goal_satisfied"] is False
    # The missing fact should be product_defective=true (needed for R1)
    assert "product_defective=true" in result["missing_facts"]
    # Both R2 and R1 should be considered
    assert "R2" in result["rules_considered"]
    assert "R1" in result["rules_considered"]


def test_unknown_goal():
    wm = WorkingMemory()
    engine = BackwardChainingEngine(load_rules())
    result = engine.query("non_existent_fact", "true", wm)
    assert result["goal_satisfied"] is False
    # No rules can produce the fact
    assert result["rules_considered"] == []
    assert "non_existent_fact=true" in result["missing_facts"]


def test_cycle_protection():
    # Create a tiny rule set with a cycle: A <- B, B <- A
    cyclic_rules = [
        {"rule_id": "C1", "conclusion": "A", "conditions": [{"fact_key": "B", "operator": "==", "expected_value": "true"}], "explanation": ""},
        {"rule_id": "C2", "conclusion": "B", "conditions": [{"fact_key": "A", "operator": "==", "expected_value": "true"}], "explanation": ""},
    ]
    wm = WorkingMemory()
    engine = BackwardChainingEngine(cyclic_rules)
    result = engine.query("A", "true", wm)
    # Should terminate without infinite recursion and report unsatisfied
    assert result["goal_satisfied"] is False
    # No infinite loop means rules_considered may contain the attempted rule(s)
    assert "C1" in result["rules_considered"] or result["rules_considered"] == []
