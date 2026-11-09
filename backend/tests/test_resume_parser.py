"""Résumé extraction and parsing. No network: every OpenAI path is monkeypatched."""

from __future__ import annotations

import io

import pytest

from app import resume_parser
from app.resume_parser import (
    ResumeProfile,
    UnsupportedResumeType,
    extract_resume_text,
    is_linkedin_pdf_text,
    merge_resume_profile,
    parse_linkedin_profile,
    parse_resume,
    sanitize_profile,
    strip_contact_details,
)

# All people below are fictional.

PLAIN_RESUME = """Alex Quill
Platform engineer, Salt Lake City
alex.quill@example.com | +1 (555) 010-2030 | https://alexquill.dev

Experience
Globex - Senior Platform Engineer (2023 - Present)
Runs the Kubernetes platform; built the eBPF-based network observability stack.

Skills
Kubernetes, Go, eBPF, OpenTelemetry, Terraform
"""

LINKEDIN_TEXT = """Contact
jane.doe@example.com
www.linkedin.com/in/jane-doe-fake (LinkedIn)
Top Skills
Kubernetes
Go
Observability
Languages
English
Jane Doe
Staff SRE at Acme | eBPF, platform engineering
Salt Lake City, Utah, United States
Summary
Runs the infrastructure team. Cares about reliability and eBPF.
Experience
Acme Corp
Staff Site Reliability Engineer
January 2022 - Present (4 years)
Remote
Globex
Site Reliability Engineer
2019 - 2021 (2 years)
Education
State University
Page 1 of 2
"""


def make_pdf(lines: list[str]) -> bytes:
    """A minimal single-page PDF with Helvetica text, enough for pypdf to extract."""
    text_ops = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
        "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*"
        for line in lines
    )
    text_ops += " ET"
    stream = text_ops.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def make_docx(paragraphs: list[str], table_rows: list[list[str]] | None = None) -> bytes:
    from docx import Document

    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table_rows:
        table = document.add_table(rows=0, cols=len(table_rows[0]))
        for row in table_rows:
            cells = table.add_row().cells
            for cell, value in zip(cells, row, strict=True):
                cell.text = value
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


@pytest.fixture
def no_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


# --- extraction --------------------------------------------------------------------------------


def test_extract_txt_normalizes_whitespace() -> None:
    text = extract_resume_text(
        b"Alex  Quill\r\n\r\n\r\n\tPlatform   engineer  \n", "text/plain", "cv.txt"
    )
    assert text == "Alex Quill\n\nPlatform engineer"


def test_extract_pdf_by_content_type_and_by_suffix() -> None:
    pdf = make_pdf(["Alex Quill", "Platform engineer", "Skills: Kubernetes, Go"])
    assert "Kubernetes" in extract_resume_text(pdf, "application/pdf", None)
    assert "Alex Quill" in extract_resume_text(pdf, "application/octet-stream", "resume.PDF")


def test_extract_docx_includes_table_cells() -> None:
    docx = make_docx(["Alex Quill", "Platform engineer"], [["Skills", "Kubernetes, Go"]])
    text = extract_resume_text(docx, resume_parser.DOCX_CONTENT_TYPE, "resume.docx")
    assert "Platform engineer" in text
    assert "Skills | Kubernetes, Go" in text


def test_extract_rejects_unknown_types() -> None:
    with pytest.raises(UnsupportedResumeType):
        extract_resume_text(b"GIF89a", "image/gif", "me.gif")


def test_extract_caps_length() -> None:
    text = extract_resume_text(b"x" * (resume_parser.MAX_RESUME_CHARS + 500), "text/plain", "a.txt")
    assert len(text) == resume_parser.MAX_RESUME_CHARS


# --- LinkedIn export ---------------------------------------------------------------------------


def test_linkedin_detection() -> None:
    assert is_linkedin_pdf_text(LINKEDIN_TEXT)
    assert not is_linkedin_pdf_text(PLAIN_RESUME)
    # The URL alone is not enough; the section headers must be there too.
    assert not is_linkedin_pdf_text("See www.linkedin.com/in/someone for more.\nSkills: Go")


def test_linkedin_sections_parse_deterministically() -> None:
    profile = parse_linkedin_profile(LINKEDIN_TEXT)
    assert profile.headline == "Staff SRE at Acme | eBPF, platform engineering"
    assert profile.skills == ["kubernetes", "go", "observability"]
    assert profile.working_on == "Staff Site Reliability Engineer at Acme Corp."
    assert profile.summary.startswith("Runs the infrastructure team.")
    assert "example.com" not in profile.model_dump_json()


def test_linkedin_name_block_after_top_skills() -> None:
    text = LINKEDIN_TEXT.replace("Languages\nEnglish\n", "")
    profile = parse_linkedin_profile(text)
    assert profile.headline == "Staff SRE at Acme | eBPF, platform engineering"
    assert profile.skills == ["kubernetes", "go", "observability"]


def test_linkedin_parse_survives_without_openai(no_openai: None) -> None:
    profile = parse_resume(LINKEDIN_TEXT)
    assert profile.skills == ["kubernetes", "go", "observability"]
    assert profile.interests == []


def test_linkedin_pdf_roundtrip(no_openai: None) -> None:
    pdf = make_pdf(LINKEDIN_TEXT.splitlines())
    text = extract_resume_text(pdf, "application/pdf", "Profile.pdf")
    assert is_linkedin_pdf_text(text)
    assert parse_resume(text).headline == "Staff SRE at Acme | eBPF, platform engineering"


# --- LLM path ----------------------------------------------------------------------------------


def test_parse_resume_returns_empty_profile_without_api_key(no_openai: None) -> None:
    assert parse_resume(PLAIN_RESUME) == ResumeProfile()
    assert parse_resume("   \n ") == ResumeProfile()


def test_parse_resume_swallows_openai_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def boom(text: str) -> dict[str, object]:
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(resume_parser, "_call_openai", boom)
    assert parse_resume(PLAIN_RESUME) == ResumeProfile()


def test_parse_resume_uses_model_output_and_strips_contact_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        resume_parser,
        "_call_openai",
        lambda text: {
            "headline": "Senior Platform Engineer (alex.quill@example.com)",
            "skills": ["Kubernetes", "kubernetes", "Go", "https://alexquill.dev", "eBPF"],
            "interests": ["Observability", "ebpf"],
            "working_on": "Call +1 (555) 010-2030 about the Kubernetes platform at Globex.",
            "can_help_with": "Kubernetes networking, see www.alexquill.dev.",
            "summary": "Platform engineer at Globex.",
        },
    )
    profile = parse_resume(PLAIN_RESUME)
    assert profile.headline == "Senior Platform Engineer"
    assert profile.skills == ["kubernetes", "go", "ebpf"]
    assert profile.interests == ["observability", "ebpf"]
    assert profile.working_on == "Call about the Kubernetes platform at Globex."
    assert profile.can_help_with == "Kubernetes networking, see."
    dumped = profile.model_dump_json()
    for leak in ("@", "555", "alexquill", "http"):
        assert leak not in dumped


def test_linkedin_deterministic_fields_win_over_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        resume_parser,
        "_call_openai",
        lambda text: {
            "headline": "Model headline",
            "skills": ["ebpf"],
            "interests": ["reliability"],
            "working_on": "Model sentence.",
            "can_help_with": "Model help.",
            "summary": "Model summary.",
        },
    )
    profile = parse_resume(LINKEDIN_TEXT)
    assert profile.headline == "Staff SRE at Acme | eBPF, platform engineering"
    assert profile.skills == ["kubernetes", "go", "observability", "ebpf"]
    assert profile.interests == ["reliability"]
    assert profile.can_help_with == "Model help."


def test_sanitize_caps_list_sizes() -> None:
    profile = sanitize_profile(
        {"skills": [f"skill{i}" for i in range(50)], "interests": [f"i{i}" for i in range(50)]}
    )
    assert len(profile.skills) == resume_parser.MAX_SKILLS
    assert len(profile.interests) == resume_parser.MAX_INTERESTS


def test_strip_contact_details_keeps_prose() -> None:
    cleaned = strip_contact_details(
        "Reach me at alex@example.com or +1 (555) 010-2030, see alexquill.dev. Loves k8s 1.31."
    )
    assert cleaned == "Reach me at or, see. Loves k8s 1.31."


# --- merge -------------------------------------------------------------------------------------


def test_merge_typed_values_win_and_lists_union() -> None:
    typed = {
        "name": "Alex",
        "headline": "Typed headline",
        "working_on": "",
        "can_help_with": "  ",
        "skills": ["Kubernetes", "Rust"],
        "interests": [],
    }
    parsed = ResumeProfile(
        headline="Parsed headline",
        working_on="Parsed working on.",
        can_help_with="Parsed help.",
        skills=["kubernetes", "go"],
        interests=["observability"],
    )
    merged = merge_resume_profile(typed, parsed)
    assert merged["name"] == "Alex"
    assert merged["headline"] == "Typed headline"
    assert merged["working_on"] == "Parsed working on."
    assert merged["can_help_with"] == "Parsed help."
    assert merged["skills"] == ["Kubernetes", "Rust", "go"]
    assert merged["interests"] == ["observability"]


def test_merge_with_empty_profile_is_identity() -> None:
    typed = {"headline": "", "skills": ["go"], "interests": ["ebpf"], "working_on": "x"}
    assert merge_resume_profile(typed, ResumeProfile()) == typed


def test_extract_contact_from_plain_resume():
    from app.resume_parser import extract_contact

    text = (
        "JANE DOE\n"
        "jane.doe@example.com | (801) 555-0100 | linkedin.com/in/jane-doe-123\n"
        "Data science student and backend developer.\n"
    )
    assert extract_contact(text) == {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "linkedin_url": "https://www.linkedin.com/in/jane-doe-123",
    }


def test_extract_contact_missing_fields_are_empty():
    from app.resume_parser import extract_contact

    assert extract_contact("Résumé\nBuilt data pipelines in 2024.") == {
        "name": "",
        "email": "",
        "linkedin_url": "",
    }
