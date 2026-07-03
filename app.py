import streamlit as st
import json
import base64
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

# Load environment variables
load_dotenv()

# ---------- Page Config ----------
st.set_page_config(
    page_title="RIPS Microcredential Verifier",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ---------- Custom CSS for better visuals ----------
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        border-radius: 12px;
        margin-bottom: 2rem;
        color: white;
    }
    .main-header h1 {
        margin: 0;
        font-weight: 700;
        font-size: 2.5rem;
        letter-spacing: 1px;
    }
    .main-header p {
        margin: 0.25rem 0 0;
        opacity: 0.85;
        font-size: 1.1rem;
    }
    .cert-card {
        background: white;
        border-radius: 16px;
        padding: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        border: 1px solid #e8ecf1;
        margin: 1.5rem 0;
        transition: all 0.2s;
    }
    .cert-card .field {
        display: flex;
        justify-content: space-between;
        padding: 0.6rem 0;
        border-bottom: 1px solid #f0f2f6;
    }
    .cert-card .field:last-child {
        border-bottom: none;
    }
    .cert-card .label {
        font-weight: 600;
        color: #4a5568;
        letter-spacing: 0.3px;
    }
    .cert-card .value {
        color: #1a202c;
        font-weight: 500;
        word-break: break-word;
        text-align: right;
    }
    .badge-valid {
        background: #48bb78;
        color: white;
        padding: 0.25rem 0.8rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
        display: inline-block;
    }
    .badge-invalid {
        background: #fc8181;
        color: white;
        padding: 0.25rem 0.8rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
        display: inline-block;
    }
    .badge-revoked {
        background: #ed8936;
        color: white;
        padding: 0.25rem 0.8rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
        display: inline-block;
    }
    .footer {
        text-align: center;
        margin-top: 3rem;
        color: #a0aec0;
        font-size: 0.9rem;
        border-top: 1px solid #edf2f7;
        padding-top: 1.5rem;
    }
    .stButton button {
        width: 100%;
        background: #2a5298;
        color: white;
        font-weight: 600;
        border-radius: 8px;
        padding: 0.6rem;
        border: none;
        transition: background 0.2s;
    }
    .stButton button:hover {
        background: #1e3c72;
        color: white;
    }
    .stTextInput input {
        border-radius: 8px;
        border: 1px solid #cbd5e0;
    }
</style>
""", unsafe_allow_html=True)
# ---------- Header with Logo ----------
# Center the logo above the header
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    try:
        st.image("Logo.png", width=120)  # Adjust the path/width as needed
    except FileNotFoundError:
        st.caption("(Logo not found)")

st.markdown("""
<div class="main-header">
    <h1>🔍 RIPS Microcredential Verifier</h1>
    <p>Verify the authenticity of your digital certificate</p>
</div>
""", unsafe_allow_html=True)

# ---------- Supabase Setup ----------
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("⚠️ Supabase credentials not found. Please set them in secrets or .env.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ---------- Load Public Key ----------
@st.cache_resource
def load_public_key():
    try:
        with open("issuer_public_key.pem", "rb") as f:
            return serialization.load_pem_public_key(f.read())
    except FileNotFoundError:
        st.error("❌ Public key file 'issuer_public_key.pem' not found.")
        st.stop()

public_key = load_public_key()

# ---------- Header ----------
st.markdown("""
<div class="main-header">
    <h1>🔍 RIPS Microcredential Verifier</h1>
    <p>Verify the authenticity of your digital certificate</p>
</div>
""", unsafe_allow_html=True)

# ---------- Input & Verification Logic ----------
# Check for QR payload in URL
payload = st.query_params.get("payload", None)

# Manual input if no payload
if not payload:
    cert_id = st.text_input("Enter Certificate ID", placeholder="e.g., ABC123")
    verify_clicked = st.button("Verify Certificate")
else:
    cert_id = None
    verify_clicked = True  # Auto-verify when QR is scanned

if verify_clicked:
    try:
        # If payload exists, decode it
        if payload:
            # The payload is base64url of {"d": cert_data, "s": signature}
            # We need to add padding if missing
            decoded_bytes = base64.urlsafe_b64decode(payload + '==')
            data = json.loads(decoded_bytes)
            
            cert_data = data.get("d")
            signature_b64 = data.get("s")
            
            if not cert_data or not signature_b64:
                st.error("❌ Invalid payload: missing data or signature.")
                st.stop()
            
            # Decode signature
            signature = base64.urlsafe_b64decode(signature_b64 + '==')
            data_to_verify = json.dumps(cert_data, sort_keys=True).encode('utf-8')
            
            # Verify signature
            sig_valid = False
            try:
                public_key.verify(signature, data_to_verify, ec.ECDSA(hashes.SHA256()))
                sig_valid = True
            except Exception:
                pass
            
            if not sig_valid:
                st.error("❌ **INVALID CERTIFICATE** – Signature verification failed. This certificate has been tampered with.")
                st.stop()
            
            # Get ID from cert_data
            cert_id = cert_data.get("id")
            if not cert_id:
                st.error("❌ Certificate ID not found in data.")
                st.stop()
        
        # If we have cert_id (either from payload or manual input)
        if cert_id:
            # Query Supabase
            response = supabase.table("certificates").select("*").eq("cert_id", cert_id).execute()
            
            if not response.data:
                st.warning("⚠️ Certificate ID not found in the official registry.")
                # Still show the signed data if we have it
                if payload and cert_data:
                    st.info("The cryptographic signature is valid, but this certificate is not registered.")
                    # Show cert data anyway? maybe not.
                st.stop()
            
            record = response.data[0]
            is_valid = record.get("is_valid", False)
            revoked_at = record.get("revoked_at")
            
            # Check status
            if is_valid and not revoked_at:
                st.success("✅ **VALID & AUTHENTIC CERTIFICATE**")
                # Display the certificate data as a beautiful card
                if payload and cert_data:
                    # Use the data from payload (more complete)
                    display_data = cert_data
                else:
                    # Use data from Supabase record
                    display_data = {
                        "id": record.get("cert_id"),
                        "name": record.get("holder_name"),
                        "course": record.get("course"),
                        "issue_date": record.get("issue_date"),
                        "expiry_date": record.get("expiry_date"),
                    }
                
                st.markdown("""
                <div class="cert-card">
                    <h3 style="margin-top:0; color:#2a5298;">📄 Certificate Details</h3>
                    <div style="margin: 1rem 0;">
                        <span class="badge-valid">✅ VALID</span>
                    </div>
                """, unsafe_allow_html=True)
                
                # Display fields
                fields = [
                    ("Certificate ID", display_data.get("id")),
                    ("Holder Name", display_data.get("name")),
                    ("Course / Program", display_data.get("course")),
                    ("Issue Date", display_data.get("issue_date")),
                    ("Expiry Date", display_data.get("expiry_date")),
                ]
                for label, value in fields:
                    if value:
                        st.markdown(f"""
                        <div class="field">
                            <span class="label">{label}</span>
                            <span class="value">{value}</span>
                        </div>
                        """, unsafe_allow_html=True)
                
                # Show signature verification badge
                if payload:
                    st.markdown("""
                    <div style="margin-top:1rem; padding:0.5rem; background:#f0fff4; border-radius:8px; border-left:4px solid #48bb78;">
                        <span style="color:#276749;">🔒 Digitally signed and verified using ECDSA</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("</div>", unsafe_allow_html=True)
                st.balloons()
            
            elif revoked_at:
                st.error("❌ **CERTIFICATE REVOKED**")
                st.markdown(f"""
                <div class="cert-card" style="border-color:#fc8181;">
                    <p>This certificate was revoked on <strong>{revoked_at}</strong>.</p>
                    <p>Please contact the issuing authority for further information.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("⚠️ **CERTIFICATE INVALID** – The certificate is marked as invalid.")
        else:
            st.info("Please enter a Certificate ID or scan a QR code.")
    
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        # In production, you might want to log the full error.

# ---------- Footer ----------
st.markdown("""
<div class="footer">
    🔒 Secure verification using ECDSA signatures + Supabase • Issued by RIPS
</div>
""", unsafe_allow_html=True)