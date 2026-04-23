"""Shared primitive library L for HPE-AFF form filling."""
from .fields import fill_text_field, fill_checkbox, fill_table_row, set_radio
from .coords import normalize_bbox, denormalize_bbox, anchor_label_to_field
from .transforms import apply_date_transform, apply_number_transform, apply_currency_transform
from .inspect import detect_field_type, compute_overflow

__all__ = [
    "fill_text_field", "fill_checkbox", "fill_table_row", "set_radio",
    "normalize_bbox", "denormalize_bbox", "anchor_label_to_field",
    "apply_date_transform", "apply_number_transform", "apply_currency_transform",
    "detect_field_type", "compute_overflow",
]
