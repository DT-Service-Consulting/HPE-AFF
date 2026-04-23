"""
execution/writer.py — Safe PdfWriter wrapper for HPE-AFF.

Wraps pypdf PdfWriter with:
  - Correct AcroForm cloning
  - NeedAppearances flag for reliable rendering
  - Per-field error isolation (one bad field does not abort the run)
  - Structured logging of every write operation
"""
from __future__ import annotations
import os
import structlog
from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from primitives.fields import fill_text_field, fill_checkbox, fill_table_row
from primitives.inspect import detect_field_type

log = structlog.get_logger()


class PdfFormWriter:
    """Safe wrapper around pypdf PdfWriter for AcroForm filling.

    Usage:
        w = PdfFormWriter("blank.pdf")
        w.write_text("company_name", "Primus Components BV")
        w.write_checkbox("currency_eur", True)
        w.write_table_row("item", 1, {"desc": "Widget", "qty": "5", "total": "50.00"})
        w.save("filled.pdf")
    """

    def __init__(self, template_pdf_path: str) -> None:
        """Load blank PDF template.

        Args:
            template_pdf_path: Path to the blank AcroForm PDF.
        """
        self._template_path = template_pdf_path
        reader = PdfReader(template_pdf_path)

        try:
            self._writer = PdfWriter(clone_from=reader)
        except Exception as clone_err:
            log.warning("pdf_clone_failed_using_fallback", error=str(clone_err),
                        template=template_pdf_path)
            self._writer = PdfWriter()
            for page in reader.pages:
                self._writer.add_page(page)
            try:
                acroform = reader.trailer["/Root"].get("/AcroForm")
                if acroform:
                    self._writer._root_object.update(
                        {NameObject("/AcroForm"): acroform}
                    )
                else:
                    log.warning("pdf_no_acroform_found", template=template_pdf_path)
            except Exception as acro_err:
                log.warning("pdf_acroform_attach_failed", error=str(acro_err),
                            template=template_pdf_path)

        # Ensure NeedAppearances so PDF viewers render written values
        self._ensure_need_appearances()

        # Build field metadata index
        self._fields: dict[str, dict] = {}
        raw = reader.get_fields() or {}
        for name, meta in raw.items():
            ff = 0
            try:
                ff = int(meta.get("/Ff", 0) or 0)
            except Exception:
                pass
            self._fields[name] = {
                "name": name,
                "type": str(meta.get("/FT", "") or ""),
                "value": meta.get("/V"),
                "ff": ff,
            }

        self._errors: list[dict] = []
        log.info("pdf_form_writer_init", template=template_pdf_path,
                 field_count=len(self._fields))

    def _ensure_need_appearances(self) -> None:
        try:
            acroform = self._writer._root_object.get("/AcroForm")
            if acroform:
                acroform.update(
                    {NameObject("/NeedAppearances"): BooleanObject(True)}
                )
        except Exception as e:
            log.warning("pdf_need_appearances_failed", error=str(e))

    @property
    def field_names(self) -> list[str]:
        return list(self._fields.keys())

    def write_text(self, field_id: str, value: str) -> bool:
        """Write a string into a text field. Returns True on success."""
        try:
            fill_text_field(self._writer, field_id, value)
            return True
        except Exception as e:
            self._errors.append({"field": field_id, "op": "write_text", "error": str(e)})
            log.error("write_text_failed", field=field_id, error=str(e))
            return False

    def write_checkbox(self, field_id: str, checked: bool) -> bool:
        """Set a checkbox field. Returns True on success."""
        try:
            fill_checkbox(self._writer, field_id, checked)
            return True
        except Exception as e:
            self._errors.append({"field": field_id, "op": "write_checkbox", "error": str(e)})
            log.error("write_checkbox_failed", field=field_id, error=str(e))
            return False

    def write_table_row(self, prefix: str, index: int, data: dict) -> bool:
        """Write one table row. Returns True if all columns written successfully."""
        try:
            fill_table_row(self._writer, prefix, index, data)
            return True
        except Exception as e:
            self._errors.append({"prefix": prefix, "index": index, "op": "write_table_row", "error": str(e)})
            log.error("write_table_row_failed", prefix=prefix, index=index, error=str(e))
            return False

    def write_field(self, field_id: str, value) -> bool:
        """Auto-detect field type and write value accordingly.

        Handles bool → checkbox, str → text field.
        """
        meta = self._fields.get(field_id, {})
        ftype = detect_field_type(meta) if meta else "text"

        if ftype == "checkbox":
            if isinstance(value, str):
                checked = value.strip().lower() in ("/yes", "yes", "true", "1", "on")
            else:
                checked = bool(value)
            return self.write_checkbox(field_id, checked)
        else:
            return self.write_text(field_id, str(value) if value is not None else "")

    def save(self, output_path: str) -> None:
        """Write filled PDF to disk.

        Args:
            output_path: Destination file path. Parent dirs created if needed.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            self._writer.write(f)
        log.info("pdf_saved", path=output_path, errors=len(self._errors))

    @property
    def errors(self) -> list[dict]:
        return list(self._errors)
