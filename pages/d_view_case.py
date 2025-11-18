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
import json, os, requests
from datetime import datetime


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
            onset_display = onset_dt.strftime('%Y-%m-%d %H:%M')
            now = datetime.utcnow()
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
    # Imaging section removed; show scan within annotation only
    if visit.scan_path:
        st.markdown("#### Annotate Scan")
        try:
            from core import database as db_core
            base_dir = db_core.BASE_DIR
            ann_dir = os.path.join(base_dir, "data", "uploads", "annotations")
            os.makedirs(ann_dir, exist_ok=True)
            ann_img_path = os.path.join(ann_dir, f"visit_{visit.id}.png")
            ann_json_path = os.path.join(ann_dir, f"visit_{visit.id}.json")

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
                load_prev = False
                if os.path.exists(ann_json_path):
                    load_prev = st.checkbox("Load previous annotation", value=True, key=f"load_prev_{visit.id}")

            with col_canvas:
                initial = None
                if os.path.exists(ann_json_path) and load_prev:
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

            save_col1, save_col2, _ = st.columns([1,1,3])
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

            if os.path.exists(ann_img_path):
                with save_col2:
                    if st.button("Show Latest Annotation", key=f"show_ann_{visit.id}"):
                        st.session_state[f"show_ann_{visit.id}"] = not st.session_state.get(f"show_ann_{visit.id}", False)
                if st.session_state.get(f"show_ann_{visit.id}"):
                    st.image(ann_img_path, caption="Latest Annotation", use_column_width=True)
        except Exception:
            st.info("Annotation tool unavailable.")

    if getattr(visit, 'tpa_eligible', None) is None:
        st.write("**tPA Eligibility:** —")
    else:
        st.write(f"**tPA Eligibility:** {'Eligible' if visit.tpa_eligible else 'NOT Eligible'}")
    st.write(f"**Reason:** {getattr(visit, 'tpa_reason', '') or '—'}")

    st.divider()
    st.subheader("ICD-10 Diagnosis")

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

    if visit.icd_code:
        desc = _lookup_icd_description(visit.icd_code)
        st.write(f"**ICD Code:** {visit.icd_code}{(' — ' + desc) if desc else ''}")
        if st.button("Change ICD Code", key="btn_change_icd"):
            st.switch_page("pages/d_icd_code.py")
    else:
        st.info("No ICD-10 code selected yet.")
        if st.button("Generate ICD Code", key="btn_generate_icd_inline"):
            st.switch_page("pages/d_icd_code.py")

    st.divider()
    st.subheader("Technician Notes")
    st.write(getattr(visit, 'technician_notes', '') or '—')

    treatment = db.query(Treatment).filter(Treatment.visit_id == visit_id).first()
    st.markdown("### Treatment Plan")
    if treatment and (treatment.plan_text or "").strip():
        st.text_area("Plan", treatment.plan_text, height=240, disabled=True)
        if st.button("Edit Treatment Plan", key="btn_edit_plan_inline"):
            st.switch_page("pages/d_treatment_plan.py")
    else:
        st.info("No treatment plan generated yet.")
        if st.button("Generate Treatment Plan", key="btn_generate_plan_inline"):
            st.switch_page("pages/d_treatment_plan.py")

    st.divider()
    st.subheader("Actions")

    if st.button("Finalize Case", key="btn_finalize_case"):
        st.switch_page("pages/d_finalise.py")

    if st.button("Back", key="btn_back"):
        st.switch_page("pages/d_dashboard.py")


if __name__ == "__main__":
    main()
