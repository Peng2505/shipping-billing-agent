"""EML parser: headers, plain/HTML bodies, attachments, inline images, nested messages."""

from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

from bs4 import BeautifulSoup

from billing_agent.schemas import BlockKind, EmailMeta, ParsedDocument, ParseStatus, SourceOrigin


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _header(msg: EmailMessage, name: str) -> str | None:
    value = msg.get(name)
    return str(value).strip() if value is not None else None


def _addresses(msg: EmailMessage, name: str) -> list[str]:
    header = msg.get(name)
    if header is None:
        return []
    addresses = getattr(header, "addresses", None)
    if addresses:
        return [str(a) for a in addresses]
    return [str(header)]


def _decode_text(part: EmailMessage, doc: ParsedDocument) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeDecodeError) as exc:
        doc.warnings.append(f"Body charset problem ({type(exc).__name__}); decoded with replacement.")
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def _is_body_part(part: EmailMessage) -> bool:
    return (
        part.get_content_maintype() == "text"
        and part.get_content_subtype() in {"plain", "html"}
        and part.get_content_disposition() != "attachment"
        and not part.get_filename()
    )


def _leaf_parts(part: EmailMessage):
    """Like walk(), but an attached message/rfc822 is yielded whole instead of entered."""
    if part.get_content_type() == "message/rfc822" or not part.is_multipart():
        yield part
        return
    for sub in part.iter_parts():
        yield from _leaf_parts(sub)


def parse(doc: ParsedDocument, data: bytes, ctx) -> None:
    from billing_agent.parsers.dispatcher import parse_bytes

    msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(data)
    meta = EmailMeta(
        subject=_header(msg, "Subject"),
        sender=_header(msg, "From"),
        to=_addresses(msg, "To"),
        cc=_addresses(msg, "Cc"),
        date=_header(msg, "Date"),
        message_id=_header(msg, "Message-ID"),
    )
    doc.email = meta
    header_text = "\n".join(
        f"{label}: {value}"
        for label, value in [
            ("Subject", meta.subject),
            ("From", meta.sender),
            ("To", ", ".join(meta.to) or None),
            ("Cc", ", ".join(meta.cc) or None),
            ("Date", meta.date),
            ("Message-ID", meta.message_id),
        ]
        if value
    )
    doc.add_block(BlockKind.EMAIL_HEADER, SourceOrigin.NATIVE, "h", header_text)

    plain_texts: list[str] = []
    attachment_index = 0
    for part in _leaf_parts(msg):
        if _is_body_part(part):
            text = _decode_text(part, doc)
            if part.get_content_subtype() == "plain":
                meta.body_plain_present = True
                plain_texts.append(text.strip())
                doc.add_block(BlockKind.EMAIL_BODY, SourceOrigin.NATIVE, "b", text.strip(),
                              meta={"content_type": "text/plain"})
            else:
                meta.body_html_present = True
                doc.add_block(
                    BlockKind.EMAIL_BODY, SourceOrigin.NATIVE, "b", html_to_text(text),
                    meta={"content_type": "text/html", "html_length": len(text)},
                )
            continue

        attachment_index += 1
        _handle_attachment(doc, part, ctx, attachment_index, parse_bytes)

    if meta.body_plain_present and meta.body_html_present:
        plain_norm = " ".join(" ".join(plain_texts).split())
        for block in doc.blocks:
            if block.meta.get("content_type") == "text/html":
                block.meta["same_as_plain"] = " ".join(block.text.split()) == plain_norm
    if not (meta.body_plain_present or meta.body_html_present):
        doc.warnings.append("E-mail has no text body.")
    if any(child.status in (ParseStatus.FAILED, ParseStatus.UNSUPPORTED) for child in doc.children):
        doc.status = ParseStatus.PARTIAL


def _handle_attachment(doc: ParsedDocument, part: EmailMessage, ctx, index: int, parse_bytes) -> None:
    filename = part.get_filename()
    content_type = part.get_content_type()
    disposition = part.get_content_disposition()
    content_id = part.get("Content-ID")
    is_inline = bool(content_id) or disposition == "inline"

    if ctx.depth + 1 > ctx.limits.max_email_depth:
        doc.warnings.append(
            f"Attachment '{filename or content_type}' skipped: nesting depth limit "
            f"{ctx.limits.max_email_depth} reached."
        )
        return
    ctx.attachment_counter[0] += 1
    if ctx.attachment_counter[0] > ctx.limits.max_email_attachments:
        doc.warnings.append(
            f"Attachment '{filename or content_type}' skipped: attachment limit "
            f"{ctx.limits.max_email_attachments} reached."
        )
        return

    if content_type == "message/rfc822":
        inner = part.get_payload()
        inner_msg = inner[0] if isinstance(inner, list) and inner else inner
        payload = inner_msg.as_bytes() if hasattr(inner_msg, "as_bytes") else b""
        filename = filename or f"attached_message_{index}.eml"
    else:
        payload = part.get_payload(decode=True) or b""
        filename = filename or f"part_{index}"

    child = parse_bytes(
        payload,
        filename,
        ctx.child(),
        source_chain=doc.source_chain,
        declared_mime=content_type,
        position=f"{doc.doc_id.split('-')[0][1:]}.{index}",
    )
    child.meta.update({
        "original_filename": part.get_filename(),
        "email_part_index": index,
        "inline": is_inline,
        "content_id": content_id,
        "disposition": disposition,
    })
    doc.children.append(child)
