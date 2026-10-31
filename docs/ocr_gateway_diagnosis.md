# OCR gateway diagnosis (synthetic / public PDF only)

- Generated (UTC): `2026-10-30T10:21:42.381468+00:00`
- Public PDF URL host: `www.w3.org`
- OCR endpoint host: `gateway.pltplt.com`
- OSS configured: `True`
- OSS region set: `True`
- OSS bucket set: `True`
- OSS expire seconds: `1800`

No AccessKeys, secrets, or full signed URLs are included below.

## A. Public PDF download (control)
- HTTP status: `200`
- Size bytes: `13264`
- Content-Type: `application/pdf; qs=0.001`
- SHA256 (12): `3df79d34abbc`
- Elapsed ms: `1186`
- Starts with %PDF: `True`

## B. OCR with direct public URL (no query string)
- Result: `PASSED`
- HTTP: `200`
- Elapsed ms: `12000`
- data.list length: `1`
- URL has query params: `False`
- Wall clock ms: `12000`

## C. Same bytes via OSS signed URL → OCR
- OSS put: `PASSED` key_hash=`42eefca3255f` size=`13264`
- Signed URL shape: `{'scheme': 'https', 'host_suffix': 'oss-cn-shanghai.aliyuncs.com', 'path_has_prefix': True, 'query_param_count': 5, 'query_param_names': ['x-oss-credential', 'x-oss-date', 'x-oss-expires', 'x-oss-signature', 'x-oss-signature-version'], 'has_signature_param': True, 'has_expires_param': True, 'url_length': 380, 'redacted': 'https://shipping-billing-agent-2026.oss-cn-shanghai.aliyuncs.com/<redacted:98b509350b>'}`
- Expire configured seconds: `1800`
- Local signed GET: status=`200` bytes=`13264` content-type=`application/pdf` elapsed_ms=`2202`
- Body SHA match upload: `True`
- Unsigned GET (expect 403): `403`
- OCR via signed URL: `FAILED` code=`HTTP_ERROR` http=`504` elapsed_ms=`62561` wall_ms=`62561`
- message: `OCR HTTP 504: 504 Gateway Time-out 504 Gateway Time-out nginx/1.24.0 (Ubuntu)`
- OSS delete: `PASSED` key_hash=`42eefca3255f`

## D. Classification
- **OCR_GATEWAY_TIMEOUT_FETCHING_FILE**

### Evidence notes
- Direct public URL OCR: `PASSED` (elapsed_ms=`12000`)
- Signed URL OCR elapsed_ms: `62561`
- If local signed GET is 200 and direct OCR works, but signed-URL OCR returns nginx 504 after ~60s, the failure is most consistent with the OCR gateway failing to download the file (remote fetch stage), not with local signing.
- Signed URLs necessarily include query parameters (Expires/Signature/...). If the OCR gateway cannot fetch URLs with query strings, that would also explain the failure; this cannot be proven from the client alone without server-side logs.

## E. Short note for OCR service vendor

```
Subject: OCR gateway 504 when file= is an Aliyun OSS signed HTTPS URL

We POST to https://gateway.pltplt.com/ai/process with task=orderChange.
Control: file=<public HTTPS PDF without query string> → success (~15–20s).
Failing case: same PDF bytes uploaded to private Aliyun OSS (cn-shanghai),
file=<HTTPS GET signed URL with query params Expires/Signature/...> →
HTTP 504 Gateway Time-out from nginx after ~60–65s.

Client-side checks already done:
- Local GET of the same signed URL returns HTTP 200 quickly.
- Unsigned object URL returns 403 (bucket remains private).
- No PublicEndpointForbidden observed on the OSS public endpoint.
- Content-Type application/pdf; object size matches upload.

Please check whether your workers can egress to *.aliyuncs.com /
oss-cn-shanghai.aliyuncs.com and inspect worker/fetch logs for the
file= request that ends in nginx 504 after ~60s.
```

---

## F. Final minimal probe (2026-10-30, synthetic PDF only)

Source: `scripts/oss_ocr_final_probe.py` → `output/oss_ocr_final_probe.txt`  
No customer files; bucket remains private; no paid acceleration enabled.

| Check | Result |
|-------|--------|
| Public PDF OCR (no query) | PASSED ~10s |
| Public PDF OCR **with** `?diag=&x=` query | PASSED ~8s |
| OSS put + V4 signed URL shape | HTTPS; query params present; expire=1800; `OSS4-HMAC-SHA256` |
| Client JSON round-trip of `file=` | **equal to original** (no truncation / no double-encoding) |
| Local signed GET | 200, `application/pdf`, 0 redirects, body SHA match, ~2.5s |
| Unsigned object GET | 403 (private ACL intact) |
| OCR via OSS signed URL | **FAILED HTTP 504** ~63s (nginx Gateway Time-out) |

### What this proves / does not prove

- **Proved (client-side):** OSS upload/signing/private ACL/Content-Type are functional from this network; the URL passed to OCR is complete HTTPS with query; client did not truncate or double-encode; our client timeout (300s) is not the 504 source.
- **Proved:** “OCR cannot handle any URL with query string” is **not** sufficient as sole root cause (public PDF + query succeeded).
- **Not proved without OCR server logs:** whether the worker failed to download from `*.aliyuncs.com`, hit a host allowlist, stalled on OSS V4 auth fetch, or timed out in a later processing stage. The ~60s nginx 504 is consistent with an upstream fetch/proxy timeout, but stage attribution remains **inconclusive** from the client alone.

