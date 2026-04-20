import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

import google.generativeai as genai
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from fpdf import FPDF


SYSTEM_PROMPT = """
You are an expert resume writer with 15 years in writing resumes. Your goal is to tailor the candidate's resume to a job description while matching a strict visual format and length constraint.

═══════════════════════════════════════
VISUAL FORMATTING RULES (CRITICAL)
═══════════════════════════════════════
1. MARGINS & SPACING: 
   - Content must be dense to fit a "Narrow Margin" (0.5 inch) layout.
   - ELIMINATE all extra vertical spacing. There should be NO empty lines between a section's text, the horizontal separator, and the following section header.

2. CONTACT HEADER (CENTERED):
   - Name centered at the top.
   - Directly below: Location | Email | Phone | LinkedIn | GitHub (centered, single line)[cite: 68].
   - Insert a horizontal line "__________________________________________________________________" immediately after the contact info.

3. SECTION HEADERS: 
   - Use these EXACT titles in ALL CAPS and BOLD: 
   - **PROFILE**, **EXPERIENCE:**, **EDUCATION**, **LEADERSHIP :**, **TECHNICAL SKILLS**, **ACADEMIC PROJECTS**, **ADDITIONAL CERTIFICATIONS**, and **Hobbies :**.

4. HORIZONTAL SEPARATORS:
   - Insert a full-width horizontal line "__________________________________________________________________" immediately after the contact header and after every section's content (as shown in the reference image).

5. SECTION STRUCTURE:
   - EXPERIENCE & LEADERSHIP: **Organization – Location** (Bold)[cite: 75], then **Role | Dates** (Bold) on the next line[cite: 76], followed by compact bullet points.
   - BOLDING: Bold key technical terms and metrics within the text (e.g., **30%**, **Python**, **SQL**, **95%**) to mirror the reference image.
6. PROJECT TITLES (NEW RULE):
   - Every project title within the **ACADEMIC PROJECTS** section MUST be in **BOLD ALL CAPS** (e.g., **GPT FROM SCRATCH**)[cite: 103].
═══════════════════════════════════════
CONTENT & LENGTH MANAGEMENT
═══════════════════════════════════════
- MAX LENGTH: 1 page. 
- SMART PRUNING: You are REQUIRED to remove irrelevant academic projects or leadership bullets if needed to stay under 1.5 pages. Prioritize the most relevant 2-3 projects for the job description [cite: 102-130].
- NO FABRICATION: Only use provided experience .
- Preserve core metrics: 4.0 GPA [cite: 88], 30% query optimization [cite: 79], and 95% accuracy[cite: 78].

═══════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════
Return the response in this exact format:

---RESUME---
[Full Tailored Resume]

---KEYWORDS MATCHED---
[List]

---ATS SCORE---
[Score & Explanation]
"""


MODEL_NAME = "models/gemini-2.5-flash-lite"
ALLOWED_FONT_SIZES = {8, 10, 12}
INPUT_TOKEN_PRICE = 0.000001
OUTPUT_TOKEN_PRICE = 0.000005

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"

app = Flask(__name__)
load_dotenv(BASE_DIR / ".env", override=True)


def _default_settings() -> Dict[str, Any]:
    return {"base_resume": "", "font_size": 10}


def normalize_font_size(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 10
    return parsed if parsed in ALLOWED_FONT_SIZES else 10


def load_settings() -> Dict[str, Any]:
    default = _default_settings()
    if not DATA_FILE.exists():
        return default

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
    except (json.JSONDecodeError, OSError):
        return default

    base_resume = str(loaded.get("base_resume", ""))
    font_size = normalize_font_size(loaded.get("font_size", 10))
    return {"base_resume": base_resume, "font_size": font_size}


def save_settings(settings: Dict[str, Any]) -> None:
    serializable = {
        "base_resume": str(settings.get("base_resume", "")),
        "font_size": normalize_font_size(settings.get("font_size", 10)),
    }
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(serializable, file, indent=2)


def parse_model_output(text: str) -> Dict[str, str]:
    result = {"resume": "", "keywords": "", "ats_score": ""}
    cleaned = text.strip()

    sections = [
        ("---RESUME---", "resume"),
        ("---KEYWORDS MATCHED---", "keywords"),
        ("---ATS SCORE---", "ats_score"),
    ]

    for idx, (header, key) in enumerate(sections):
        if header not in cleaned:
            continue
        start = cleaned.find(header) + len(header)
        if idx < len(sections) - 1:
            next_header = sections[idx + 1][0]
            end = cleaned.find(next_header, start)
            chunk = cleaned[start:end if end != -1 else None]
        else:
            chunk = cleaned[start:]
        result[key] = chunk.strip()

    if not result["resume"]:
        result["resume"] = cleaned

    return result


def compute_cost(usage: Any) -> Dict[str, Any]:
    input_tokens = 0
    output_tokens = 0

    if usage is not None:
        input_tokens = int(
            getattr(usage, "input_tokens", 0)
            or getattr(usage, "prompt_token_count", 0)
            or 0
        )
        output_tokens = int(
            getattr(usage, "output_tokens", 0)
            or getattr(usage, "candidates_token_count", 0)
            or 0
        )

    input_cost = input_tokens * INPUT_TOKEN_PRICE
    output_cost = output_tokens * OUTPUT_TOKEN_PRICE
    total_cost = input_cost + output_cost

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": round(input_cost, 8),
        "output_cost": round(output_cost, 8),
        "total_cost": round(total_cost, 8),
        "display": f"${total_cost:.8f}",
    }


def configure_gemini_client() -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable.")
    genai.configure(api_key=api_key)


def build_prompt(base_resume: str, job_description: str) -> str:
    return "BASE_RESUME:\n" + base_resume + "\n\nJOB_DESCRIPTION:\n" + job_description


def sanitize_pdf_text(text: str) -> str:
    replacements = {
        "\u2022": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\xa0": " ",
    }
    normalized = text
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized.encode("latin-1", errors="replace").decode("latin-1")


def split_markdown_bold_segments(text: str) -> list[tuple[str, bool]]:
    segments: list[tuple[str, bool]] = []
    parts = text.split("**")
    for idx, part in enumerate(parts):
        if not part:
            continue
        segments.append((part, idx % 2 == 1))
    if not segments:
        return [("", False)]
    return segments


def generate_pdf_bytes(resume_text: str, font_size: int) -> bytes:
    pdf = FPDF()
    narrow_margin_mm = 12.7
    pdf.set_margins(narrow_margin_mm, narrow_margin_mm, narrow_margin_mm)
    pdf.set_auto_page_break(auto=True, margin=narrow_margin_mm)
    pdf.add_page()
    pdf.set_font("Times", size=font_size)

    line_height = max(3.2, font_size * 0.42)
    rendered_line_count = 0
    for line in resume_text.splitlines():
        stripped = sanitize_pdf_text(line.strip())
        if not stripped:
            continue
        plain_for_center = stripped.replace("**", "")
        if rendered_line_count < 2:
            pdf.set_font("Times", style="B", size=font_size)
            pdf.cell(0, 10, plain_for_center, align="C", ln=1)
            pdf.set_font("Times", size=font_size)
            rendered_line_count += 1
            continue
        if stripped.replace("_", "") == "" and len(stripped) >= 10:
            y_pos = min(pdf.get_y() + 2, pdf.h - pdf.b_margin)
            pdf.set_y(y_pos)
            pdf.line(pdf.l_margin, y_pos, pdf.w - pdf.r_margin, y_pos)
            pdf.set_y(y_pos + 2)
            pdf.set_x(pdf.l_margin)
            rendered_line_count += 1
            continue
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, line_height, stripped, markdown=True)
        rendered_line_count += 1

    payload = pdf.output(dest="S")
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    return payload.encode("latin-1", errors="replace")


def generate_docx_bytes(resume_text: str, font_size: int) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.5)
    section.left_margin = Inches(0.5)
    section.right_margin = Inches(0.5)

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(font_size)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0

    rendered_line_count = 0
    for line in resume_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.replace("_", "") == "" and len(stripped) >= 10:
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0

            p_pr = paragraph._p.get_or_add_pPr()
            p_bdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:space"), "0")
            bottom.set(qn("w:color"), "auto")
            p_bdr.append(bottom)
            p_pr.append(p_bdr)

            rendered_line_count += 1
            continue
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.0
        if rendered_line_count < 2:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for segment_text, segment_bold in split_markdown_bold_segments(stripped):
            run = paragraph.add_run(segment_text)
            run.font.name = "Times New Roman"
            run.font.size = Pt(font_size)
            run.bold = segment_bold or (rendered_line_count < 2)
        rendered_line_count += 1

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())


@app.route("/settings", methods=["POST"])
def update_settings():
    data = request.get_json(silent=True) or {}
    base_resume = str(data.get("base_resume", "")).strip()
    font_size = normalize_font_size(data.get("font_size", 10))

    payload = {"base_resume": base_resume, "font_size": font_size}
    save_settings(payload)
    return jsonify(payload)


@app.route("/tailor", methods=["POST"])
def tailor_resume():
    data = request.get_json(silent=True) or {}
    base_resume = str(data.get("base_resume", "")).strip()
    job_description = str(data.get("job_description", "")).strip()

    if not base_resume:
        return jsonify({"error": "Base resume cannot be empty."}), 400
    if not job_description:
        return jsonify({"error": "Job description cannot be empty."}), 400

    try:
        configure_gemini_client()
        model = genai.GenerativeModel(
            MODEL_NAME,
            system_instruction=SYSTEM_PROMPT
        )
        response = model.generate_content(
            build_prompt(base_resume, job_description),
            generation_config={"max_output_tokens": 1800},
        )
        response_text = (getattr(response, "text", "") or "").strip()
        parsed = parse_model_output(response_text)
        costs = compute_cost(getattr(response, "usage_metadata", None))

        return jsonify(
            {
                "resume": parsed["resume"],
                "keywords_matched": parsed["keywords"],
                "ats_score": parsed["ats_score"],
                "raw_response": response_text,
                "cost": costs,
            }
        )
    except Exception as exc:
        error_message = str(exc).strip() or "Unknown API error."
        if "timeout" in error_message.lower():
            return (
                jsonify({"error": "Gemini API timeout. Please try again."}),
                500,
            )
        return jsonify({"error": f"Failed to tailor resume: {error_message}"}), 500


def _validate_download_input(data: Dict[str, Any]) -> Tuple[str, int, Any]:
    resume_text = str(data.get("resume_text", "")).strip()
    font_size = normalize_font_size(data.get("font_size", 10))
    if not resume_text:
        return "", font_size, (jsonify({"error": "Resume text is required."}), 400)
    return resume_text, font_size, None


@app.route("/download/pdf", methods=["POST"])
def download_pdf():
    data = request.get_json(silent=True) or {}
    resume_text, font_size, error_response = _validate_download_input(data)
    if error_response:
        return error_response

    try:
        pdf_bytes = generate_pdf_bytes(resume_text, font_size)
        return send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name="tailored_resume.pdf",
            mimetype="application/pdf",
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to generate PDF: {str(exc).strip()}"}), 500


@app.route("/download/docx", methods=["POST"])
def download_docx():
    data = request.get_json(silent=True) or {}
    resume_text, font_size, error_response = _validate_download_input(data)
    if error_response:
        return error_response

    docx_bytes = generate_docx_bytes(resume_text, font_size)
    return send_file(
        io.BytesIO(docx_bytes),
        as_attachment=True,
        download_name="tailored_resume.docx",
        mimetype=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


if __name__ == "__main__":
    if not DATA_FILE.exists():
        save_settings(_default_settings())
    app.run(debug=True)
