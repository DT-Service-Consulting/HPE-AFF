"""
HPE-AFF Streamlit App v2
Run: python -m streamlit run app.py
"""
import json
import os
import re
import sys
import tempfile
from difflib import SequenceMatcher

import streamlit as st

from env_config import ensure_env_loaded

# ── path setup ────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
ensure_env_loaded()

# ── page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="HPE-AFF Form Filler",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

FORMS_DIR = os.path.join(ROOT, "data", "test_forms")

FORM_OPTIONS = {
    "Custom upload": None,
    "Form 01 — Personal Info (16 fields)":              "form_01_personal_info",
    "Form 02 — Supplier Registration (20 fields)":      "form_02_supplier_registration",
    "Form 03 — Product Sheet (24 fields)":              "form_03_product_sheet",
    "Form 04 — Compliance Doc (18 fields)":             "form_04_compliance_doc",
    "Form 05 — Invoice (51 fields)":                    "form_05_invoice",
    "Form 06 — Job Application (16 fields)":            "form_06_job_application",
    "Form 07 — Patient Intake (33 fields)":             "form_07_patient_intake",
    "Form 08 — Expense Report (64 fields)":             "form_08_expense_report",
    "Form 09 — GDPR DSR (21 fields)":                   "form_09_gdpr_dsr",
    "Form 10 — Certificate of Origin (64 fields)":      "form_10_certificate_of_origin",
}

FORM_ID_MAP = {
    "form_01_personal_info":         "form_01",
    "form_02_supplier_registration": "form_02",
    "form_03_product_sheet":         "form_03",
    "form_04_compliance_doc":        "form_04",
    "form_05_invoice":               "form_05",
    "form_06_job_application":       "form_06",
    "form_07_patient_intake":        "form_07",
    "form_08_expense_report":        "form_08",
    "form_09_gdpr_dsr":              "form_09",
    "form_10_certificate_of_origin": "form_10",
}

SCORE_COLORS = {
    "ok":                   "🟢",
    "missing":              "🔴",
    "semantic_mismatch":    "🟠",
    "format_error":         "🟡",
    "wrong_checkbox_state": "🟠",
    "overflow":             "🟡",
    "wrong_type":           "🔴",
}


# ── helpers ───────────────────────────────────────────────────────

def flatten_payload(obj, prefix=""):
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            flat.update(flatten_payload(v, new_key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            flat.update(flatten_payload(item, f"{prefix}[{i}]"))
    else:
        flat[prefix] = obj
    return flat


@st.cache_data(show_spinner=False)
def load_test_payload(form_name: str) -> dict:
    form_id = FORM_ID_MAP.get(form_name, "")
    path = os.path.join(FORMS_DIR, f"{form_id}_payload.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_best_fill_code(form_name: str) -> str | None:
    """Load best evolved fill_code from experiment_state pool, if available."""
    if not form_name:
        return None
    form_id = FORM_ID_MAP.get(form_name, "")
    if not form_id:
        return None
    pool_path = os.path.join(ROOT, "experiment_state", f"pool_{form_id}.json")
    if not os.path.exists(pool_path):
        return None
    try:
        with open(pool_path, encoding="utf-8") as f:
            pool = json.load(f)
        scored = [c for c in pool if c.get("score") is not None and c.get("fill_code")]
        if not scored:
            return None
        best = max(scored, key=lambda c: c["score"])
        return best["fill_code"]
    except Exception:
        return None


def _extract_pdf_form_fields(pdf_path: str) -> dict:
    from pypdf import PdfReader
    fields = PdfReader(pdf_path).get_fields() or {}
    return {
        name: {"name": name, "value": meta.get("/V"),
               "type": str(meta.get("/FT")) if meta else None}
        for name, meta in fields.items()
    }


_HEURISTIC_SYNONYMS = {
    "addr": {"address", "street"}, "amount": {"cost", "price", "total"},
    "company": {"business", "supplier", "vendor"}, "desc": {"description"},
    "email": {"mail"}, "first": {"given"}, "last": {"family", "surname"},
    "mobile": {"phone", "telephone"}, "qty": {"quantity"}, "tax": {"vat"}, "vat": {"tax"},
}


def _heuristic_score(field_name: str, key: str) -> float:
    def norm(s):
        s = re.sub(r"(?<!^)(?=[A-Z])", "_", str(s))
        return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    fn, kn = norm(field_name), norm(key)
    ft = {t for t in fn.split("_") if t}
    for t in list(ft): ft |= _HEURISTIC_SYNONYMS.get(t, set())
    kt = {t for t in kn.split("_") if t}
    for t in list(kt): kt |= _HEURISTIC_SYNONYMS.get(t, set())
    score = 0.0
    if fn == kn: score += 10.0
    if fn in kn or kn in fn: score += 3.0
    score += len(ft & kt) * 2.0 + SequenceMatcher(None, fn, kn).ratio()
    return score


def _generate_heuristic_mapping(form_fields: dict, user_data: dict) -> dict:
    mapping = {}
    for field_name in form_fields:
        best_key, best_score = None, 1.75
        for key in user_data:
            s = _heuristic_score(field_name, key)
            if s > best_score:
                best_key, best_score = key, s
        mapping[field_name] = {"source": best_key, "transform": None}
    return mapping


def run_fill_and_eval(pdf_path: str, payload: dict, expected_mapping: dict | None,
                      form_name: str | None = None):
    """Core fill + evaluate pipeline. Returns (filled_bytes, eval_result, form_fields, mapping)."""
    from execution.executor import _validate_program, _SAFE_BUILTINS
    from execution.writer import PdfFormWriter
    from evaluation.scorer import build_eval_result

    form_fields = _extract_pdf_form_fields(pdf_path)
    clean_payload = {k: v for k, v in payload.items() if k != "_expected_field_mapping"}
    flat = flatten_payload(clean_payload)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        out_path = tmp.name

    writer = PdfFormWriter(pdf_path)
    fill_code = _load_best_fill_code(form_name)
    method = "heuristic"
    mapping = {}

    if fill_code:
        try:
            _validate_program(fill_code, f"pool:{form_name}")
            ns: dict = {"__builtins__": _SAFE_BUILTINS}
            exec(fill_code, ns)  # noqa: S102  — validated + builtins restricted
            fill_fn = ns.get("fill")
            if fill_fn:
                fill_fn(writer, flat)
                method = "evolved"
            else:
                raise ValueError("no fill() in evolved code")
        except Exception as e:
            st.warning(f"Evolved program failed ({e}), falling back to heuristic.")
            fill_code = None

    if not fill_code:
        mapping = _generate_heuristic_mapping(form_fields, flat)
        for field_id, entry in mapping.items():
            src = entry.get("source") if isinstance(entry, dict) else entry
            if src and src in flat:
                writer.write_field(field_id, flat[src])

    writer.save(out_path)

    with open(out_path, "rb") as f:
        filled_bytes = f.read()

    eval_result = None
    if expected_mapping:
        actual_values = {}
        try:
            from pypdf import PdfReader
            reader = PdfReader(out_path)
            raw = reader.get_fields() or {}
            actual_values = {k: str(v.get("/V", "") or "") for k, v in raw.items()}
        except Exception:
            pass
        eval_result = build_eval_result(
            form_id=form_name or "uploaded",
            candidate_id=method,
            expected_mapping=expected_mapping,
            actual_values=actual_values,
        )

    try:
        os.unlink(out_path)
    except Exception:
        pass

    return filled_bytes, eval_result, form_fields, mapping, method


# ── sidebar ───────────────────────────────────────────────────────

st.sidebar.title("HPE-AFF")
st.sidebar.caption("Hierarchical Prompt Evolution — Automated Form Filling")
st.sidebar.divider()

selected_label = st.sidebar.selectbox("Select test form", list(FORM_OPTIONS.keys()))
selected_form = FORM_OPTIONS[selected_label]

forms_exist = os.path.exists(os.path.join(FORMS_DIR, "form_01_personal_info.pdf"))
if not forms_exist:
    st.sidebar.error("Test forms not found. Run `generate_test_forms.py` first.")

st.sidebar.divider()
show_all_fields = st.sidebar.checkbox("Show all fields (incl. correct)", value=False)
show_mapping = st.sidebar.checkbox("Show raw mapping", value=False)

# ── main ──────────────────────────────────────────────────────────

st.title("📄 HPE-AFF Form Filler")

col_left, col_right = st.columns([1, 1], gap="large")

# ── LEFT: inputs ──────────────────────────────────────────────────
with col_left:
    st.subheader("Inputs")

    pdf_path = None
    payload = {}
    expected_mapping = None

    if selected_form:
        # Test form mode
        pdf_path = os.path.join(FORMS_DIR, f"{selected_form}.pdf")
        if not os.path.exists(pdf_path):
            st.error(f"PDF not found: {pdf_path}")
            pdf_path = None
        else:
            st.success(f"Using: `{selected_form}.pdf`")

        raw_payload = load_test_payload(selected_form)
        expected_mapping = {
            fid: info["value"]
            for fid, info in raw_payload.get("_expected_field_mapping", {}).items()
        }
        clean_payload = {k: v for k, v in raw_payload.items() if k != "_expected_field_mapping"}
        payload_str = st.text_area(
            "Payload JSON",
            value=json.dumps(clean_payload, indent=2),
            height=300,
        )
        try:
            payload = json.loads(payload_str)
        except Exception as e:
            st.error(f"Invalid JSON: {e}")
            payload = {}

    else:
        # Custom upload mode
        uploaded_pdf = st.file_uploader("Upload blank PDF form", type=["pdf"])
        if uploaded_pdf:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(uploaded_pdf.read())
                pdf_path = tmp.name

        payload_str = st.text_area(
            "Payload JSON",
            height=300,
            value='{\n  "first_name": "Ada",\n  "last_name": "Lovelace",\n  "email": "ada@example.com"\n}',
        )
        try:
            payload = json.loads(payload_str)
        except Exception as e:
            st.error(f"Invalid JSON: {e}")

    run_btn = st.button(
        "▶ Fill Form",
        type="primary",
        disabled=(pdf_path is None or not payload),
        use_container_width=True,
    )

# ── RIGHT: results ────────────────────────────────────────────────
with col_right:
    st.subheader("Results")

    if run_btn and pdf_path and payload:
        with st.spinner("Filling form…"):
            try:
                filled_bytes, eval_result, form_fields, mapping, method = run_fill_and_eval(
                    pdf_path, payload, expected_mapping
                )
                fill_ok = True
            except Exception as e:
                st.error(f"Fill failed: {e}")
                import traceback
                st.code(traceback.format_exc())
                fill_ok = False

        if fill_ok:
            # Download
            fname = f"{selected_form}_filled.pdf" if selected_form else "filled.pdf"
            st.download_button(
                "⬇ Download Filled PDF",
                data=filled_bytes,
                file_name=fname,
                mime="application/pdf",
                use_container_width=True,
            )

            st.divider()

            # Metrics row
            if eval_result:
                total  = len(eval_result.field_results)
                ok     = sum(1 for r in eval_result.field_results if r.failure_mode == "ok")
                score  = eval_result.numeric_score

                m1, m2, m3 = st.columns(3)
                m1.metric("Field accuracy", f"{score:.0%}")
                m2.metric("Correct", f"{ok} / {total}")
                failures = {}
                for r in eval_result.field_results:
                    if r.failure_mode != "ok":
                        failures[r.failure_mode] = failures.get(r.failure_mode, 0) + 1
                top_fail = max(failures, key=failures.get) if failures else "none"
                m3.metric("Top failure", top_fail)

                st.divider()

                # Per-field table
                st.markdown("**Field results**")
                rows = []
                for r in eval_result.field_results:
                    if not show_all_fields and r.failure_mode == "ok":
                        continue
                    icon = SCORE_COLORS.get(r.failure_mode, "⚪")
                    rows.append({
                        "": icon,
                        "Field": r.field_name,
                        "Expected": str(r.expected)[:40],
                        "Actual": str(r.actual)[:40],
                        "Score": f"{r.score:.1f}",
                        "Failure": r.failure_mode,
                        "Level": r.level,
                    })

                if rows:
                    st.dataframe(
                        rows,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "": st.column_config.TextColumn(width="small"),
                            "Score": st.column_config.TextColumn(width="small"),
                            "Level": st.column_config.TextColumn(width="small"),
                        },
                    )
                elif not show_all_fields:
                    st.success("All fields correct!")

                # Trace expander
                if eval_result.textual_trace:
                    with st.expander("Mutation trace (for HPE evolution loop)"):
                        st.code(eval_result.textual_trace, language="text")

            else:
                # No expected mapping → just show detected fields
                st.info(f"Filled {len(form_fields)} fields. No ground-truth mapping to evaluate against.")

            # Raw mapping
            if show_mapping:
                with st.expander("Raw heuristic mapping"):
                    st.json(mapping)

            # Field inventory
            with st.expander(f"Form field inventory ({len(form_fields)} fields)"):
                st.dataframe(
                    [{"Field ID": k, "Type": v.get("type",""), "Current value": str(v.get("value",""))}
                     for k, v in form_fields.items()],
                    use_container_width=True,
                    hide_index=True,
                )

    else:
        st.info("Select a form and click **Fill Form** to run.")

        if forms_exist:
            baseline_path  = os.path.join(ROOT, "docs", "baseline_results.json")
            evolution_path = os.path.join(ROOT, "docs", "evolution_results.json")

            has_baseline  = os.path.exists(baseline_path)
            has_evolution = os.path.exists(evolution_path)

            if has_baseline or has_evolution:
                st.divider()

            # ── side-by-side comparison ───────────────────────────────────
            if has_baseline and has_evolution:
                with open(baseline_path)  as f: baseline  = json.load(f)
                with open(evolution_path) as f: evolution = json.load(f)

                b_agg = baseline.get("aggregate", {})
                e_agg = evolution.get("aggregate", {})

                b_mean = b_agg.get("mean_field_accuracy", 0)
                e_mean = e_agg.get("mean_score", 0)

                st.markdown("**Phase comparison — heuristic vs. evolved**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Phase 1 mean", f"{b_mean:.0%}")
                c2.metric("Phase 2 mean", f"{e_mean:.0%}",
                          delta=f"{(e_mean - b_mean):+.0%}")
                c3.metric("Forms converged (≥92%)",
                          f"{e_agg.get('forms_converged', 0)} / 10")

                st.divider()

                # Per-form comparison table
                b_map = {r["form_name"]: r for r in baseline.get("forms", [])}
                rows = []
                for r in evolution.get("forms", []):
                    fname  = r.get("form_name", "")
                    e_score = r.get("best_score", 0) or 0
                    b_score = b_map.get(fname, {}).get("field_accuracy", 0) or 0
                    delta   = e_score - b_score
                    icon    = "🟢" if e_score >= 0.92 else ("🟡" if e_score >= 0.75 else "🔴")
                    rows.append({
                        "": icon,
                        "Form": fname.replace("form_", "").replace("_", " ").title(),
                        "Phase 1": f"{b_score:.0%}",
                        "Phase 2": f"{e_score:.0%}",
                        "Delta": f"{delta:+.0%}",
                        "Gen": r.get("best_generation", "—"),
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True,
                             column_config={
                                 "": st.column_config.TextColumn(width="small"),
                                 "Gen": st.column_config.TextColumn(width="small"),
                             })

            # ── baseline only ─────────────────────────────────────────────
            elif has_baseline:
                with open(baseline_path) as f: baseline = json.load(f)
                agg = baseline.get("aggregate", {})
                st.markdown("**Phase 1 baseline (heuristic mode)**")
                b1, b2, b3 = st.columns(3)
                b1.metric("Mean accuracy", f"{agg.get('mean_field_accuracy', 0):.0%}")
                b2.metric("Forms fully correct", f"{agg.get('forms_fully_correct', 0)} / 10")
                b3.metric("Top failure", agg.get("top_failure_mode", "—"))
                form_rows = [
                    {
                        "Form": r["form_name"],
                        "Accuracy": f"{r['field_accuracy']:.0%}",
                        "Correct": f"{r['fields_correct']} / {r['expected_mappings']}",
                        "Top failure": max(r["failure_modes"], key=r["failure_modes"].get),
                    }
                    for r in baseline.get("forms", [])
                ]
                st.dataframe(form_rows, use_container_width=True, hide_index=True)

            # ── evolution only ────────────────────────────────────────────
            elif has_evolution:
                with open(evolution_path) as f: evolution = json.load(f)
                agg = evolution.get("aggregate", {})
                st.markdown("**Phase 2 evolution results**")
                e1, e2, e3 = st.columns(3)
                e1.metric("Mean accuracy", f"{agg.get('mean_score', 0):.0%}")
                e2.metric("Forms converged", f"{agg.get('forms_converged', 0)} / 10")
                e3.metric("Model", evolution.get("model_generator", "—"))
                form_rows = [
                    {
                        "Form": r.get("form_name", ""),
                        "Score": f"{r.get('best_score', 0):.0%}",
                        "Gen": r.get("best_generation", "—"),
                    }
                    for r in evolution.get("forms", [])
                ]
                st.dataframe(form_rows, use_container_width=True, hide_index=True)
