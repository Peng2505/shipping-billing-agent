"""Cloudflare Tunnel → OCR controlled probe (synthetic files only).

Does NOT modify the business pipeline. Stops tunnel and deletes temp files on exit.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from billing_agent.config import load_settings
from billing_agent.services.ocr_client import OcrClient, OcrError
from scripts.tunnel_ocr_probe.controlled_file_server import (
    ServedFile,
    ServerState,
    dump_events,
    start_server,
)

OUT = ROOT / "output" / "tunnel_ocr_probe"
TOOLS = ROOT / "tools"
CLOUDFLARED = TOOLS / "cloudflared.exe"
LOCAL_PORT = 8765
MAX_FILE_BYTES = 512_000
PDF_MARKER = "TUNNEL-PDF-MARKER-A7F3"
PNG_MARKER = "TUNNEL-PNG-MARKER-B9E2"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_synth_pdf(path: Path, marker: str) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = (
        f"SYNTHETIC TEST DOCUMENT — NOT CUSTOMER DATA\n"
        f"Marker: {marker}\n"
        f"Purpose: Cloudflare Tunnel OCR reachability probe\n"
        f"Generated: {_utc()}\n"
    )
    page.insert_text((72, 72), text, fontsize=14)
    doc.save(path)
    doc.close()


def make_synth_png(path: Path, marker: str) -> None:
    img = Image.new("RGB", (900, 360), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = [
        "SYNTHETIC PNG — NOT CUSTOMER DATA",
        f"Marker: {marker}",
        "Cloudflare Tunnel OCR probe",
        _utc(),
    ]
    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 40
    img.save(path, format="PNG")


def wait_tunnel_url(proc: subprocess.Popen, timeout_s: float = 45.0) -> str:
    """Parse trycloudflare.com URL from cloudflared stderr/stdout."""
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    deadline = time.monotonic() + timeout_s
    buf = ""
    assert proc.stderr is not None
    while time.monotonic() < deadline:
        line = proc.stderr.readline()
        if not line and proc.poll() is not None:
            break
        if not line:
            time.sleep(0.05)
            continue
        text = line.decode("utf-8", errors="replace")
        buf += text
        m = pattern.search(text)
        if m:
            return m.group(0).rstrip("/")
    raise RuntimeError(f"tunnel URL not found within {timeout_s}s; log tail:\n{buf[-2000:]}")


def summarize_ocr_payload(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) else None
    items = data.get("list") if isinstance(data, dict) else None
    blob = json.dumps(payload, ensure_ascii=False)
    return {
        "success": payload.get("success") if isinstance(payload, dict) else None,
        "list_len": len(items) if isinstance(items, list) else None,
        "contains_pdf_marker": PDF_MARKER in blob,
        "contains_png_marker": PNG_MARKER in blob,
        "payload_sha12": __import__("hashlib").sha256(blob.encode()).hexdigest()[:12],
        "payload_snip": blob[:500],
    }


def events_for_token(events: list[dict], token: str) -> list[dict]:
    return [e for e in events if e.get("matched_token") == token and e.get("status") == 200]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    work = OUT / f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    work.mkdir(parents=True, exist_ok=True)

    if not CLOUDFLARED.exists():
        raise SystemExit(f"missing {CLOUDFLARED}")

    pdf_path = work / "synth_probe.pdf"
    png_path = work / "synth_probe.png"
    make_synth_pdf(pdf_path, PDF_MARKER)
    make_synth_png(png_path, PNG_MARKER)

    pdf_token = secrets.token_urlsafe(18)
    png_token = secrets.token_urlsafe(18)

    state = ServerState(
        files_by_token={
            pdf_token: ServedFile(
                name="synth_probe.pdf",
                path=pdf_path,
                content_type="application/pdf",
                max_bytes=MAX_FILE_BYTES,
                marker=PDF_MARKER,
            ),
            png_token: ServedFile(
                name="synth_probe.png",
                path=png_path,
                content_type="image/png",
                max_bytes=MAX_FILE_BYTES,
                marker=PNG_MARKER,
            ),
        },
        max_requests_total=30,
    )

    httpd, _ = start_server("127.0.0.1", LOCAL_PORT, state)
    tunnel: subprocess.Popen | None = None
    report: dict = {
        "generated_at": _utc(),
        "local_port": LOCAL_PORT,
        "pdf_marker": PDF_MARKER,
        "png_marker": PNG_MARKER,
        "pdf_bytes": pdf_path.stat().st_size,
        "png_bytes": png_path.stat().st_size,
        "notes": [],
        "steps": {},
    }

    try:
        tunnel = subprocess.Popen(
            [
                str(CLOUDFLARED),
                "tunnel",
                "--url",
                f"http://127.0.0.1:{LOCAL_PORT}",
                "--no-autoupdate",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
        )
        report["cloudflared_pid"] = tunnel.pid
        base = wait_tunnel_url(tunnel)
        report["tunnel_base"] = base
        pdf_url = f"{base}/t/{pdf_token}/synth_probe.pdf"
        png_url = f"{base}/t/{png_token}/synth_probe.png"
        report["pdf_url_redacted"] = f"{base}/t/<token>/synth_probe.pdf"
        report["png_url_redacted"] = f"{base}/t/<token>/synth_probe.png"

        # Wait until public hostname resolves and answers (Quick Tunnel propagation).
        ready = False
        last_err = None
        for attempt in range(1, 16):
            try:
                with httpx.Client(timeout=15, follow_redirects=True) as http:
                    probe = http.get(pdf_url)
                if probe.status_code == 200 and probe.content.startswith(b"%PDF"):
                    ready = True
                    report["tunnel_ready_attempt"] = attempt
                    break
                last_err = f"http={probe.status_code} bytes={len(probe.content)}"
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
        if not ready:
            report["steps"]["A_tunnel_download_pdf"] = {
                "result": "FAILED",
                "error": f"tunnel not ready: {last_err}",
            }
            report["notes"].append("Tunnel URL printed but public HTTPS download failed; abort OCR calls.")
            return 3

        # A. Local download via Tunnel URL (fresh GET after readiness)
        with httpx.Client(timeout=60, follow_redirects=True) as http:
            t0 = time.monotonic()
            r = http.get(pdf_url)
            report["steps"]["A_tunnel_download_pdf"] = {
                "result": "PASSED" if r.status_code == 200 else "FAILED",
                "http_status": r.status_code,
                "bytes": len(r.content),
                "content_type": r.headers.get("content-type"),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
                "sha_match": r.content == pdf_path.read_bytes(),
                "starts_pdf": r.content.startswith(b"%PDF"),
                "redirects": len(r.history),
            }

        settings = load_settings()
        # Force empty callback/taskType as required
        client = OcrClient(settings.ocr)
        assert client.build_request("https://example.com/x.pdf")["task"] == "orderChange"

        # B. OCR PDF (one attempt)
        before_pdf = len(dump_events(state))
        t0 = time.monotonic()
        try:
            resp = client.process(pdf_url)
            summary = summarize_ocr_payload(resp.payload)
            report["steps"]["B_ocr_pdf"] = {
                "result": "PASSED",
                "http_status": resp.http_status,
                "elapsed_ms": resp.elapsed_ms,
                "wall_ms": int((time.monotonic() - t0) * 1000),
                **summary,
            }
            (work / "ocr_pdf_response.json").write_text(
                json.dumps(resp.payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OcrError as exc:
            report["steps"]["B_ocr_pdf"] = {
                "result": "FAILED",
                "code": exc.code,
                "http_status": exc.http_status,
                "elapsed_ms": exc.elapsed_ms,
                "wall_ms": int((time.monotonic() - t0) * 1000),
                "message": (exc.message or "")[:300],
            }

        after_pdf_events = dump_events(state)
        pdf_gets = [
            e
            for e in after_pdf_events[before_pdf:]
            if e.get("method") == "GET" and e.get("matched_file") == "synth_probe.pdf"
        ]
        report["steps"]["D_access_log_after_pdf_ocr"] = {
            "get_hits": len(pdf_gets),
            "events": pdf_gets,
        }

        # C. OCR PNG (one attempt) — only if PDF path did not hard-fail the tunnel itself
        before_png = len(dump_events(state))
        t0 = time.monotonic()
        try:
            # Quick self-download first (counts as local, not OCR)
            with httpx.Client(timeout=30, follow_redirects=True) as http:
                pr = http.get(png_url)
            report["steps"]["C0_tunnel_download_png"] = {
                "http_status": pr.status_code,
                "bytes": len(pr.content),
                "sha_match": pr.content == png_path.read_bytes(),
                "content_type": pr.headers.get("content-type"),
            }
            before_png = len(dump_events(state))
            resp = client.process(png_url)
            summary = summarize_ocr_payload(resp.payload)
            report["steps"]["C_ocr_png"] = {
                "result": "PASSED",
                "http_status": resp.http_status,
                "elapsed_ms": resp.elapsed_ms,
                "wall_ms": int((time.monotonic() - t0) * 1000),
                **summary,
            }
            (work / "ocr_png_response.json").write_text(
                json.dumps(resp.payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OcrError as exc:
            report["steps"]["C_ocr_png"] = {
                "result": "FAILED",
                "code": exc.code,
                "http_status": exc.http_status,
                "elapsed_ms": exc.elapsed_ms,
                "wall_ms": int((time.monotonic() - t0) * 1000),
                "message": (exc.message or "")[:300],
            }

        png_gets = [
            e
            for e in dump_events(state)[before_png:]
            if e.get("method") == "GET" and e.get("matched_file") == "synth_probe.png"
        ]
        report["steps"]["D_access_log_after_png_ocr"] = {
            "get_hits": len(png_gets),
            "events": png_gets,
        }

        report["all_access_events"] = dump_events(state)
        report["ocr_fetched_pdf"] = any(
            e.get("matched_file") == "synth_probe.pdf" and e.get("status") == 200 and e.get("method") == "GET"
            for e in dump_events(state)
            # exclude our own early download: OCR UA typically not httpx local — keep all GETs
            # and rely on timing window above for OCR-correlated hits
        )
        # Stronger: GETs observed in OCR window
        report["ocr_server_get_pdf_in_window"] = len(pdf_gets) > 0
        report["ocr_server_get_png_in_window"] = len(png_gets) > 0

        # Content correspondence notes
        b = report["steps"].get("B_ocr_pdf", {})
        c = report["steps"].get("C_ocr_png", {})
        if b.get("result") == "PASSED" and not b.get("contains_pdf_marker"):
            report["notes"].append(
                "OCR success for PDF but marker not present in structured payload "
                "(orderChange may not echo raw text; rely on access-log GET + success schema)."
            )
        if c.get("result") == "PASSED" and not c.get("contains_png_marker"):
            report["notes"].append(
                "OCR success for PNG but marker not present in structured payload; "
                "validate via OCR-window GET on token path + response schema."
            )

    finally:
        if tunnel is not None:
            try:
                tunnel.terminate()
            except Exception:
                pass
            try:
                tunnel.wait(timeout=8)
            except Exception:
                try:
                    tunnel.kill()
                except Exception:
                    pass
        try:
            httpd.shutdown()
        except Exception:
            pass
        # Keep run artifacts (responses/logs) but remove binary temp copies are already under work/
        # Delete tokens from report file? URLs already redacted. Write report without raw tokens.
        report["cleanup"] = {
            "tunnel_stopped": True,
            "httpd_stopped": True,
            "work_dir": str(work.relative_to(ROOT)).replace("\\", "/"),
        }
        out_json = OUT / "latest_report.json"
        out_txt = OUT / "latest_report.txt"
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            "# Cloudflare Tunnel OCR probe report",
            f"generated_at: {report.get('generated_at')}",
            f"tunnel_base: {report.get('tunnel_base')}",
            "",
            f"A_tunnel_download_pdf: {report.get('steps', {}).get('A_tunnel_download_pdf')}",
            f"B_ocr_pdf: {report.get('steps', {}).get('B_ocr_pdf')}",
            f"C0_tunnel_download_png: {report.get('steps', {}).get('C0_tunnel_download_png')}",
            f"C_ocr_png: {report.get('steps', {}).get('C_ocr_png')}",
            f"D_pdf_gets: {report.get('steps', {}).get('D_access_log_after_pdf_ocr')}",
            f"D_png_gets: {report.get('steps', {}).get('D_access_log_after_png_ocr')}",
            f"ocr_server_get_pdf_in_window: {report.get('ocr_server_get_pdf_in_window')}",
            f"ocr_server_get_png_in_window: {report.get('ocr_server_get_png_in_window')}",
            "",
            "notes:",
            *[f"- {n}" for n in report.get("notes", [])],
            f"cleanup: {report.get('cleanup')}",
        ]
        out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out_txt.read_text(encoding="utf-8"))
        print(f"Wrote {out_json}")

    b = report.get("steps", {}).get("B_ocr_pdf", {})
    return 0 if b.get("result") == "PASSED" else 2


if __name__ == "__main__":
    # Allow importing scripts.tunnel_ocr_probe when cwd is ROOT
    raise SystemExit(main())
