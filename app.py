# ---------- Input & Verification Logic ----------
# Check for QR payload in URL
payload = st.query_params.get("payload", None)

# Manual input if no payload
if not payload:
    cert_id = st.text_input("Enter Certificate ID", placeholder="e.g., CERT-2024-001")
    verify_clicked = st.button("Verify Certificate")
else:
    cert_id = None
    verify_clicked = True  # Auto-verify when QR is scanned

if verify_clicked:
    try:
        # If payload exists, decode it
        if payload:
            # The payload is base64url of {"d": cert_data, "s": signature}
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
            
            # Get cert_id from cert_data
            cert_id = cert_data.get("cert_id") or cert_data.get("id")
            if not cert_id:
                st.error("❌ Certificate ID not found in data.")
                st.stop()
        
        # If we have cert_id (either from payload or manual input)
        if cert_id:
            # Query Supabase using cert_id (not the auto-generated id)
            response = supabase.table("certificates").select("*").eq("cert_id", cert_id).execute()
            
            if not response.data:
                st.warning("⚠️ Certificate ID not found in the official registry.")
                if payload and cert_data:
                    st.info("The cryptographic signature is valid, but this certificate is not registered in our system.")
                st.stop()
            
            record = response.data[0]
            
            # Map database columns to display fields
            is_valid = record.get("is_valid", False)
            revoked_at = record.get("revoked_at")
            
            # Check status
            if is_valid and not revoked_at:
                st.success("✅ **VALID & AUTHENTIC CERTIFICATE**")
                
                # Display the certificate data as a beautiful card
                # Prefer data from payload (if available) for display, else use Supabase record
                if payload and cert_data:
                    # Use the data from payload (more complete, includes signature-verified fields)
                    display_data = {
                        "cert_id": cert_data.get("cert_id") or record.get("cert_id"),
                        "name": cert_data.get("name") or record.get("name"),
                        "program": cert_data.get("program") or record.get("program"),
                        "issuer": cert_data.get("issuer") or record.get("issuer"),
                        "issued_at": cert_data.get("issued_at") or record.get("issued_at"),
                    }
                else:
                    # Use data from Supabase record
                    display_data = {
                        "cert_id": record.get("cert_id"),
                        "name": record.get("name"),
                        "program": record.get("program"),
                        "issuer": record.get("issuer"),
                        "issued_at": record.get("issued_at"),
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
                    ("Certificate ID", display_data.get("cert_id")),
                    ("Holder Name", display_data.get("name")),
                    ("Program / Course", display_data.get("program")),
                    ("Issuer", display_data.get("issuer")),
                    ("Issue Date", display_data.get("issued_at")),
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
                st.warning("⚠️ **CERTIFICATE INVALID** – The certificate is marked as invalid in our system.")
        else:
            st.info("Please enter a Certificate ID or scan a QR code.")
    
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")

# ---------- Footer ----------
st.markdown("""
<div class="footer">
    🔒 Secure verification using ECDSA signatures + Supabase • Issued by RIPS
</div>
""", unsafe_allow_html=True)