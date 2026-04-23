"""
Generate 10 diverse fillable PDFs for HPE-AFF architecture testing.
Each form tests a different combination of field types, complexity, and domain.
Uses reportlab for layout + pypdf for AcroForm field injection.
"""
import os
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.units import mm, inch
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    NameObject, DictionaryObject, ArrayObject, TextStringObject as StringObject,
    BooleanObject, NumberObject, IndirectObject, RectangleObject
)
import io

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test_forms")
os.makedirs(OUT, exist_ok=True)

W, H = A4  # 595.27 x 841.89 pts


def add_acroform_field(writer, name, field_type, rect, page_idx=0,
                       default_value="", checked_value="/Yes", choices=None,
                       multiline=False, font_size=10):
    """Inject an AcroForm field onto an existing page."""
    page = writer.pages[page_idx]

    field = DictionaryObject({
        NameObject("/Type"):    NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"):      NameObject(field_type),
        NameObject("/T"):       StringObject(name),
        NameObject("/Rect"):    ArrayObject([
            NumberObject(rect[0]), NumberObject(rect[1]),
            NumberObject(rect[2]), NumberObject(rect[3])
        ]),
        NameObject("/F"):       NumberObject(4),
    })

    if field_type == "/Tx":
        da_str = f"/Helvetica {font_size} Tf 0 g"
        field[NameObject("/DA")] = StringObject(da_str)
        field[NameObject("/V")] = StringObject(default_value)
        if multiline:
            field[NameObject("/Ff")] = NumberObject(4096)

    elif field_type == "/Btn":
        field[NameObject("/V")] = NameObject("/Off")
        field[NameObject("/AS")] = NameObject("/Off")
        field[NameObject("/Ff")] = NumberObject(0)
        ap = DictionaryObject({
            NameObject("/N"): DictionaryObject({
                NameObject("/Yes"):  StringObject(""),
                NameObject("/Off"):  StringObject(""),
            })
        })
        field[NameObject("/AP")] = ap

    elif field_type == "/Ch" and choices:
        opts = ArrayObject([StringObject(c) for c in choices])
        field[NameObject("/Opt")] = opts
        field[NameObject("/V")] = StringObject("")
        field[NameObject("/DA")] = StringObject(f"/Helvetica {font_size} Tf 0 g")

    ref = writer._add_object(field)

    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    page[NameObject("/Annots")].append(ref)

    if "/AcroForm" not in writer._root_object:
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject(),
            NameObject("/DR"): DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/Helvetica"): DictionaryObject({
                        NameObject("/Type"):     NameObject("/Font"),
                        NameObject("/Subtype"):  NameObject("/Type1"),
                        NameObject("/BaseFont"): NameObject("/Helvetica"),
                    })
                })
            }),
            NameObject("/DA"): StringObject("/Helvetica 10 Tf 0 g"),
        })

    writer._root_object["/AcroForm"]["/Fields"].append(ref)
    return ref


def draw_form_header(c, title, subtitle, page_w=W, page_h=H):
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(page_w / 2, page_h - 50, title)
    c.setFont("Helvetica", 10)
    c.drawCentredString(page_w / 2, page_h - 65, subtitle)
    c.setLineWidth(1.5)
    c.line(40, page_h - 72, page_w - 40, page_h - 72)


def draw_label(c, text, x, y, bold=False, size=9):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(x, y, text)


def draw_field_box(c, x, y, w, h=16):
    c.setLineWidth(0.5)
    c.rect(x, y, w, h)


def draw_checkbox_with_label(c, cx, cy, label, size=9):
    c.setLineWidth(0.5)
    c.rect(cx, cy, 10, 10)
    c.setFont("Helvetica", size)
    c.drawString(cx + 14, cy + 1, label)


def save_canvas_to_writer(c_buffer) -> PdfWriter:
    c_buffer.seek(0)
    reader = PdfReader(c_buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    return writer


# ─────────────────────────────────────────────────────────────────
# FORM 1: Simple personal info (mirrors the TheWebJockeys sample,
#          but properly filled + more fields)
# ─────────────────────────────────────────────────────────────────
def form_01_personal():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "Personal Information Form", "Form 01 — Simple text + checkbox (HPE-AFF baseline test)")

    y = H - 110
    fields = [
        ("Last Name",    "last_name",   50, y,      260, y),
        ("First Name",   "first_name",  50, y - 35, 260, y - 35),
        ("Middle Name",  "middle_name", 50, y - 70, 260, y - 70),
        ("Email",        "email",       50, y - 105,260, y - 105),
        ("Phone",        "phone",       50, y - 140,260, y - 140),
        ("Date of Birth","dob",         50, y - 175,260, y - 175),
    ]
    for label, fid, lx, ly, fx, fy in fields:
        draw_label(c, label + ":", lx, ly + 2)
        draw_field_box(c, fx, fy - 2, 250, 16)

    draw_label(c, "Gender:", 50, y - 215 + 2)
    for i, opt in enumerate(["Male", "Female", "Non-binary", "Prefer not to say"]):
        draw_checkbox_with_label(c, 130 + i * 110, y - 215, opt)

    draw_label(c, "Preferred Contact:", 50, y - 250 + 2)
    for i, opt in enumerate(["Email", "Phone", "Post"]):
        draw_checkbox_with_label(c, 175 + i * 90, y - 250, opt)

    draw_label(c, "Nationality:", 50, y - 285 + 2)
    draw_field_box(c, 140, y - 287, 160, 16)

    draw_label(c, "Signature:", 50, y - 330 + 2)
    draw_field_box(c, 130, y - 332, 200, 16)
    draw_label(c, "Date:", 350, y - 330 + 2)
    draw_field_box(c, 385, y - 332, 120, 16)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 01 — HPE-AFF Test Suite | Personal Information")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = y
    for label, fid, lx, ly, fx, fy in fields:
        add_acroform_field(writer, fid, "/Tx", [fx, fy - 2, fx + 250, fy + 14])
    add_acroform_field(writer, "gender_male",     "/Btn", [130, y0 - 215, 140, y0 - 205])
    add_acroform_field(writer, "gender_female",   "/Btn", [240, y0 - 215, 250, y0 - 205])
    add_acroform_field(writer, "gender_nonbinary","/Btn", [350, y0 - 215, 360, y0 - 205])
    add_acroform_field(writer, "gender_other",    "/Btn", [460, y0 - 215, 470, y0 - 205])
    add_acroform_field(writer, "contact_email",   "/Btn", [175, y0 - 250, 185, y0 - 240])
    add_acroform_field(writer, "contact_phone",   "/Btn", [265, y0 - 250, 275, y0 - 240])
    add_acroform_field(writer, "contact_post",    "/Btn", [355, y0 - 250, 365, y0 - 240])
    add_acroform_field(writer, "nationality",     "/Tx",  [140, y0 - 287, 300, y0 - 271])
    add_acroform_field(writer, "signature",       "/Tx",  [130, y0 - 332, 330, y0 - 316])
    add_acroform_field(writer, "date",            "/Tx",  [385, y0 - 332, 505, y0 - 316])

    with open(f"{OUT}/form_01_personal_info.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_01_personal_info.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 2: Supplier / Vendor Registration
# ─────────────────────────────────────────────────────────────────
def form_02_supplier():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "Supplier Registration Form", "Form 02 — Vendor onboarding | Company + contact + banking")

    y = H - 110
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "COMPANY DETAILS")
    c.line(50, y - 3, W - 50, y - 3)
    y -= 20

    company_fields = [
        ("Legal Company Name", "company_name",    y),
        ("Trading Name",       "trading_name",    y - 30),
        ("Registration No.",   "reg_number",      y - 60),
        ("VAT / Tax ID",       "vat_number",      y - 90),
        ("Industry Sector",    "industry_sector", y - 120),
        ("Country of Regist.", "country",         y - 150),
        ("Website",            "website",         y - 180),
    ]
    for label, fid, fy in company_fields:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 185, fy - 2, 355, 16)

    y2 = y - 220
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "PRIMARY CONTACT")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    y2 -= 20

    contact_fields = [
        ("Full Name",    "contact_name",  y2),
        ("Job Title",    "contact_title", y2 - 30),
        ("Email",        "contact_email", y2 - 60),
        ("Phone",        "contact_phone", y2 - 90),
    ]
    for label, fid, fy in contact_fields:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 185, fy - 2, 355, 16)

    y3 = y2 - 130
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y3, "BANKING DETAILS")
    c.line(50, y3 - 3, W - 50, y3 - 3)
    y3 -= 20

    bank_fields = [
        ("Bank Name",       "bank_name",    y3),
        ("Account Holder",  "acct_holder",  y3 - 30),
        ("IBAN",            "iban",         y3 - 60),
        ("BIC / SWIFT",     "bic_swift",    y3 - 90),
    ]
    for label, fid, fy in bank_fields:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 185, fy - 2, 355, 16)

    draw_label(c, "Currency:", 50, y3 - 120 + 2)
    for i, curr in enumerate(["EUR", "USD", "GBP", "CHF", "Other"]):
        draw_checkbox_with_label(c, 130 + i * 80, y3 - 120, curr)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 02 — HPE-AFF Test Suite | Supplier Registration")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 130
    for label, fid, fy in company_fields:
        add_acroform_field(writer, fid, "/Tx", [185, fy - 2, 540, fy + 14])
    y2a = y0 - 240
    for label, fid, fy in contact_fields:
        add_acroform_field(writer, fid, "/Tx", [185, fy - 2, 540, fy + 14])
    y3a = y2a - 150
    for label, fid, fy in bank_fields:
        add_acroform_field(writer, fid, "/Tx", [185, fy - 2, 540, fy + 14])
    for i, curr in enumerate(["eur", "usd", "gbp", "chf", "other"]):
        add_acroform_field(writer, f"currency_{curr}", "/Btn",
                           [130 + i*80, y3a - 120, 140 + i*80, y3a - 110])

    with open(f"{OUT}/form_02_supplier_registration.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_02_supplier_registration.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 3: Product Data Sheet (repeating line items)
# ─────────────────────────────────────────────────────────────────
def form_03_product_sheet():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "Product Data Sheet", "Form 03 — Repeating table rows + product metadata")

    y = H - 110
    meta = [
        ("Manufacturer",   "manufacturer",   y),
        ("Product Family", "product_family", y - 30),
        ("Product Name",   "product_name",   y - 60),
        ("Model / SKU",    "sku",            y - 90),
        ("EAN / GTIN",     "ean",            y - 120),
        ("Origin Country", "origin_country", y - 150),
    ]
    for label, fid, fy in meta:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 165, fy - 2, 370, 16)

    y2 = y - 200
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "TECHNICAL SPECIFICATIONS")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    y2 -= 18

    col_x  = [50, 130, 250, 370, 480]
    col_w  = [75, 115, 115, 105, 65]
    headers = ["Parameter", "Value", "Unit", "Standard", "Tolerance"]
    c.setFont("Helvetica-Bold", 8)
    for i, h in enumerate(headers):
        c.rect(col_x[i], y2 - 14, col_w[i], 16)
        c.drawString(col_x[i] + 3, y2 - 6, h)

    spec_labels = [
        "Weight", "Dimensions", "Voltage", "Power",
        "Temp. Range", "IP Rating",
    ]
    row_h = 20
    for r, lbl in enumerate(spec_labels):
        ry = y2 - 14 - (r + 1) * row_h
        for ci in range(5):
            c.rect(col_x[ci], ry, col_w[ci], row_h)
        c.setFont("Helvetica", 8)
        c.drawString(col_x[0] + 3, ry + 5, lbl)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 03 — HPE-AFF Test Suite | Product Data Sheet")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 110
    for label, fid, fy in meta:
        add_acroform_field(writer, fid, "/Tx", [165, fy - 2, 535, fy + 14])

    y2a = y0 - 218
    row_h = 20
    for r, lbl in enumerate(["weight", "dimensions", "voltage", "power", "temp_range", "ip_rating"]):
        ry = y2a - (r + 1) * row_h
        for ci, col_name in enumerate(["value", "unit", "standard", "tolerance"]):
            if ci == 0:
                continue
            add_acroform_field(writer, f"spec_{lbl}_{col_name}", "/Tx",
                               [col_x[ci], ry, col_x[ci] + col_w[ci], ry + row_h], font_size=8)

    with open(f"{OUT}/form_03_product_sheet.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_03_product_sheet.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 4: Compliance / Declaration of Conformity
# ─────────────────────────────────────────────────────────────────
def form_04_compliance():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "EU Declaration of Conformity", "Form 04 — Regulatory compliance | checkboxes + directives + signature")

    y = H - 110
    top_fields = [
        ("Manufacturer Name",    "mfr_name",    y),
        ("Manufacturer Address", "mfr_address", y - 30),
        ("Authorised Rep. (EU)", "auth_rep",    y - 60),
        ("Product Name",         "prod_name",   y - 90),
        ("Model / Type",         "model_type",  y - 120),
        ("Serial / Batch No.",   "serial_no",   y - 150),
        ("Year of Manufacture",  "year_mfr",    y - 180),
    ]
    for label, fid, fy in top_fields:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 190, fy - 2, 350, 16)

    y2 = y - 220
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "APPLICABLE DIRECTIVES / REGULATIONS")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    y2 -= 16
    directives = [
        ("Low Voltage Directive 2014/35/EU",          "dir_lvd"),
        ("EMC Directive 2014/30/EU",                  "dir_emc"),
        ("Machinery Directive 2006/42/EC",             "dir_mach"),
        ("RoHS Directive 2011/65/EU",                  "dir_rohs"),
        ("REACH Regulation (EC) 1907/2006",            "dir_reach"),
        ("General Product Safety Regulation 2023/988", "dir_gpsr"),
    ]
    for i, (label, fid) in enumerate(directives):
        ry = y2 - i * 20
        draw_checkbox_with_label(c, 55, ry - 10, label)

    y3 = y2 - len(directives) * 20 - 20
    draw_label(c, "Notified Body (if applicable):", 50, y3 + 2)
    draw_field_box(c, 210, y3 - 2, 330, 16)
    draw_label(c, "NB Certificate No.:", 50, y3 - 30 + 2)
    draw_field_box(c, 175, y3 - 32, 200, 16)

    draw_label(c, "Place & Date:", 50, y3 - 65 + 2)
    draw_field_box(c, 135, y3 - 67, 180, 16)
    draw_label(c, "Signature:", 360, y3 - 65 + 2)
    draw_field_box(c, 415, y3 - 67, 125, 16)
    draw_label(c, "Name & Title of Signatory:", 50, y3 - 95 + 2)
    draw_field_box(c, 210, y3 - 97, 330, 16)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 04 — HPE-AFF Test Suite | EU Declaration of Conformity")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 110
    for label, fid, fy in top_fields:
        add_acroform_field(writer, fid, "/Tx", [190, fy - 2, 540, fy + 14])
    y2a = y0 - 238
    for i, (label, fid) in enumerate(directives):
        ry = y2a - i * 20
        add_acroform_field(writer, fid, "/Btn", [55, ry - 10, 65, ry])
    y3a = y2a - len(directives) * 20 - 20
    add_acroform_field(writer, "notified_body",    "/Tx", [210, y3a - 2,  540, y3a + 14])
    add_acroform_field(writer, "nb_cert_no",       "/Tx", [175, y3a - 32, 375, y3a - 16])
    add_acroform_field(writer, "place_date",       "/Tx", [135, y3a - 67, 315, y3a - 51])
    add_acroform_field(writer, "signature",        "/Tx", [415, y3a - 67, 540, y3a - 51])
    add_acroform_field(writer, "signatory_name",   "/Tx", [210, y3a - 97, 540, y3a - 81])

    with open(f"{OUT}/form_04_compliance_doc.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_04_compliance_doc.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 5: Invoice / Billing
# ─────────────────────────────────────────────────────────────────
def form_05_invoice():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "INVOICE", "Form 05 — Line items + totals + payment terms")

    y = H - 100
    # Seller block
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, y, "FROM (Seller)")
    for label, fid, fy in [
        ("Company", "seller_company", y - 18),
        ("Address",  "seller_address",y - 36),
        ("VAT ID",   "seller_vat",    y - 54),
        ("Email",    "seller_email",  y - 72),
    ]:
        draw_label(c, label + ":", 50, fy + 2, size=8)
        draw_field_box(c, 105, fy - 2, 165, 14)

    # Buyer block
    c.setFont("Helvetica-Bold", 9)
    c.drawString(310, y, "TO (Buyer)")
    for label, fid, fy in [
        ("Company", "buyer_company", y - 18),
        ("Address",  "buyer_address",y - 36),
        ("VAT ID",   "buyer_vat",    y - 54),
        ("PO Ref.",  "buyer_po",     y - 72),
    ]:
        draw_label(c, label + ":", 310, fy + 2, size=8)
        draw_field_box(c, 360, fy - 2, 175, 14)

    # Invoice meta
    y2 = y - 100
    for label, fid, x1, x2 in [
        ("Invoice No.",   "invoice_no",   50, 140),
        ("Invoice Date",  "invoice_date", 50, 140),
        ("Due Date",      "due_date",     310, 400),
        ("Payment Terms", "payment_terms",310, 400),
    ]:
        row_y = y2 if "Invoice No" in label or "Due Date" in label else y2 - 24
        draw_label(c, label + ":", x1, row_y + 2, size=8)
        draw_field_box(c, x2, row_y - 2, 140, 14)

    # Line items table
    y3 = y2 - 55
    cx = [50, 180, 340, 390, 445, 500]
    cw = [125, 155, 45, 50, 50, 45]
    hdr = ["Description", "Notes", "Qty", "Unit Price", "VAT %", "Total"]
    c.setFont("Helvetica-Bold", 8)
    for i, h in enumerate(hdr):
        c.rect(cx[i], y3 - 14, cw[i], 16)
        c.drawString(cx[i] + 2, y3 - 6, h)

    for row in range(6):
        ry = y3 - 14 - (row + 1) * 18
        for ci in range(6):
            c.rect(cx[ci], ry, cw[ci], 18)

    # Totals
    y4 = y3 - 14 - 7 * 18 - 10
    for label, fid, tx, fx in [
        ("Subtotal",      "subtotal",    380, 455),
        ("VAT Amount",    "vat_amount",  380, 455),
        ("Total Due",     "total_due",   380, 455),
    ]:
        draw_label(c, label + ":", tx, y4 + 2, bold=True, size=9)
        draw_field_box(c, fx, y4 - 2, 85, 14)
        y4 -= 22

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 05 — HPE-AFF Test Suite | Invoice")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 100
    for label, fid, fy in [
        ("Company", "seller_company", y0 - 18),
        ("Address",  "seller_address",y0 - 36),
        ("VAT ID",   "seller_vat",    y0 - 54),
        ("Email",    "seller_email",  y0 - 72),
    ]:
        add_acroform_field(writer, fid, "/Tx", [105, fy - 2, 270, fy + 12], font_size=8)
    for label, fid, fy in [
        ("Company", "buyer_company", y0 - 18),
        ("Address",  "buyer_address",y0 - 36),
        ("VAT ID",   "buyer_vat",    y0 - 54),
        ("PO Ref.",  "buyer_po",     y0 - 72),
    ]:
        add_acroform_field(writer, fid, "/Tx", [360, fy - 2, 535, fy + 12], font_size=8)
    y2a = y0 - 100
    add_acroform_field(writer, "invoice_no",   "/Tx", [140, y2a - 2, 280, y2a + 12], font_size=8)
    add_acroform_field(writer, "invoice_date", "/Tx", [140, y2a - 26, 280, y2a - 12], font_size=8)
    add_acroform_field(writer, "due_date",     "/Tx", [400, y2a - 2, 540, y2a + 12], font_size=8)
    add_acroform_field(writer, "payment_terms","/Tx", [400, y2a - 26, 540, y2a - 12], font_size=8)
    y3a = y2a - 55
    for row in range(6):
        ry = y3a - 14 - (row + 1) * 18
        for ci, col in enumerate(["desc", "notes", "qty", "unit_price", "vat_pct", "total"]):
            add_acroform_field(writer, f"item{row+1}_{col}", "/Tx",
                               [cx[ci], ry, cx[ci] + cw[ci], ry + 18], font_size=7)
    y4a = y3a - 14 - 7 * 18 - 10
    for fid in ["subtotal", "vat_amount", "total_due"]:
        add_acroform_field(writer, fid, "/Tx", [455, y4a - 2, 540, y4a + 12], font_size=9)
        y4a -= 22

    with open(f"{OUT}/form_05_invoice.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_05_invoice.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 6: HR / Job Application
# ─────────────────────────────────────────────────────────────────
def form_06_job_application():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "Job Application Form", "Form 06 — HR | multi-section, dropdown, textarea")

    y = H - 110
    personal = [
        ("Surname",       "surname",    y),
        ("First Name",    "first_name", y - 28),
        ("Date of Birth", "dob",        y - 56),
        ("Nationality",   "nationality",y - 84),
        ("Email Address", "email",      y - 112),
        ("Phone",         "phone",      y - 140),
        ("LinkedIn URL",  "linkedin",   y - 168),
    ]
    for label, fid, fy in personal:
        draw_label(c, label + ":", 50, fy + 2, size=9)
        draw_field_box(c, 160, fy - 2, 375, 16)

    y2 = y - 210
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "POSITION APPLIED FOR")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    y2 -= 20
    draw_label(c, "Role Title:", 50, y2 + 2)
    draw_field_box(c, 130, y2 - 2, 200, 16)
    draw_label(c, "Department:", 355, y2 + 2)
    draw_field_box(c, 430, y2 - 2, 110, 16)
    draw_label(c, "Employment Type:", 50, y2 - 30 + 2)
    for i, opt in enumerate(["Full-time", "Part-time", "Contract", "Internship"]):
        draw_checkbox_with_label(c, 165 + i * 95, y2 - 30, opt)
    draw_label(c, "Available From:", 50, y2 - 60 + 2)
    draw_field_box(c, 145, y2 - 62, 120, 16)
    draw_label(c, "Salary Expectation (€):", 300, y2 - 60 + 2)
    draw_field_box(c, 440, y2 - 62, 100, 16)

    y3 = y2 - 90
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y3, "COVER NOTE")
    c.line(50, y3 - 3, W - 50, y3 - 3)
    y3 -= 8
    draw_field_box(c, 50, y3 - 80, W - 100, 80)  # textarea

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 06 — HPE-AFF Test Suite | Job Application")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 110
    for label, fid, fy in personal:
        add_acroform_field(writer, fid, "/Tx", [160, fy - 2, 535, fy + 14])
    y2a = y0 - 230
    add_acroform_field(writer, "role_title",   "/Tx", [130, y2a - 2, 330, y2a + 14])
    add_acroform_field(writer, "department",   "/Tx", [430, y2a - 2, 540, y2a + 14])
    for i, typ in enumerate(["fulltime", "parttime", "contract", "internship"]):
        add_acroform_field(writer, f"emp_{typ}", "/Btn", [165 + i*95, y2a - 30, 175 + i*95, y2a - 20])
    add_acroform_field(writer, "available_from",    "/Tx", [145, y2a - 62, 265, y2a - 46])
    add_acroform_field(writer, "salary_expectation","/Tx", [440, y2a - 62, 540, y2a - 46])
    y3a = y2a - 98
    add_acroform_field(writer, "cover_note", "/Tx", [50, y3a - 80, W - 50, y3a - 8], multiline=True)

    with open(f"{OUT}/form_06_job_application.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_06_job_application.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 7: Medical Patient Intake
# ─────────────────────────────────────────────────────────────────
def form_07_patient_intake():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "Patient Intake Form", "Form 07 — Medical | boolean flags, dropdowns, allergy list")

    y = H - 110
    for label, fid, fy in [
        ("Patient Full Name",   "patient_name",   y),
        ("Date of Birth",       "dob",            y - 28),
        ("NHS / Patient ID",    "patient_id",     y - 56),
        ("GP / Referring Doctor","gp_name",        y - 84),
        ("Emergency Contact",   "emergency_name", y - 112),
        ("Emergency Phone",     "emergency_phone",y - 140),
    ]:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 185, fy - 2, 350, 16)

    draw_label(c, "Blood Type:", 50, y - 170 + 2)
    for i, bt in enumerate(["A+", "A−", "B+", "B−", "AB+", "AB−", "O+", "O−", "Unknown"]):
        draw_checkbox_with_label(c, 130 + i * 48, y - 170, bt, size=8)

    y2 = y - 205
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "CURRENT MEDICATIONS")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    for r in range(4):
        ry = y2 - 20 - r * 22
        draw_label(c, f"Med {r+1}:", 50, ry + 2, size=8)
        draw_field_box(c, 90, ry - 2, 180, 16)
        draw_label(c, "Dose:", 280, ry + 2, size=8)
        draw_field_box(c, 308, ry - 2, 80, 16)
        draw_label(c, "Frequency:", 400, ry + 2, size=8)
        draw_field_box(c, 455, ry - 2, 85, 16)

    y3 = y2 - 115
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y3, "KNOWN ALLERGIES / CONTRAINDICATIONS")
    c.line(50, y3 - 3, W - 50, y3 - 3)
    draw_field_box(c, 50, y3 - 55, W - 100, 48)

    y4 = y3 - 75
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y4, "CONSENT")
    c.line(50, y4 - 3, W - 50, y4 - 3)
    consents = [
        ("I consent to examination and treatment",    "consent_treatment"),
        ("I consent to data sharing with GP",         "consent_data_gp"),
        ("I consent to anonymous research use",       "consent_research"),
    ]
    for i, (label, fid) in enumerate(consents):
        draw_checkbox_with_label(c, 55, y4 - 20 - i * 20, label)

    draw_label(c, "Patient Signature:", 50, y4 - 85 + 2)
    draw_field_box(c, 165, y4 - 87, 160, 16)
    draw_label(c, "Date:", 350, y4 - 85 + 2)
    draw_field_box(c, 380, y4 - 87, 100, 16)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 07 — HPE-AFF Test Suite | Patient Intake")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 110
    for label, fid, fy in [
        ("Patient Full Name", "patient_name", y0),
        ("Date of Birth", "dob", y0 - 28),
        ("NHS / Patient ID", "patient_id", y0 - 56),
        ("GP / Referring Doctor", "gp_name", y0 - 84),
        ("Emergency Contact", "emergency_name", y0 - 112),
        ("Emergency Phone", "emergency_phone", y0 - 140),
    ]:
        add_acroform_field(writer, fid, "/Tx", [185, fy - 2, 535, fy + 14])
    for i, bt in enumerate(["apos", "aneg", "bpos", "bneg", "abpos", "abneg", "opos", "oneg", "unknown"]):
        add_acroform_field(writer, f"blood_{bt}", "/Btn", [130 + i*48, y0 - 170, 140 + i*48, y0 - 160])
    y2a = y0 - 223
    for r, med_n in enumerate(["med1", "med2", "med3", "med4"]):
        ry = y2a - r * 22
        add_acroform_field(writer, f"{med_n}_name", "/Tx", [90, ry - 2, 270, ry + 12], font_size=8)
        add_acroform_field(writer, f"{med_n}_dose", "/Tx", [308, ry - 2, 388, ry + 12], font_size=8)
        add_acroform_field(writer, f"{med_n}_freq", "/Tx", [455, ry - 2, 540, ry + 12], font_size=8)
    y3a = y2a - 115
    add_acroform_field(writer, "allergies", "/Tx", [50, y3a - 55, W - 50, y3a - 10], multiline=True)
    y4a = y3a - 75
    for i, (label, fid) in enumerate(consents):
        add_acroform_field(writer, fid, "/Btn", [55, y4a - 20 - i*20, 65, y4a - 10 - i*20])
    add_acroform_field(writer, "patient_signature", "/Tx", [165, y4a - 87, 325, y4a - 71])
    add_acroform_field(writer, "signature_date",    "/Tx", [380, y4a - 87, 480, y4a - 71])

    with open(f"{OUT}/form_07_patient_intake.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_07_patient_intake.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 8: Travel / Expense Report (multi-row, currency transform)
# ─────────────────────────────────────────────────────────────────
def form_08_expense_report():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "Expense Report", "Form 08 — Travel & expenses | date transforms, per-row currency")

    y = H - 110
    for label, fid, fy in [
        ("Employee Name",    "employee_name",    y),
        ("Employee ID",      "employee_id",      y - 28),
        ("Department",       "department",       y - 56),
        ("Cost Centre",      "cost_centre",      y - 84),
        ("Report Period",    "report_period",    y - 112),
        ("Manager Approval", "manager_name",     y - 140),
    ]:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 175, fy - 2, 355, 16)

    y2 = y - 178
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "EXPENSE ITEMS")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    y2 -= 16

    ecx  = [50, 112, 232, 300, 370, 435, 490]
    ecw  = [58, 115, 63, 65, 60, 50, 50]
    ehdr = ["Date", "Description", "Category", "Receipted", "Amount", "Currency", "EUR Equiv."]
    c.setFont("Helvetica-Bold", 7)
    for i, h in enumerate(ehdr):
        c.rect(ecx[i], y2 - 14, ecw[i], 16)
        c.drawString(ecx[i] + 2, y2 - 6, h)

    for row in range(8):
        ry = y2 - 14 - (row + 1) * 18
        for ci in range(7):
            c.rect(ecx[ci], ry, ecw[ci], 18)

    y3 = y2 - 14 - 9 * 18 - 10
    draw_label(c, "Total (EUR):", 380, y3 + 2, bold=True)
    draw_field_box(c, 450, y3 - 2, 90, 16)
    draw_label(c, "Notes / Justification:", 50, y3 - 30 + 2)
    draw_field_box(c, 185, y3 - 32, 350, 40)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 08 — HPE-AFF Test Suite | Expense Report")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 110
    for label, fid, fy in [
        ("Employee Name", "employee_name", y0),
        ("Employee ID", "employee_id", y0 - 28),
        ("Department", "department", y0 - 56),
        ("Cost Centre", "cost_centre", y0 - 84),
        ("Report Period", "report_period", y0 - 112),
        ("Manager Approval", "manager_name", y0 - 140),
    ]:
        add_acroform_field(writer, fid, "/Tx", [175, fy - 2, 530, fy + 14])
    y2a = y0 - 194
    for row in range(8):
        ry = y2a - (row + 1) * 18
        for ci, cn in enumerate(["date", "desc", "cat", "receipted", "amount", "currency", "eur_equiv"]):
            add_acroform_field(writer, f"exp{row+1}_{cn}", "/Tx",
                               [ecx[ci], ry, ecx[ci] + ecw[ci], ry + 18], font_size=7)
    y3a = y2a - 9 * 18 - 10
    add_acroform_field(writer, "total_eur", "/Tx", [450, y3a - 2, 540, y3a + 14])
    add_acroform_field(writer, "notes", "/Tx", [185, y3a - 32, 535, y3a + 8], multiline=True)

    with open(f"{OUT}/form_08_expense_report.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_08_expense_report.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 9: GDPR / Data Subject Request (complex logic tree)
# ─────────────────────────────────────────────────────────────────
def form_09_gdpr_dsr():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_form_header(c, "Data Subject Request Form", "Form 09 — GDPR | conditional fields, request type routing")

    y = H - 110
    for label, fid, fy in [
        ("Full Name",        "full_name",   y),
        ("Email Address",    "email",       y - 28),
        ("Phone",            "phone",       y - 56),
        ("Account / Ref. No","account_ref", y - 84),
        ("Relationship to Data Controller", "relationship", y - 112),
    ]:
        draw_label(c, label + ":", 50, fy + 2)
        draw_field_box(c, 230, fy - 2, 305, 16)

    y2 = y - 150
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "TYPE OF REQUEST (select one)")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    requests = [
        ("Right of Access (Art. 15)",          "req_access"),
        ("Right to Rectification (Art. 16)",   "req_rectification"),
        ("Right to Erasure (Art. 17)",          "req_erasure"),
        ("Right to Restriction (Art. 18)",     "req_restriction"),
        ("Right to Data Portability (Art. 20)","req_portability"),
        ("Right to Object (Art. 21)",           "req_object"),
    ]
    for i, (label, fid) in enumerate(requests):
        draw_checkbox_with_label(c, 55, y2 - 20 - i * 20, label)

    y3 = y2 - len(requests) * 20 - 35
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y3, "DETAILS OF REQUEST")
    c.line(50, y3 - 3, W - 50, y3 - 3)
    y3 -= 8
    draw_field_box(c, 50, y3 - 70, W - 100, 65)

    y4 = y3 - 90
    draw_label(c, "Preferred response format:", 50, y4 + 2)
    for i, opt in enumerate(["PDF", "CSV", "Email summary", "Post"]):
        draw_checkbox_with_label(c, 220 + i * 85, y4, opt)

    draw_label(c, "Identity Verification attached:", 50, y4 - 28 + 2)
    for i, opt in enumerate(["Passport copy", "National ID", "Utility bill"]):
        draw_checkbox_with_label(c, 230 + i * 115, y4 - 28, opt)

    draw_label(c, "Signature:", 50, y4 - 60 + 2)
    draw_field_box(c, 120, y4 - 62, 180, 16)
    draw_label(c, "Date:", 330, y4 - 60 + 2)
    draw_field_box(c, 358, y4 - 62, 120, 16)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 09 — HPE-AFF Test Suite | GDPR Data Subject Request")
    c.save()

    writer = save_canvas_to_writer(buf)
    y0 = H - 110
    for label, fid, fy in [
        ("Full Name", "full_name", y0),
        ("Email Address", "email", y0 - 28),
        ("Phone", "phone", y0 - 56),
        ("Account / Ref. No", "account_ref", y0 - 84),
        ("Relationship to Data Controller", "relationship", y0 - 112),
    ]:
        add_acroform_field(writer, fid, "/Tx", [230, fy - 2, 535, fy + 14])
    y2a = y0 - 168
    for i, (label, fid) in enumerate(requests):
        add_acroform_field(writer, fid, "/Btn", [55, y2a - 20 - i*20, 65, y2a - 10 - i*20])
    y3a = y2a - len(requests) * 20 - 43
    add_acroform_field(writer, "request_details", "/Tx", [50, y3a - 70, W - 50, y3a - 10], multiline=True)
    y4a = y3a - 90
    for i, opt in enumerate(["pdf", "csv", "email", "post"]):
        add_acroform_field(writer, f"fmt_{opt}", "/Btn", [220 + i*85, y4a, 230 + i*85, y4a + 10])
    for i, opt in enumerate(["passport", "national_id", "utility_bill"]):
        add_acroform_field(writer, f"id_{opt}", "/Btn", [230 + i*115, y4a - 28, 240 + i*115, y4a - 18])
    add_acroform_field(writer, "signature", "/Tx", [120, y4a - 62, 300, y4a - 46])
    add_acroform_field(writer, "date",      "/Tx", [358, y4a - 62, 478, y4a - 46])

    with open(f"{OUT}/form_09_gdpr_dsr.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_09_gdpr_dsr.pdf")


# ─────────────────────────────────────────────────────────────────
# FORM 10: Multi-page Certificate of Origin
# ─────────────────────────────────────────────────────────────────
def form_10_certificate_of_origin():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # PAGE 1
    draw_form_header(c, "Certificate of Origin", "Form 10 — Trade / Export | multi-page, HS codes, transport")

    y = H - 110
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "EXPORTER / SELLER")
    c.line(50, y - 3, W - 50, y - 3)
    y -= 16
    for label, fid, fy in [
        ("Company Name",   "exp_company", y),
        ("Street Address", "exp_street",  y - 26),
        ("City / Postcode","exp_city",    y - 52),
        ("Country",        "exp_country", y - 78),
        ("EORI / Tax No.", "exp_eori",    y - 104),
    ]:
        draw_label(c, label + ":", 50, fy + 2, size=9)
        draw_field_box(c, 160, fy - 2, 375, 16)

    y2 = y - 140
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "CONSIGNEE / BUYER")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    y2 -= 16
    for label, fid, fy in [
        ("Company Name",   "con_company", y2),
        ("Street Address", "con_street",  y2 - 26),
        ("City / Postcode","con_city",    y2 - 52),
        ("Country",        "con_country", y2 - 78),
    ]:
        draw_label(c, label + ":", 50, fy + 2, size=9)
        draw_field_box(c, 160, fy - 2, 375, 16)

    y3 = y2 - 115
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y3, "TRANSPORT DETAILS")
    c.line(50, y3 - 3, W - 50, y3 - 3)
    y3 -= 16
    for label, fid, fy in [
        ("Vessel / Flight No.",  "transport_vessel", y3),
        ("Port of Loading",      "port_loading",     y3 - 26),
        ("Port of Discharge",    "port_discharge",   y3 - 52),
        ("Country of Destination","dest_country",    y3 - 78),
        ("Incoterms",            "incoterms",        y3 - 104),
    ]:
        draw_label(c, label + ":", 50, fy + 2, size=9)
        draw_field_box(c, 175, fy - 2, 360, 16)

    draw_label(c, "Transport Mode:", 50, y3 - 130 + 2)
    for i, mode in enumerate(["Sea", "Air", "Road", "Rail", "Courier"]):
        draw_checkbox_with_label(c, 155 + i * 80, y3 - 130, mode)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 10 — HPE-AFF Test Suite | Certificate of Origin  •  Page 1 of 2")
    c.showPage()

    # PAGE 2 — goods table + declaration
    draw_form_header(c, "Certificate of Origin — Goods & Declaration", "Form 10 continued — HS codes, quantities, declaration")

    y = H - 110
    gcx = [50, 150, 280, 355, 415, 475]
    gcw = [95, 125, 70, 55, 55, 65]
    ghdr = ["Description", "HS Code", "Quantity", "Net Wt (kg)", "Gross Wt", "Invoice Val."]
    c.setFont("Helvetica-Bold", 8)
    for i, h in enumerate(ghdr):
        c.rect(gcx[i], y - 14, gcw[i], 16)
        c.drawString(gcx[i] + 2, y - 6, h)

    for row in range(7):
        ry = y - 14 - (row + 1) * 20
        for ci in range(6):
            c.rect(gcx[ci], ry, gcw[ci], 20)

    y2 = y - 14 - 8 * 20 - 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y2, "DECLARATION")
    c.line(50, y2 - 3, W - 50, y2 - 3)
    y2 -= 8
    c.setFont("Helvetica", 8)
    decl_text = ("The undersigned hereby declares that the above details and statements are correct, "
                 "that all the goods were produced in the country shown, and that they comply with "
                 "the origin requirements for the preferential tariff treatment.")
    c.drawString(50, y2 - 12, decl_text[:90])
    c.drawString(50, y2 - 24, decl_text[90:])
    draw_label(c, "Place & Date:", 50, y2 - 50 + 2)
    draw_field_box(c, 140, y2 - 52, 160, 16)
    draw_label(c, "Authorised Signature:", 330, y2 - 50 + 2)
    draw_field_box(c, 455, y2 - 52, 85, 16)
    draw_label(c, "Name & Title:", 50, y2 - 78 + 2)
    draw_field_box(c, 135, y2 - 80, 200, 16)
    draw_label(c, "Chamber Stamp / Seal:", 360, y2 - 78 + 2)
    draw_field_box(c, 455, y2 - 80, 85, 36)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Form 10 — HPE-AFF Test Suite | Certificate of Origin  •  Page 2 of 2")
    c.save()

    writer = save_canvas_to_writer(buf)

    # Page 1 fields
    y0 = H - 126
    for label, fid, fy in [
        ("Company Name", "exp_company", y0),
        ("Street Address","exp_street",  y0 - 26),
        ("City / Postcode","exp_city",   y0 - 52),
        ("Country",       "exp_country", y0 - 78),
        ("EORI / Tax No.","exp_eori",    y0 - 104),
    ]:
        add_acroform_field(writer, fid, "/Tx", [160, fy - 2, 535, fy + 14])
    y2a = y0 - 156
    for label, fid, fy in [
        ("Company Name",  "con_company", y2a),
        ("Street Address","con_street",  y2a - 26),
        ("City / Postcode","con_city",   y2a - 52),
        ("Country",       "con_country", y2a - 78),
    ]:
        add_acroform_field(writer, fid, "/Tx", [160, fy - 2, 535, fy + 14])
    y3a = y2a - 131
    for label, fid, fy in [
        ("Vessel / Flight No.", "transport_vessel", y3a),
        ("Port of Loading",     "port_loading",     y3a - 26),
        ("Port of Discharge",   "port_discharge",   y3a - 52),
        ("Country of Destination","dest_country",   y3a - 78),
        ("Incoterms",           "incoterms",        y3a - 104),
    ]:
        add_acroform_field(writer, fid, "/Tx", [175, fy - 2, 535, fy + 14])
    for i, mode in enumerate(["sea","air","road","rail","courier"]):
        add_acroform_field(writer, f"mode_{mode}", "/Btn",
                           [155 + i*80, y3a - 130, 165 + i*80, y3a - 120])

    # Page 2 fields (page_idx=1)
    y_p2 = H - 110
    for row in range(7):
        ry = y_p2 - 14 - (row + 1) * 20
        for ci, cn in enumerate(["desc","hs_code","qty","net_wt","gross_wt","invoice_val"]):
            add_acroform_field(writer, f"good{row+1}_{cn}", "/Tx",
                               [gcx[ci], ry, gcx[ci] + gcw[ci], ry + 20],
                               page_idx=1, font_size=8)
    y2b = y_p2 - 14 - 8*20 - 23
    add_acroform_field(writer, "decl_place_date",  "/Tx", [140, y2b - 52, 300, y2b - 36], page_idx=1)
    add_acroform_field(writer, "auth_signature",   "/Tx", [455, y2b - 52, 540, y2b - 36], page_idx=1)
    add_acroform_field(writer, "signatory_name",   "/Tx", [135, y2b - 80, 335, y2b - 64], page_idx=1)

    with open(f"{OUT}/form_10_certificate_of_origin.pdf", "wb") as f:
        writer.write(f)
    print("✓ form_10_certificate_of_origin.pdf")


if __name__ == "__main__":
    print("Generating HPE-AFF test forms...\n")
    form_01_personal()
    form_02_supplier()
    form_03_product_sheet()
    form_04_compliance()
    form_05_invoice()
    form_06_job_application()
    form_07_patient_intake()
    form_08_expense_report()
    form_09_gdpr_dsr()
    form_10_certificate_of_origin()
    print(f"\n✅ All 10 forms written to {OUT}/")
