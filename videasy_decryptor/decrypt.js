"use strict";
const fs  = require("fs");
const path = require("path");
const { webcrypto } = require("crypto");

const CONFIG = {
  wasmFile: "module1.wasm",
  hostname: "vidking.net",
};

function md5(data) {
  const len  = data.length;
  const pad  = len + 1 + ((len + 1) % 64 < 56 ? 56 - ((len + 1) % 64) : 120 - ((len + 1) % 64)) + 8;
  const buf  = new Uint8Array(pad);
  buf.set(data);
  buf[len] = 0x80;
  const dv  = new DataView(buf.buffer);
  dv.setUint32(pad - 8, (len * 8) & 0xffffffff, true);
  dv.setUint32(pad - 4, 0, true);
  let a = 0x67452301, b = 0xefcdab89, c = 0x98badcfe, d = 0x10325476;
  const S = [7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22,5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23,6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21];
  const K = Int32Array.from([0xd76aa478,0xe8c7b756,0x242070db,0xc1bdceee,0xf57c0faf,0x4787c62a,0xa8304613,0xfd469501,0x698098d8,0x8b44f7af,0xffff5bb1,0x895cd7be,0x6b901122,0xfd987193,0xa679438e,0x49b40821,0xf61e2562,0xc040b340,0x265e5a51,0xe9b6c7aa,0xd62f105d,0x02441453,0xd8a1e681,0xe7d3fbc8,0x21e1cde6,0xc33707d6,0xf4d50d87,0x455a14ed,0xa9e3e905,0xfcefa3f8,0x676f02d9,0x8d2a4c8a,0xfffa3942,0x8771f681,0x6d9d6122,0xfde5380c,0xa4beea44,0x4bdecfa9,0xf6bb4b60,0xbebfbc70,0x289b7ec6,0xeaa127fa,0xd4ef3085,0x04881d05,0xd9d4d039,0xe6db99e5,0x1fa27cf8,0xc4ac5665,0xf4292244,0x432aff97,0xab9423a7,0xfc93a039,0x655b59c3,0x8f0ccc92,0xffeff47d,0x85845dd1,0x6fa87e4f,0xfe2ce6e0,0xa3014314,0x4e0811a1,0xf7537e82,0xbd3af235,0x2ad7d2bb,0xeb86d391]);
  for (let off = 0; off < pad; off += 64) {
    let A = a, B = b, C = c, D = d;
    const M = new Int32Array(16);
    for (let i = 0; i < 16; i++) M[i] = buf[off+i*4] | (buf[off+i*4+1]<<8) | (buf[off+i*4+2]<<16) | (buf[off+i*4+3]<<24);
    for (let i = 0; i < 64; i++) {
      let f, g;
      if      (i < 16) { f = (B & C) | (~B & D); g = i; }
      else if (i < 32) { f = (D & B) | (~D & C); g = (5*i+1)%16; }
      else if (i < 48) { f = B ^ C ^ D;           g = (3*i+5)%16; }
      else             { f = C ^ (B | ~D);         g = (7*i)%16; }
      const t = D; D = C; C = B;
      B = (B + (((A+f+K[i]+M[g])<<S[i]) | ((A+f+K[i]+M[g])>>>(32-S[i])))) | 0;
      A = t;
    }
    a=(a+A)|0; b=(b+B)|0; c=(c+C)|0; d=(d+D)|0;
  }
  const out = new Uint8Array(16);
  for (let i = 0; i < 4; i++) { out[i]=a>>>(i*8); out[i+4]=b>>>(i*8); out[i+8]=c>>>(i*8); out[i+12]=d>>>(i*8); }
  return out;
}

function evpBytesToKey(salt, password = "", keySize = 32, ivSize = 16) {
  const pw = new TextEncoder().encode(password);
  let hash = new Uint8Array(0);
  let derived = new Uint8Array(0);
  while (derived.length < keySize + ivSize) {
    const input = new Uint8Array(hash.length + pw.length + salt.length);
    input.set(hash); input.set(pw, hash.length); input.set(salt, hash.length + pw.length);
    hash = md5(input);
    const tmp = new Uint8Array(derived.length + hash.length);
    tmp.set(derived); tmp.set(hash, derived.length);
    derived = tmp;
  }
  return { key: derived.slice(0, keySize), iv: derived.slice(keySize, keySize + ivSize) };
}

async function aesDecrypt(base64Data) {
  const bin = atob(base64Data);
  const raw = Uint8Array.from(bin, c => c.charCodeAt(0));
  if (raw.length < 16 || new TextDecoder().decode(raw.slice(0, 8)) !== "Salted__")
    throw new Error("Unexpected WASM output format (not OpenSSL salted)");
  const salt       = raw.slice(8, 16);
  const ciphertext = raw.slice(16);
  const { key, iv } = evpBytesToKey(salt);
  const cryptoKey  = await webcrypto.subtle.importKey("raw", key, { name: "AES-CBC" }, false, ["decrypt"]);
  const pt         = await webcrypto.subtle.decrypt({ name: "AES-CBC", iv }, cryptoKey, ciphertext);
  return new TextDecoder().decode(pt);
}

function patchPow(code) {
  const primary = code.replace(/_0x24\(\),_0x36\(/g, "_0x36(");
  if (primary !== code) return primary;
  const cutoff = Math.max(0, code.length - 2000);
  const tail   = code.slice(cutoff).replace(/_0x[a-f0-9]+\(\),(_0x[a-f0-9]+\()/g, "$1");
  return code.slice(0, cutoff) + tail;
}

let _wasmModule = null;

async function loadWasm() {
  if (_wasmModule) return _wasmModule;
  const wasmBytes = fs.readFileSync(path.join(__dirname, CONFIG.wasmFile));
  const { instance } = await WebAssembly.instantiate(wasmBytes, {
    env: { seed: () => Date.now() * Math.random(), abort() {} },
  });
  const exp = instance.exports;
  const mem = exp.memory;

  function readStr(ptr) {
    ptr = ptr >>> 0;
    if (!ptr) return null;
    const u32 = new Uint32Array(mem.buffer);
    const u16 = new Uint16Array(mem.buffer);
    const end = (ptr + u32[(ptr - 4) >>> 2]) >>> 1;
    let n = ptr >>> 1, s = "";
    while (end - n > 1024) s += String.fromCharCode(...u16.subarray(n, n += 1024));
    return s + String.fromCharCode(...u16.subarray(n, end));
  }

  function writeStr(str) {
    const ptr = exp.__new(str.length << 1, 2) >>> 0;
    const u16 = new Uint16Array(mem.buffer);
    for (let i = 0; i < str.length; i++) u16[(ptr >>> 1) + i] = str.charCodeAt(i);
    return ptr;
  }

  _wasmModule = {
    serve:   ()       => readStr(exp.serve()),
    verify:  (h)      => exp.verify(writeStr(h)) !== 0,
    decrypt: (ct, id) => readStr(exp.decrypt(writeStr(ct), parseInt(id))),
  };
  return _wasmModule;
}

let _cachedHash = null;

async function getHash(wasm) {
  if (_cachedHash) return _cachedHash;
  const patched = patchPow(wasm.serve());
  const fakeWin = {
    location: { hostname: CONFIG.hostname, href: `https://www.${CONFIG.hostname}/` },
    hash: undefined,
  };
  new Function("window", "crypto", "TextEncoder", patched)(fakeWin, webcrypto, TextEncoder);
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 100));
    if (fakeWin.hash !== undefined) break;
  }
  const hash = String(fakeWin.hash);
  if (!hash || hash === "undefined") throw new Error("serve() did not set window.hash");
  _cachedHash = hash;
  return hash;
}

async function decrypt(ciphertextHex, tmdbId) {
  const wasm = await loadWasm();
  const hash = await getHash(wasm);
  if (!wasm.verify(hash)) throw new Error("WASM verify() failed");
  const intermediate = wasm.decrypt(ciphertextHex, tmdbId);
  if (!intermediate) throw new Error("WASM decrypt() returned null");
  const plaintext = await aesDecrypt(intermediate);
  return JSON.parse(plaintext);
}

if (require.main === module) {
  const [,, ciphertextHex, tmdbId] = process.argv;
  decrypt(ciphertextHex, tmdbId)
    .then(data  => console.log(JSON.stringify({ success: true,  data  })))
    .catch(err  => console.log(JSON.stringify({ success: false, error: err.message })));
}

module.exports = { decrypt };
