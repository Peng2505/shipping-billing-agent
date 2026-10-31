/**
 * Private R2 file proxy for OCR file= URLs.
 * - PUT/DELETE /admin/objects/<urlencoded-key>  (Bearer UPLOAD_TOKEN)
 * - GET /o/<urlencoded-key>?exp=&sig=           (HMAC, no custom header)
 *
 * Bucket stays private via R2 binding (OCR_BUCKET). Never redirect to a public R2 URL.
 */

import { decodeKeyPath, verifySig } from "./hmac.js";

const DEFAULT_PREFIX = "ocr-tmp/";
const ALLOWED_SUFFIXES = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"];
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (err) {
      console.error("worker_error", err && err.message ? err.message : String(err));
      return json(500, { error: "internal_error" });
    }
  },
};

async function handle(request, env) {
  const url = new URL(request.url);
  const path = url.pathname;

  if (request.method === "PUT" && path.startsWith("/admin/objects/")) {
    return putObject(request, env, path.slice("/admin/objects/".length));
  }
  if (request.method === "DELETE" && path.startsWith("/admin/objects/")) {
    return deleteObject(request, env, path.slice("/admin/objects/".length));
  }
  if (request.method === "GET" && path.startsWith("/o/")) {
    return getObject(request, env, path.slice("/o/".length), url);
  }
  if (request.method === "GET" && path === "/health") {
    return json(200, { ok: true });
  }
  return json(404, { error: "not_found" });
}

function prefix(env) {
  const p = (env.KEY_PREFIX || DEFAULT_PREFIX).replace(/^\/+/, "");
  return p.endsWith("/") ? p : `${p}/`;
}

function isSafeKey(key, pref) {
  if (!key || typeof key !== "string") return false;
  if (key.includes("\\") || key.startsWith("/")) return false;
  const parts = key.split("/");
  if (parts.some((part) => part === "" || part === "." || part === "..")) return false;
  if (parts.includes("..")) return false;
  if (!key.startsWith(pref)) return false;
  const lower = key.toLowerCase();
  return ALLOWED_SUFFIXES.some((sfx) => lower.endsWith(sfx));
}

function decodeKeyOrNull(encoded) {
  try {
    if (!encoded) return null;
    return decodeKeyPath(encoded);
  } catch {
    return null;
  }
}

async function requireUploadAuth(request, env) {
  const header = request.headers.get("Authorization") || "";
  const expected = `Bearer ${env.UPLOAD_TOKEN || ""}`;
  if (!env.UPLOAD_TOKEN || header !== expected) {
    return json(401, { error: "unauthorized" });
  }
  return null;
}

async function putObject(request, env, encodedKey) {
  const denied = await requireUploadAuth(request, env);
  if (denied) return denied;

  const key = decodeKeyOrNull(encodedKey);
  const pref = prefix(env);
  if (!key || !isSafeKey(key, pref)) {
    return json(400, { error: "invalid_key" });
  }

  const lenHeader = request.headers.get("Content-Length");
  if (lenHeader && Number(lenHeader) > MAX_UPLOAD_BYTES) {
    return json(413, { error: "too_large" });
  }

  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_UPLOAD_BYTES) {
    return json(413, { error: "too_large" });
  }

  const contentType =
    request.headers.get("Content-Type") || guessContentType(key) || "application/octet-stream";

  await env.OCR_BUCKET.put(key, body, {
    httpMetadata: { contentType },
  });

  // Do not log secrets or full URLs.
  const keyHash = await shortHash(key);
  console.log("put_ok", keyHash, body.byteLength);
  return json(200, { ok: true, key_hash: keyHash, bytes: body.byteLength });
}

async function deleteObject(request, env, encodedKey) {
  const denied = await requireUploadAuth(request, env);
  if (denied) return denied;

  const key = decodeKeyOrNull(encodedKey);
  const pref = prefix(env);
  if (!key || !isSafeKey(key, pref)) {
    return json(400, { error: "invalid_key" });
  }

  await env.OCR_BUCKET.delete(key);
  console.log("delete_ok", await shortHash(key));
  return json(200, { ok: true });
}

async function getObject(request, env, encodedKey, url) {
  const key = decodeKeyOrNull(encodedKey);
  const pref = prefix(env);
  if (!key || !isSafeKey(key, pref)) {
    return json(400, { error: "invalid_key" });
  }

  const exp = url.searchParams.get("exp");
  const sig = url.searchParams.get("sig");
  const nowSec = Math.floor(Date.now() / 1000);
  const reason = await verifySig(env.HMAC_SECRET || "", key, exp, sig, nowSec);
  if (reason === "expired") {
    return json(401, { error: "expired" });
  }
  if (reason) {
    return json(403, { error: reason });
  }

  const obj = await env.OCR_BUCKET.get(key);
  if (!obj) {
    return json(404, { error: "not_found" });
  }

  const contentType =
    (obj.httpMetadata && obj.httpMetadata.contentType) ||
    guessContentType(key) ||
    "application/octet-stream";

  const headers = new Headers();
  headers.set("Content-Type", contentType);
  headers.set("Cache-Control", "no-store");
  if (obj.size != null) {
    headers.set("Content-Length", String(obj.size));
  }

  console.log("get_ok", await shortHash(key));
  // Stream body directly — never Response.redirect to a public R2 URL.
  return new Response(obj.body, { status: 200, headers });
}

function guessContentType(key) {
  const lower = key.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".tif") || lower.endsWith(".tiff")) return "image/tiff";
  return null;
}

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

async function shortHash(value) {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return bufferToHex(digest).slice(0, 12);
}

function bufferToHex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
