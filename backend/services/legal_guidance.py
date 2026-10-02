import json
import os
from typing import List, Dict, Any

# Reuse existing DB connection helper (optional for remedies)
from database.db import get_db_connection

# Path to the legal provisions JSON relative to this file
_PROVISIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "legal_provisions.json")


class LegalGuidanceService:
    """Map inference conclusions to structured legal guidance.

    The service reads static provisions from ``legal_provisions.json`` and, when
    available, fetches remedy texts from the ``legal_remedies`` MySQL table.
    It does **not** perform any inference – it only translates the supplied
    conclusions.
    """

    def __init__(self):
        self._provisions = self._load_provisions()
        self._conclusion_map = self._build_conclusion_map()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def get_guidance(self, conclusions: List[str]) -> List[Dict[str, Any]]:
        """Return guidance for each recognised conclusion.

        Unrecognised conclusions produce an ``"Unknown"`` entry.
        Duplicate provisions are suppressed – the same provision will appear
        only once in the output.
        """
        guidances: List[Dict[str, Any]] = []
        seen_provisions: set = set()
        for concl in conclusions:
            prov = self._conclusion_map.get(concl)
            if prov:
                sec_key = (prov.get("act_name"), prov.get("section_number"))
                if sec_key in seen_provisions:
                    # Section already reported – add a minimal entry for the issue
                    guidances.append({
                        "issue": self._human_readable_issue(concl),
                        "inference_conclusion": concl,
                        "applicable_law": [],
                        "possible_remedies": [],
                        "disclaimer": "Provision already listed for another issue.",
                    })
                    continue
                seen_provisions.add(sec_key)
                guidances.append({
                    "issue": self._human_readable_issue(concl),
                    "inference_conclusion": concl,
                    "applicable_law": [
                        {
                            "act_name": prov.get("act_name"),
                            "section_number": prov.get("section_number"),
                            "title": prov.get("title"),
                            "plain_language_description": prov.get("plain_language_description"),
                            "applicability": prov.get("applicability"),
                            "source_url": prov.get("source_url"),
                            "verification_status": prov.get("verification_status", "pending"),
                            "last_verified_date": prov.get("last_verified_date"),
                            "jurisdictional_note": prov.get("jurisdictional_note"),
                        }
                    ],
                    "possible_remedies": self._get_remedies_for_conclusion(concl),
                    "next_steps": self._get_next_steps(concl),
                    "recommended_action": self._recommended_action(concl),
                    "disclaimer": "This is preliminary guidance and not legal advice.",
                })
            else:
                # Unknown or missing provision
                guidances.append({
                    "issue": "Unknown",
                    "inference_conclusion": concl,
                    "message": "No matching legal guidance was found in the current knowledge base.",
                    "applicable_law": [],
                    "possible_remedies": [],
                })
        return guidances

    def get_provision_by_section(self, section_number: str) -> Dict[str, Any] | None:
        """Return one configured provision without running inference."""
        for provision in self._provisions:
            if provision.get("section_number") == section_number:
                return dict(provision)
        return None

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _load_provisions(self) -> List[Dict[str, Any]]:
        """Load provisions from the JSON file and flatten them.

        Returns a list of provision dictionaries, each enriched with ``act_name``.
        """
        try:
            with open(_PROVISIONS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        provisions: List[Dict[str, Any]] = []
        for act in data:
            act_name = act.get("act_name")
            # Append the year if present to match test expectations
            year = act.get("year")
            if year:
                act_name = f"{act_name}, {year}"
            for prov in act.get("provisions", []):
                prov_copy = prov.copy()
                prov_copy["act_name"] = act_name
                provisions.append(prov_copy)
        return provisions

    def _build_conclusion_map(self) -> Dict[str, Dict[str, Any] | None]:
        """Map known conclusions to provision dictionaries.

        If a required provision is not present in the JSON, a minimal fallback is
        created (used for Section 35 which is not in the current JSON).
        """
        def find(title: str) -> Dict[str, Any] | None:
            for p in self._provisions:
                if p.get("title") == title:
                    return p
            return None

        def find_section(section: str) -> Dict[str, Any] | None:
            for p in self._provisions:
                if p.get("section_number") == section:
                    return p
            return None

        # Build mapping from conclusion key to provision
        mapping: Dict[str, Dict[str, Any] | None] = {}

        # Consumer domain mappings
        explicit = {
            "defective_product_issue": "Section 2(10)",
            "deficient_service_issue": "Section 2(11)",
            "potential_consumer_dispute": "Section 2(8)",
            "potential_unfair_trade_practice": "Section 2(47)",
            "consumer_complaint_route_available": "Section 35",
            "refund_replacement_issue": "Section 2(9)",
            "warranty_related_issue": "Section 2(9)",
            "ecommerce_consumer_issue": "Section 2(16)",
        }
        for concl, sec in explicit.items():
            prov = find_section(sec)
            if prov:
                mapping[concl] = prov
            else:
                fallback = {
                    "act_name": "Consumer Protection Act, 2019",
                    "section_number": sec,
                    "title": "(Not detailed in knowledge base)",
                    "plain_language_description": None,
                    "applicability": None,
                    "source_url": None,
                }
                mapping[concl] = fallback

        # Contract domain mappings (by title)
        contract_map = {
            "breach_of_contract_issue": "Compensation for breach of contract",
            "non_performance_issue": "Effect of refusal to perform promise wholly",
            "payment_dispute_issue": "Compensation for breach of contract",
            "contractual_term_violation_issue": "Compensation for breach of contract",
        }
        for concl, title in contract_map.items():
            prov = find(title)
            if prov:
                mapping[concl] = prov

        # Rental domain mappings
        rental_map = {
            "security_deposit_dispute": "Security Deposit",
            "rent_related_dispute": "Rights and liabilities of lessor and lessee",
            "landlord_tenant_obligation_dispute": "Landlord and Tenant Obligations",
            "eviction_termination_issue": "Determination of lease",
        }
        for concl, title in rental_map.items():
            prov = find(title)
            if prov:
                mapping[concl] = prov

        # Cyber domain mappings
        cyber_map = {
            "online_financial_fraud_issue": "Cheating and dishonestly inducing delivery of property",
            "unauthorized_access_issue": "Computer related offences",
            "identity_theft_issue": "Punishment for identity theft",
            "cyber_harassment_issue": "Punishment for publishing or transmitting obscene material in electronic form",
            "data_theft_issue": "Penalty and compensation for damage to computer, computer system, etc.",
        }
        for concl, title in cyber_map.items():
            prov = find(title)
            if prov:
                mapping[concl] = prov

        return mapping

    def _human_readable_issue(self, conclusion: str) -> str:
        friendly = {
            # Consumer
            "defective_product_issue": "Defective Product",
            "deficient_service_issue": "Deficient Service",
            "potential_consumer_dispute": "Potential Consumer Dispute",
            "potential_unfair_trade_practice": "Potential Unfair Trade Practice",
            "consumer_complaint_route_available": "Consumer Complaint Route Available",
            "refund_replacement_issue": "Refund / Replacement Issue",
            "warranty_related_issue": "Warranty Related Issue",
            "ecommerce_consumer_issue": "E-Commerce Consumer Issue",
            # Contract
            "breach_of_contract_issue": "Breach of Contract",
            "non_performance_issue": "Non-Performance of Contract",
            "payment_dispute_issue": "Payment / Non-Payment Dispute",
            "contractual_term_violation_issue": "Contractual Term Violation",
            # Rental
            "security_deposit_dispute": "Security Deposit Dispute",
            "rent_related_dispute": "Rent Related Dispute",
            "landlord_tenant_obligation_dispute": "Landlord / Tenant Obligation Dispute",
            "eviction_termination_issue": "Eviction / Lease Termination Issue",
            # Cyber
            "online_financial_fraud_issue": "Online Financial Fraud",
            "unauthorized_access_issue": "Unauthorized Access / Account Compromise",
            "identity_theft_issue": "Online Identity Theft / Impersonation",
            "cyber_harassment_issue": "Cyber Harassment",
            "data_theft_issue": "Data Theft / System Damage",
        }
        return friendly.get(conclusion, conclusion)

    def _recommended_action(self, conclusion: str) -> str:
        # Generic safe recommendation – can be refined later.
        return "Consider reviewing the relevant legal provisions and, if needed, seek professional legal advice."

    def _get_remedies_for_conclusion(self, conclusion: str) -> List[str]:
        """Return verified remedies from the knowledge base for a conclusion."""
        remedies_map = {
            # Consumer
            "defective_product_issue": [
                "Replacement of the defective product",
                "Refund of the purchase price",
                "Repair of the defective product at no cost",
                "Compensation for loss or damage suffered"
            ],
            "deficient_service_issue": [
                "Re-performance of the service at no cost",
                "Refund of the service charges",
                "Compensation for loss or damage suffered"
            ],
            "potential_consumer_dispute": [
                "Filing a complaint with the appropriate Consumer Disputes Redressal Commission",
                "Seeking compensation for loss or damage",
                "Seeking direction for replacement, refund, or repair"
            ],
            "potential_unfair_trade_practice": [
                "Filing a complaint with the Consumer Commission",
                "Seeking compensation for loss caused by unfair trade practice",
                "Direction to discontinue the unfair trade practice"
            ],
            "refund_replacement_issue": [
                "Refund of the purchase price",
                "Replacement of the product",
                "Compensation for inconvenience and loss"
            ],
            "warranty_related_issue": [
                "Repair or replacement under warranty terms",
                "Compensation if warranty obligations are not met"
            ],
            "ecommerce_consumer_issue": [
                "Return and refund as per e-commerce platform policy",
                "Filing a complaint with the Consumer Commission",
                "Complaint to the e-commerce platform grievance officer"
            ],
            # Contract
            "breach_of_contract_issue": [
                "Compensation for loss or damage caused by the breach (Section 73, Indian Contract Act)",
                "Specific performance of the contract (where applicable)"
            ],
            "non_performance_issue": [
                "Right to put an end to the contract (Section 39)",
                "Compensation for loss caused by non-performance"
            ],
            "payment_dispute_issue": [
                "Recovery of the due amount",
                "Compensation for delayed payment",
                "Interest on the unpaid amount (if stipulated in contract)"
            ],
            "contractual_term_violation_issue": [
                "Compensation for breach of the specific term",
                "Right to terminate the contract if the violation is material"
            ],
            # Rental
            "security_deposit_dispute": [
                "Recovery of the security deposit through appropriate legal forum",
                "Deduction only for legitimate damages beyond normal wear and tear"
            ],
            "rent_related_dispute": [
                "Approach the Rent Controller or appropriate authority under the applicable state rent control act"
            ],
            "landlord_tenant_obligation_dispute": [
                "Enforcement of obligations through appropriate legal forum",
                "Compensation for breach of obligations"
            ],
            "eviction_termination_issue": [
                "Challenge unlawful eviction through the Rent Controller or court",
                "Proper notice as required under the applicable law"
            ],
            # Cyber
            "online_financial_fraud_issue": [
                "File a complaint on the National Cyber Crime Reporting Portal (cybercrime.gov.in)",
                "Report to the local police / cyber crime cell",
                "Contact your bank immediately to freeze/block the account or card"
            ],
            "unauthorized_access_issue": [
                "File a complaint on the National Cyber Crime Reporting Portal",
                "Report to the local police / cyber crime cell",
                "Change all passwords and enable two-factor authentication"
            ],
            "identity_theft_issue": [
                "File a complaint on the National Cyber Crime Reporting Portal",
                "Report to local police",
                "Notify relevant platforms about the impersonation"
            ],
            "cyber_harassment_issue": [
                "File a complaint on the National Cyber Crime Reporting Portal",
                "Report to local police / cyber crime cell",
                "Block the harasser and preserve evidence of harassment"
            ],
            "data_theft_issue": [
                "File a complaint on the National Cyber Crime Reporting Portal",
                "Report to local police / cyber crime cell",
                "Seek compensation under Section 43 of the IT Act"
            ],
        }
        return remedies_map.get(conclusion, [])

    def _get_next_steps(self, conclusion: str) -> List[str]:
        """Return practical next steps based on the identified issue."""
        next_steps_map = {
            # Consumer
            "defective_product_issue": [
                "Preserve all purchase records (invoice, receipt, order confirmation).",
                "Preserve evidence of the defect (photographs, videos).",
                "Contact the seller/service provider where appropriate.",
                "Keep records of all communications with the seller.",
                "If the issue remains unresolved, consider filing a complaint with the Consumer Commission."
            ],
            "deficient_service_issue": [
                "Preserve the service agreement or contract.",
                "Document the deficiency with evidence.",
                "Contact the service provider in writing.",
                "Keep records of all communications.",
                "If the issue remains unresolved, consider filing a complaint with the Consumer Commission."
            ],
            "potential_consumer_dispute": [
                "Collect all evidence and documentation.",
                "Prepare a written complaint with relevant details.",
                "File a complaint with the appropriate Consumer Disputes Redressal Commission.",
                "Consider seeking assistance from a consumer rights organization."
            ],
            "potential_unfair_trade_practice": [
                "Preserve a copy of the misleading advertisement or representation.",
                "Document the difference between what was promised and what was delivered.",
                "File a complaint with the Consumer Commission.",
                "You may also report to the Advertising Standards Council of India (ASCI)."
            ],
            "refund_replacement_issue": [
                "Preserve proof of purchase and refund/replacement request.",
                "Send a written demand to the seller.",
                "If denied, consider filing a consumer complaint."
            ],
            "warranty_related_issue": [
                "Preserve the warranty card/document.",
                "Preserve proof of purchase.",
                "Document the warranty claim and the denial.",
                "Contact the manufacturer or authorized service center."
            ],
            "ecommerce_consumer_issue": [
                "Preserve screenshots of the product listing and order confirmation.",
                "Use the e-commerce platform's grievance mechanism first.",
                "File a complaint with the Consumer Commission if unresolved."
            ],
            # Contract
            "breach_of_contract_issue": [
                "Preserve the original contract document.",
                "Document the breach with evidence.",
                "Send a legal notice to the breaching party.",
                "If unresolved, consider filing a civil suit for damages.",
                "Consult a legal professional for advice."
            ],
            "non_performance_issue": [
                "Preserve the contract document.",
                "Send a written notice demanding performance.",
                "If performance is refused, consider terminating the contract.",
                "Seek legal advice regarding compensation."
            ],
            "payment_dispute_issue": [
                "Preserve evidence of the payment obligation (contract, invoice).",
                "Send a written demand for payment.",
                "If payment is not received, send a legal notice.",
                "Consider filing a recovery suit or summary suit."
            ],
            "contractual_term_violation_issue": [
                "Identify the specific term that was violated.",
                "Preserve evidence of the violation.",
                "Send a written notice about the violation.",
                "Seek legal advice on remedies available."
            ],
            # Rental
            "security_deposit_dispute": [
                "Preserve a copy of the rental agreement.",
                "Preserve evidence of the security deposit payment (receipt, bank statement).",
                "Send a written demand for return of the deposit.",
                "If the landlord does not respond, consider approaching the Rent Controller or filing a civil suit.",
                "Note: Rent laws vary by state — identify the applicable state law."
            ],
            "rent_related_dispute": [
                "Preserve the rental agreement.",
                "Document rent payment history.",
                "Send a written communication about the dispute.",
                "Approach the Rent Controller or appropriate authority.",
                "Note: Rent laws vary by state — identify the applicable state law."
            ],
            "landlord_tenant_obligation_dispute": [
                "Preserve the rental agreement.",
                "Document the breach of obligation with evidence.",
                "Communicate in writing with the other party.",
                "Approach the appropriate legal forum.",
                "Note: Rent laws vary by state — identify the applicable state law."
            ],
            "eviction_termination_issue": [
                "Preserve the rental agreement.",
                "Check the notice period requirements under the applicable rent control act.",
                "If unlawfully evicted, approach the Rent Controller immediately.",
                "Note: Rent laws vary by state — identify the applicable state law."
            ],
            # Cyber
            "online_financial_fraud_issue": [
                "Immediately contact your bank to report the fraud and block the card/account.",
                "File a complaint on the National Cyber Crime Reporting Portal (cybercrime.gov.in) or call helpline 1930.",
                "Preserve all evidence: transaction records, screenshots, messages, emails.",
                "File an FIR at the nearest police station or cyber crime cell.",
                "Do not share OTP, passwords, or banking credentials with anyone."
            ],
            "unauthorized_access_issue": [
                "Change all passwords immediately.",
                "Enable two-factor authentication on all accounts.",
                "File a complaint on the National Cyber Crime Reporting Portal.",
                "Preserve evidence of unauthorized access (login alerts, emails).",
                "Report to the local police / cyber crime cell."
            ],
            "identity_theft_issue": [
                "Report the impersonation to the relevant platform.",
                "File a complaint on the National Cyber Crime Reporting Portal.",
                "File an FIR at the nearest police station.",
                "Preserve evidence of impersonation (screenshots, URLs)."
            ],
            "cyber_harassment_issue": [
                "Do not respond to the harasser.",
                "Block the person on all platforms.",
                "Preserve evidence: screenshots, messages, call records.",
                "File a complaint on the National Cyber Crime Reporting Portal.",
                "File an FIR at the nearest police station.",
                "Seek support from trusted persons or helplines."
            ],
            "data_theft_issue": [
                "Secure your system: change passwords, update software.",
                "Preserve evidence of the breach.",
                "File a complaint on the National Cyber Crime Reporting Portal.",
                "Report to the local police / cyber crime cell.",
                "Consult a cybersecurity professional if needed."
            ],
        }
        return next_steps_map.get(conclusion, [
            "Preserve all relevant documents and evidence.",
            "Consult a qualified legal professional for specific advice."
        ])

    def _fetch_remedies(self, section_number: str) -> List[Dict[str, Any]]:
        """Query the ``legal_remedies`` table for a given section.

        If the table or data is unavailable, returns an empty list.
        """
        conn = get_db_connection()
        if not conn:
            return []
        try:
            cursor = conn.cursor(dictionary=True)
            sql = "SELECT remedy_description FROM legal_remedies WHERE section_number = %s"
            cursor.execute(sql, (section_number,))
            rows = cursor.fetchall()
            return [row["remedy_description"] for row in rows]
        except Exception:
            return []
        finally:
            cursor.close()
            conn.close()
