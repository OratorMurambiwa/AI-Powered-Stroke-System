import streamlit as st
from core.session_manager import require_role
from core.helpers import render_technician_sidebar
from services.visit_service import get_visit_by_id, update_visit
from services.scan_service import process_scan
from services.tpa_service import run_tpa_eligibility

# Page config is set globally in app.py

require_role("technician")
render_technician_sidebar()

st.title("CT/MRI Scan Upload")
st.write("Upload the patient's scan and run automated analysis.")

# Ensure visit exists
if "current_visit_id" not in st.session_state:
    st.error("No active visit found. Please start a new stroke visit.")
    st.stop()

visit_id = st.session_state["current_visit_id"]
visit = get_visit_by_id(visit_id)

if not visit:
    st.error("Visit not found.")
    st.stop()

# Display patient info
st.subheader(f"Patient: {visit.patient.name}  |  Visit ID: {visit.id}")

uploaded_file = st.file_uploader("Upload CT/MRI scan image", type=["jpg", "jpeg", "png"])


if st.button("Run Scan Analysis", type="primary"):
    if not uploaded_file:
        st.error("Please upload a scan first.")
        st.stop()

    with st.spinner("Processing scan..."):
        result = process_scan(
            visit_id=visit.id,
            file=uploaded_file
        )

    if not result:
        st.error("Scan processing failed. Check your model or service code.")
        st.stop()

    # Show top prediction with accuracy
    top_conf = result.get("confidence")
    if top_conf is not None:
        st.success(f"Scan processed successfully. Prediction: **{result['prediction']}** ({top_conf:.2f}%)")
    else:
        st.success(f"Scan processed successfully. Prediction: **{result['prediction']}**")

    # Preview the uploaded scan image
    scan_path = result.get("scan_path")
    if scan_path:
        st.markdown("### Scan Preview")
        caption_conf = f"{top_conf:.2f}%" if top_conf is not None else "-"
        caption = f"Uploaded scan — {result['prediction']} ({caption_conf})"
        st.image(scan_path, caption=caption, use_column_width=True)

    # Save result into visit (map service keys to Visit model fields)
    update_visit(
        visit.id,
        scan_path=result["scan_path"],
        prediction_label=result["prediction"],
        prediction_confidence=result["confidence"]
    )

    # Show full class confidence breakdown (if available)
    probs = result.get("probabilities") or []
    # Persist probabilities for this visit in session so they show after rerun
    st.session_state[f"visit_probs_{visit.id}"] = probs
    if probs:
        st.markdown("### Class Confidence Breakdown")
        for item in probs:
            st.write(f"- {item['label']}: {item['confidence']:.2f}%")

    # Run tPA eligibility
    with st.spinner("Running tPA eligibility evaluation..."):
        eligibility = run_tpa_eligibility(visit.id)

    update_visit(
        visit.id,
        tpa_eligible=eligibility["eligible"],
        tpa_reason=eligibility["reason"]
    )

    # Plain text eligibility (no markdown or asterisks)
    st.info(
        f"tPA Eligibility:\n"
        f"Eligible: {eligibility['eligible']}\n"
        f"Reason: {eligibility['reason']}"
    )

    st.success("All scan data saved successfully.")
    # After processing, rerun to show standardized view below
    st.rerun()

# --- Always show current results and comment editor below ---
st.markdown("---")
st.subheader("Results")

# Refresh visit state to reflect latest DB updates
visit = get_visit_by_id(visit_id)

if visit.scan_path:
    # Highlight top result
    if getattr(visit, 'prediction_label', None) is not None:
        pred = visit.prediction_label
        conf_txt = (
            f"{float(getattr(visit, 'prediction_confidence', 0.0)):.2f}%"
            if getattr(visit, 'prediction_confidence', None) is not None else "-"
        )
        st.success(f"Prediction: {pred} ({conf_txt})")
    # Show image just below the highlighted result
    caption_conf = f"{float(getattr(visit, 'prediction_confidence', 0.0)):.2f}%" if getattr(visit, 'prediction_confidence', None) is not None else "-"
    caption = f"Uploaded scan — {getattr(visit, 'prediction_label', '—')} ({caption_conf})"
    st.image(visit.scan_path, caption=caption, use_column_width=True)
else:
    st.info("No scan has been processed yet for this visit.")

if getattr(visit, 'prediction_label', None):
    st.write(f"Prediction: {visit.prediction_label}")
    if getattr(visit, 'prediction_confidence', None) is not None:
        st.write(f"Confidence: {float(visit.prediction_confidence):.2f}%")

# Class confidence breakdown from session if available
probs_session = st.session_state.get(f"visit_probs_{visit.id}") or []
if probs_session:
    st.markdown("### Class Confidence Breakdown")
    for item in probs_session:
        st.write(f"- {item['label']}: {item['confidence']:.2f}%")

# tPA status if available
if getattr(visit, 'tpa_eligible', None) is not None:
    status = "Eligible" if visit.tpa_eligible else "NOT Eligible"
    st.info(f"tPA Status: {status}\nReason: {visit.tpa_reason or ''}")

# Technician comment editor (persistent, no redirect)
st.markdown("### Technician Comment (optional)")
existing_notes = getattr(visit, 'technician_notes', '') or ''
tech_comment = st.text_area(
    "Comment",
    key="tech_comment",
    value=existing_notes,
    placeholder="Add any relevant notes about the scan or patient status...",
)
if st.button("Save Comment", key="save_comment"):
    update_visit(visit.id, technician_notes=tech_comment)
    st.success("Comment saved.")

st.markdown("---")
if st.button("Review & Send to Doctor"):
    st.switch_page("pages/t_review_and_send.py")
