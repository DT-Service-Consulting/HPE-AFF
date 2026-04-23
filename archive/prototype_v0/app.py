import json
import os

import streamlit as st

from core_logic import (
    evolve_mappings,
    extract_pdf_form_fields,
    extract_pdf_text,
    fill_pdf_form,
    get_runtime_configuration,
)

st.set_page_config(
    page_title="PDF Form ETTC",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("PDF Form ETTC (Azure)")
st.markdown("Evolutionary test-time compute for PDF form filling using Azure AI Inference.")

runtime_config = get_runtime_configuration()
if runtime_config["mode"] != "azure":
    missing = ", ".join(runtime_config["missing"]) or "none"
    st.warning(
        f"Azure configuration not detected. Running in local heuristic mode. Missing: {missing}"
    )

st.sidebar.header("Run Settings")
generations = st.sidebar.slider("Generations", min_value=1, max_value=6, value=3)
population = st.sidebar.slider("Population", min_value=2, max_value=10, value=5)

uploaded = st.file_uploader("Upload a fillable PDF", type=["pdf"])
user_data_raw = st.text_area(
    "User data JSON",
    height=180,
    value='{"first_name": "Ada", "last_name": "Lovelace", "dob": "1815-12-10", "email": "ada@example.com"}',
)

if uploaded and user_data_raw:
    try:
        user_data = json.loads(user_data_raw)
    except Exception as e:
        st.error(f"Invalid JSON: {e}")
        st.stop()

    with st.spinner("Parsing PDF..."):
        tmp_pdf = os.path.join("outputs", "uploaded.pdf")
        os.makedirs("outputs", exist_ok=True)
        with open(tmp_pdf, "wb") as f:
            f.write(uploaded.read())

        fields = extract_pdf_form_fields(tmp_pdf)
        form_text = extract_pdf_text(tmp_pdf)

    st.subheader("Detected Fields")
    st.write(list(fields.keys()))

    if st.button("Run ETTC"):
        with st.spinner("Running evolutionary loop..."):
            candidates = evolve_mappings(
                fields,
                user_data,
                form_text,
                generations=generations,
                population=population,
            )

        best = candidates[0]
        st.subheader("Best Mapping")
        st.json(best.mapping)
        st.caption(best.notes)

        out_pdf = os.path.join("outputs", "filled.pdf")
        fill_pdf_form(tmp_pdf, out_pdf, best.mapping, user_data)

        with open(out_pdf, "rb") as f:
            st.download_button("Download Filled PDF", data=f, file_name="filled.pdf")
else:
    st.info("Upload a fillable PDF and provide user data JSON to start.")
