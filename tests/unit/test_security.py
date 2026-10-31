import pytest

from billing_agent.security import (
    SecurityError,
    check_size,
    redact_text,
    redact_url,
    sanitize_filename,
    validate_remote_file_url,
)


@pytest.mark.parametrize("raw, expected", [
    ("../../etc/passwd", "passwd"),
    ("..\\..\\Windows\\system32\\evil.exe", "evil.exe"),
    ("C:\\Users\\a\\bill.pdf", "bill.pdf"),
    ('in<voi>ce:"1"?.pdf', "in_voi_ce__1__.pdf"),
    ("CON.pdf", "_CON.pdf"),
    ("...", "unnamed"),
    ("", "unnamed"),
    (None, "unnamed"),
    ("深圳容宇 PRE-ALERT.eml", "深圳容宇 PRE-ALERT.eml"),
    ("4055331281\xa0MBL.pdf", "4055331281 MBL.pdf"),  # regression: NBSP in real sample attachment
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_limits_length_and_keeps_extension():
    name = sanitize_filename("a" * 500 + ".pdf")
    assert len(name) <= 180 and name.endswith(".pdf")


def test_check_size():
    check_size(10, 10, "f")
    with pytest.raises(SecurityError):
        check_size(11, 10, "f")


@pytest.mark.parametrize("url", [
    "C:\\data\\bill.pdf",
    "/tmp/bill.pdf",
    "./bill.pdf",
    "file:///etc/passwd",
    "http://example.com/a.pdf",
    "https://localhost/a.pdf",
    "https://127.0.0.1/a.pdf",
    "https://10.0.0.8/a.pdf",
    "https://192.168.1.2/a.pdf",
    "https://169.254.169.254/latest/meta-data",
    "https://[::1]/a.pdf",
    "",
])
def test_rejects_non_public_urls(url):
    with pytest.raises(SecurityError):
        validate_remote_file_url(url)


def test_accepts_public_https_url():
    url = "https://bucket.oss-cn-shanghai.aliyuncs.com/ocr-tmp/x.pdf?Expires=1&Signature=abc"
    assert validate_remote_file_url(url) == url


def test_redaction_hides_signature_and_account_numbers():
    url = "https://bucket.oss.aliyuncs.com/k.pdf?OSSAccessKeyId=AK123&Signature=secret"
    assert "secret" not in redact_url(url) and "AK123" not in redact_url(url)
    text = redact_text("ACCOUNT #: 01607-61186 url?Signature=abc&x-oss-credential=zzz")
    assert "01607-61186" not in text
    assert "Signature=***" in text and "zzz" not in text
