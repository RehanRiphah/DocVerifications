import streamlit as st
import json
import base64
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

load_dotenv()

st.set_page_config(page_title="Certificate Verifier", layout="centered")

# Use anon key for verifier (safer)
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

@st.cache_resource
def load_public_key():
    with open("issuer_public_key.pem", "rb") as f:
        return serialization.load_pem_public_key(f.read())

public_key = load_public_key()

st.title("🔍 Official Certificate Verifier")
st.write("Scan the QR code on your certificate")

payload = st.text_input("Verification Payload", "")

if st.button("Verify") or payload:
    try:
        if "payload" in st.query_params:
            payload = st.query_params["payload"]
        
        if payload:
            decoded_bytes = base64.urlsafe_b64decode(payload + '==')
            data = json.loads(decoded_bytes)
            
            cert_data = data.get("d")
            signature_b64 = data.get("s")
            
            # Signature check
            signature = base64.urlsafe_b64decode(signature_b64 + '==')
            data_to_verify = json.dumps(cert_data, sort_keys=True).encode('utf-8')
            
            sig_valid = False
            try:
                public_key.verify(signature, data_to_verify, ec.ECDSA(hashes.SHA256()))
                sig_valid = True
            except:
                pass
            
            if sig_valid:
                cert_id = cert_data.get("id")
                response = supabase.table("certificates").select("*").eq("cert_id", cert_id).execute()
                record = response.data[0] if response.data else None
                
                if record and record.get("is_valid") and not record.get("revoked_at"):
                    st.success("✅ **VALID & AUTHENTIC CERTIFICATE**")
                    st.json(cert_data)
                    st.balloons()
                else:
                    st.warning("⚠️ Certificate found but marked invalid or revoked.")
            else:
                st.error("❌ **INVALID CERTIFICATE** - Signature verification failed")
    except Exception as e:
        st.error(f"Error: {str(e)}")

st.caption("Secure verification using ECDSA signatures + Supabase")