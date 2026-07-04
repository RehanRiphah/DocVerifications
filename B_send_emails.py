import argparse
import csv
import logging
import os
import re
from pathlib import Path
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pandas as pd
from dotenv import load_dotenv

DEFAULT_CONFIG_FILE = "certificate_config.toml"
LOG_FILE = "email_sender.log"


def setup_logging(log_path: Path):
    logger = logging.getLogger("certificate_email_sender")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def load_config(config_path: str = DEFAULT_CONFIG_FILE):
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("rb") as f:
        return tomllib.load(f), config_path


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    normalized = re.sub(r"[^\w]+", " ", str(value).strip()).lower()
    return re.sub(r"\s+", " ", normalized).strip()


def find_certificate_file(name: str, output_dir: Path):
    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    target = normalize_text(name)
    if not target:
        return None

    for file_path in sorted(output_dir.glob("*.pdf")):
        file_token = normalize_text(file_path.stem)
        if target in file_token:
            return file_path

    candidates = []
    for file_path in sorted(output_dir.glob("*.pdf")):
        file_token = normalize_text(file_path.stem)
        if all(word in file_token for word in target.split()):
            candidates.append(file_path)

    return candidates[0] if candidates else None


def create_email_message(sender: str, recipient: str, subject: str, body: str, attachment_path: Path):
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with attachment_path.open("rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={attachment_path.name}",
    )
    msg.attach(part)
    return msg


def send_email(smtp_host: str, smtp_port: int, sender: str, password: str, recipient: str, message: MIMEMultipart):
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, message.as_string())


def build_subject(template: str, program_name: str) -> str:
    return template.format(program_name=program_name)


def build_body(template: str, name: str, program_name: str, issuer: str) -> str:
    return template.format(name=name, program_name=program_name, issuer=issuer)


def write_failure_report(report_path: Path, rows):
    headers = ["row_index", "name", "email", "error", "certificate_file"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run(config_path: str, dry_run: bool = False):
    config, config_path_obj = load_config(config_path)
    load_dotenv(config_path_obj.parent / ".env")

    paths = config.get("paths", {})
    workshop = config.get("workshop", {})
    email_config = config.get("email", {})

    csv_path = (config_path_obj.parent / paths.get("csv_path", "RIPS_FPS.csv")).resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    output_dir = (config_path_obj.parent / paths.get("output_dir", "certificates_output")).resolve()
    failure_report_name = paths.get("failure_report", "failed_matches.csv")
    failure_report_path = (config_path_obj.parent / failure_report_name).resolve()

    name_column = paths.get("name_column", "Names of faculty member/s")
    email_column = paths.get("email_column", "Email Address of facuty member/s")

    program_name = workshop.get("program_name", "")
    issuer = workshop.get("issuer", "")
    if not program_name:
        raise ValueError("program_name is required in the toml workshop section.")

    smtp_host = email_config.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_config.get("smtp_port", 465))
    sender_email = email_config.get("sender_email") or os.getenv("SENDER_EMAIL")
    app_password = email_config.get("app_password") or os.getenv("EMAIL_APP_PASSWORD")
    subject_template = email_config.get(
        "subject_template", "Thank you for attending the training on {program_name}"
    )
    body_template = email_config.get(
        "body_template",
        "Dear {name},\n\nThank you for attending the training on {program_name}. Attached is your certificate of participation.\n\nBest regards,\n{issuer}\n",
    )

    log_path = config_path_obj.parent / LOG_FILE
    logger = setup_logging(log_path)
    logger.info("Starting email send run")

    if not sender_email:
        raise ValueError(
            "Sender email is required. Set it in certificate_config.toml under [email] or via the SENDER_EMAIL environment variable."
        )
    if not app_password:
        raise ValueError(
            "SMTP app password is required. Set it in certificate_config.toml under [email] or via the EMAIL_APP_PASSWORD environment variable."
        )

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    failure_rows = []
    sent = 0
    skipped = 0

    for index, row in df.iterrows():
        name = str(row.get(name_column, "") or "").strip()
        recipient_email = str(row.get(email_column, "") or "").strip()
        certificate_file = None
        error_message = ""

        if not name or not recipient_email or recipient_email.lower() in {"nan", "none", ""}:
            error_message = "Invalid row data: missing name or email"
            logger.warning("Skipping invalid row %s: name=%r email=%r", index + 1, name, recipient_email)
            skipped += 1
        else:
            try:
                certificate_file = find_certificate_file(name, output_dir)
                if certificate_file is None:
                    error_message = "Certificate file not found"
                    logger.warning("Certificate not found for %s at %s", name, output_dir)
                    skipped += 1
                else:
                    subject = build_subject(subject_template, program_name)
                    body = build_body(body_template, name, program_name, issuer)
                    message = create_email_message(sender_email, recipient_email, subject, body, certificate_file)

                    if dry_run:
                        logger.info("[DRY RUN] Would send %s to %s", certificate_file.name, recipient_email)
                        sent += 1
                    else:
                        try:
                            send_email(smtp_host, smtp_port, sender_email, app_password, recipient_email, message)
                            logger.info("Sent certificate %s to %s <%s>", certificate_file.name, name, recipient_email)
                            sent += 1
                        except Exception as exc:
                            error_message = f"Send failed: {exc}"
                            logger.error("Failed to send email for %s <%s>: %s", name, recipient_email, exc)
                            skipped += 1
            except Exception as exc:
                error_message = f"Processing failed: {exc}"
                logger.exception("Error while processing row %s for %s", index + 1, name)
                skipped += 1

        if error_message:
            failure_rows.append({
                "row_index": index + 1,
                "name": name,
                "email": recipient_email,
                "error": error_message,
                "certificate_file": certificate_file.name if certificate_file else "",
            })

    if failure_rows:
        write_failure_report(failure_report_path, failure_rows)
        logger.info("Wrote failure report to %s", failure_report_path)
    logger.info("Run complete: sent=%s skipped=%s", sent, skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send generated certificate PDFs by email using configuration from certificate_config.toml.")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="Path to the TOML configuration file.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without sending email.")
    args = parser.parse_args()
    run(args.config, dry_run=args.dry_run)
