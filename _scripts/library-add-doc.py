#!/usr/bin/env python3
"""Add or update one document in library/blob.json (macOS/Linux counterpart of build-library.ps1).

Decrypts the existing blob with your passphrase, inserts the doc, re-encrypts.
Plaintext never touches disk and the passphrase is prompted, never passed as an argument.

Usage:
  python3 _scripts/library-add-doc.py path/to/doc.html --id home-server --title "Home Server Guide" \
      --desc "What the Mac runs and how to fix the internet if it breaks." [--blob library/blob.json]

If the HTML file contains <!-- DOC START --> / <!-- DOC END --> markers, only the content
between them is stored (lets one file double as a standalone page and a library doc).
An existing doc with the same id is replaced; otherwise the doc is appended.
"""
import argparse, base64, datetime, getpass, hashlib, hmac, json, os, re, sys

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ITER = 310000


def derive(passphrase: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations, dklen=64)


def decrypt(blob: dict, keys: bytes) -> dict:
    iv, ct = base64.b64decode(blob["iv"]), base64.b64decode(blob["ct"])
    mac = hmac.new(keys[32:], iv + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, base64.b64decode(blob["mac"])):
        sys.exit("Passphrase did not verify against the existing blob. Nothing changed.")
    dec = Cipher(algorithms.AES(keys[:32]), modes.CBC(iv)).decryptor()
    padded = dec.update(ct) + dec.finalize()
    return json.loads(padded[: -padded[-1]].decode())


def encrypt(payload: dict, passphrase: str, old: dict) -> dict:
    # Reuse the existing salt/iter: the derived key bits must stay stable so the
    # enrolled security keys in "keys" (which wrap those bits) keep working.
    salt, iv = base64.b64decode(old["salt"]), os.urandom(16)
    iters = old.get("iter", ITER)
    keys = derive(passphrase, salt, iters)
    plain = json.dumps(payload, ensure_ascii=False).encode()
    pad = 16 - len(plain) % 16
    enc = Cipher(algorithms.AES(keys[:32]), modes.CBC(iv)).encryptor()
    ct = enc.update(plain + bytes([pad]) * pad) + enc.finalize()
    mac = hmac.new(keys[32:], iv + ct, hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode()
    out = {"v": 1, "iter": iters, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct), "mac": b64(mac)}
    if old.get("keys"):
        out["keys"] = old["keys"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html_file")
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--desc", default="")
    ap.add_argument("--updated", default=datetime.date.today().isoformat())
    ap.add_argument("--blob", default=os.path.expanduser("~/Server/library/blob.json"))
    args = ap.parse_args()

    with open(args.html_file, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"<!-- DOC START -->(.*)<!-- DOC END -->", html, re.S)
    if m:
        html = m.group(1).strip()

    with open(args.blob, encoding="utf-8") as f:
        blob = json.load(f)
    passphrase = getpass.getpass("Library passphrase: ")
    payload = decrypt(blob, derive(passphrase, base64.b64decode(blob["salt"]), blob["iter"]))

    doc = {"id": args.id, "title": args.title, "desc": args.desc, "updated": args.updated, "html": html}
    docs = payload.setdefault("docs", [])
    idx = next((i for i, d in enumerate(docs) if d.get("id") == args.id), None)
    if idx is not None:
        docs[idx] = doc
        action = "replaced"
    else:
        docs.append(doc)
        action = "added"

    with open(args.blob, "w", encoding="utf-8") as f:
        json.dump(encrypt(payload, passphrase, blob), f, indent=2)
        f.write("\n")
    print(f"{action} doc '{args.id}' ({len(html)} bytes html); {args.blob} now holds {len(docs)} doc(s)")


if __name__ == "__main__":
    main()
