import re
from typing import Dict, Any, Tuple, Optional, List, Set


class FactExtractor:
    """Deterministic rule-based fact extraction from natural language user input.

    Uses pure symbolic AI: regex patterns, keyword/synonym dictionaries,
    and text normalization. NO ML, LLM, or external pretrained models are used.
    """

    PRODUCT_SYNONYMS: Dict[str, List[str]] = {
        "laptop": ["laptop", "laptops", "notebook", "notebooks", "macbook", "macbooks"],
        "phone": ["phone", "phones", "mobile", "mobiles", "cellphone", "cellphones", "smartphone", "smartphones", "iphone", "iphones"],
        "television": ["television", "televisions", "tv", "tvs"],
        "computer": ["computer", "computers", "pc", "desktop", "desktops"],
        "tablet": ["tablet", "tablets", "ipad", "ipads"],
        "refrigerator": ["refrigerator", "refrigerators", "fridge", "fridges", "appliance", "appliances"],
        "washing machine": ["washing machine", "washing machines", "washer", "washers"],
        "earphones": ["earphones", "earphone", "headphones", "headphone", "airpods", "earbuds"],
        "camera": ["camera", "cameras"],
        "furniture": ["furniture", "sofa", "bed", "chair", "table"],
        "clothing": ["clothing", "shirt", "shoes", "dress", "pants", "clothes", "apparel"],
        "product": ["product", "products", "item", "items", "goods", "device", "devices", "electronics"]
    }

    PURCHASE_VERBS: List[str] = [
        "bought", "buy", "purchased", "purchase", "brought", "got", "ordered",
        "ordering", "paid for", "paying for", "acquired", "acquire", "took delivery of", "take delivery of"
    ]

    DEFECT_TERMS: List[str] = [
        "damaged", "damage", "damages", "broken", "defective", "defect", "defects",
        "faulty", "fault", "faults", "not working", "does not work", "doesnt work", "doesn't work",
        "stopped working", "malfunctioning", "malfunction", "problem with the product",
        "problem with my product", "problem with the item", "problem with it",
        "arrived damaged", "arrived broken", "arrived defective", "cracked", "scratched",
        "doa", "dead on arrival", "poor quality"
    ]

    REFUND_TERMS: List[str] = [
        "return the money", "return my money", "give my money back", "give money back",
        "money back", "refund", "refund my money", "get a refund", "request a refund",
        "requested a refund", "returning the money", "returning my money", "give the money back"
    ]
    
    REPLACEMENT_TERMS: List[str] = [
        "replace", "replacement", "exchange", "wrong item", "wrong product", "defective replacement"
    ]

    REFUSAL_TERMS: List[str] = [
        "refused", "refuses", "refusing", "denied", "denies", "denying", "rejected",
        "rejects", "rejecting", "declined", "declines", "won't", "wont", "will not",
        "not returning", "not giving", "no help"
    ]

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Convert to lowercase, expand contractions, and normalize punctuation/whitespace."""
        if not text:
            return ""

        lowered = text.lower()

        # Common contraction expansions
        lowered = re.sub(r"\bwon't\b", "will not", lowered)
        lowered = re.sub(r"\bcan't\b", "cannot", lowered)
        lowered = re.sub(r"\bdoesn't\b", "does not", lowered)
        lowered = re.sub(r"\bdidn't\b", "did not", lowered)
        lowered = re.sub(r"\bisn't\b", "is not", lowered)
        lowered = re.sub(r"\baren't\b", "are not", lowered)
        lowered = re.sub(r"\bdon't\b", "do not", lowered)

        # Replace non-alphanumeric characters with spaces
        cleaned = re.sub(r"[^\w\s]", " ", lowered)
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", cleaned).strip()
        return normalized

    @classmethod
    def extract_facts(
        cls,
        text: str,
        existing_facts: Optional[Dict[str, Any]] = None,
        existing_case_details: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Extract deterministic rule-based facts from natural language input.

        Accumulates new facts into existing facts without overwriting previous facts.
        """
        facts = dict(existing_facts) if existing_facts else {}
        case_details = dict(existing_case_details) if existing_case_details else {}

        raw_text = text or ""
        norm_text = cls.normalize_text(raw_text)

        if not norm_text:
            return facts, case_details

        # -----------------------------------------------------
        # 1. Product Identification
        # -----------------------------------------------------
        found_product = None
        for canonical, synonyms in cls.PRODUCT_SYNONYMS.items():
            for syn in synonyms:
                pattern = r"\b" + re.escape(syn) + r"\b"
                if re.search(pattern, norm_text):
                    found_product = canonical
                    break
            if found_product:
                break

        if found_product:
            facts["product"] = found_product

        # -----------------------------------------------------
        # 2. Purchase Fact Extraction
        # -----------------------------------------------------
        has_purchase_verb = any(
            re.search(r"\b" + re.escape(verb) + r"\b", norm_text) for verb in cls.PURCHASE_VERBS
        )
        has_received = bool(
            re.search(r"\b(received|receive)\s+(a|an|the|my|this|our)?\s*([a-z]+)?\b", norm_text)
        )

        if has_purchase_verb or (has_received and (found_product or "order" in norm_text or "delivery" in norm_text)):
            facts["product_purchased"] = True

        # -----------------------------------------------------
        # 3. Defect Extraction
        # -----------------------------------------------------
        has_defect = any(term in norm_text for term in cls.DEFECT_TERMS)
        if has_defect:
            facts["product_defective"] = True

        # -----------------------------------------------------
        # 4. Refund / Replacement Extraction
        # -----------------------------------------------------
        has_refund_mention = any(term in norm_text for term in cls.REFUND_TERMS)
        if has_refund_mention:
            facts["refund_requested"] = True
            facts["refund_or_replacement_sought"] = True

        has_replacement_mention = any(term in norm_text for term in cls.REPLACEMENT_TERMS)
        if has_replacement_mention:
            facts["replacement_requested"] = True
            facts["refund_or_replacement_sought"] = True
            if "wrong item" in norm_text or "wrong product" in norm_text:
                facts["wrong_product_delivered"] = True

        # -----------------------------------------------------
        # 4b. Delivery and E-commerce Extraction
        # -----------------------------------------------------
        if any(term in norm_text for term in ["never arrived", "not delivered", "missing delivery", "order hasn't arrived", "order has not arrived", "delivered late"]):
            facts["product_not_delivered"] = True
            
        if any(term in norm_text for term in ["online purchase", "online order", "e-commerce", "shopping website", "marketplace", "seller platform"]):
            facts["online_transaction"] = True

        # -----------------------------------------------------
        # 4c. Warranty and Advertisement Extraction
        # -----------------------------------------------------
        if any(term in norm_text for term in ["warranty", "guarantee", "service center", "under warranty"]):
            facts["warranty_exists"] = True
            if "warranty claim" in norm_text or "service center" in norm_text:
                facts["warranty_claim_made"] = True
            if "refused" in norm_text or "denied" in norm_text or "expired" in norm_text:
                facts["warranty_service_refused"] = True

        if any(term in norm_text for term in ["misleading advertisement", "false advertisement", "false claim", "advertisement promised", "product was different from advertisement"]):
            facts["misleading_advertisement"] = True

        # -----------------------------------------------------
        # 5. Seller Refusal / Refusal Extraction
        # -----------------------------------------------------
        has_seller_refusal_phrase = any(phrase in norm_text for phrase in [
            "not returning", "not giving my money", "not giving money", "won't return",
            "will not return", "refused to return", "refuses to return", "refusing to return",
            "refused refund", "refuses refund", "refusing refund", "won't refund",
            "will not refund", "seller refused", "seller refuses", "seller is refusing",
            "they refused", "they are refusing", "seller denied", "seller rejected",
            "won't help", "will not help"
        ])

        has_general_refusal = any(term in norm_text for term in cls.REFUSAL_TERMS)

        if has_seller_refusal_phrase or (has_general_refusal and (has_refund_mention or "seller" in norm_text or "they" in norm_text or "shop" in norm_text or "store" in norm_text)):
            facts["seller_contacted"] = True
            facts["seller_denied_or_disputed_claim"] = True
            if has_refund_mention or any(w in norm_text for w in ["money", "refund", "return", "pay"]):
                facts["seller_refuses_refund"] = True
                facts["refund_requested"] = True
                facts["refund_or_replacement_sought"] = True
                facts["refund_or_replacement_denied"] = True

        # Standalone seller contacted phrases
        if any(phrase in norm_text for phrase in ["contacted", "complained", "told seller", "spoke to seller", "informed seller", "reached out to seller"]):
            facts["seller_contacted"] = True
            
        if any(phrase in norm_text for phrase in ["seller ignored", "did not respond", "no response"]):
            facts["seller_contacted"] = True
            facts["seller_denied_or_disputed_claim"] = True

        # -----------------------------------------------------
        # 6. Delivery Timing / Defect Timing
        # -----------------------------------------------------
        if any(phrase in norm_text for phrase in [
            "when delivered", "arrived damaged", "arrived broken", "arrived defective",
            "on arrival", "when i received", "already damaged", "in transit", "when unpacked", "when opened"
        ]):
            facts["damaged_on_delivery"] = True
        elif any(phrase in norm_text for phrase in [
            "became damaged later", "damaged later", "after a few days", "after some time",
            "after a week", "after a month", "stopped working after"
        ]):
            facts["damaged_on_delivery"] = False

        # -----------------------------------------------------
        # 7. Service Domain Extraction
        # -----------------------------------------------------
        if any(w in norm_text for w in ["service", "repair service", "subscription", "hired"]):
            facts["service_purchased"] = True
        if any(p in norm_text for p in ["poor service", "bad service", "deficient service", "service defect", "terrible service", "unsatisfactory service"]):
            facts["service_deficient"] = True

        # -----------------------------------------------------
        # 8. Contract Domain Extraction
        # -----------------------------------------------------
        if any(w in norm_text for w in ["contract", "agreement", "signed deed"]):
            facts["contract_exists"] = True
        if any(p in norm_text for p in ["did not perform", "failed to perform", "breach of contract", "violated contract", "breach"]):
            facts["obligation_not_performed"] = True
        if any(p in norm_text for p in ["refused to perform", "refuses to perform", "unwilling", "cancel", "cancelling"]):
            facts["party_refused_performance"] = True
        if any(p in norm_text for p in ["payment due", "payment is due", "invoice due"]):
            facts["payment_due"] = True
        if any(p in norm_text for p in ["payment not received", "has not paid", "did not pay me"]):
            facts["payment_not_received"] = True

        # -----------------------------------------------------
        # 9. Rental Domain Extraction
        # -----------------------------------------------------
        if any(w in norm_text for w in ["rent", "rental", "lease", "tenant", "landlord"]):
            facts["rental_agreement_exists"] = True
        if any(w in norm_text for w in ["security deposit", "deposit"]):
            facts["security_deposit_paid"] = True
        if any(p in norm_text for p in ["deposit not returned", "refused to return deposit", "withheld deposit", "not returning deposit"]):
            facts["deposit_not_returned"] = True
        if any(w in norm_text for w in ["evict", "eviction", "kicked out", "lease termination"]):
            facts["eviction_or_termination_issue"] = True

        # -----------------------------------------------------
        # 10. Cyber Domain Extraction
        # -----------------------------------------------------
        if any(p in norm_text for p in ["online transaction", "transferred money", "paid online", "upi transaction"]):
            facts["online_transaction"] = True
        if any(p in norm_text for p in ["scam", "scammed", "fraud", "cheated", "phishing"]):
            facts["fraud_or_deception"] = True
        if any(p in norm_text for p in ["lost money", "money deducted", "money stolen"]):
            facts["financial_loss"] = True
        if any(p in norm_text for p in ["hacked", "unauthorized access", "account compromised"]):
            facts["unauthorized_access"] = True
            facts["account_compromised"] = True

        # -----------------------------------------------------
        # 11. Case Details (Amount Paid)
        # -----------------------------------------------------
        amount_match = re.search(r"(?:rs\.?|rupees?|₹)\s*([\d,]+)|([\d,]+)\s*(?:rupees?|rs\.?)", raw_text, re.IGNORECASE)
        if amount_match:
            amt_str = (amount_match.group(1) or amount_match.group(2)).replace(",", "")
            try:
                case_details["amount_paid"] = float(amt_str)
            except ValueError:
                pass

        return facts, case_details
