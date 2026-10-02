from io import BytesIO
import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def _body_font():
    candidates = [
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arial.ttf"),
        os.path.join(os.path.dirname(__file__), "..", ".venv", "Lib", "site-packages", "reportlab", "fonts", "Vera.ttf"),
    ]
    for font_path in candidates:
        if os.path.isfile(font_path):
            try:
                if "LegalAssistUnicode" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("LegalAssistUnicode", font_path))
                return "LegalAssistUnicode"
            except (OSError, ValueError):
                continue
    return "Helvetica"


def _format_date(value):
    if value in (None, ""):
        return "Not provided"
    try:
        from datetime import date
        parsed = date.fromisoformat(str(value)[:10])
        return f"{parsed.day} {parsed.strftime('%B %Y')}"
    except (TypeError, ValueError):
        return str(value)


def _format_amount(value):
    if value in (None, ""):
        return "Not provided"
    try:
        number = str(int(round(float(value))))
        if len(number) <= 3:
            grouped = number
        else:
            last_three = number[-3:]
            prefix = number[:-3]
            groups = []
            while prefix:
                groups.insert(0, prefix[-2:])
                prefix = prefix[:-2]
            grouped = f"{','.join(groups)},{last_three}"
        return f"₹{grouped}"
    except (TypeError, ValueError):
        return str(value)


def _paragraph(value, style):
    if value is None or value == "":
        value = "Not provided"
    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)


def build_case_report_pdf(report, case_id, created_at, facts, timeline, case_title=None):
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
    font_name = _body_font()
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
        fontName=font_name,
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
        ["Case title", case_title or report.get("case_summary", {}).get("selected_issue", "Defective Product")],
        ["Case date", _format_date(created_at)],
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
        ("Purchase date", _format_date(summary.get("purchase_date"))),
        ("Amount paid", _format_amount(summary.get("amount_paid"))),
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
    for evidence_name, available in (summary.get("evidence_availability") or {}).items():
        story.append(_paragraph(
            f"{evidence_name}: {'Reported available' if available is True else 'Not reported'}",
            body_style,
        ))

    story.append(Paragraph("Answers / Facts", heading_style))
    for fact_key, value in facts.items():
        display_value = _yes_no(value) if isinstance(value, bool) or value is None else str(value)
        story.append(_paragraph(f"{fact_key.replace('_', ' ').title()}: {display_value}", body_style))

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
        contacts = ", ".join(
            value for value in (grievance.get("phone"), grievance.get("alternate_phone")) if value
        )
        story.append(_paragraph(
            f"{grievance.get('name')}: {contacts}; {grievance.get('url')}. {grievance.get('description')}",
            body_style,
        ))
    formal = complaint.get("formal_complaint") or {}
    if formal:
        story.append(_paragraph(formal.get("message"), body_style))
    pecuniary = complaint.get("pecuniary_jurisdiction") or {}
    if pecuniary.get("determined"):
        story.append(_paragraph(
            f"Informational jurisdiction estimate: {pecuniary.get('authority')} based on consideration paid of {_format_amount(pecuniary.get('consideration_paid'))}. {pecuniary.get('message')}",
            body_style,
        ))
    else:
        story.append(_paragraph(pecuniary.get("message"), body_style))
    story.append(_paragraph(complaint.get("territorial_note"), body_style))
    for factor in complaint.get("territorial_jurisdiction_factors", []):
        story.append(_paragraph(f"• {factor}", small_style))

    if timeline:
        story.append(Paragraph("Case Activity", heading_style))
        for item in timeline:
            detail = item.get("details", {})
            suffix = f" ({detail.get('fact')})" if detail.get("fact") else ""
            activity_date = _format_date(item.get("at"))
            story.append(_paragraph(f"{activity_date} — {item.get('event', 'Case event')}{suffix}", small_style))

    story.extend([
        Spacer(1, 4 * mm),
        Paragraph("Disclaimer", heading_style),
        _paragraph(report.get("disclaimer"), small_style),
    ])
    document.build(story)
    return output.getvalue()


def build_legal_document_pdf(document_title, draft_text, case_id):
    """Render one explicitly requested legal-document draft for printing."""
    output = BytesIO()
    font_name = _body_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LegalDocumentTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#193b53"),
        spaceAfter=4 * mm,
    )
    meta_style = ParagraphStyle(
        "LegalDocumentMeta",
        parent=styles["BodyText"],
        fontName=font_name,
        alignment=TA_CENTER,
        fontSize=9,
        textColor=colors.HexColor("#586b77"),
        spaceAfter=5 * mm,
    )
    heading_style = ParagraphStyle(
        "LegalDocumentHeading",
        parent=styles["Heading3"],
        textColor=colors.HexColor("#236f6c"),
        spaceBefore=3 * mm,
        spaceAfter=1.5 * mm,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "LegalDocumentBody",
        parent=styles["BodyText"],
        leading=15,
        spaceAfter=2.3 * mm,
        wordWrap="CJK",
    )
    story = [
        Paragraph("LegalAssist", title_style),
        Paragraph(escape(document_title), styles["Heading1"]),
        Paragraph(f"Case ID: {escape(case_id or 'Not provided')} · Draft for review", meta_style),
    ]
    for line in draft_text.splitlines():
        normalized = line.strip()
        if not normalized:
            story.append(Spacer(1, 1.5 * mm))
        elif normalized.isupper() and len(normalized) < 100:
            story.append(Paragraph(escape(normalized), heading_style))
        else:
            story.append(Paragraph(escape(line).replace("\n", "<br/>"), body_style))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#586b77"))
        canvas.drawString(20 * mm, 11 * mm, "Preliminary draft for review; not proof of filing or acceptance.")
        canvas.drawRightString(A4[0] - 20 * mm, 11 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=document_title,
        author="LegalAssist",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def _yes_no(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not provided"