"""Render structured resume content to HTML and PDF via Jinja + WeasyPrint."""

import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.paths import BASE_DIR

TEMPLATE_DIR = os.path.join(BASE_DIR, "app", "web", "templates", "resume_templates")
_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def _default_colors() -> dict:
    return {"primary": "#1F4E79", "secondary": "#2563eb", "accent": "#7c3aed"}


def _default_typography() -> dict:
    return {"font_family": "Inter, sans-serif", "font_size": 11}


def _default_section_order() -> list:
    return ["summary", "skills", "experience", "education", "custom_sections"]


def _default_section_visibility() -> dict:
    return {"summary": True, "skills": True, "experience": True, "education": True, "custom_sections": True}


def render_session_html(session) -> str:
    """Render a TailoringSession to an HTML string using the selected template."""
    content = session.content or {}
    template_id = session.template_id or "business_professional_1"
    page_format = session.page_format or "letter"
    spacing_in = session.spacing_in if session.spacing_in is not None else 0.75
    typography = session.typography or _default_typography()
    colors = session.colors or _default_colors()
    section_order = session.section_order or _default_section_order()
    section_visibility = session.section_visibility or _default_section_visibility()

    # Normalize legacy shapes
    if not isinstance(content.get("experience"), list):
        content["experience"] = []
    if not isinstance(content.get("education"), list):
        content["education"] = []
    if not isinstance(content.get("skills"), list):
        content["skills"] = [s.strip() for s in str(content.get("skills", "")).split(",") if s.strip()]
    if not isinstance(content.get("custom_sections"), list):
        content["custom_sections"] = []

    personal_info = content.get("personal_info") or {}
    if not isinstance(personal_info, dict):
        personal_info = {}

    template = _env.get_template(f"{template_id}.html")
    html = template.render(
        content=content,
        personal_info=personal_info,
        typography=typography,
        colors=colors,
        spacing_in=spacing_in,
        page_format=page_format,
        section_order=section_order,
        section_visibility=section_visibility,
    )
    return html


def render_session_pdf(session) -> bytes:
    """Render a TailoringSession to PDF bytes via WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("WeasyPrint is not installed") from exc

    html = render_session_html(session)
    return HTML(string=html).write_pdf()
