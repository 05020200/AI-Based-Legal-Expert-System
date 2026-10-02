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


@pytest.mark.parametrize(
    "document_type,expected_phrase",
    [
        ("seller_complaint", "Complaint about a product problem"),
        ("replacement_request", "consider replacement"),
        ("refund_request", "consider refund"),
    ],
)
def test_defective_product_documents_use_case_values_and_placeholders(
    setup_db, document_type, expected_phrase
):
    service = TemplateGenerationService()
    draft = service.generate_defective_product_document(document_type, {
        "product_name": "Laptop",
        "seller_name": "Raju Electronics",
        "purchase_date": "2026-10-01",
        "amount_paid": 240000,
        "order_or_invoice_number": "9876",
        "problem_description": "Not working",
        "seller_response": "Refused replacement",
        "desired_resolution": "Replacement",
    })
    assert expected_phrase in draft
    assert "Raju Electronics" in draft
    assert "Laptop" in draft
    assert "1 October 2026" in draft
    assert "₹2,40,000" in draft
    assert "9876" in draft
    assert "Not working" in draft
    assert "Refused replacement" in draft
    assert "[Consumer Name Not Provided]" in draft


def test_defective_product_document_marks_missing_details():
    service = TemplateGenerationService()
    draft = service.generate_defective_product_document("seller_complaint", {})
    assert "[Seller/Business Name Not Provided]" in draft
    assert "[Product Name Not Provided]" in draft
    assert "[Purchase Date Not Provided]" in draft
    assert "[Amount Paid Not Provided]" in draft
    assert "[Order/Invoice Number Not Provided]" in draft
    assert "[Product Problem Not Provided]" in draft
    assert "[Seller Response Not Provided]" in draft
    assert "[Desired Resolution Not Provided]" in draft


def test_refund_document_is_independent_of_selected_case_resolution():
    service = TemplateGenerationService()
    draft = service.generate_defective_product_document(
        "refund_request",
        {
            "desired_resolution": "Refund",
            "selected_resolution": "Replacement",
            "answers": {"purchase_proof_available": True},
        },
        {"consumer_name": "Priya S", "document_date": "2026-10-02"},
    )
    assert draft.startswith("REFUND REQUEST")
    assert "Selected resolution in case: Replacement" in draft
    assert "consider a refund" in draft
    assert "Priya S" in draft
    assert "Purchase Invoice / Receipt" in draft
    assert "Photographs / Videos of Defect" not in draft


def test_consumer_commission_complaint_is_structured_and_distinct():
    service = TemplateGenerationService()
    report = {
        "legal_provisions": [
            {"act_name": "Consumer Protection Act, 2019", "section_number": "Section 2(10)", "title": "Defect"},
            {"act_name": "Consumer Protection Act, 2019", "section_number": "Section 35", "title": "Manner in which complaint shall be made"},
            {"act_name": "Consumer Protection Act, 2019", "section_number": "Section 39", "title": "Findings of District Commission"},
        ],
        "where_to_complain": {
            "pecuniary_jurisdiction": {
                "determined": True,
                "authority": "District Consumer Disputes Redressal Commission",
            },
        },
    }
    draft = service.generate_defective_product_document(
        "consumer_commission_complaint",
        {
            "case_id": "CASE-2026-0014",
            "product_name": "Laptop",
            "seller_name": "Raju",
            "purchase_date": "2026-10-01",
            "amount_paid": 240000,
            "order_or_invoice_number": "9876",
            "problem_description": "Laptop is damaged",
            "seller_response": "refused replacemnt",
            "answers": {
                "product_purchased": True,
                "product_has_problem": True,
                "seller_contacted": True,
                "seller_resolved": False,
                "desired_resolution": "Replacement",
                "purchase_proof_available": True,
                "problem_evidence_available": True,
                "seller_communication_available": True,
            },
            "report": report,
        },
        {
            "consumer_name": "Priya S",
            "consumer_address": "Consumer address",
            "consumer_phone": "555-0100",
            "consumer_email": "priya@example.test",
            "document_date": "2 October 2026",
        },
    )
    assert draft.startswith("BEFORE THE DISTRICT CONSUMER DISPUTES REDRESSAL COMMISSION")
    for section in ["COMPLAINANT:", "OPPOSITE PARTY:", "FACTS OF THE CASE:", "GROUNDS / POSSIBLE LEGAL BASIS:", "RELIEF / PRAYER:", "EVIDENCE / DOCUMENTS REPORTED:", "VERIFICATION / DECLARATION:"]:
        assert section in draft
    assert "Priya S" in draft
    assert "Raju" in draft
    assert "Laptop is damaged" in draft
    assert "refused replacemnt" in draft
    assert "Section 2(10)" in draft
    assert "Section 35" in draft
    assert "Section 39" in draft
    assert "Purchase Invoice / Receipt" in draft
    assert "Photographs / Videos of Defect" in draft
    assert "Communication Records with Seller" in draft
    assert "not proof of filing" in draft


def test_seller_letter_uses_consumer_identity_and_preserves_original_case_text():
    service = TemplateGenerationService()
    draft = service.generate_defective_product_document(
        "seller_complaint",
        {
            "case_id": "CASE-2026-0014",
            "product_name": "Laptop",
            "seller_name": "Raju",
            "seller_address": "Seller address supplied",
            "purchase_date": "2026-10-01",
            "amount_paid": 240000,
            "order_or_invoice_number": "9876",
            "problem_description": "Laptop is damaged",
            "seller_response": "refused replacemnt",
            "selected_resolution": "Replacement",
            "answers": {
                "purchase_proof_available": True,
                "problem_evidence_available": True,
                "seller_communication_available": True,
            },
        },
        {
            "consumer_name": "Priya S",
            "consumer_address": "Consumer address",
            "consumer_phone": "555-0100",
            "consumer_email": "priya@example.test",
            "document_date": "2 October 2026",
        },
    )
    for value in [
        "Priya S", "Consumer address", "555-0100", "priya@example.test",
        "Raju", "Seller address supplied", "Laptop", "1 October 2026",
        "₹2,40,000", "9876", "Laptop is damaged", "refused replacemnt",
        "Replacement", "Purchase Invoice / Receipt", "Photographs / Videos of Defect",
        "Communication Records with Seller", "Signature:",
    ]:
        assert value in draft


def test_consumer_name_is_not_taken_from_case_details():
    service = TemplateGenerationService()
    draft = service.generate_defective_product_document(
        "replacement_request",
        {"consumer_name": "Account Holder", "product_name": "Laptop"},
        {"consumer_name": "Different Consumer"},
    )
    assert "Different Consumer" in draft
    assert "Account Holder" not in draft
