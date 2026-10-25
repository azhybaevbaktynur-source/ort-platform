/**
 * Phase 7a S5: the fixed id of an assessment's quiz assignment (PHASE_7A_DESIGN 2.1, backend
 * `app/lms/assignments/ids.py`): uuid5(ASSIGN_NS, "assignment:assessment:{assessment_id}") with
 * ASSIGN_NS = uuid5(NAMESPACE_URL, "https://ort-platform/lms/assignments"). Pure, synchronous, no imports
 * (checked by quizAssignmentId.check.ts against the Python values).
 */

function sha1(bytes: Uint8Array): Uint8Array {
  const ml = bytes.length * 8;
  const withOne = bytes.length + 1;
  const padded = new Uint8Array(Math.ceil((withOne + 8) / 64) * 64);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padded.length - 8, Math.floor(ml / 0x100000000));
  view.setUint32(padded.length - 4, ml >>> 0);
  let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0;
  const w = new Uint32Array(80);
  const rotl = (x: number, n: number) => ((x << n) | (x >>> (32 - n))) >>> 0;
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getUint32(off + i * 4);
    for (let i = 16; i < 80; i++) w[i] = rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    for (let i = 0; i < 80; i++) {
      let f: number, k: number;
      if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
      else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
      else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
      else { f = b ^ c ^ d; k = 0xca62c1d6; }
      const tmp = (rotl(a, 5) + (f >>> 0) + e + k + w[i]) >>> 0;
      e = d; d = c; c = rotl(b, 30); b = a; a = tmp;
    }
    h0 = (h0 + a) >>> 0; h1 = (h1 + b) >>> 0; h2 = (h2 + c) >>> 0; h3 = (h3 + d) >>> 0; h4 = (h4 + e) >>> 0;
  }
  const out = new Uint8Array(20);
  const ov = new DataView(out.buffer);
  [h0, h1, h2, h3, h4].forEach((h, i) => ov.setUint32(i * 4, h));
  return out;
}

function uuidBytes(uuid: string): Uint8Array {
  const hex = uuid.replace(/-/g, "").toLowerCase();
  if (!/^[0-9a-f]{32}$/.test(hex)) throw new Error("invalid uuid");
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function fmtUuid(b: Uint8Array): string {
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
}

function utf8(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

export function uuid5(namespace: string, name: string): string {
  const ns = uuidBytes(namespace);
  const nm = utf8(name);
  const buf = new Uint8Array(ns.length + nm.length);
  buf.set(ns);
  buf.set(nm, ns.length);
  const hash = sha1(buf).slice(0, 16);
  hash[6] = (hash[6] & 0x0f) | 0x50;
  hash[8] = (hash[8] & 0x3f) | 0x80;
  return fmtUuid(hash);
}

const NAMESPACE_URL = "6ba7b811-9dad-11d1-80b4-00c04fd430c8";
export const ASSIGN_NS = uuid5(NAMESPACE_URL, "https://ort-platform/lms/assignments");

/** The quiz assignment id of an assessment (same value as the backend's `assignment_id_for`). */
export function quizAssignmentId(assessmentId: string): string {
  return uuid5(ASSIGN_NS, `assignment:assessment:${fmtUuid(uuidBytes(assessmentId))}`);
}
