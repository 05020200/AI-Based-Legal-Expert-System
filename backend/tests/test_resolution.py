import pytest

from backend.inference_engine.resolution import ResolutionEngine


def test_simple_fact():
    kb = [["A"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "A")
    assert result["entailed"] is True


def test_simple_implication():
    kb = [["A"], ["NOT_A", "B"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "B")
    assert result["entailed"] is True


def test_multi_step_reasoning():
    kb = [["A"], ["NOT_A", "B"], ["NOT_B", "C"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "C")
    assert result["entailed"] is True


def test_goal_not_entailed():
    kb = [["A"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "B")
    assert result["entailed"] is False


def test_contradictory_goal():
    kb = [["A"], ["NOT_A"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "B")
    # Should safely terminate and not raise.
    assert isinstance(result, dict)
    # Since B is unrelated, not entailed.
    assert result["entailed"] is False


def test_legal_style_example():
    kb = [["product_purchased"], ["NOT_product_purchased", "consumer_transaction"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "consumer_transaction")
    assert result["entailed"] is True


def test_duplicate_clause_protection():
    # This set can generate a duplicate clause (A ∨ B) from two different pairs.
    kb = [["A"], ["NOT_A", "B"], ["NOT_B", "A"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "A")
    # Should terminate without infinite loop.
    assert isinstance(result, dict)
    # A is directly a fact, so entailed.
    assert result["entailed"] is True


def test_resolution_step_recording():
    kb = [["A"], ["NOT_A", "B"]]
    engine = ResolutionEngine()
    result = engine.resolution(kb, "B")
    assert result["entailed"] is True
    steps = result["resolution_steps"]
    # There should be at least one step showing resolution on "A".
    assert any(step["resolved_literal"] == "A" for step in steps)
    # The result of that step should contain "B".
    assert any("B" in step["result"] for step in steps)
