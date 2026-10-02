import pytest
from backend.knowledge_base.populate_kb import populate
from backend.services.document_recommendation import DocumentRecommendationService
from backend.database.db import get_db_connection

# Helper to insert documents for testing
def insert_documents(conn, docs):
    cursor = conn.cursor()
    for name, mandatory in docs:
        cursor.execute(
            "INSERT INTO documents (document_name, is_mandatory) VALUES (%s, %s)",
            (name, mandatory),
        )
    conn.commit()
    cursor.close()

@pytest.fixture(scope="function")
def setup_db():
    # Populate base knowledge (authorities etc.)
    populate()
    conn = get_db_connection()
    # Ensure clean documents table
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE documents")
    conn.commit()
    cursor.close()
    yield conn
    # Cleanup after test
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE documents")
    conn.commit()
    cursor.close()
    conn.close()

def test_defective_product_documents(setup_db):
    conn = setup_db
    # Insert some documents, marking one as mandatory
    insert_documents(conn, [
        ("purchase_invoice", True),
        ("defect_photos", False),
        ("warranty_document", False),
    ])
    service = DocumentRecommendationService()
    result = service.recommend("Defective Product", available_documents=["purchase_invoice"])
    assert result["issue"] == "Defective Product"
    # Recommended list should contain the mapped docs
    expected_recommended = [
        "purchase_invoice",
        "defect_photos",
        "seller_communication",
    ]
    assert result["recommended_documents"] == expected_recommended
    # Available docs are correctly echoed
    assert result["available_documents"] == ["purchase_invoice"]
    # Missing docs are those not in available
    assert set(result["missing_documents"]) == set(expected_recommended) - {"purchase_invoice"}
    # Mandatory docs reflect DB flag
    assert result["mandatory_documents"] == ["purchase_invoice"]

def test_unknown_issue(setup_db):
    conn = setup_db
    service = DocumentRecommendationService()
    # No mapping for this issue, should not crash and return empty lists
    result = service.recommend("Unknown Issue")
    assert result["issue"] == "Unknown Issue"
    assert result["recommended_documents"] == []
    assert result["available_documents"] == []
    assert result["missing_documents"] == []
    assert result["mandatory_documents"] == []
