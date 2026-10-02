from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
import os
import json

from config import Config
from routes.auth import auth_bp
from routes.cases import cases_bp

# Inference engine and services
from inference_engine.working_memory import WorkingMemory
from inference_engine.forward_chaining import ForwardChainingEngine
from inference_engine.backward_chaining import BackwardChainingEngine
from inference_engine.reasoning_trace import ReasoningTrace
from inference_engine.resolution import ResolutionEngine
from services.legal_guidance import LegalGuidanceService
from services.authority_info import AuthorityInfoService
from services.document_recommendation import DocumentRecommendationService
from services.fact_extraction import FactExtractor
from services.defective_product import DefectiveProductService
import uuid


# ---------------------------------------------------------
# Flask Application
# ---------------------------------------------------------

app = Flask(__name__)
app.secret_key = 'super-secret-legal-key'
CORS(app, supports_credentials=True)
app.config.from_object(Config)

app.register_blueprint(auth_bp)
app.register_blueprint(cases_bp)

# Cases routes are disabled — no DB-backed case management needed yet.

# ---------------------------------------------------------
# In-Memory Session Store (replaces DB for guest usage)
# ---------------------------------------------------------
# Maps session_token -> { "facts": {}, "case_details": {}, "messages": [], "created_at": str }

_sessions = {}


def _get_or_create_session(token):
    """Return the session dict for token, creating one if needed."""
    if not token or token not in _sessions:
        token = token or str(uuid.uuid4())
        from datetime import datetime
        _sessions[token] = {
            "facts": {},
            "case_details": {},
            "messages": [],
            "created_at": datetime.utcnow().isoformat(),
        }
    return token, _sessions[token]


# ---------------------------------------------------------
# Frontend Configuration
# ---------------------------------------------------------

frontend_folder = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "frontend"
)


# ---------------------------------------------------------
# Frontend Routes
# ---------------------------------------------------------

@app.route("/")
def home():
    return send_from_directory(frontend_folder, "index.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(frontend_folder, filename)


# ---------------------------------------------------------
# Health Check API
# ---------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "message": "Legal Expert System Backend is running."
    })


@app.route("/api/phase1/questions", methods=["GET"])
def phase1_questions():
    return jsonify({"questions": DefectiveProductService.get_questions()}), 200


@app.route("/api/phase1/question", methods=["POST"])
def phase1_question():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", {})
    current_key = data.get("current_key")
    direction = data.get("direction", "next")
    if not isinstance(answers, dict) or not isinstance(current_key, (str, type(None))):
        return jsonify({"error": "Invalid question navigation data."}), 400
    try:
        result = DefectiveProductService.get_next_question(
            answers, current_key, direction
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result), 200


@app.route("/api/phase1/analyze", methods=["POST"])
def analyze_defective_product():
    if not request.is_json:
        return jsonify({"error": "A JSON request body is required."}), 400

    data = request.get_json() or {}
    answers = data.get("answers", {})
    case_details = data.get("case_details", {})
    if not isinstance(answers, dict) or not isinstance(case_details, dict):
        return jsonify({"error": "Answers and case details must be objects."}), 400

    try:
        result = DefectiveProductService.analyze(answers, case_details)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except (OSError, json.JSONDecodeError) as error:
        app.logger.exception("Unable to prepare Phase 1 guidance")
        return jsonify({"error": "Unable to prepare the guidance report."}), 500

    session_token, guest_session = _get_or_create_session(data.get("session_token"))
    guest_session["facts"] = result["facts"]
    guest_session["case_details"] = result["case_details"]
    guest_session["reasoning_trace"] = result["internal"]["reasoning_trace"]
    guest_session["backward_result"] = result["internal"]["backward_result"]
    guest_session["report"] = result["report"]
    guest_session["messages"].append({"role": "assistant", "summary": "Defective Product report prepared"})

    return jsonify({
        "success": True,
        "session_token": session_token,
        "report": result["report"],
    }), 200


# ---------------------------------------------------------
# Legal Analysis API (no auth required)
# ---------------------------------------------------------

@app.route("/api/analyze", methods=["POST"])
def analyze():

    # ---------------------------------------------------------
    # Validate request
    # ---------------------------------------------------------

    if not request.is_json:
        return jsonify({
            "error": "Invalid request: JSON body required."
        }), 400

    data = request.get_json()

    text = data.get("text", "")
    facts_input = data.get("facts")
    case_details_input = data.get("case_details", {})

    if not isinstance(facts_input, dict):
        if facts_input is None:
            facts_input = {}
        else:
            return jsonify({
                "error": "Invalid request: 'facts' must be an object."
            }), 400

    if not isinstance(case_details_input, dict):
        return jsonify({
            "error": "Invalid request: 'case_details' must be an object."
        }), 400

    # ---------------------------------------------------------
    # Session Management (in-memory, no DB, no auth)
    # ---------------------------------------------------------

    session_token = data.get("session_token")
    session_token, sess = _get_or_create_session(session_token)

    # Merge stored facts with any facts provided by the frontend
    merged_facts = {**sess["facts"], **(facts_input or {})}
    merged_case_details = {**sess["case_details"], **(case_details_input or {})}

    # ---------------------------------------------------------
    # Fact Extraction from user text
    # ---------------------------------------------------------

    new_facts, case_details = FactExtractor.extract_facts(
        text, merged_facts, merged_case_details
    )

    facts = new_facts

    # Store the updated facts and case_details back into the session
    sess["facts"] = facts
    sess["case_details"] = case_details

    # Record messages for conversation history
    if text:
        sess["messages"].append({"role": "user", "text": text})

    # ---------------------------------------------------------
    # Working Memory
    # ---------------------------------------------------------

    wm = WorkingMemory()

    for key, val in facts.items():
        if isinstance(val, bool):
            wm.add_fact(
                key,
                "true" if val else "false",
                source="user"
            )

    # ---------------------------------------------------------
    # Load Inference Rules
    # ---------------------------------------------------------

    try:
        rules_path = os.path.join(
            os.path.dirname(__file__),
            "knowledge_base",
            "inference_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
    except Exception as error:
        print("Error loading inference rules:", error)
        return jsonify({
            "error": "Failed to load inference rules."
        }), 500


    # ---------------------------------------------------------
    # Forward Chaining + Reasoning Trace
    # ---------------------------------------------------------

    trace = ReasoningTrace()

    fc_engine = ForwardChainingEngine(rules)

    inference_result = fc_engine.run(
        wm,
        trace=trace
    )

    conclusions = inference_result.get(
        "conclusions",
        []
    )


    # ---------------------------------------------------------
    # Backward Chaining / Missing Facts Questioning
    # ---------------------------------------------------------

    targeted_question = None

    # Try multiple goals to find the best targeted question
    bc_goals = [
        "potential_consumer_dispute",
        "defective_product_issue",
        "refund_replacement_issue",
        "warranty_related_issue",
        "ecommerce_consumer_issue",
        "deficient_service_issue",
        "potential_unfair_trade_practice",
    ]

    if not conclusions:
        bc_engine = BackwardChainingEngine(rules)
        all_missing = []
        for goal in bc_goals:
            bc_result = bc_engine.query(goal, "true", wm)
            missing = bc_result.get("missing_facts", [])
            if missing:
                all_missing.extend(missing)

        # Deduplicate and pick the first meaningful missing fact
        seen = set()
        unique_missing = []
        for m in all_missing:
            key = m.split('=')[0]
            if key not in seen and not wm.has_fact(key):
                seen.add(key)
                unique_missing.append(key)

        question_map = {
            "product_purchased": "Did you purchase a product or service?",
            "product_defective": "Was the product defective or damaged when you received it?",
            "seller_contacted": "Have you contacted the seller or service provider about this issue?",
            "seller_denied_or_disputed_claim": "Did the seller refuse your request or dispute your claim?",
            "refund_requested": "Have you requested a refund?",
            "refund_or_replacement_sought": "Have you asked the seller for a refund or replacement?",
            "refund_or_replacement_denied": "Did the seller refuse to give you a refund or replacement?",
            "warranty_exists": "Is the product covered by a warranty?",
            "warranty_claim_denied": "Was your warranty claim denied?",
            "warranty_claim_made": "Did you make a formal warranty claim?",
            "misleading_advertisement": "Was the product significantly different from how it was advertised?",
            "online_purchase": "Was this an online / e-commerce purchase?",
            "service_purchased": "Did you purchase a service (e.g., repair, subscription)?",
            "service_deficient": "Was the service deficient or unsatisfactory?",
            "representation_related_to_goods_or_service": "Was a representation (e.g., advertisement) made about the product or service?",
            "false_or_misleading_representation": "Was the representation false or misleading?",
        }

        if unique_missing:
            first_missing = unique_missing[0]
            targeted_question = question_map.get(
                first_missing,
                f"Could you provide more details about your situation? (Specifically: {first_missing.replace('_', ' ')})"
            )

    # ---------------------------------------------------------
    # Conflict Detection (via Resolution Engine)
    # ---------------------------------------------------------

    conflicts = []
    # Check for contradictory facts
    contradiction_pairs = [
        ("product_defective", "product_not_defective"),
        ("seller_contacted", "seller_not_contacted"),
        ("refund_requested", "refund_not_requested"),
    ]
    for pos, neg in contradiction_pairs:
        if facts.get(pos) is True and facts.get(neg) is True:
            conflicts.append(f"Conflict detected: both '{pos}' and '{neg}' are true.")

    # ---------------------------------------------------------
    # Legal Guidance
    # ---------------------------------------------------------

    try:
        legal_guidance = LegalGuidanceService().get_guidance(
            conclusions
        )
    except Exception as error:
        print("Error retrieving legal guidance:", error)
        legal_guidance = []


    # ---------------------------------------------------------
    # Authority Information
    # ---------------------------------------------------------

    amount = case_details.get("amount_paid")

    if amount is not None:
        try:
            authority_info = (
                AuthorityInfoService()
                .get_authority_information(amount)
            )
        except Exception as error:
            print(
                "Error retrieving authority information:",
                error
            )
            authority_info = {
                "note": "Authority information requires database setup. General guidance: file a complaint with the appropriate Consumer Disputes Redressal Commission."
            }
    else:
        authority_info = {
            "note": "Provide the amount paid to determine the appropriate complaint authority."
        }


    # ---------------------------------------------------------
    # Document Recommendation
    # ---------------------------------------------------------

    issue_name = None

    if legal_guidance:
        issue_name = legal_guidance[0].get("issue")

    try:
        documents = (
            DocumentRecommendationService()
            .recommend(
                issue_name or "",
                available_documents=None
            )
        )
    except Exception as error:
        print(
            "Error retrieving document recommendations:",
            error
        )
        documents = []


    # ---------------------------------------------------------
    # Out-of-Scope Detection
    # ---------------------------------------------------------

    out_of_scope = False
    out_of_scope_message = None
    if not conclusions and not targeted_question:
        # Check if we have at least some consumer-relevant facts
        consumer_relevant_keys = {
            "product_purchased", "product_defective", "service_purchased",
            "service_deficient", "refund_requested", "replacement_requested",
            "seller_contacted", "warranty_exists", "misleading_advertisement",
            "online_transaction", "product_not_delivered", "wrong_product_delivered",
        }
        has_consumer_fact = any(
            facts.get(k) is True for k in consumer_relevant_keys
        )
        if not has_consumer_fact and text:
            out_of_scope = True
            out_of_scope_message = (
                "I specialize in consumer legal issues such as defective products, "
                "refund problems, warranty disputes, misleading advertisements, "
                "and e-commerce issues. Could you describe a consumer-related problem?"
            )
            targeted_question = out_of_scope_message


    # ---------------------------------------------------------
    # Final Response
    # ---------------------------------------------------------

    # Record assistant response summary
    if legal_guidance:
        sess["messages"].append({"role": "assistant", "summary": legal_guidance[0].get("issue", "Analysis")})
    elif targeted_question:
        sess["messages"].append({"role": "assistant", "summary": targeted_question})

    response = {

        "success": True,

        "case": {
            "facts": facts,
            "case_details": case_details
        },

        "inference": inference_result,

        "reasoning": {
            "steps": trace.get_steps()
        },

        "session_token": session_token,
        "legal_guidance": legal_guidance,

        "authority": authority_info,

        "documents": documents,

        "targeted_question": targeted_question,

        "conflicts": conflicts,

        "out_of_scope": out_of_scope,

        "disclaimer": (
            "This system provides preliminary legal information "
            "for academic/informational purposes and is not a "
            "substitute for advice from a qualified legal professional."
        )
    }

    return jsonify(response), 200


# ---------------------------------------------------------
# Glossary / Knowledge Search API
# ---------------------------------------------------------

@app.route("/api/glossary", methods=["GET"])
def glossary_search():
    """Search the legal concepts knowledge base."""
    query = request.args.get("q", "").strip().lower()

    try:
        concepts_path = os.path.join(
            os.path.dirname(__file__),
            "knowledge_base",
            "legal_concepts.json"
        )
        with open(concepts_path, "r", encoding="utf-8") as f:
            concepts = json.load(f)

        provisions_path = os.path.join(
            os.path.dirname(__file__),
            "knowledge_base",
            "legal_provisions.json"
        )
        with open(provisions_path, "r", encoding="utf-8") as f:
            provisions_data = json.load(f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = []

    # Search concepts
    for concept in concepts:
        if not query or query in concept.get("concept_key", "").lower() or query in concept.get("description", "").lower():
            results.append({
                "type": "concept",
                "key": concept["concept_key"],
                "domain": concept.get("domain", ""),
                "description": concept.get("description", ""),
            })

    # Search provisions
    for act in provisions_data:
        act_name = act.get("act_name", "")
        year = act.get("year")
        if year:
            act_name = f"{act_name}, {year}"
        for prov in act.get("provisions", []):
            title = prov.get("title", "")
            section = prov.get("section_number", "")
            desc = prov.get("plain_language_description", "")
            if not query or query in title.lower() or query in section.lower() or query in (desc or "").lower():
                results.append({
                    "type": "provision",
                    "act_name": act_name,
                    "section_number": section,
                    "title": title,
                    "description": desc,
                })

    return jsonify({"results": results, "query": query}), 200


# ---------------------------------------------------------
# Case Export API
# ---------------------------------------------------------

@app.route("/api/export", methods=["POST"])
def export_case():
    """Export the current case as a structured summary."""
    data = request.get_json() or {}
    session_token = data.get("session_token")

    if not session_token or session_token not in _sessions:
        return jsonify({"error": "No active case found for this session."}), 404

    sess = _sessions[session_token]
    facts = sess["facts"]
    case_details = sess["case_details"]
    messages = sess["messages"]

    # Run inference one more time to get the full analysis
    wm = WorkingMemory()
    for key, val in facts.items():
        if isinstance(val, bool):
            wm.add_fact(key, "true" if val else "false", source="user")

    try:
        rules_path = os.path.join(
            os.path.dirname(__file__),
            "knowledge_base",
            "inference_rules.json"
        )
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
    except Exception:
        rules = []

    trace = ReasoningTrace()
    fc_engine = ForwardChainingEngine(rules)
    inference_result = fc_engine.run(wm, trace=trace)
    conclusions = inference_result.get("conclusions", [])

    try:
        legal_guidance = LegalGuidanceService().get_guidance(conclusions)
    except Exception:
        legal_guidance = []

    issue_name = legal_guidance[0].get("issue") if legal_guidance else None

    # Generate template only on explicit export
    template_content = ""
    try:
        from services.template_generation import TemplateGenerationService
        template_content = TemplateGenerationService().generate_template(
            issue_name or "", case_details
        )
    except Exception as e:
        # Template generation may fail without DB; provide a fallback
        template_content = _generate_fallback_template(issue_name, case_details, facts)

    export = {
        "success": True,
        "case_summary": {
            "facts": facts,
            "case_details": case_details,
            "identified_issues": [g.get("issue") for g in legal_guidance],
            "legal_guidance": legal_guidance,
        },
        "conversation_history": messages,
        "template": template_content,
        "created_at": sess["created_at"],
    }

    return jsonify(export), 200


def _generate_fallback_template(issue, case_details, facts):
    """Generate a basic complaint template without DB."""
    issue_str = issue or "Consumer Issue"
    lines = [
        f"Preliminary Complaint Draft — {issue_str}",
        "=" * 50,
        "",
        "1. Consumer Details",
        "   Name: [CONSUMER NAME]",
        "   Address: [CONSUMER ADDRESS]",
        "",
        "2. Opposite Party Details",
        "   Name: [SELLER / SERVICE PROVIDER NAME]",
        "   Address: [OPPOSITE PARTY ADDRESS]",
        "",
        "3. Subject",
        f"   Complaint regarding: {issue_str}",
        "",
        "4. Facts of the Matter",
    ]
    for k, v in facts.items():
        if isinstance(v, bool) and v:
            lines.append(f"   - {k.replace('_', ' ').title()}: Yes")
        elif isinstance(v, str):
            lines.append(f"   - {k.replace('_', ' ').title()}: {v}")

    if case_details.get("amount_paid"):
        lines.append(f"   - Amount Paid: Rs. {case_details['amount_paid']}")

    lines += [
        "",
        "5. Relief / Request Sought",
        "   [RELIEF REQUESTED]",
        "",
        "6. Declaration",
        "   I hereby declare that the above facts are true to the best of my knowledge.",
        "",
        "Date: ____________  Place: ____________  Signature: ____________",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------
# Run Application
# ---------------------------------------------------------

if __name__ == "__main__":

    app.run(
        debug=True,
        port=5000
    )