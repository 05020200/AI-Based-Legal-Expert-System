import json
from typing import List, Dict, Any, Optional

from database.db import get_db_connection


class DocumentRecommendationService:
    """Service to recommend supporting documents for a given legal issue.

    The service uses a static mapping of known issues to typical evidence
    documents. It also consults the ``documents`` table for any documents that are
    explicitly marked as mandatory (``is_mandatory = TRUE``). The result is a
    deterministic JSON‑compatible dictionary.
    """

    # Mapping of issue name (lower‑case) to a list of document identifiers.
    _ISSUE_DOCUMENT_MAP: Dict[str, List[str]] = {
        # Consumer domain
        "defective product": [
            "purchase_invoice",
            "defect_photos",
            "seller_communication",
        ],
        "refund / replacement issue": [
            "purchase_invoice",
            "refund_receipt",
            "correspondence_with_seller",
        ],
        "deficiency in service": [
            "service_agreement",
            "communication_logs",
            "payment_proof",
        ],
        "deficient service": [
            "service_agreement",
            "communication_logs",
            "payment_proof",
        ],
        "warranty related issue": [
            "warranty_document",
            "purchase_invoice",
            "repair_receipt",
        ],
        "misleading advertisement / unfair trade practice": [
            "advertisement_copy",
            "purchase_invoice",
            "communication_with_seller",
        ],
        "potential unfair trade practice": [
            "advertisement_copy",
            "purchase_invoice",
            "communication_with_seller",
        ],
        "e-commerce consumer issue": [
            "order_confirmation",
            "payment_proof",
            "shipping_receipt",
            "communication_logs",
        ],
        "potential consumer dispute": [
            "purchase_invoice",
            "complaint_copy",
            "seller_communication",
            "payment_proof",
            "defect_photos",
        ],
        # Contract domain
        "breach of contract": [
            "contract_document",
            "correspondence_between_parties",
            "payment_receipts",
            "evidence_of_breach",
            "legal_notice_copy",
        ],
        "non-performance of contract": [
            "contract_document",
            "correspondence_between_parties",
            "evidence_of_non_performance",
        ],
        "payment / non-payment dispute": [
            "contract_document",
            "invoice_or_payment_demand",
            "payment_receipts",
            "bank_statements",
        ],
        "contractual term violation": [
            "contract_document",
            "evidence_of_violation",
            "correspondence_between_parties",
        ],
        # Rental domain
        "security deposit dispute": [
            "rental_agreement",
            "deposit_payment_receipt",
            "bank_statement_showing_deposit",
            "property_condition_photos",
            "correspondence_with_landlord",
        ],
        "rent related dispute": [
            "rental_agreement",
            "rent_payment_receipts",
            "bank_statements",
            "correspondence_between_parties",
        ],
        "landlord / tenant obligation dispute": [
            "rental_agreement",
            "evidence_of_breach",
            "photographs_of_property",
            "correspondence_between_parties",
        ],
        "eviction / lease termination issue": [
            "rental_agreement",
            "eviction_notice",
            "correspondence_between_parties",
            "rent_payment_receipts",
        ],
        # Cyber domain
        "online financial fraud": [
            "transaction_records",
            "bank_statements",
            "screenshots_of_fraud",
            "communication_with_fraudster",
            "fir_copy",
        ],
        "unauthorized access / account compromise": [
            "screenshots_of_unauthorized_activity",
            "login_alerts",
            "email_notifications",
            "device_logs",
        ],
        "online identity theft / impersonation": [
            "screenshots_of_impersonation",
            "profile_urls",
            "identity_proof",
            "fir_copy",
        ],
        "cyber harassment": [
            "screenshots_of_harassment",
            "message_records",
            "call_records",
            "platform_report_copy",
        ],
        "data theft / system damage": [
            "system_logs",
            "screenshots_of_breach",
            "forensic_report",
            "fir_copy",
        ],
    }

    # Human-readable names for document identifiers
    _DOCUMENT_DISPLAY_NAMES: Dict[str, str] = {
        "purchase_invoice": "Purchase Invoice / Receipt",
        "order_confirmation": "Order Confirmation",
        "warranty_document": "Warranty Document",
        "defect_photos": "Photographs / Videos of the Defect",
        "seller_communication": "Communication Records with Seller",
        "payment_proof": "Payment Proof (receipt, bank statement, UPI)",
        "refund_receipt": "Refund Receipt / Acknowledgement",
        "correspondence_with_seller": "Correspondence with Seller",
        "service_agreement": "Service Agreement / Contract",
        "communication_logs": "Communication Logs",
        "repair_receipt": "Repair Receipt",
        "advertisement_copy": "Copy of the Advertisement",
        "communication_with_seller": "Communication with Seller",
        "shipping_receipt": "Shipping / Delivery Receipt",
        "complaint_copy": "Copy of Written Complaint",
        "contract_document": "Contract Document / Agreement",
        "correspondence_between_parties": "Correspondence Between Parties",
        "payment_receipts": "Payment Receipts",
        "evidence_of_breach": "Evidence of Breach",
        "legal_notice_copy": "Legal Notice Copy",
        "evidence_of_non_performance": "Evidence of Non-Performance",
        "invoice_or_payment_demand": "Invoice / Payment Demand",
        "bank_statements": "Bank Statements",
        "evidence_of_violation": "Evidence of Violation",
        "rental_agreement": "Rental / Lease Agreement",
        "deposit_payment_receipt": "Deposit Payment Receipt",
        "bank_statement_showing_deposit": "Bank Statement Showing Deposit",
        "property_condition_photos": "Property Condition Photographs",
        "correspondence_with_landlord": "Correspondence with Landlord",
        "rent_payment_receipts": "Rent Payment Receipts",
        "eviction_notice": "Eviction Notice",
        "photographs_of_property": "Photographs of Property",
        "transaction_records": "Transaction Records",
        "screenshots_of_fraud": "Screenshots of Fraudulent Activity",
        "communication_with_fraudster": "Communication with Fraudster",
        "fir_copy": "FIR Copy",
        "screenshots_of_unauthorized_activity": "Screenshots of Unauthorized Activity",
        "login_alerts": "Login Alerts / Notifications",
        "email_notifications": "Email Notifications",
        "device_logs": "Device Logs",
        "screenshots_of_impersonation": "Screenshots of Impersonation",
        "profile_urls": "Profile URLs of Fake Accounts",
        "identity_proof": "Identity Proof",
        "screenshots_of_harassment": "Screenshots of Harassment",
        "message_records": "Message Records",
        "call_records": "Call Records",
        "platform_report_copy": "Platform Report / Complaint Copy",
        "system_logs": "System Logs",
        "screenshots_of_breach": "Screenshots of Breach",
        "forensic_report": "Forensic Report (if available)",
    }

    def __init__(self) -> None:
        self._conn = get_db_connection()
        if not self._conn:
            # Allow graceful operation without DB
            self._conn = None

    def _fetch_mandatory_documents(self, document_names: List[str]) -> List[str]:
        """Return the subset of *document_names* that are marked mandatory in the DB.
        """
        if not document_names or not self._conn:
            return []
        try:
            cursor = self._conn.cursor(dictionary=True)
            # Build a parameter list for the IN clause.
            placeholders = ",".join(["%s"] * len(document_names))
            query = f"SELECT document_name FROM documents WHERE document_name IN ({placeholders}) AND is_mandatory = TRUE"
            cursor.execute(query, tuple(document_names))
            rows = cursor.fetchall()
            cursor.close()
            return [row["document_name"] for row in rows]
        except Exception:
            return []

    def get_display_name(self, doc_id: str) -> str:
        """Return a human-readable name for a document identifier."""
        return self._DOCUMENT_DISPLAY_NAMES.get(doc_id, doc_id.replace("_", " ").title())

    def recommend(self, issue: str, available_documents: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return a structured recommendation for *issue*.

        Parameters
        ----------
        issue: str
            Human readable name of the consumer issue (case‑insensitive).
        available_documents: list[str] | None
            Document identifiers the user already possesses.
        """
        issue_key = (issue or "").strip().lower()
        recommended = self._ISSUE_DOCUMENT_MAP.get(issue_key, [])
        available = available_documents or []
        missing = [doc for doc in recommended if doc not in available]
        mandatory = self._fetch_mandatory_documents(recommended)

        # Build display-friendly list
        recommended_display = [
            {"id": doc, "name": self.get_display_name(doc)} for doc in recommended
        ]
        missing_display = [
            {"id": doc, "name": self.get_display_name(doc)} for doc in missing
        ]

        return {
            "issue": issue,
            "recommended_documents": recommended,
            "recommended_documents_display": recommended_display,
            "available_documents": available,
            "missing_documents": missing,
            "missing_documents_display": missing_display,
            "mandatory_documents": mandatory,
            "notes": [],
        }
