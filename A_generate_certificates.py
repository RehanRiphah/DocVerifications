import argparse
import json
import os
import uuid
import base64
from datetime import datetime
from io import BytesIO
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pandas as pd
from dotenv import load_dotenv
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
import qrcode
from supabase import create_client, Client
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

load_dotenv()

DEFAULT_CONFIG_FILE = "certificate_config.toml"

DEFAULT_PRIVATE_KEY_PATH = "issuer_private_key.pem"
DEFAULT_PUBLIC_KEY_PATH = "issuer_public_key.pem"
DEFAULT_TABLE_NAME = "certificates"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Stronger key for inserts

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def load_config(config_path: str = DEFAULT_CONFIG_FILE):
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("rb") as f:
        return tomllib.load(f)


def load_or_generate_keys(private_key_path: str, public_key_path: str):
    if os.path.exists(private_key_path):
        with open(private_key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        with open(public_key_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())
        return private_key, public_key
    
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    
    with open(private_key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(public_key_path, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    return private_key, public_key

def sign_data(data_dict, private_key):
    data_json = json.dumps(data_dict, sort_keys=True).encode('utf-8')
    signature = private_key.sign(data_json, ec.ECDSA(hashes.SHA256()))
    return base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')

def generate_qr_url(cert_data, signature, base_url="https://docverifications.streamlit.app", qr_mode="cert_id"):
    if qr_mode == "payload":
        payload = {"d": cert_data, "s": signature}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode('utf-8').rstrip('=')
        return f"{base_url.rstrip('/')}/?payload={encoded}"
    return f"{base_url.rstrip('/')}/?cert_id={cert_data['id']}"

def save_to_supabase(cert_data, table_name: str):
    row = {
        "cert_id": cert_data["id"],
        "name": cert_data["name"],
        "program": cert_data["program"],
        "issuer": cert_data["issuer"],
        "issued_at": cert_data["issued_at"],
        "is_valid": True,
        "revoked_at": None,
    }

    optional_fields = [
        "facilitators",
        "facilitator_name",
        "facilitator_email",
        "facilitator_contact",
        "office_contact",
    ]
    for field in optional_fields:
        if cert_data.get(field):
            row[field] = cert_data[field]

    try:
        response = supabase.table(table_name).insert(row).execute()
        print(f"✅ Saved to Supabase: {cert_data['id']}")
        return True
    except Exception as e:
        print(f"❌ Supabase insert failed: {e}")
        return False

def generate_certificates(config: dict):
    paths = config.get("paths", {})
    layout = config.get("layout", {})
    workshop = config.get("workshop", {})
    facilitator = config.get("facilitator", {})
    keys = config.get("keys", {})
    supabase_config = config.get("supabase", {})

    csv_path = paths.get("csv_path")
    template_path = paths.get("template_path")
    output_dir = paths.get("output_dir")
    name_column = paths.get("name_column", "Names of faculty member/s")
    if not csv_path or not template_path or not output_dir:
        raise ValueError("Missing paths configuration: csv_path, template_path, and output_dir are required.")

    name_center_x = layout.get("name_center_x")
    name_center_y = layout.get("name_center_y")
    program_center_x = layout.get("program_center_x")
    program_center_y = layout.get("program_center_y")
    date_center_x = layout.get("date_center_x")
    date_center_y = layout.get("date_center_y")
    id_center_x = layout.get("id_center_x")
    id_center_y = layout.get("id_center_y")
    time_center_x = layout.get("time_center_x")
    time_center_y = layout.get("time_center_y")
    venue_center_x = layout.get("venue_center_x")
    venue_center_y = layout.get("venue_center_y")
    chair_center_x = layout.get("chair_center_x")
    chair_center_y = layout.get("chair_center_y")
    facilitators_center_x = layout.get("facilitators_center_x")
    facilitators_center_y = layout.get("facilitators_center_y")
    facilitators_box_width = layout.get("facilitators_box_width", 300)
    facilitators_line_height = layout.get("facilitators_line_height", 18)
    max_width = layout.get("max_width", 400)
    initial_font_size = layout.get("initial_font_size", 40)
    min_font_size = layout.get("min_font_size", 12)

    program_name = workshop.get("program_name")
    issuer = workshop.get("issuer")
    version = workshop.get("version", "1.0")
    base_url = workshop.get("base_url", "https://docverifications.streamlit.app")
    workshop_date = workshop.get("date")
    time_text = workshop.get("time")
    venue_text = workshop.get("venue")
    chair_text = workshop.get("chair")
    facilitators = workshop.get("facilitators", [])
    facilitators_text = ", ".join(facilitators) if facilitators else None
    table_name = supabase_config.get("table_name", DEFAULT_TABLE_NAME)

    if not program_name or not issuer:
        raise ValueError("Missing workshop configuration: program_name and issuer are required.")

    private_key_path = keys.get("private_key_path", DEFAULT_PRIVATE_KEY_PATH)
    public_key_path = keys.get("public_key_path", DEFAULT_PUBLIC_KEY_PATH)

    private_key, _ = load_or_generate_keys(private_key_path, public_key_path)
    df = pd.read_csv(csv_path)
    os.makedirs(output_dir, exist_ok=True)

    font_dir = Path(__file__).resolve().parent / "fonts"
    cinzel_path = font_dir / "Cinzel-Medium.ttf"
    if cinzel_path.exists():
        pdfmetrics.registerFont(TTFont("Cinzel", str(cinzel_path)))
    else:
        print(f"⚠️ Cinzel font not found at {cinzel_path}. Using default font instead.")

    focal_facilitator = config.get("focal_facilitator", {})
    focal_facilitator_fields = {
        "facilitator_name": focal_facilitator.get("name"),
        "facilitator_email": focal_facilitator.get("email"),
        "facilitator_contact": focal_facilitator.get("contact_number"),
        "office_contact": focal_facilitator.get("office_contact"),
    }

    for _, row in df.iterrows():
        name = str(row.get(name_column, "")).strip()
        if not name:
            print("⚠️ Skipping row with missing name column", name_column)
            continue
        cert_id = str(uuid.uuid4())[:8].upper()
        issue_date = workshop_date #or datetime.now().strftime("%B %d, %Y")
        
        cert_data = {
            "id": cert_id,
            "name": name,
            "program": program_name,
            "issuer": issuer,
            "issued_at": issue_date,
            "version": version,
        }

        if facilitators_text:
            cert_data["facilitators"] = facilitators_text

        for key, value in focal_facilitator_fields.items():
            if value:
                cert_data[key] = value

        signature = sign_data(cert_data, private_key)
        if not save_to_supabase(cert_data, table_name):
            print(f"⚠️ Skipping PDF generation for {name} due to DB error")
            continue

        cert_id_url = generate_qr_url(cert_data, signature, base_url=base_url, qr_mode="cert_id")
        
        # PDF Generation
        packet = BytesIO()
        template_reader = PdfReader(open(template_path, 'rb'))
        page_width = float(template_reader.pages[0].mediabox.width)
        page_height = float(template_reader.pages[0].mediabox.height)
        
        c = canvas.Canvas(packet, pagesize=(page_width, page_height))
        
        def draw_text(x, y, text, size, font='Helvetica', align='center'):
            c.setFont(font, size)
            if align == 'left':
                c.drawString(x, y, text)
            elif align == 'right':
                c.drawRightString(x, y, text)
            else:
                c.drawCentredString(x, y, text)

        def wrap_text(text, max_width, font_name='Helvetica', font_size=16):
            words = text.split(' ')
            lines = []
            current_line = ''
            for word in words:
                candidate = f"{current_line} {word}".strip()
                if stringWidth(candidate, font_name, font_size) <= max_width or not current_line:
                    current_line = candidate
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            return lines

        def draw_qr(canvas_obj, data, x, y, size):
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_buffer = BytesIO()
            qr_img.save(qr_buffer, format='PNG')
            qr_buffer.seek(0)
            canvas_obj.drawImage(ImageReader(qr_buffer), x, y, width=size, height=size, preserveAspectRatio=True, mask='auto')

        # Name (auto-fit)
        font_size = initial_font_size
        while stringWidth(name, 'Helvetica', font_size) > max_width and font_size > min_font_size:
            font_size -= 1
        draw_text(name_center_x, name_center_y, name, font_size)
        
        # Other fields
        draw_text(program_center_x, program_center_y, f'"{program_name}"', 45, font='Cinzel')
        if time_text and time_center_x is not None and time_center_y is not None:
            draw_text(time_center_x, time_center_y, time_text, 20, align='left')
        if venue_text and venue_center_x is not None and venue_center_y is not None:
            draw_text(venue_center_x, venue_center_y, venue_text, 20, align='left')
        if chair_text and chair_center_x is not None and chair_center_y is not None:
            draw_text(chair_center_x, chair_center_y, chair_text, 20, align='left')
        if facilitators_text and facilitators_center_x is not None and facilitators_center_y is not None:
            lines = wrap_text(facilitators_text, facilitators_box_width, font_name='Helvetica', font_size=16)
            for index, line in enumerate(lines):
                draw_text(facilitators_center_x, facilitators_center_y - index * facilitators_line_height, line, 16, align='left')
        draw_text(date_center_x, date_center_y, f"{issue_date}", 20, align='left')
        c.setFillColorRGB(1, 1, 1)
        draw_text(id_center_x, id_center_y, f"ID: {cert_id}", 20)
        c.setFillColorRGB(0, 0, 0)
        
        # QR Code: short cert_id only
        print(f"🔗 Short QR URL: {cert_id_url}")
        draw_qr(c, cert_id_url, 50, 50, 220)
        draw_text(160, 40, "Scan for ID lookup", 10, align='center')
        
        c.save()
        packet.seek(0)
        
        # Merge
        overlay_pdf = PdfReader(packet)
        writer = PdfWriter()
        for i, page in enumerate(template_reader.pages):
            if i == 0:
                page.merge_page(overlay_pdf.pages[0])
            writer.add_page(page)
        
        out_path = os.path.join(output_dir, f"{cert_id}_{name.replace(' ', '_')[:30]}.pdf")
        with open(out_path, 'wb') as f:
            writer.write(f)
        print(f"✅ Generated: {out_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate certificates from a TOML configuration file.")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="Path to the TOML config file")
    args = parser.parse_args()

    config = load_config(args.config)
    generate_certificates(config)