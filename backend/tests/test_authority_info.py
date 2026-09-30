import pytest

# Populate knowledge base before running tests
from backend.knowledge_base.populate_kb import populate

# Import the service
from backend.services.authority_info import AuthorityInfoService

# Ensure the DB is populated
populate()

service = AuthorityInfoService()

@pytest.mark.parametrize("amount,expected_name", [
    (5000000, "District Consumer Disputes Redressal Commission"),  # exactly 50 lakh
    (5000001, "State Consumer Disputes Redressal Commission"),   # just above 50 lakh
    (20000000, "State Consumer Disputes Redressal Commission"),  # exactly 2 crore
    (20000001, "National Consumer Disputes Redressal Commission"),  # just above 2 crore
])
def test_authority_lookup(amount, expected_name):
    result = service.get_authority_for_amount(amount)
    assert isinstance(result, dict)
    assert result["name"] == expected_name

@pytest.mark.parametrize("invalid_input", [0, -100, None, "invalid"])
def test_invalid_amount_handling(invalid_input):
    result = service.get_authority_for_amount(invalid_input)
    assert isinstance(result, str)
    assert "Invalid" in result or "cannot determine" in result

def test_territorial_jurisdiction_info():
    info = service.get_territorial_jurisdiction_info()
    assert "territorial_jurisdiction" in info
    factors = info["territorial_jurisdiction"]
    assert isinstance(factors, list)
    assert len(factors) == 3
    assert "place where the opposite party resides or carries on business" in factors[0]

def test_complaint_procedure_structure():
    # Use District authority id (should be 1 after population)
    # First retrieve authority to get its id
    authority = service.get_authority_for_amount(5000000)
    authority_id = authority["authority_id"]
    steps = service.get_complaint_procedure(authority_id)
    assert isinstance(steps, list)
    assert len(steps) >= 1
    # Ensure step descriptions do not contain invented deadlines or fees
    for step in steps:
        desc = step["step_description"].lower()
        assert "deadline" not in desc
        assert "fee" not in desc
        assert "fees" not in desc
