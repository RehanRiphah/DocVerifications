# Next Training Round — Quick Checklist

A concise step-by-step checklist to run the next training round using the A_, B_, C_ scripts and the TOML configuration.

## Overview
- Purpose: generate certificates, send them by email, and create an office record (CSV + PDF).
- Primary scripts:
  - [A_generate_certificates.py](certificates/Certificates_2/A_generate_certificates.py) — creates certificate PDFs in the output folder.
  - [B_send_emails.py](certificates/Certificates_2/B_send_emails.py) — sends certificates by email using `certificate_config.toml` and `.env` secrets.
  - [C_office_report.py](certificates/Certificates_2/C_office_report.py) — generates `office_record.csv` and `office_record.pdf`.
- Config file: [certificate_config.toml](certificates/Certificates_2/certificate_config.toml)

## Before you start
1. Make a quick backup copy of `certificate_config.toml` and your input CSV.
2. Ensure you are in the correct virtual environment with dependencies installed (reportlab, python-dotenv, tomli if Python <3.11).
3. Optional: commit current changes to git so you can roll back easily.

## 1) Update configuration (certificate_config.toml)
Update only these fields for the new training:
- `paths.csv_path` — path to the attendee CSV for the new workshop (relative to the TOML file).
- `paths.output_dir` — where the generated certificate PDFs will be written.
- `paths.name_column` and `paths.email_column` — column names in your CSV for name and email.
- `workshop.program_name`, `workshop.date`, `workshop.time`, `workshop.venue`, `workshop.chair`, `workshop.facilitators` — metadata used in the office report and email templates.
- `workshop.base_url` — base verification URL used in the office report.
- `email.subject` / `email.body` — update templates if wording changes.

Note: The script expects certificate filenames as `<CERTID>_<Name>.pdf`. Keep that naming convention.

## 2) Prepare the attendee CSV
- Ensure CSV encoding is UTF-8 and it includes the columns named in `paths.name_column` and `paths.email_column`.
- Remove or handle duplicate rows and correct obvious typos in names and emails.
- Save under the path referenced by `paths.csv_path`.

## 3) Generate certificates
- Run generation script (dry run not available here — test with a small subset first):

```bash
cd certificates/Certificates_2
python A_generate_certificates.py
```

- Verify output: check `paths.output_dir` for `.pdf` files. Filenames should begin with the certificate ID (used for verification links).
- Spot-check several PDFs visually to confirm names and program metadata are correct.

## 4) Prepare email sending
- Add your Gmail App Password to `.env` (16-character app password for smtp):
  - `EMAIL_APP_PASSWORD=your_app_password_here`
  or place it under `[email].app_password` in `certificate_config.toml` (less recommended).
- Verify `[email].smtp` and `[email].port` in the TOML (`smtp.gmail.com`, port `465` for SSL by default).

## 5) Test email sending (dry run)
- Run B_send_emails.py in dry-run to confirm matching and message building without sending:

```bash
cd certificates/Certificates_2
python B_send_emails.py --dry-run
```

- Check logs: `email_sender.log` and `failed_matches.csv` to see unmatched names or missing files.
- Fix any mismatches in the CSV or certificate filenames.

## 6) Send emails (production)
- When satisfied with dry-run results, run without `--dry-run`:

```bash
python B_send_emails.py
```

- Monitor `email_sender.log` and `failed_matches.csv` for failed deliveries / missing certificates.
- Gmail limits: send in batches if you expect many emails — use pauses or split the CSV to avoid rate limits.

## 7) Produce office record
- After sending (or even before sending), run the office report generator to produce CSV and PDF for records:

```bash
python C_office_report.py
```

- Output files: `office_record.csv` and `office_record.pdf` in the same folder as the TOML file.
- `office_record.csv` contains: `row_index,name,email,cert_id,certificate_file`.
- `office_record.pdf` is a landscape summary (Program metadata, counts, table with Name / Email / Cert ID).

## 8) Post-run housekeeping
- Archive the `certificates_output` folder and `office_record.*` into a dated folder, e.g., `archive/2026-07-04_workshop_X/`.
- Keep `failed_matches.csv` and `email_sender.log` for troubleshooting and records.
- If re-sending is needed, fix CSV or certificates, then re-run `B_send_emails.py` with a filtered CSV.

## Maintenance & checks to do regularly
- Keep `certificate_config.toml` up-to-date with any template or base_url changes.
- Ensure fonts used in certificate templates are available in the generation environment.
- Update `requirements.txt` (reportlab, python-dotenv, tomli) if you add new packages.
- Periodically test `B_send_emails.py` with a small internal list to validate SMTP credentials.

## Troubleshooting quick tips
- SMTP authentication errors: check `.env` for `EMAIL_APP_PASSWORD` and ensure app password is valid; enable less secure apps is not used — use app password.
- Missing certificate for a name: check `certificate_file` values in `office_record.csv` and the `certificates_output` folder for name-token differences.
- Long names cut off in PDF: `C_office_report.py` uses landscape layout; if needed, increase page width (not recommended) or adjust column positions in the script.

## Useful commands
```bash
# Regenerate certificates
cd certificates/Certificates_2
python A_generate_certificates.py

# Dry-run email matching
python B_send_emails.py --dry-run

# Send emails
python B_send_emails.py

# Create office record
python C_office_report.py
```

## Where to change things
- Script logic: [A_generate_certificates.py](certificates/Certificates_2/A_generate_certificates.py)
- Email sending: [B_send_emails.py](certificates/Certificates_2/B_send_emails.py)
- Report generation: [C_office_report.py](certificates/Certificates_2/C_office_report.py)
- Configuration: [certificate_config.toml](certificates/Certificates_2/certificate_config.toml)
- Secrets: `.env` in the same folder as the TOML file.


---
Keep this file updated with any new steps you add (QR codes, verification page changes, or batch-sending helpers). If you want, I can also add a small checklist of commands to automate backups and archives.
