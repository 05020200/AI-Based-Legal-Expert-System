import json
import pytest
from backend.knowledge_base.populate_kb import populate
from backend.services.template_generation import TemplateGenerationService
from backend.database.db import get_db_connection

@pytest.fixture(scope="function")
def setup_db():
    # Populate base knowledge (authorities etc.)
    populate()
    conn = get_db_connection()
    # Ensure clean templates table
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE templates")
    conn.commit()
    cursor.close()
    yield conn
    # Cleanup after test
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE templates")
    conn.commit()
    cursor.close()
    conn.close()

def insert_template(conn, issue_name, content, placeholders):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO templates (document_name, content, placeholders) VALUES (%s, %s, %s)",
        (issue_name, content, json.dumps(placeholders)),
    )
    conn.commit()
    cursor.close()

def test_basic_complaint_template(setup_db):
    conn = setup_db
    service = TemplateGenerationService()
    data = {
        "consumer name": "Alice Patel",
        "seller / service provider name": "BestBuy Electronics",
        "date of purchase": "2023-05-10",
        "amount paid": "₹ 15,000",
        "description of product/service": "Smartphone XYZ Model",
        "problem encountered": "Screen flickers intermittently",
        "relief requested": "Replacement of the device",
        "any additional facts": "Attempted to contact support on 2023-05-15",
    }
    output = service.generate_template("Defective Product", data)
    # Ensure placeholders are replaced
    assert "Alice Patel" in output
    assert "BestBuy Electronics" in output
    assert "2023-05-10" in output
    assert "₹ 15,000" in output
    assert "Smartphone XYZ Model" in output
    assert "Screen flickers intermittently" in output
    assert "Replacement of the device" in output
    # Legal reference should be present for defective product
    assert "Legal Reference: Consumer Protection Act, 2019 — Section 2(10)" in output

def test_missing_information_placeholders(setup_db):
    conn = setup_db
    service = TemplateGenerationService()
    data = {
        "consumer name": "Rohit Kumar",
        "seller / service provider name": "OnlineMart",
        # date of purchase and amount omitted
        "description of product/service": "Laptop ABC",
        "problem encountered": "Battery drains quickly",
        "relief requested": "Refund of purchase price",
    }
    output = service.generate_template("Defective Product", data)
    # Provided values should appear
    assert "Rohit Kumar" in output
    assert "OnlineMart" in output
    assert "Laptop ABC" in output
    # Missing placeholders should remain unchanged
    assert "[DATE OF PURCHASE]" in output
    assert "[AMOUNT PAID]" in output

def test_no_fabricated_facts(setup_db):
    conn = setup_db
    service = TemplateGenerationService()
    data = {
        "consumer name": "Neha Sharma",
        "seller / service provider name": "TechStore",
        "description of product/service": "Tablet",
        "problem encountered": "Screen cracked",
        "relief requested": "Repair",
    }
    output = service.generate_template("Defective Product", data)
    # Ensure no unknown placeholders or fabricated facts appear
    assert "[ANY ADDITIONAL FACTS]" in output  # placeholder remains
    assert "[CONSUMER ADDRESS]" in output  # not fabricated
    # No invented date or amount
    assert "[DATE OF PURCHASE]" in output
    assert "[AMOUNT PAID]" in output

def test_stored_template_used(setup_db):
    conn = setup_db
    # Insert a stored template for the issue
    stored_content = (
        "Stored Template Header\n"
        "Consumer: [CONSUMER NAME]\n"
        "Issue: {issue}\n"
        "Details: [PROBLEM ENCOUNTERED]\n"
    )
    placeholders = ["[CONSUMER NAME]", "[PROBLEM ENCOUNTERED]"]
    insert_template(conn, "Defective Product", stored_content, placeholders)
    service = TemplateGenerationService()
    data = {
        "consumer name": "Sunil",
        "problem encountered": "Defect description",
    }
    output = service.generate_template("Defective Product", data)
    # Should use stored content and replace placeholders
    assert "Stored Template Header" in output
    assert "Consumer: Sunil" in output
    assert "Details: Defect description" in output
    # Issue placeholder should be filled via f-string in stored content
    assert "Issue: Defective Product" in output
