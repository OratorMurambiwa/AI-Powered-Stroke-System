# Stroke System

> A prototype Streamlit application for managing stroke patient workflows across Technician, Doctor, and Patient roles. Includes image upload and annotation, AI-assisted treatment plan drafting, ICD-10 lookup, visit lifecycle tracking, and basic tPA eligibility display. This is NOT a substitute for clinical judgment; for educational / prototyping use only.

## Table of Contents
1. Overview
2. Core Features
3. Roles & User Flows
4. Architecture & Directory Layout
5. Data Model Summary
6. Installation & Setup
7. Environment Configuration (`.env`)
8. Running the App
9. ML Model & Inference
10. Image Annotation
11. Treatment Plan Generation
12. ICD-10 Code Search
13. Session & Navigation
14. Security & Privacy Notes
15. Troubleshooting
16. Roadmap / Future Ideas
17. License / Disclaimer

---
## 1. Overview
The Stroke System streamlines the capture and review of stroke patient visit data:
* Technicians register patients, record vitals & NIHSS, upload scans.
* Doctors review cases, annotate scans, select ICD codes, and generate concise treatment plans.
* Patients can log in to view ALL their visits (not just completed), and see annotated scans and plans once available.

Technologies:
* UI: Streamlit multi-page app.
* DB: SQLite via SQLAlchemy ORM.
* ML: Pretrained `MedStroke.pt` loaded for simple prediction scoring.
* AI Text: OpenAI chat completion.
* Annotation: `streamlit-drawable-canvas` with PNG + JSON saved.
* ICD Lookup: NLM Clinical Tables API.

---
## 2. Core Features
* Patient registration & visit tracking.
* Vitals + NIHSS entry; shows prior visit values if current missing.
* Scan upload & annotated overlay saving (composited image with markings).
* Doctor case review with onset time & elapsed duration display.
* AI-assisted treatment plan generation (exactly 5 concise numbered points).
* Editable treatment plan; subsequent display in case view & patient portal.
* ICD-10 code search & selection.
* tPA eligibility flag & reason display (basic fields).
* Role-based sidebars and session-based navigation.

---
## 3. Roles & User Flows
### Technician
1. Login → Dashboard cards (patients, cases not reviewed, completed).
2. Register patient / list patients / open visits.
3. Enter vitals, NIHSS, upload scan, send to doctor.

### Doctor
1. Login → Dashboard (case counts: sent, in review, completed).
2. Open a case: view patient data, vitals, onset time, scan (annotation canvas), technician notes.
3. Annotate & save; choose ICD code; generate/edit treatment plan; finalize case.

### Patient
1. Login → Dashboard with profile and ALL visits listed (any status).
2. Open visit summary: annotated scan (with option to view original), prediction placeholders, treatment plan (if available), ICD code, tPA info.

---
## 4. Architecture & Directory Layout
```
Stroke_System/
	app.py                  # Streamlit entrypoint (sets title, routing)
	requirements.txt        # Python dependencies
	.gitignore              # Ignore rules (includes .env, data artifacts)
	core/
		database.py           # SQLAlchemy engine & session helpers
		session_manager.py    # Role enforcement & session utilities
		auth.py               # Password hashing (bcrypt)
		helpers.py            # Sidebar rendering helpers
	models/                 # ORM models: Patient, Visit, Treatment, User
	pages/                  # Streamlit multipage views (role-specific)
	services/               # Business/utility services (AI, ICD, visit, etc.)
	ml/                     # Model loader, predictor, weights (MedStroke.pt)
	data/
		stroke.db             # SQLite database
		uploads/              # Uploaded scans & annotations
			annotations/        # visit_<id>.png (composited) + .json drawing data
	assets/                 # Static assets (CSS, sample scans)
	scripts/                # Migration & inspection scripts
```

Page naming uses prefixes:
* `t_` Technician pages
* `d_` Doctor pages
* `p_` Patient pages

---
## 5. Data Model Summary (High-Level)
| Model    | Key Fields | Notes |
|----------|------------|-------|
| Patient  | `id`, `patient_id`, `name`, `age`, `gender` | `patient_id` used as login username.
| Visit    | `id`, `patient_id`, vitals, `nihss_score`, `scan_path`, `status`, `onset_time`, `prediction_label`, `prediction_confidence`, `tpa_eligible`, `tpa_reason`, `icd_code`, `technician_notes` | Lifecycle statuses: e.g. `in_progress`, `sent_to_doctor`, `in_review`, `completed`.
| Treatment| `id`, `visit_id`, `plan_text` | One per visit (editable by doctor).
| User     | Role-based login (doctor, technician, patient) | Session gating.

Annotations: `visit_<id>.png` is the composited base scan + drawn overlay. Raw drawing JSON preserved separately for re-loading.

---
## 6. Installation & Setup
### Prerequisites
* Python 3.11+
* Virtual environment recommended.

### Steps
```bash
git clone <repo-url>
cd Stroke_System
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

If using CPU-only Torch wheels, ensure the `--extra-index-url` line remains in `requirements.txt`.

Run initial DB setup or migrations if provided (not always required):
```bash
python scripts/migrate_onset_time.py
python scripts/migrate_technician_notes.py
```

---
## 7. Environment Configuration (`.env`)
Create a `.env` file at the project root for secrets:
```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
```
The `.gitignore` already excludes `.env` / `*.env`.

If no key is provided, AI plan generation will fail.

---
## 8. Running the App
```bash
streamlit run app.py
# Or with explicit interpreter
python -m streamlit run app.py
```
Access via printed Local URL (default: `http://localhost:8501`).

### Common Arguments
* `--server.port 8502` to change port.

---
## 9. ML Model & Inference
* Weight file: `ml/MedStroke.pt` (placeholder) loaded by `model_loader.py`.
* `services/scan_service.py` calls model for classification probabilities.
* Predictions saved onto Visit: `prediction_label`, `prediction_confidence`.
* (Current doctor view has prediction section removed per latest adjustments; patient view still shows placeholders.)

Performance caveats: CPU inference only; large model weights may slow initial load.

---
## 10. Image Annotation
* Implemented with `streamlit-drawable-canvas`.
* Canvas loads the actual scan as background.
* On save:
	1. Drawn overlay (RGBA) merged with base scan using alpha compositing.
	2. Saved PNG: `data/uploads/annotations/visit_<id>.png`.
	3. JSON drawing data saved for re-loading / future edits.
* Patients see annotated version first; can expand to view original.

---
## 11. Treatment Plan Generation
* Doctor clicks “Generate Treatment Plan”.
* Prompt engineered to produce exactly 5 concise, plain-text, numbered recommendations.
* Sanitization removes markdown/intended formatting, enforces numbering.
* Doctor can edit before saving; stored in `Treatment.plan_text`.
* Patient portal shows saved plan if available.

OpenAI usage is optional; absence of a key simply blocks generation.

---
## 12. ICD-10 Code Search
* Uses NLM Clinical Tables API (`icd10cm`).
* Selected code stored on the Visit (`icd_code`).
* Patient & doctor views display code plus resolved description when available.

---
## 13. Session & Navigation
* Role gating via `require_role()` (redirects / stops page if mismatch).
* `st.session_state` keys:
	* `open_visit_id` – current doctor case.
	* `selected_patient` (technician flows).
	* `patient_visit_id` – patient’s selected visit.
	* Various annotation flags: `show_ann_<id>`, etc.

Sidebars:
* Doctor / Technician: role-specific links & logout.
* Patient: logout only (simplified per requirements).

---
## 14. Security & Privacy Notes
This is a prototype. Not production-ready:
* No encryption at rest (SQLite file plain text).
* Authentication is minimal; ensure passwords hashed (`bcrypt`).
* Avoid storing real PHI / sensitive medical data.
* Do NOT deploy in a clinical environment without audit, access control, logging, and compliance review (HIPAA/GDPR).

---
## 15. Troubleshooting
| Issue | Possible Cause | Fix |
|-------|----------------|-----|
| OpenAI errors | Missing / invalid API key | Set `OPENAI_API_KEY` in `.env`. |
| Model load slow | Large Torch CPU wheels | Preload or reduce model size. |
| Annotation not visible to patient | Old saved PNG was overlay only | Re-save annotation (new logic composites). |
| App restarts on save | Normal Streamlit rerun | Use session state persistence keys. |
| Import error `bcrypt` | Package not installed | `pip install bcrypt` (already in requirements). |
| Torch install fails | Wrong Python / platform | Use matching wheel versions or remove Torch if not needed. |

Logs: Consider adding explicit logging handlers for production or debugging.


## 17. License / Disclaimer
This repository is provided “as is” for educational and prototyping purposes only. Not medical advice. Always follow institutional protocols and consult qualified clinicians.

---
## Quick Start Recap
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
echo OPENAI_API_KEY=sk-xxxx > .env # optional
streamlit run app.py
```

Happy prototyping!
