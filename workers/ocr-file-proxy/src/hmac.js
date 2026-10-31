/**
 * HMAC helpers — must stay aligned with billing_agent/services/hmac_url.py
 *
 * message = `${key}\n${exp}`
 * sig     = hex(HMAC_SHA256(secret, message))  // lowercase
 */

/** Per-segment encodeURIComponent, preserve '/' (matches Python quote(key, safe='/')). */
export function encodeKeyPath(key) {
  return key
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}

export function decodeKeyPath(encoded) {
  return encoded
    .split("/")
    .map((part) => decodeURIComponent(part))
    .join("/");
}

export async function computeSig(secret, key, exp) {
  const message = `${key}\n${exp}`;
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sigBuf = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(message));
  return bufferToHex(sigBuf);
}

export async function verifySig(secret, key, exp, sig, nowSec) {
  if (!sig || typeof sig !== "string") return "missing_sig";
  if (!/^[0-9a-fA-F]{64}$/.test(sig)) return "bad_sig_format";
  const expNum = Number(exp);
  if (!Number.isFinite(expNum) || !Number.isInteger(expNum)) return "bad_exp";
  if (expNum < nowSec) return "expired";
  const expected = await computeSig(secret, key, expNum);
  if (!timingSafeEqualHex(expected, sig.toLowerCase())) return "bad_sig";
  return null;
}

function bufferToHex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqualHex(a, b) {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i += 1) {
    out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return out === 0;
}
