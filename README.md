# 🧠 Stroke System  
> A prototype Streamlit application for managing stroke patient workflows across Technician, Doctor, and Patient roles. Includes image upload/annotation, AI-assisted treatment plan drafting, ICD-10 lookup, visit lifecycle tracking, and tPA eligibility logic.  
⚠️ **Not a clinical tool — for educational and prototyping purposes only.**


## 📚 Table of Contents  
1. [Overview](#1--overview)  
2. [Core Features](#2-️-core-features)  
3. [Roles & User Flows](#3--roles--user-flows)  
4. [Architecture & Directory Layout](#4-️-architecture--directory-layout)  
5. [Data Model Summary](#5--data-model-summary-high-level)  
6. [Installation & Setup](#6-️-installation--setup)  
7. [Environment Configuration (.env)](#7--environment-configuration-env)  
8. [Running the App](#8-️-running-the-app)  
9. [ML Model & Inference](#9--ml-model--inference)  
10. [Image Annotation](#10--image-annotation)  
11. [Treatment Plan (Inline)](#11--treatment-plan-inline)  
12. [ICD-10 Code (Inline)](#12--icd-10-code-inline)  
13. [tPA Eligibility Logic](#13--tpa-eligibility-logic)  
14. [Time Handling (UTC)](#14--time-handling-utc)  
15. [Session & Navigation](#15--session--navigation)  
16. [Security & Privacy Notes](#16--security--privacy-notes)  
17. [Troubleshooting](#17-️️-troubleshooting)  
18. [License / Disclaimer](#18--license--disclaimer)


---
## 1. 📝 Overview  
The Stroke System streamlines stroke patient visit workflows:

- 👩‍🔬 **Technicians** register patients, record vitals/NIHSS, upload scans.  
- 🩺 **Doctors** review cases, annotate scans, generate treatment plans, assign ICD-10 codes.  
- 👤 **Patients** view their visit history, annotated scans, and care plans.

Technologies:
- 🖥️ UI: Streamlit multipage app  
- 🗄️ DB: SQLite + SQLAlchemy ORM  
- 🤖 ML: Pretrained `MedStroke.pt`  
- 🧠 AI Text: OpenAI Chat API  
- 🖌️ Annotation: `streamlit-drawable-canvas` with PNG + JSON saved.
- 🔍 ICD Lookup: NLM Clinical Tables API  

---
## 2. ⚙️ Core Features
* Patient registration & visit tracking.
* Vitals + NIHSS entry; shows prior visit values if current missing.
* Scan upload & annotated overlay saving (composited image with markings).
* Doctor case review with onset time & elapsed duration display.
* AI-assisted treatment plan generation (exactly 5 concise numbered points)  view.
* Editable treatment plan; subsequent display in case view & patient portal (stored per-visit and patient).
* ICD-10 code search & selection 
* tPA eligibility flag & reason display, including "Indeterminate" when no imaging and automatic NOT eligible when bleeding/hemorrhage predicted.
* Role-based sidebars and session-based navigation.

---
## 3. 👥 Roles & User Flows
### 👩‍🔬 Technician
1. Login → Dashboard cards (patients, cases not reviewed, completed).
2. Register patient / list patients / open visits.
3. Enter vitals, NIHSS, upload scan, send to doctor.

### 🩺 Doctor
1. Login → Dashboard (case counts: sent, in review, completed).
2. Open a case: view patient data, vitals, onset time, scan (annotation canvas), technician notes.
3. Annotate & save; choose ICD code; generate/edit treatment plan; finalize case.

### 👤 Patient
1. Login → Dashboard with profile and ALL visits listed (any status).
2. Open visit summary: annotated scan (with option to view original), prediction placeholders, treatment plan (if available), ICD code, tPA info.

---
## 4. 🏗️ Architecture & Directory Layout
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
## 5. 🧩 Data Model Summary (High-Level)
| Model    | Key Fields | Notes |
|----------|------------|-------|
| Patient  | `id`, `patient_id`, `name`, `age`, `gender` | `patient_id` used as login username.
| Visit    | `id`, `patient_id`, vitals, `nihss_score`, `scan_path`, `status`, `onset_time`, `prediction_label`, `prediction_confidence`, `tpa_eligible`, `tpa_reason`, `icd_code`, `technician_notes` | Lifecycle statuses: e.g. `in_progress`, `sent_to_doctor`, `in_review`, `completed`.
| Treatment| `id`, `visit_id`, `plan_text` | One per visit (editable by doctor).
| User     | Role-based login (doctor, technician, patient) | Session gating.

Annotations: `visit_<id>.png` is the composited base scan + drawn overlay. Raw drawing JSON preserved separately for re-loading.

---
## 6. 🛠️ Installation & Setup
### Prerequisites
* Python 3.11+
* Virtual environment recommended.

### Steps
```bash
git clone <repo-url>
cd Stroke_System
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt      # Mac: requirements-mac.txt
```

If using CPU-only Torch wheels, ensure the `--extra-index-url` line remains in `requirements.txt`.

Run initial DB setup or migrations if provided (not always required):
```bash
python scripts/migrate_onset_time.py
python scripts/migrate_technician_notes.py
```

---
## 7. 🔐 Environment Configuration (`.env`)
Create a `.env` file at the project root for secrets:
```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
```
The `.gitignore` already excludes `.env` / `*.env`.

If no key is provided, AI plan generation will fail.

---
## 8. ▶️ Running the App
```bash
streamlit run app.py
# Or with explicit interpreter
python -m streamlit run app.py
```
Access via printed Local URL (default: `http://localhost:8501`).

### Common Arguments
* `--server.port 8502` to change port.

---
## 9. 🤖 ML Model & Inference
* Weight file: `ml/MedStroke.pt` (placeholder) loaded by `model_loader.py`.
* `services/scan_service.py` calls model for classification probabilities.
* Predictions saved onto Visit: `prediction_label`, `prediction_confidence`.
* Doctor view shows a compact prediction confidence breakdown when available.

Notes: CPU inference only; large model weights may slow initial load.

---
## 10. 🖌️ Image Annotation
* Implemented with `streamlit-drawable-canvas`.
* Canvas loads the actual scan as background for editing.
* Doctor view: the composed annotated image preview below the canvas has been removed; edits happen only within the canvas.
* On save:
	1. Drawn overlay (RGBA) is merged with base scan and written to a composed PNG.
	2. The JSON drawing data is also saved so you can reload and keep editing.
* Patient view may display the composed annotation where applicable.

---
## 11. 📝 Treatment Plan (Inline)
* On the doctor case view (`pages/d_view_case.py`):
	- Click "Generate Treatment Plan" to draft a 5-point plan.
	- Edit in the inline editor and click "Save Treatment Plan".
	- Saved plans immediately display under the Treatment Plan section.
* Storage rules:
	- Plans are saved to `Treatment` and tied strictly to the current `visit_id`, plus `patient_code` and `patient_name` for safety.
	- Plans from other visits or patients will not display.
* OpenAI SDK: the app uses the v1 client. Ensure `OPENAI_API_KEY` is set and `openai>=1.40.0` is installed.

OpenAI usage is optional; absence of a key simply blocks generation.

---
## 12. 🧾 ICD-10 Code (Inline)
* Inline search on the doctor case view powered by NLM Clinical Tables API.
* Save writes the selected code to `Visit.icd_code`.
* You can switch between view and edit modes without leaving the page.

---
## 13. 💉 tPA Eligibility Logic
* Time window: NOT eligible if onset-to-now > 4.5 hours.
* Imaging rules:
	- No scan → result is Indeterminate (neither true nor false) with a clear reason.
	- If model predicts hemorrhage/bleeding (or related terms), tPA is NOT eligible.
* Vitals and labs (BP, INR, glucose) can disqualify as implemented.

---
## 14. 🌍 Time Handling (UTC)
* All timestamps and `onset_time` values are stored and displayed as timezone-aware UTC.
* Naive datetime inputs are coerced to UTC to avoid runtime errors.

---
## 15. 🧭 Session & Navigation
* Role gating via `require_role()` (redirects / stops page if mismatch).
* `st.session_state` keys:
	* `open_visit_id` – current doctor case.
	* `selected_patient` (technician flows).
	* `patient_visit_id` – patient's selected visit.
	* Various annotation flags: `show_ann_<id>`, etc.

Sidebars:
* Doctor / Technician: role-specific links & logout.
* Patient: logout only (simplified per requirements).

---
## 16. 🔒 Security & Privacy Notes
This is a prototype. Not production-ready:
* No encryption at rest (SQLite file plain text).
* Authentication is minimal; ensure passwords hashed (`bcrypt`).
* Avoid storing real PHI / sensitive medical data.
* Do NOT deploy in a clinical environment without audit, access control, logging, and compliance review (HIPAA/GDPR).

---
## 17. 🛠️⚙️ Troubleshooting
| Issue | Possible Cause | Fix |
|-------|----------------|-----|
| OpenAI errors | Missing / invalid API key or wrong SDK | Set `OPENAI_API_KEY` in `.env` and ensure `openai>=1.40.0`. |
| Model load slow | Large Torch CPU wheels | Preload or reduce model size. |
| Annotation preview appears | Old cached UI | Refresh; doctor view no longer shows preview below the canvas. |
| App restarts on save | Normal Streamlit rerun | Use session state persistence keys. |
| Import error `bcrypt` | Package not installed | `pip install bcrypt` (already in requirements). |
| Torch install fails | Wrong Python / platform | Use matching wheel versions or remove Torch if not needed. |

### Migration: Treatment Patient Fields
We introduced `Treatment.patient_code` and `Treatment.patient_name` to enforce per-visit/per-patient display. Run the migration script once after upgrading:

```powershell
D:/Users/DELL/Desktop/Stroke_System/venv/Scripts/python.exe scripts/migrate_treatment_patient_fields.py
```

### NumPy / Torch Compatibility
If you see NumPy/PyTorch ABI errors, the app pins NumPy to 1.26.x for compatibility with the current Torch build. Re-install dependencies with:

```powershell
D:/Users/DELL/Desktop/Stroke_System/venv/Scripts/python.exe -m pip install -r requirements.txt
```

Logs: Consider adding explicit logging handlers for production or debugging.

---
## 18. 📄 License / Disclaimer
This repository is provided "as is" for educational and prototyping purposes only. Not medical advice. Always follow institutional protocols and consult qualified clinicians.

---
## Quick Start Recap
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Set-Content -Path .env -Value "OPENAI_API_KEY=sk-xxxx"  # optional
python -m streamlit run app.py
```

Happy prototyping!