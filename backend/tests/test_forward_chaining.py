import json
from pathlib import Path

import pytest

from backend.inference_engine.working_memory import WorkingMemory
from backend.inference_engine.forward_chaining import ForwardChainingEngine

def load_rules() -> list:
    rules_path = Path(__file__).resolve().parents[1] / "knowledge_base" / "inference_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_forward_chaining_derives_expected_facts():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("product_defective", "true")
    wm.add_fact("seller_contacted", "true")
    wm.add_fact("seller_denied_or_disputed_claim", "true")

    engine = ForwardChainingEngine(load_rules())
    result = engine.run(wm)

    # Verify derived facts contain both expected conclusions
    derived = result.get("derived_facts", {})
    assert derived.get("defective_product_issue") == "true"
    assert derived.get("potential_consumer_dispute") == "true"

    # Verify fired rules include R1 and R2 in order
    fired = result.get("fired_rules", [])
    assert fired == ["R1", "R2"]

def test_forward_chaining_initial_facts_preserved():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    engine = ForwardChainingEngine(load_rules())
    result = engine.run(wm)
    # Initial facts should be captured correctly
    initial = result.get("initial_facts", {})
    assert initial == {"product_purchased": "true"}
    # No derived facts when conditions not met
    assert result.get("derived_facts") == {}
    assert result.get("fired_rules") == []
