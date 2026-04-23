"""
primitives/fields.py — Core PDF field-writing primitives for HPE-AFF.

All functions operate on a pypdf PdfWriter instance.
Coordinates: pypdf rects are [left, bottom, right, top] with y=0 at page bottom.
"""
import structlog
from pypdf import PdfWriter
from pypdf.generic import ByteStringObject, NameObject

log = structlog.get_logger()


def _field_page(writer: PdfWriter, field_id: str) -> int:
    """Return 0-based page index for a given AcroForm field name.
    Falls back to page 0 if field not found (safe default).
    """
    for page_idx, page in enumerate(writer.pages):
        annots = page.get("/Annots", [])
        for annot_ref in annots:
            try:
                annot = annot_ref.get_object()
                if annot.get("/T") == field_id:
                    return page_idx
            except Exception:
                continue
    return 0


def fill_text_field(writer: PdfWriter, field_id: str, value: str) -> None:
    """Write a string value into a text (Tx) AcroForm field.

    Writes /V as ByteStringObject (PDFDocEncoding / Latin-1) instead of
    update_page_form_field_values, which encodes as UTF-16BE TextStringObject.
    UTF-16BE null bytes cause &-prefixed glyphs when rendered by single-byte
    Helvetica Type1 fonts. With NeedAppearances=True the viewer re-renders.

    Args:
        writer:   PdfWriter with the form loaded.
        field_id: AcroForm field name (/T key).
        value:    String to write.
    """
    encoded = ByteStringObject(str(value).encode("latin-1", errors="replace"))
    found = False
    for page in writer.pages:
        annots = page.get("/Annots", [])
        for annot_ref in annots:
            try:
                annot = annot_ref.get_object()
                if annot.get("/T") == field_id:
                    annot.update({NameObject("/V"): encoded})
                    found = True
            except Exception:
                continue
    log.debug("fill_text_field", field=field_id, found=found, value=str(value)[:50])


def fill_checkbox(writer: PdfWriter, field_id: str, checked: bool) -> None:
    """Set a checkbox (Btn) field to checked or unchecked.

    Uses /Yes for checked and /Off for unchecked.
    Export value /Yes is confirmed for all 10 HPE-AFF test forms.
    In production, read export value from field metadata via detect_field_type.

    Args:
        writer:   PdfWriter with the form loaded.
        field_id: AcroForm field name.
        checked:  True → /Yes, False → /Off.
    """
    value = NameObject("/Yes") if checked else NameObject("/Off")
    page_idx = _field_page(writer, field_id)

    # Update both /V (value) and /AS (appearance state) for reliable rendering
    for page in writer.pages:
        annots = page.get("/Annots", [])
        for annot_ref in annots:
            try:
                annot = annot_ref.get_object()
                if annot.get("/T") == field_id:
                    annot.update({
                        NameObject("/V"):  value,
                        NameObject("/AS"): value,
                    })
            except Exception:
                continue

    log.debug("fill_checkbox", field=field_id, checked=checked)


def set_radio(writer: PdfWriter, group_field_id: str, selected_value: str) -> None:
    """Set a radio button group to the specified export value.

    Radio groups share a parent /T; children have individual /AS values.
    This sets the group value and updates child appearance states.

    Args:
        writer:          PdfWriter with the form loaded.
        group_field_id:  Parent field name for the radio group.
        selected_value:  Export value of the button to select (e.g. "Option1").
    """
    for page in writer.pages:
        annots = page.get("/Annots", [])
        for annot_ref in annots:
            try:
                annot = annot_ref.get_object()
                if annot.get("/T") == group_field_id:
                    annot.update({
                        NameObject("/V"): NameObject(f"/{selected_value}"),
                    })
                # Handle kids (child radio buttons)
                kids = annot.get("/Kids", [])
                for kid_ref in kids:
                    kid = kid_ref.get_object()
                    ap = kid.get("/AP", {})
                    n_dict = ap.get("/N", {}) if ap else {}
                    export_vals = list(n_dict.keys()) if n_dict else []
                    # Find the non-/Off export value
                    kid_export = next((v for v in export_vals if v != "/Off"), None)
                    if kid_export and kid_export.lstrip("/") == selected_value:
                        kid.update({NameObject("/AS"): NameObject(f"/{selected_value}")})
                    else:
                        kid.update({NameObject("/AS"): NameObject("/Off")})
            except Exception:
                continue

    log.debug("set_radio", group=group_field_id, selected=selected_value)


def fill_table_row(writer: PdfWriter, prefix: str, index: int, data: dict) -> None:
    """Write one row of a repeating table section.

    Field naming convention: {prefix}{index}_{column_name}
    e.g. prefix="item", index=1, data={"desc": "Widget"} → fills "item1_desc"

    Args:
        writer: PdfWriter with the form loaded.
        prefix: Row prefix string (e.g. "item", "exp", "good").
        index:  1-based row index.
        data:   Dict of column_name → value for this row.
    """
    for col_name, value in data.items():
        field_id = f"{prefix}{index}_{col_name}"
        fill_text_field(writer, field_id, str(value) if value is not None else "")

    log.debug("fill_table_row", prefix=prefix, index=index, cols=list(data.keys()))
