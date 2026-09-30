import json
import os
from pathlib import Path

import pytest

from backend.inference_engine.working_memory import WorkingMemory
from backend.inference_engine.forward_chaining import ForwardChainingEngine
from backend.inference_engine.reasoning_trace import ReasoningTrace

# Helper to load inference rules
def load_rules() -> list:
    rules_path = Path(__file__).resolve().parents[1] / "knowledge_base" / "inference_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_reasoning_trace_empty():
    trace = ReasoningTrace()
    assert trace.get_steps() == []
    assert len(trace) == 0


def test_reasoning_trace_add_step():
    trace = ReasoningTrace()
    step = {
        "step": 1,
        "rule_id": "R1",
        "rule_name": "Identify Defective Product Issue",
        "conditions": [
            {
                "fact_key": "product_purchased",
                "expected_value": "true",
                "actual_value": "true",
                "source": "user",
            }
        ],
        "conclusion": "defective_product_issue",
        "explanation": "example explanation",
    }
    trace.add_step(step)
    stored = trace.get_steps()[0]
    for key, value in step.items():
        assert stored[key] == value
    assert len(trace) == 1


def test_reasoning_trace_multiple_steps_order():
    trace = ReasoningTrace()
    steps = [
        {"step": 1, "rule_id": "R1", "rule_name": "R1", "conditions": [], "conclusion": "c1", "explanation": ""},
        {"step": 2, "rule_id": "R2", "rule_name": "R2", "conditions": [], "conclusion": "c2", "explanation": ""},
    ]
    for s in steps:
        trace.add_step(s)
    retrieved = trace.get_steps()
    assert [s["rule_id"] for s in retrieved] == ["R1", "R2"]
    assert retrieved[0]["step"] == 1
    assert retrieved[1]["step"] == 2


def test_reasoning_trace_clear():
    trace = ReasoningTrace()
    trace.add_step({"step": 1, "rule_id": "R1", "rule_name": "R1", "conditions": [], "conclusion": "c1", "explanation": ""})
    trace.clear()
    assert trace.get_steps() == []
    assert len(trace) == 0


def test_forward_chaining_records_trace_steps():
    # Setup working memory with initial facts
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("product_defective", "true")
    wm.add_fact("seller_contacted", "true")
    wm.add_fact("seller_denied_or_disputed_claim", "true")

    rules = load_rules()
    engine = ForwardChainingEngine(rules)
    trace = ReasoningTrace()
    result = engine.run(wm, trace=trace)

    steps = trace.get_steps()
    # Expect at least two steps corresponding to R1 and R2
    rule_ids = [s["rule_id"] for s in steps]
    assert "R1" in rule_ids
    assert "R2" in rule_ids
    # Ensure order: R1 before R2
    assert rule_ids.index("R1") < rule_ids.index("R2")

    # Verify conclusions recorded in steps match derived facts
    conclusions = [s["conclusion"] for s in steps]
    assert "defective_product_issue" in conclusions
    assert "potential_consumer_dispute" in conclusions

    # Also verify engine result includes derived facts
    assert result["derived_facts"].get("defective_product_issue") == "true"
    assert result["derived_facts"].get("potential_consumer_dispute") == "true"


def test_forward_chaining_trace_content_details():
    wm = WorkingMemory()
    wm.add_fact("product_purchased", "true")
    wm.add_fact("product_defective", "true")
    wm.add_fact("seller_contacted", "true")
    wm.add_fact("seller_denied_or_disputed_claim", "true")

    rules = load_rules()
    engine = ForwardChainingEngine(rules)
    trace = ReasoningTrace()
    engine.run(wm, trace=trace)

    # Find R1 step and verify condition details
    r1_step = next(s for s in trace.get_steps() if s["rule_id"] == "R1")
    cond_keys = {c["fact_key"] for c in r1_step["conditions"]}
    assert cond_keys == {"product_purchased", "product_defective"}
    for cond in r1_step["conditions"]:
        assert cond["actual_value"] == "true"
        assert cond["source"] == "user"

    # Verify R2 step includes a derived fact as condition
    r2_step = next(s for s in trace.get_steps() if s["rule_id"] == "R2")
    cond_keys_r2 = {c["fact_key"] for c in r2_step["conditions"]}
    assert "defective_product_issue" in cond_keys_r2
    # derived fact should have source "derived"
    derived_cond = next(c for c in r2_step["conditions"] if c["fact_key"] == "defective_product_issue")
    assert derived_cond["source"] == "derived"
