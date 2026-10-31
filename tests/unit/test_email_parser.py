import synthetic_builders as sb
from billing_agent.config import LimitSettings
from billing_agent.parsers import ParseContext, parse_bytes
from billing_agent.schemas import BlockKind, DocType, ParseStatus


def _bodies(doc):
    return {b.meta["content_type"]: b for b in doc.blocks if b.kind == BlockKind.EMAIL_BODY}


def test_headers_and_both_bodies():
    doc = parse_bytes(sb.eml_bytes(), "mail.eml")
    assert doc.detected_type == DocType.EML and doc.status == ParseStatus.PARSED
    assert doc.email.subject == "SYNTHETIC 测试 Pre-Alert"
    assert "sender@example.com" in doc.email.sender
    assert len(doc.email.to) == 2
    bodies = _bodies(doc)
    assert "Handling Fee to USD 45.00" in bodies["text/plain"].text
    assert "USD 45.00" in bodies["text/html"].text
    assert "<b>" not in bodies["text/html"].text


def test_html_only_body():
    doc = parse_bytes(sb.eml_bytes(plain=None), "mail.eml")
    assert doc.email.body_html_present and not doc.email.body_plain_present
    assert "USD 45.00" in _bodies(doc)["text/html"].text


def test_attachments_parsed_by_real_format_even_with_wrong_mime():
    eml = sb.eml_bytes(attachments=[
        ("charges.pdf", "application/octet-stream", sb.pdf_bytes()),
        ("sheet.xlsx", "application/octet-stream", sb.xlsx_bytes()),
        ("note.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", sb.docx_bytes()),
    ])
    doc = parse_bytes(eml, "mail.eml")
    types = [c.detected_type for c in doc.children]
    assert types == [DocType.PDF, DocType.XLSX, DocType.DOCX]
    assert doc.children[0].source_chain == ["mail.eml", "charges.pdf"]
    assert "Handling Fee USD 40.00" in doc.children[0].blocks[0].text
    assert doc.children[1].blocks[0].table[2][0] == "Doc Fee"


def test_nested_eml_is_recursive():
    inner = sb.eml_bytes(subject="inner", attachments=[("x.pdf", "application/pdf", sb.pdf_bytes())])
    outer = sb.eml_bytes(subject="outer", nested=inner)
    doc = parse_bytes(outer, "outer.eml")
    nested = doc.children[0]
    assert nested.detected_type == DocType.EML
    assert nested.email.subject == "inner"
    assert nested.children[0].detected_type == DocType.PDF
    assert nested.children[0].source_chain[0] == "outer.eml"


def test_depth_limit_stops_recursion():
    level3 = sb.eml_bytes(subject="l3")
    level2 = sb.eml_bytes(subject="l2", nested=level3)
    level1 = sb.eml_bytes(subject="l1", nested=level2)
    ctx = ParseContext(limits=LimitSettings(max_email_depth=1))
    doc = parse_bytes(level1, "l1.eml", ctx)
    nested = doc.children[0]
    assert nested.email.subject == "l2"
    assert nested.children == []
    assert any("depth limit" in w for w in nested.warnings)


def test_attachment_count_limit():
    atts = [(f"a{i}.json", "application/json", sb.bills_json_bytes()) for i in range(5)]
    ctx = ParseContext(limits=LimitSettings(max_email_attachments=2))
    doc = parse_bytes(sb.eml_bytes(attachments=atts), "m.eml", ctx)
    assert len(doc.children) == 2
    assert sum("attachment limit" in w for w in doc.warnings) == 3


def test_malicious_attachment_name_is_sanitized():
    eml = sb.eml_bytes(attachments=[("../../evil.pdf", "application/pdf", sb.pdf_bytes())])
    doc = parse_bytes(eml, "m.eml")
    assert doc.children[0].file_name == "evil.pdf"
