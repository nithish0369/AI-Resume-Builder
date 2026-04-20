# AI Resume Builder (Job Tailor)

## 📌 Project Overview

AI Resume Builder is a Flask web application that tailors a base resume to a target job description using the Google Gemini API, then lets users download the generated result as PDF or DOCX.

### What problem it solves

- Reduces manual resume rewriting for each job application.
- Adds ATS-oriented keyword matching and score feedback in the UI.
- Keeps formatting consistent with one-click export.

### Key features

- Save and load base resume + preferred font size via local settings.
- Generate tailored resume content from a job description.
- Parse and display:
  - tailored resume body
  - matched keywords
  - ATS score explanation
- Show estimated token/cost metrics from model usage metadata.
- Download generated resume as:
  - `tailored_resume.pdf`
  - `tailored_resume.docx`

### Tech stack

- **Language:** Python (project currently executed with CPython 3.14 based on `__pycache__/app.cpython-314.pyc`)
- **Backend framework:** Flask
- **AI SDK:** `google-generativeai`
- **Document generation:**
  - `fpdf2` (PDF)
  - `python-docx` (DOCX)
- **Config management:** `python-dotenv`
- **Frontend:** Server-rendered HTML + vanilla JavaScript + CSS
- **Frontend helper library:** `marked` loaded via CDN for Markdown rendering in preview
- **Other dependency listed:** `anthropic` (present in `requirements.txt`, not used in current `app.py`)

> Dependency versions are not pinned in `requirements.txt` (package names only).

### High-level architecture

1. Browser loads `templates/index.html`.
2. Frontend calls Flask JSON endpoints (`/settings`, `/tailor`, `/download/*`).
3. Backend:
   - reads/writes user settings in `data.json`
   - calls Gemini model with strict system instructions
   - parses structured model output
   - returns tailored content + metadata
4. Export endpoints transform resume text into PDF/DOCX bytes and stream files back.

---

## 🧱 Project Structure

```text
job-tailor/
├── .env
├── .gitignore
├── app.py
├── data.json
├── requirements.txt
├── _tmp_resume.txt
├── _tmp_test.docx
├── _tmp_test.pdf
├── templates/
│   └── index.html
└── __pycache__/
    └── app.cpython-314.pyc
```

### Major files and folders

- `app.py` - Main Flask app, API routes, Gemini integration, parsing logic, PDF/DOCX generation.
- `templates/index.html` - Entire UI (layout, styling, and frontend logic).
- `requirements.txt` - Python dependency list.
- `.env` - Local environment variables (contains Gemini API key).
- `data.json` - Persisted user settings (`base_resume`, `font_size`).
- `_tmp_resume.txt`, `_tmp_test.docx`, `_tmp_test.pdf` - Temporary/generated local artifacts.
- `__pycache__/` - Python bytecode cache (generated automatically).

---

## ⚙️ Prerequisites

- **Python:** 3.10+ recommended (current local run evidence shows Python 3.14)
- **pip:** Python package installer
- **Git:** for cloning the repository
- **Gemini API key:** `GEMINI_API_KEY` from Google AI Studio / Gemini API account

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone <repo-url>
cd job-tailor
```

### 2. Environment Setup

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

`.env.example` template:

```env
GEMINI_API_KEY=
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Database / Services Setup

No database or migration setup is required.

External service dependency:
- Gemini API (requires valid `GEMINI_API_KEY`)

### 5. Run the Project

Development mode (actual project startup command):

```bash
python app.py
```

Open in browser:
- `http://127.0.0.1:5000`

Build command:
- Not applicable (no separate build pipeline in this repository).

Production mode:
- Not configured in this codebase.
- `app.py` currently runs Flask with `debug=True`, which is not production-safe.

### 6. Run Tests

No automated test suite is currently configured in this repository.

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | API key used by `configure_gemini_client()` to authenticate calls to Gemini. | `AIza...` |

---

## 📡 API Reference

### `GET /`
- **Description:** Serves the main UI page.
- **Response:** HTML (`templates/index.html`)

### `GET /settings`
- **Description:** Returns saved local settings from `data.json` (or defaults).
- **Response example:**

```json
{
  "base_resume": "",
  "font_size": 10
}
```

### `POST /settings`
- **Description:** Saves base resume and font size preferences.
- **Request body example:**

```json
{
  "base_resume": "Your resume content...",
  "font_size": 10
}
```

- **Success response example:**

```json
{
  "base_resume": "Your resume content...",
  "font_size": 10
}
```

### `POST /tailor`
- **Description:** Tailors base resume against a job description using Gemini.
- **Request body example:**

```json
{
  "base_resume": "Base resume text...",
  "job_description": "Job description text..."
}
```

- **Success response example:**

```json
{
  "resume": "Tailored resume text...",
  "keywords_matched": "python, flask, sql",
  "ats_score": "84/100 - strong keyword alignment...",
  "raw_response": "...full model output...",
  "cost": {
    "input_tokens": 1200,
    "output_tokens": 900,
    "input_cost": 0.0012,
    "output_cost": 0.0045,
    "total_cost": 0.0057,
    "display": "$0.00570000"
  }
}
```

- **Validation errors:** `400` when base resume or job description is empty.
- **Server errors:** `500` when Gemini request fails/timeouts.

### `POST /download/pdf`
- **Description:** Generates and downloads PDF from resume text.
- **Request body example:**

```json
{
  "resume_text": "Tailored resume text...",
  "font_size": 10
}
```

- **Response:** File download (`tailored_resume.pdf`)

### `POST /download/docx`
- **Description:** Generates and downloads DOCX from resume text.
- **Request body example:**

```json
{
  "resume_text": "Tailored resume text...",
  "font_size": 10
}
```

- **Response:** File download (`tailored_resume.docx`)

---

## 🤝 Contributing

This repository does not currently define formal contribution guidelines. Recommended lightweight workflow:

- Create a feature branch, e.g.:
  - `feature/resume-export-fixes`
  - `fix/tailor-endpoint-validation`
  - `docs/readme-improvements`
- Keep changes focused and test manually via the UI.
- Open a Pull Request with:
  - clear change summary
  - setup/test steps
  - screenshots for UI changes (if relevant)

---

## 📄 License

No license file is currently present in this repository.
Add a `LICENSE` file (for example MIT) if you plan to distribute or accept external contributions.
