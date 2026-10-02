from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _paragraph(value, style):
    if value is None or value == "":
        value = "Not provided"
    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)


def build_case_report_pdf(report, case_id, created_at, facts, timeline):
    """Render the existing case report as a readable, non-JSON PDF."""
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="LegalAssist Defective Product Case Report",
        author="LegalAssist",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LegalAssistTitle",
        parent=base["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#193b53"),
        spaceAfter=7 * mm,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=base["Heading2"],
        textColor=colors.HexColor("#236f6c"),
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=base["BodyText"],
        leading=14,
        spaceAfter=2 * mm,
        wordWrap="CJK",
    )
    small_style = ParagraphStyle(
        "ReportSmall",
        parent=body_style,
        fontSize=8.5,
        textColor=colors.HexColor("#586b77"),
    )
    story = [
        Paragraph("LegalAssist", title_style),
        _paragraph("Defective Product Case Report", heading_style),
    ]

    metadata = [
        ["Case ID", case_id or "Not provided"],
        ["Case date", created_at or "Not provided"],
        ["Selected issue", report.get("case_summary", {}).get("selected_issue", "Defective Product")],
    ]
    metadata_table = Table(
        [[_paragraph(key, body_style), _paragraph(value, body_style)] for key, value in metadata],
        colWidths=[42 * mm, 118 * mm],
        hAlign="LEFT",
    )
    metadata_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf4f4")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d5e0e4")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5e0e4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([metadata_table, Spacer(1, 3 * mm)])

    summary = report.get("case_summary", {})
    resolution = summary.get("seller_response_resolution", {})
    summary_fields = [
        ("Product purchased from seller/business", _yes_no(summary.get("product_purchased"))),
        ("Product has a problem", _yes_no(summary.get("product_has_problem"))),
        ("Product name", summary.get("product_name")),
        ("Seller/business name", summary.get("seller_name")),
        ("Purchase date", summary.get("purchase_date")),
        ("Amount paid", summary.get("amount_paid")),
        ("Order/invoice number", summary.get("order_or_invoice_number")),
        ("Problem/situation", summary.get("problem_situation")),
        ("Seller contacted", _yes_no(summary.get("seller_contacted"))),
        ("Seller resolved problem", _yes_no(resolution.get("problem_resolved"))),
        ("Seller response/details", resolution.get("response_details")),
        ("Desired resolution", summary.get("desired_resolution")),
    ]
    story.append(Paragraph("Your Situation / Case Summary", heading_style))
    summary_table = Table(
        [[_paragraph(key, small_style), _paragraph(value, body_style)] for key, value in summary_fields],
        colWidths=[58 * mm, 102 * mm],
        repeatRows=0,
        hAlign="LEFT",
    )
    summary_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d5e0e4")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5e0e4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_table)

    story.append(Paragraph("Answers / Facts", heading_style))
    for fact_key, value in facts.items():
        story.append(_paragraph(f"{fact_key.replace('_', ' ').title()}: {_yes_no(value)}", body_style))

    story.append(Paragraph("Possible Legal Issue", heading_style))
    story.append(_paragraph(report.get("possible_issue") or report.get("assessment"), body_style))
    story.append(Paragraph("Relevant Law", heading_style))
    provisions = report.get("legal_provisions") or []
    if not provisions and report.get("legal_provision"):
        provisions = [report["legal_provision"]]
    for provision in provisions:
        story.append(_paragraph(
            f"{provision.get('act_name')} — {provision.get('section_number')}: {provision.get('title')}",
            body_style,
        ))
        if provision.get("description"):
            story.append(_paragraph(provision["description"], body_style))
    story.append(Paragraph("Why This May Apply", heading_style))
    story.append(_paragraph(report.get("why_relevant"), body_style))

    story.append(Paragraph("Evidence", heading_style))
    for item in report.get("evidence_checklist", []):
        status = "Reported available" if item.get("available") is True else "Not reported"
        story.append(_paragraph(f"{item.get('name')}: {status}", body_style))

    story.append(Paragraph("Possible Options / Remedies", heading_style))
    for option in report.get("possible_options", []):
        story.append(_paragraph(f"• {option}", body_style))

    story.append(Paragraph("What To Do Next", heading_style))
    for step_number, step in enumerate(report.get("next_steps", []), start=1):
        story.append(_paragraph(f"{step_number}. {step}", body_style))

    story.append(Paragraph("Where To Complain", heading_style))
    complaint = report.get("where_to_complain") or {}
    grievance = complaint.get("grievance_support") or {}
    if grievance:
        story.append(_paragraph(
            f"{grievance.get('name')}: {grievance.get('phone')}; {grievance.get('url')}. {grievance.get('description')}",
            body_style,
        ))
    formal = complaint.get("formal_complaint") or {}
    if formal:
        story.append(_paragraph(formal.get("message"), body_style))
    pecuniary = complaint.get("pecuniary_jurisdiction") or {}
    if pecuniary.get("determined"):
        story.append(_paragraph(
            f"Informational jurisdiction estimate: {pecuniary.get('authority')} based on consideration paid of INR {pecuniary.get('consideration_paid')}. {pecuniary.get('message')}",
            body_style,
        ))
    else:
        story.append(_paragraph(pecuniary.get("message"), body_style))
    story.append(_paragraph(complaint.get("territorial_note"), body_style))
    for factor in complaint.get("territorial_jurisdiction_factors", []):
        story.append(_paragraph(f"• {factor}", small_style))

    if timeline:
        story.append(Paragraph("Case Timeline", heading_style))
        for item in timeline:
            detail = item.get("details", {})
            suffix = f" ({detail.get('fact')})" if detail.get("fact") else ""
            story.append(_paragraph(f"{item.get('at', 'Date not recorded')} — {item.get('event', 'Case event')}{suffix}", small_style))

    story.extend([
        Spacer(1, 4 * mm),
        _paragraph(report.get("disclaimer"), small_style),
    ])
    document.build(story)
    return output.getvalue()


def _yes_no(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not provided"