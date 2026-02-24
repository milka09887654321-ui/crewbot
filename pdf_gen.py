from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


def _safe(v):
    v = (v or "").strip()
    return v if v else "Unknown"


def generate_profile_pdf(profile: dict):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    x = 18 * mm
    y = height - 20 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Seafarer Profile (CREWONBOARD.NET)")
    y -= 10 * mm

    c.setFont("Helvetica", 11)

    lines = [
        ("Full name", _safe(profile.get("full_name"))),
        ("Rank", _safe(profile.get("rank"))),
        ("Nationality", _safe(profile.get("nationality"))),
        ("D.O.B", _safe(profile.get("dob"))),
        ("Phone", _safe(profile.get("phone"))),
        ("WhatsApp", _safe(profile.get("whatsapp"))),
        ("Email", _safe(profile.get("email"))),
        ("English", _safe(profile.get("english"))),
        ("Available from", _safe(profile.get("available_from"))),
        ("Vessel experience", _safe(profile.get("vessel_exp"))),
        ("Sea service / experience", _safe(profile.get("experience"))),
        ("Certificates", _safe(profile.get("certificates"))),
    ]

    for k, v in lines:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y, f"{k}:")
        c.setFont("Helvetica", 11)

        max_chars = 95
        chunks = [v[i:i+max_chars] for i in range(0, len(v), max_chars)] or ["Unknown"]

        c.drawString(x + 40 * mm, y, chunks[0])
        y -= 7 * mm

        for ch in chunks[1:]:
            c.drawString(x + 40 * mm, y, ch)
            y -= 7 * mm

        y -= 1 * mm

        if y < 25 * mm:
            c.showPage()
            y = height - 20 * mm
            c.setFont("Helvetica", 11)

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(x, 15 * mm, "Generated via Telegram bot • CREWONBOARD.NET")

    c.save()
    buf.seek(0)
    return buf
