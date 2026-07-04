import csv
import os
from pathlib import Path
import re

try:
    import tomllib
except Exception:
    import tomli as tomllib

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

DEFAULT_CONFIG = "certificate_config.toml"


def load_config(path: str = DEFAULT_CONFIG):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    with p.open("rb") as f:
        return tomllib.load(f), p


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    s = re.sub(r"[^\w]+", " ", str(value)).strip().lower()
    return re.sub(r"\s+", " ", s)


def find_certificate(name: str, output_dir: Path):
    """Return tuple (file_name, cert_id) or (None, None)."""
    target = normalize_text(name)
    if not target:
        return None, None
    for file in sorted(output_dir.glob("*.pdf")):
        token = normalize_text(file.stem)
        if target in token:
            parts = file.stem.split("_", 1)
            cert_id = parts[0] if parts else ""
            return file.name, cert_id
    # fallback: all words
    words = target.split()
    for file in sorted(output_dir.glob("*.pdf")):
        token = normalize_text(file.stem)
        if all(w in token for w in words):
            parts = file.stem.split("_", 1)
            cert_id = parts[0] if parts else ""
            return file.name, cert_id
    return None, None


def generate_pdf(report_path: Path, rows, summary, title="Office Record"):
    c = canvas.Canvas(str(report_path), pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = 20 * mm
    x = margin
    y = height - margin
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, title)
    y -= 10 * mm

    # summary lines
    c.setFont("Helvetica", 10)
    # show program metadata neatly
    meta_lines = [
        f"Program: {summary.get('Program','')}",
        f"Date: {summary.get('Date','')}",
        f"Time: {summary.get('Time','')}",
        f"Venue: {summary.get('Venue','')}",
        f"Chair: {summary.get('Chair','')}",
        f"Facilitators: {summary.get('Facilitators','')}",
        f"Verification base URL: {summary.get('Base URL','')}",
        f"Total Attendees: {summary.get('Total Attendees','')}",
        f"Certificates Found: {summary.get('Certificates Generated (found)','')}",
    ]
    for line in meta_lines:
        c.drawString(x, y, line)
        y -= 6 * mm

    y -= 4 * mm
    # table header: #, Name, Email, Cert ID
    c.setFont("Helvetica-Bold", 10)
    # columns positions within A4 landscape width
    col_x = [x, x + 12*mm, x + 120*mm, x + 230*mm]
    c.drawString(col_x[0], y, "#")
    c.drawString(col_x[1], y, "Name")
    c.drawString(col_x[2], y, "Email")
    c.drawString(col_x[3], y, "Cert ID")
    y -= 6 * mm
    c.setFont("Helvetica", 9)

    line_height = 6 * mm
    per_page = int((y - margin) // line_height) - 2
    count = 0
    page = 1
    def shorten_middle(s: str, max_chars: int = 60) -> str:
        if not s:
            return ""
        s = str(s)
        if len(s) <= max_chars:
            return s
        half = max_chars // 2 - 2
        return s[:half] + "..." + s[-half:]

    for r in rows:
        if count and (count % per_page == 0):
            c.showPage()
            y = height - margin
            c.setFont("Helvetica-Bold", 10)
            c.drawString(col_x[0], y, "#")
            c.drawString(col_x[1], y, "Name")
            c.drawString(col_x[2], y, "Email")
            c.drawString(col_x[3], y, "Cert ID")
            y -= 6 * mm
            c.setFont("Helvetica", 9)
            page += 1
        c.drawString(col_x[0], y, str(r.get("row_index", "")))
        c.drawString(col_x[1], y, r.get("name", ""))
        c.drawString(col_x[2], y, r.get("email", ""))
        c.drawString(col_x[3], y, r.get("cert_id", ""))
        y -= line_height
        count += 1

    c.save()


def run(config_file: str = DEFAULT_CONFIG):
    config, config_path = load_config(config_file)
    paths = config.get("paths", {})
    workshop = config.get("workshop", {})

    csv_path = (config_path.parent / paths.get("csv_path", "RIPS_FPS.csv")).resolve()
    output_dir = (config_path.parent / paths.get("output_dir", "certificates_output")).resolve()
    name_col = paths.get("name_column", "Names of faculty member/s")
    email_col = paths.get("email_column", "Email Address of facuty member/s")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not output_dir.exists():
        print(f"Warning: output_dir {output_dir} does not exist; continuing")

    # Read CSV using built-in csv as a fallback to avoid pandas requirement
    rows = []
    matched = 0
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for idx, row in enumerate(reader):
            name = str(row.get(name_col, "")).strip()
            email = str(row.get(email_col, "")).strip()
            cert_file, cert_id = (None, None)
            if name:
                cert_file, cert_id = find_certificate(name, output_dir)
            if cert_file:
                matched += 1
            rows.append({
                "row_index": idx + 1,
                "name": name,
                "email": email,
                "cert_id": cert_id or "",
                "certificate_file": cert_file or "",
            })

    facilitators = workshop.get("facilitators", []) or []
    focal = config.get("focal_facilitator", {})
    if focal:
        facilitators = [*facilitators, focal.get("name")] if focal.get("name") else facilitators

    summary = {
        "Program": workshop.get("program_name", ""),
        "Issuer": workshop.get("issuer", ""),
        "Total Attendees": len(rows),
        "Certificates Generated (found)": matched,
        "Facilitators Count": len([f for f in facilitators if f]),
    }
    # add program metadata
    summary["Date"] = workshop.get("date", "")
    summary["Time"] = workshop.get("time", "")
    summary["Venue"] = workshop.get("venue", "")
    summary["Chair"] = workshop.get("chair", "")
    summary["Facilitators"] = ", ".join([f for f in facilitators if f])
    summary["Base URL"] = workshop.get("base_url", "")

    report_pdf = config_path.parent / "office_record.pdf"
    report_csv = config_path.parent / "office_record.csv"

    # write CSV record using csv module
    with report_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["row_index", "name", "email", "cert_id", "certificate_file"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # generate PDF
    generate_pdf(report_pdf, rows, summary, title="Office Record")
    print(f"Wrote {report_pdf}")
    print(f"Wrote {report_csv}")


if __name__ == "__main__":
    run()
