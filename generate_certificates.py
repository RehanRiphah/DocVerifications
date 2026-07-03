import pandas as pd
import os
import uuid
import json
import base64
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO
import qrcode
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

load_dotenv()

# ========================= CONFIG =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Stronger key for inserts

if not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_SERVICE_ROLE_KEY not found in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

PRIVATE_KEY_PATH = "issuer_private_key.pem"
PUBLIC_KEY_PATH = "issuer_public_key.pem"
PROGRAM_NAME = "Research Internship Program in Science (RIPS)"
ISSUER = "Your Organization / University Name"
TABLE_NAME = "certificates"

def load_or_generate_keys():
    if os.path.exists(PRIVATE_KEY_PATH):
        with open(PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        with open(PUBLIC_KEY_PATH, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())
        return private_key, public_key
    
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    
    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    return private_key, public_key

def sign_data(data_dict, private_key):
    data_json = json.dumps(data_dict, sort_keys=True).encode('utf-8')
    signature = private_key.sign(data_json, ec.ECDSA(hashes.SHA256()))
    return base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')

def generate_qr_url(cert_data, signature, base_url="https://your-app.streamlit.app"):
    payload = {"d": cert_data, "s": signature}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{base_url}/verify?payload={encoded}"

def save_to_supabase(cert_data):
    try:
        response = supabase.table(TABLE_NAME).insert({
            "cert_id": cert_data["id"],
            "name": cert_data["name"],
            "program": cert_data["program"],
            "issuer": cert_data["issuer"],
            "issued_at": cert_data["issued_at"],
            "is_valid": True,
            "revoked_at": None
        }).execute()
        print(f"✅ Saved to Supabase: {cert_data['id']}")
        return True
    except Exception as e:
        print(f"❌ Supabase insert failed: {e}")
        return False

def generate_certificates(csv_path, template_path, output_dir, 
                          name_center_x, name_center_y,
                          program_center_x, program_center_y,
                          date_center_x, date_center_y,
                          id_center_x, id_center_y,
                          max_width=400, initial_font_size=40, min_font_size=12):
    
    private_key, _ = load_or_generate_keys()
    df = pd.read_csv(csv_path)
    os.makedirs(output_dir, exist_ok=True)
    
    for _, row in df.iterrows():
        name = str(row['Names of faculty member/s']).strip()
        cert_id = str(uuid.uuid4())[:8].upper()
        issue_date = datetime.now().strftime("%B %d, %Y")
        
        cert_data = {
            "id": cert_id,
            "name": name,
            "program": PROGRAM_NAME,
            "issuer": ISSUER,
            "issued_at": issue_date,
            "version": "1.0"
        }
        
        # Save to database first
        if not save_to_supabase(cert_data):
            print(f"⚠️ Skipping PDF generation for {name} due to DB error")
            continue
        
        signature = sign_data(cert_data, private_key)
        qr_url = generate_qr_url(cert_data, signature)
        
        # PDF Generation
        packet = BytesIO()
        template_reader = PdfReader(open(template_path, 'rb'))
        page_width = float(template_reader.pages[0].mediabox.width)
        page_height = float(template_reader.pages[0].mediabox.height)
        
        c = canvas.Canvas(packet, pagesize=(page_width, page_height))
        
        def draw_text(x, y, text, size, font='Helvetica'):
            c.setFont(font, size)
            c.drawCentredString(x, y, text)
        
        # Name (auto-fit)
        font_size = initial_font_size
        while stringWidth(name, 'Helvetica', font_size) > max_width and font_size > min_font_size:
            font_size -= 1
        draw_text(name_center_x, name_center_y, name, font_size)
        
        # Other fields
        draw_text(program_center_x, program_center_y, PROGRAM_NAME, 24)
        draw_text(date_center_x, date_center_y, f"Date: {issue_date}", 18)
        draw_text(id_center_x, id_center_y, f"ID: {cert_id}", 16)
        
        # QR Code
        qr = qrcode.QRCode(version=2, box_size=4, border=2)
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        c.drawImage(ImageReader(qr_buffer), 50, 50, width=120, height=120)
        
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
    generate_certificates(
        csv_path='RIPS_FPS_Remaining.csv',
        template_path='Attendance.pdf',
        output_dir='certificates_output',
        name_center_x=780, name_center_y=530,
        program_center_x=780, program_center_y=620,
        date_center_x=780, date_center_y=400,
        id_center_x=780, id_center_y=380,
        max_width=420,
        initial_font_size=40,
        min_font_size=12
    )