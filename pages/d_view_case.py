import streamlit as st
from core.session_manager import require_role
from core.database import get_db
from sqlalchemy.orm import Session
from models.visit import Visit
from models.patient import Patient
from models.treatment import Treatment
from sqlalchemy import or_
from core.helpers import render_doctor_sidebar
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import json, os, requests, re
import hashlib
from datetime import timezone
from core.time_utils import now_utc
import openai
from dotenv import load_dotenv
from streamlit_searchbox import st_searchbox


def main():
    require_role("doctor")
    render_doctor_sidebar()

    visit_id = st.session_state.get("open_visit_id")
    if not visit_id:
        st.error("No open case selected.")
        return

    db = next(get_db())
    visit = db.query(Visit).filter(Visit.id == visit_id).first()
    if not visit:
        st.error("Visit not found.")
        return

    patient = db.query(Patient).filter(Patient.id == visit.patient_id).first()
    st.title("Case Review")
    if patient:
        st.caption(f"Patient: {getattr(patient, 'name', '—')} | Age: {getattr(patient, 'age', '—')}")

    st.subheader("Vitals & NIHSS")
    bp = "—"
    if visit.systolic_bp is not None and visit.diastolic_bp is not None:
        bp = f"{visit.systolic_bp}/{visit.diastolic_bp} mmHg"
    st.write(f"**Blood Pressure:** {bp}")
    st.write(f"**Heart Rate:** {visit.heart_rate if visit.heart_rate is not None else '—'}")
    st.write(f"**Respiratory Rate:** {visit.respiratory_rate if visit.respiratory_rate is not None else '—'}")
    st.write(f"**Temperature:** {visit.temperature if visit.temperature is not None else '—'}")
    st.write(f"**Oxygen Saturation:** {visit.oxygen_saturation if visit.oxygen_saturation is not None else '—'}")
    st.write(f"**Glucose:** {visit.glucose if visit.glucose is not None else '—'}")
    st.write(f"**INR:** {visit.inr if visit.inr is not None else '—'}")
    st.write(f"**NIHSS Score:** {visit.nihss_score if visit.nihss_score is not None else '—'}")

    def _format_timedelta(td):
        try:
            secs = int(td.total_seconds())
        except Exception:
            return "—"
        if secs < 0:
            secs = 0
        days = secs // 86400
        hours = (secs % 86400) // 3600
        minutes = (secs % 3600) // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)

    onset_display = '—'
    since_display = '—'
    try:
        if getattr(visit, 'onset_time', None):
            onset_dt = visit.onset_time
            # Coerce naive datetimes to UTC for display safety
            if getattr(onset_dt, 'tzinfo', None) is None:
                try:
                    onset_dt = onset_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            onset_display = onset_dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            now = now_utc()
            since_display = _format_timedelta(now - onset_dt)
    except Exception:
        pass
    st.write(f"**Onset Time:** {onset_display}")
    st.write(f"**Time Since Onset:** {since_display}")

    if (
        visit.systolic_bp is None
        and visit.diastolic_bp is None
        and visit.heart_rate is None
        and visit.glucose is None
        and visit.nihss_score is None
    ):
        prior = (
            db.query(Visit)
            .filter(Visit.patient_id == visit.patient_id)
            .filter(Visit.id != visit.id)
            .filter(
                or_(
                    Visit.systolic_bp.isnot(None),
                    Visit.diastolic_bp.isnot(None),
                    Visit.heart_rate.isnot(None),
                    Visit.glucose.isnot(None),
                    Visit.nihss_score.isnot(None),
                )
            )
            .order_by(Visit.id.desc())
            .first()
        )
        if prior:
            st.info("No vitals/NIHSS recorded for this visit. Showing previous visit values below.")
            pbp = (
                f"{prior.systolic_bp}/{prior.diastolic_bp} mmHg"
                if prior.systolic_bp is not None and prior.diastolic_bp is not None
                else "—"
            )
            st.markdown("#### Previous Visit Vitals")
            st.write(f"**Blood Pressure:** {pbp}")
            st.write(f"**Heart Rate:** {prior.heart_rate if prior.heart_rate is not None else '—'}")
            st.write(f"**Glucose:** {prior.glucose if prior.glucose is not None else '—'}")
            st.write(f"**NIHSS Score:** {prior.nihss_score if prior.nihss_score is not None else '—'}")

    st.divider()
    # Imaging section: show predictions summary and annotate scan
    if visit.scan_path:
        st.markdown("#### Annotate Scan")
        # Show prediction breakdown with top highlighted
        try:
            from ml.predict import predict_scan
            pred_result = predict_scan(visit.scan_path)
            probs = pred_result.get("probabilities", []) or []
            if probs:
                top = probs[0]
                st.markdown(f"**Top Prediction:** :green[{top.get('label','—')} — {top.get('confidence',0)}%]")
                # Display all label confidences
                lines = [f"- {p.get('label','—')}: {p.get('confidence',0)}%" for p in probs]
                st.markdown("\n".join(lines))
            else:
                st.caption("No prediction probabilities available.")
        except Exception:
            st.caption("Predictions unavailable.")
        try:
            from core.annotation_utils import get_annotation_paths
            ann_img_path, ann_json_path = get_annotation_paths(visit)

            bg_img = Image.open(visit.scan_path).convert("RGBA")
            max_w = 900
            if bg_img.width > max_w:
                ratio = max_w / float(bg_img.width)
                bg_img = bg_img.resize((int(bg_img.width * ratio), int(bg_img.height * ratio)))

            col_tools, col_canvas = st.columns([1, 4])
            with col_tools:
                st.caption("Drawing Tools")
                stroke_width = st.slider("Brush Size", 1, 30, 5, key=f"stroke_{visit.id}")
                stroke_color = st.color_picker("Brush Color", "#ff0000", key=f"color_{visit.id}")
                draw_mode = st.selectbox("Mode", ["freedraw", "line", "rect", "circle", "transform"], key=f"mode_{visit.id}")
                # Persisted flags in session
                ann_show_key = f"show_ann_{visit.id}"
                ann_loaded_key = f"loaded_ann_{visit.id}"

                annotation_exists = os.path.exists(ann_json_path)

                # Auto-load initial drawing if annotation exists and we've shown it before
                auto_load = annotation_exists and st.session_state.get(ann_show_key, False)

                # Provide checkbox only if user wants to disable auto load
                load_prev = False
                if annotation_exists:
                    # Default to True if previously shown or never chosen
                    load_prev_default = auto_load or not st.session_state.get(ann_loaded_key, False)
                    load_prev = st.checkbox(
                        "Load saved annotation for editing",
                        value=load_prev_default,
                        key=f"load_prev_{visit.id}"
                    )
                    st.session_state[ann_loaded_key] = True

            with col_canvas:
                initial = None
                if annotation_exists and load_prev:
                    try:
                        with open(ann_json_path, "r", encoding="utf-8") as f:
                            initial = json.load(f)
                    except Exception:
                        initial = None
                canvas_result = st_canvas(
                    fill_color="rgba(255, 0, 0, 0.2)",
                    stroke_width=stroke_width,
                    stroke_color=stroke_color,
                    background_color="#00000000",
                    background_image=bg_img,
                    update_streamlit=True,
                    height=bg_img.height,
                    width=bg_img.width,
                    drawing_mode=draw_mode,
                    initial_drawing=initial,
                    key=f"canvas_{visit.id}",
                )

            save_col1, _, _ = st.columns([1,1,3])
            with save_col1:
                if st.button("Save Annotation", key=f"save_ann_{visit.id}"):
                    if canvas_result is not None and canvas_result.image_data is not None:
                        img_data = canvas_result.image_data
                        try:
                            overlay = Image.fromarray(img_data.astype("uint8"), mode="RGBA")
                        except Exception:
                            overlay = Image.fromarray(img_data.astype("uint8"))
                        if overlay.size != bg_img.size:
                            overlay = overlay.resize(bg_img.size)
                        try:
                            base_rgba = bg_img if bg_img.mode == "RGBA" else bg_img.convert("RGBA")
                            composed = Image.alpha_composite(base_rgba, overlay)
                        except Exception:
                            # Fallback: paste using alpha channel
                            composed = bg_img.copy()
                            composed.paste(overlay, (0, 0), overlay)
                        composed.save(ann_img_path)
                        if canvas_result.json_data is not None:
                            with open(ann_json_path, "w", encoding="utf-8") as f:
                                json.dump(canvas_result.json_data, f)
                        st.success("Annotation saved.")
                        st.session_state[f"ann_saved_{visit.id}"] = True
                        st.session_state[ann_show_key] = True  # auto-show after save

            # Do not render the saved annotated image below; editing happens only in the canvas.
        except Exception:
            st.info("Annotation tool unavailable.")

    if getattr(visit, 'tpa_eligible', None) is None:
        st.write("**tPA Eligibility:** —")
    else:
        st.write(f"**tPA Eligibility:** {'Eligible' if visit.tpa_eligible else 'NOT Eligible'}")
    st.write(f"**Reason:** {getattr(visit, 'tpa_reason', '') or '—'}")

    st.divider()
    st.subheader("ICD-10 Diagnosis")

    # Inline ICD search and save
    @st.cache_data(show_spinner=False)
    def _lookup_icd_description(code: str) -> str:
        if not code:
            return ""
        try:
            url = f"https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?sf=code,name&terms={code}"
            data = requests.get(url, timeout=6).json()
            results = data[3] if isinstance(data, list) and len(data) > 3 else []
            for c, name in results:
                if c == code:
                    return name
        except Exception:
            pass
        return ""

    @st.cache_data(show_spinner=False)
    def _icd_lookup(term: str):
        term = (term or "").strip()
        if not term:
            return []
        url = f"https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?sf=code,name&terms={term}"
        try:
            data = requests.get(url, timeout=8).json()
            results = data[3] if isinstance(data, list) and len(data) > 3 else []
        except Exception:
            results = []
        return [f"{code} — {name}" for code, name in results][:20]

    icd_edit_key = f"icd_edit_{visit.id}"
    if icd_edit_key not in st.session_state:
        st.session_state[icd_edit_key] = False

    if visit.icd_code and not st.session_state[icd_edit_key]:
        desc = _lookup_icd_description(visit.icd_code)
        st.write(f"**ICD Code:** {visit.icd_code}{(' — ' + desc) if desc else ''}")
        if st.button("Change ICD Code", key=f"btn_change_icd_{visit.id}"):
            st.session_state[icd_edit_key] = True
    else:
        current_display = ""
        if visit.icd_code:
            d = _lookup_icd_description(visit.icd_code)
            current_display = f"{visit.icd_code}{(' — ' + d) if d else ''}"
        sel = st_searchbox(
            _icd_lookup,
            key=f"icd10_search_{visit.id}",
            placeholder="Type keywords, e.g. ischemic stroke",
            default=current_display,
        )
        if sel and sel.strip():
            st.markdown("### Selected")
            st.write(sel)
            if st.button("Save ICD-10 Code", type="primary", key=f"btn_save_icd_{visit.id}"):
                text = sel.strip()
                m = re.match(r"^([A-Za-z0-9][A-Za-z0-9\.]+)\s*(?:—|-|:)?\s*(.*)$", text)
                if m:
                    code = m.group(1).upper()
                else:
                    code = text.upper()
                visit.icd_code = code
                db.commit()
                st.success(f"ICD Code Saved: {code}")
                st.session_state[icd_edit_key] = False

    st.divider()
    st.subheader("Technician Notes")
    st.write(getattr(visit, 'technician_notes', '') or '—')

    # Only show Treatment Plan section if a saved plan exists for THIS visit
    # and belongs to the currently viewed patient identity.
    # Inline Treatment Plan generation and save
    # Load API key once
    try:
        load_dotenv()
    except Exception:
        pass
    if not getattr(openai, "api_key", None):
        k = os.getenv("OPENAI_API_KEY")
        if k:
            openai.api_key = k

    # Requirement: Hide Treatment Plan section entirely until a draft is generated
    # or a saved plan exists. Remove unconditional heading; heading rendered only
    # in the else block below when draft_exists or treatment_exists is true.
    draft_key = f"draft_treatment_plan_{visit_id}"
    gen_key = f"generating_plan_{visit_id}"
    edit_key = f"editing_plan_{visit_id}"
    if gen_key not in st.session_state:
        st.session_state[gen_key] = False
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    treatment = (
        db.query(Treatment)
        .filter(Treatment.visit_id == visit_id)
        .filter(Treatment.patient_code == getattr(patient, 'patient_id', None))
        .filter(Treatment.patient_name == getattr(patient, 'name', None))
        .first()
    )

    def _severity_from_nihss(score):
        try:
            s = int(score)
        except Exception:
            return "unknown"
        if s <= 5:
            return "mild"
        if s <= 14:
            return "moderate"
        if s <= 24:
            return "severe"
        return "very severe"

    def _sanitize_plain_five_points(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("**", "").replace("*", "").replace("##", "").replace("#", "")
        points = []
        for line in text.splitlines():
            m = re.match(r"^\s*(?:[-*•–]|\d+[\.)])\s+(.+)$", line)
            if m:
                points.append(m.group(1).strip())
        if not points:
            parts = re.split(r"(?<=[.!?])\s+", text.strip())
            for p in parts:
                if p:
                    points.append(p.strip())
        clean = []
        for p in points:
            p = re.sub(r"[#*_`]+", "", p)
            p = re.sub(r"\s+", " ", p).strip()
            if p:
                clean.append(p)
            if len(clean) >= 5:
                break
        clean = clean[:5]
        return "\n".join(f"{i+1}. {p}" for i, p in enumerate(clean))

    treatment_exists = bool(treatment and (treatment.plan_text or "").strip())
    draft_exists = bool(st.session_state.get(draft_key))

    # Only show full Treatment Plan section AFTER a draft has been generated or a saved plan exists.
    if not treatment_exists and not draft_exists:
        if st.button("Generate Treatment Plan", disabled=st.session_state.get(gen_key, False), key=f"btn_gen_plan_initial_{visit.id}"):
            st.session_state[gen_key] = True
            severity = _severity_from_nihss(visit.nihss_score)
            scan_result = (getattr(visit, 'prediction_label', None) or "normal").lower()
            prompt = f"""You are an experienced stroke care physician. Generate a brief, practical treatment plan for the following stroke patient.

Patient Information:
- Name: {patient.name}
- Age: {patient.age} years
- Gender: {patient.gender}

Vital Signs:
- Blood Pressure: {visit.systolic_bp if visit.systolic_bp is not None else 'N/A'}/{visit.diastolic_bp if visit.diastolic_bp is not None else 'N/A'} mmHg
- Heart Rate: {visit.heart_rate if visit.heart_rate is not None else 'N/A'} bpm
- Temperature: {visit.temperature if visit.temperature is not None else 'N/A'}°C
- Oxygen Saturation: {visit.oxygen_saturation if visit.oxygen_saturation is not None else 'N/A'}%

Stroke Assessment:
- NIHSS Score: {visit.nihss_score} ({severity} stroke)
- CT/MRI Scan Result: {scan_result.capitalize()} stroke pattern
- tPA Eligible: {'Yes' if visit.tpa_eligible else 'No'}

Generate exactly 5 concise treatment recommendations. Each point should be actionable and specific to this patient's presentation. Format as a numbered list (1-5) with plain text only - no bold, italics, asterisks, or special formatting. Keep each point to 1-2 sentences maximum. Focus on immediate care priorities, monitoring parameters, and specific interventions based on the scan results and tPA eligibility."""

            success = False
            try:
                with st.spinner("Generating plan..."):
                    completion = openai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": "You are an expert stroke physician providing clear, actionable treatment plans. Use plain text only with no markdown formatting."
                            },
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=500,
                        temperature=0.3,
                    )
                    plan = completion.choices[0].message.content if completion and completion.choices else ""
                plan = _sanitize_plain_five_points(plan)
                st.session_state[draft_key] = plan
                st.session_state[edit_key] = True
                st.success("Draft generated. Review and click Save when ready.")
                success = True
            except Exception as e:
                # Avoid treating Streamlit rerun control exceptions as failures (none used now)
                st.error(f"Failed to generate plan: {e}")
            finally:
                st.session_state[gen_key] = False
            if success:
                # Trigger rerun after state updates to enter the else-block that renders the full section.
                st.rerun()
    else:
        st.markdown("### Treatment Plan")
        colA, colB, colC = st.columns(3)
        with colA:
            if st.button("Generate New Draft", disabled=st.session_state.get(gen_key, False), key=f"btn_regen_plan_{visit.id}"):
                st.session_state[gen_key] = True
                severity = _severity_from_nihss(visit.nihss_score)
                scan_result = (getattr(visit, 'prediction_label', None) or "normal").lower()
                prompt = f"""You are an experienced stroke care physician. Generate a brief, practical treatment plan for the following stroke patient.

Patient Information:
- Name: {patient.name}
- Age: {patient.age} years
- Gender: {patient.gender}

Vital Signs:
- Blood Pressure: {visit.systolic_bp if visit.systolic_bp is not None else 'N/A'}/{visit.diastolic_bp if visit.diastolic_bp is not None else 'N/A'} mmHg
- Heart Rate: {visit.heart_rate if visit.heart_rate is not None else 'N/A'} bpm
- Temperature: {visit.temperature if visit.temperature is not None else 'N/A'}°C
- Oxygen Saturation: {visit.oxygen_saturation if visit.oxygen_saturation is not None else 'N/A'}%

Stroke Assessment:
- NIHSS Score: {visit.nihss_score} ({severity} stroke)
- CT/MRI Scan Result: {scan_result.capitalize()} stroke pattern
- tPA Eligible: {'Yes' if visit.tpa_eligible else 'No'}

Generate exactly 5 concise treatment recommendations. Each point should be actionable and specific to this patient's presentation. Format as a numbered list (1-5) with plain text only - no bold, italics, asterisks, or special formatting. Keep each point to 1-2 sentences maximum. Focus on immediate care priorities, monitoring parameters, and specific interventions based on the scan results and tPA eligibility."""
                try:
                    with st.spinner("Generating plan..."):
                        completion = openai.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You are an expert stroke physician providing clear, actionable treatment plans. Use plain text only with no markdown formatting."
                                },
                                {"role": "user", "content": prompt},
                            ],
                            max_tokens=500,
                            temperature=0.3,
                        )
                        plan = completion.choices[0].message.content if completion and completion.choices else ""
                    plan = _sanitize_plain_five_points(plan)
                    st.session_state[draft_key] = plan
                    st.session_state[edit_key] = True
                    st.success("New draft generated.")
                except Exception as e:
                    st.error(f"Failed to generate plan: {e}")
                finally:
                    st.session_state[gen_key] = False
        with colB:
            if treatment_exists and st.button("Edit Existing Plan", key=f"btn_edit_plan_{visit.id}"):
                st.session_state[draft_key] = treatment.plan_text
                st.session_state[edit_key] = True
        with colC:
            if st.button("Save Treatment Plan", key=f"btn_save_plan_{visit.id}"):
                text = (st.session_state.get(draft_key) or "").strip()
                if not text:
                    st.warning("Plan is empty. Please enter or generate content before saving.")
                else:
                    t = db.query(Treatment).filter(Treatment.visit_id == visit_id).first()
                    if not t:
                        t = Treatment(visit_id=visit_id)
                    t.patient_code = getattr(patient, 'patient_id', None)
                    t.patient_name = getattr(patient, 'name', None)
                    t.plan_text = text
                    db.add(t)
                    db.commit()
                    st.success("Treatment plan saved.")
                    st.session_state[edit_key] = False
                    st.rerun()

        # Editor area
        if st.session_state.get(edit_key, False):
            st.text_area("Plan Editor", height=300, key=draft_key)
        elif treatment_exists:
            st.text_area("Plan", treatment.plan_text, height=240, disabled=True, key=f"readonly_plan_{visit.id}")

    st.divider()
    st.subheader("Actions")

    if st.button("Finalize Case", key="btn_finalize_case"):
        st.switch_page("pages/d_finalise.py")

    if st.button("Back", key="btn_back"):
        st.switch_page("pages/d_dashboard.py")


if __name__ == "__main__":
    main()
