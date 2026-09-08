import os
import re

from pypdf import PdfReader

from app.paths import UPLOAD_DIR


def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
        # Extract hyperlink annotations
        try:
            for annot in page.get("/Annots", []):
                annot_obj = annot.get_object()
                a_dict = annot_obj.get("/A")
                if a_dict:
                    url = a_dict.get("/URI", "")
                    if url and url not in "\n".join(parts):
                        parts.append(url)
        except Exception:
            continue
    return "\n".join(parts)


def extract_text_from_docx(path: str) -> str:
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(path)
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
        # Extract hyperlink URLs from paragraph XML
        for hyperlink in para._element.findall(qn('w:hyperlink')):
            r_id = hyperlink.get(qn('r:id'))
            if r_id and r_id in doc.part.rels:
                url = doc.part.rels[r_id].target_ref
                if url and url.startswith('http'):
                    parts.append(url)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    if ext in (".docx", ".doc"):
        return extract_text_from_docx(path)
    raise ValueError(f"Unsupported file type: {ext}")


def save_upload(file_storage, filename: str) -> str:
    dest = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(dest)
    return dest


# -------- lightweight regex fallback (used when no Gemini key) --------

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-()]{7,}\d)")
URL_RE = re.compile(r"https?://[^\s]+")


def extract_email(text: str) -> str:
    match = EMAIL_RE.search(text or "")
    return match.group(0) if match else ""


def extract_contact(text: str) -> dict:
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    urls = URL_RE.findall(text)

    linkedin = github = portfolio = website = ""
    for u in urls:
        u_clean = u.rstrip(".,;)")
        u_low = u_clean.lower()
        if "linkedin.com" in u_low and not linkedin:
            linkedin = u_clean
        elif "github.com" in u_low and not github:
            github = u_clean
        elif not website:
            website = u_clean
        elif not portfolio:
            portfolio = u_clean

    return {
        "email": emails[0] if emails else "",
        "phone": phones[0].strip() if phones else "",
        "linkedin": linkedin,
        "github": github,
        "website": website,
        "portfolio": portfolio,
    }


def first_line_name(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and len(line) < 60 and not re.match(r"^[\W_]+$", line):
            return line
    return ""
