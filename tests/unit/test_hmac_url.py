"""HMAC URL contract — must match workers/ocr-file-proxy/src/hmac.js."""

from __future__ import annotations

import hashlib
import hmac

from billing_agent.services.hmac_url import (
    build_signed_get_url,
    compute_sig,
    encode_key_path,
    is_safe_object_key,
    sign_message,
    verify_sig,
)

SECRET = "test-hmac-secret-for-vector-only"
KEY = "ocr-tmp/20261030/abcd1234ef.pdf"
EXP = 1761868800


def test_sign_message_format():
    assert sign_message(KEY, EXP) == f"{KEY}\n{EXP}"


def test_compute_sig_fixed_vector():
    expected = hmac.new(
        SECRET.encode(),
        f"{KEY}\n{EXP}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert compute_sig(SECRET, KEY, EXP) == expected
    # Pin for Worker cross-check docs:
    assert len(expected) == 64


def test_encode_key_path_preserves_slashes():
    assert encode_key_path(KEY) == KEY
    assert encode_key_path("ocr-tmp/a b.pdf") == "ocr-tmp/a%20b.pdf"


def test_build_signed_get_url():
    url = build_signed_get_url("https://example.workers.dev", KEY, secret=SECRET, exp=EXP)
    assert url.startswith("https://example.workers.dev/o/ocr-tmp/20261030/abcd1234ef.pdf?")
    assert f"exp={EXP}" in url
    assert f"sig={compute_sig(SECRET, KEY, EXP)}" in url


def test_verify_sig_ok_and_failures():
    sig = compute_sig(SECRET, KEY, EXP)
    assert verify_sig(SECRET, KEY, EXP, sig, now=EXP - 5) is None
    assert verify_sig(SECRET, KEY, EXP, sig, now=EXP + 1) == "expired"
    assert verify_sig(SECRET, KEY, EXP, "ab" * 32, now=EXP - 1) == "bad_sig"
    assert verify_sig(SECRET, KEY, EXP, "", now=EXP - 1) == "missing_sig"
    assert verify_sig(SECRET, KEY, "nope", sig, now=EXP - 1) == "bad_exp"


def test_is_safe_object_key_rejects_traversal_and_bad_suffix():
    assert is_safe_object_key(KEY)
    assert not is_safe_object_key("../ocr-tmp/x.pdf")
    assert not is_safe_object_key("ocr-tmp/../secret.pdf")
    assert not is_safe_object_key("/ocr-tmp/x.pdf")
    assert not is_safe_object_key("ocr-tmp/x.exe")
    assert not is_safe_object_key("other/x.pdf")
