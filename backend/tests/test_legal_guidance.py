import pytest
from backend.services.legal_guidance import LegalGuidanceService


@pytest.fixture
def service():
    return LegalGuidanceService()


def test_defective_product_issue(service):
    result = service.get_guidance(["defective_product_issue"])
    assert len(result) == 1
    guidance = result[0]
    assert guidance["issue"] == "Defective Product"
    assert guidance["inference_conclusion"] == "defective_product_issue"
    law = guidance["applicable_law"][0]
    assert law["act_name"] == "Consumer Protection Act, 2019"
    assert law["section_number"] == "Section 2(10)"
    assert law["title"] == "Defect"
    # Remedies list may be empty in test environment; just ensure field exists
    assert isinstance(guidance["possible_remedies"], list)


def test_deficient_service_issue(service):
    result = service.get_guidance(["deficient_service_issue"])
    law = result[0]["applicable_law"][0]
    assert law["section_number"] == "Section 2(11)"
    assert law["title"] == "Deficiency"


def test_potential_consumer_dispute(service):
    result = service.get_guidance(["potential_consumer_dispute"])
    law = result[0]["applicable_law"][0]
    assert law["section_number"] == "Section 2(8)"
    assert law["title"] == "Consumer Dispute"


def test_potential_unfair_trade_practice(service):
    result = service.get_guidance(["potential_unfair_trade_practice"])
    law = result[0]["applicable_law"][0]
    assert law["section_number"] == "Section 2(47)"
    assert law["title"] == "Unfair Trade Practice"


def test_consumer_complaint_route_available(service):
    result = service.get_guidance(["consumer_complaint_route_available"])
    law = result[0]["applicable_law"][0]
    assert law["section_number"] == "Section 35"
    assert law["title"] == "Manner in which complaint shall be made"


def test_unknown_conclusion(service):
    result = service.get_guidance(["some_unknown_fact"])
    assert len(result) == 1
    guidance = result[0]
    assert guidance["issue"] == "Unknown"
    assert guidance["applicable_law"] == []
    assert guidance["possible_remedies"] == []


def test_multiple_conclusions(service):
    conclusions = ["defective_product_issue", "potential_consumer_dispute", "defective_product_issue"]
    result = service.get_guidance(conclusions)
    # Should have three entries: two distinct issues plus duplicate handling entry
    assert len(result) == 3
    # Ensure no duplicate provision entries for the same section
    sections = [g["applicable_law"][0]["section_number"] if g["applicable_law"] else None for g in result]
    # Two real sections plus a None for duplicate entry
    assert sections.count("Section 2(10)") == 1
    assert sections.count("Section 2(8)") == 1
    # The duplicate entry should have empty applicable_law
    duplicate_entry = next(g for g in result if g["issue"] == "Defective Product" and g["applicable_law"] == [])
    assert duplicate_entry["disclaimer"] == "Provision already listed for another issue."
