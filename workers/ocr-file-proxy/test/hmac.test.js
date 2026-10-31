/**
 * Cross-check with billing_agent/services/hmac_url.py
 */
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import test from "node:test";
import { computeSig, encodeKeyPath, verifySig } from "../src/hmac.js";

const SECRET = "test-hmac-secret-for-vector-only";
const KEY = "ocr-tmp/20261030/abcd1234ef.pdf";
const EXP = 1761868800;

test("encodeKeyPath preserves slashes and encodes spaces", () => {
  assert.equal(encodeKeyPath(KEY), KEY);
  assert.equal(encodeKeyPath("ocr-tmp/a b.pdf"), "ocr-tmp/a%20b.pdf");
});

test("computeSig matches Node crypto and Python HMAC-SHA256", async () => {
  const sig = await computeSig(SECRET, KEY, EXP);
  const ref = createHmac("sha256", SECRET).update(`${KEY}\n${EXP}`, "utf8").digest("hex");
  assert.equal(sig, ref);
});

test("verifySig accepts valid and rejects expired/bad", async () => {
  const sig = await computeSig(SECRET, KEY, EXP);
  assert.equal(await verifySig(SECRET, KEY, EXP, sig, EXP - 10), null);
  assert.equal(await verifySig(SECRET, KEY, EXP, sig, EXP + 1), "expired");
  assert.equal(await verifySig(SECRET, KEY, EXP, "00".repeat(32), EXP - 1), "bad_sig");
});
