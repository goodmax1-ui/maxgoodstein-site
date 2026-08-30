#!/usr/bin/env python3
"""Add or update one quick link in library/blob.json (shown under "Apartment server" on the shelf).

Decrypts the existing blob with your passphrase, inserts the link, re-encrypts.
Plaintext never touches disk and the passphrase is prompted, never passed as an argument.

Usage:
  python3 _scripts/library-add-link.py --id jellyfin --title Jellyfin \
      --addr "Tailscale=http://100.117.16.114:8096" --addr "Home wifi=http://192.168.0.137:8096" \
      [--desc "note shown under the title"] [--blob library/blob.json] [--remove]

Each --addr is Label=URL and renders as its own row with a Copy button.
An existing link with the same id is replaced; otherwise the link is appended.
--remove deletes the link with that id instead.
"""
import argparse, base64, getpass, hashlib, hmac, json, os, sys

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


def encrypt(payload: dict, passphrase: str) -> dict:
    salt, iv = os.urandom(32), os.urandom(16)
    keys = derive(passphrase, salt, ITER)
    plain = json.dumps(payload, ensure_ascii=False).encode()
    pad = 16 - len(plain) % 16
    enc = Cipher(algorithms.AES(keys[:32]), modes.CBC(iv)).encryptor()
    ct = enc.update(plain + bytes([pad]) * pad) + enc.finalize()
    mac = hmac.new(keys[32:], iv + ct, hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "iter": ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct), "mac": b64(mac)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--title")
    ap.add_argument("--addr", action="append", default=[], metavar="LABEL=URL")
    ap.add_argument("--desc", default="")
    ap.add_argument("--blob", default="library/blob.json")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    if not args.remove and not (args.title and args.addr):
        ap.error("--title and at least one --addr are required unless --remove is given")
    addrs = []
    for spec in args.addr:
        label, sep, url = spec.partition("=")
        if not sep or not url:
            ap.error(f"--addr must be LABEL=URL, got: {spec!r}")
        addrs.append({"label": label, "url": url})

    with open(args.blob, encoding="utf-8") as f:
        blob = json.load(f)
    passphrase = getpass.getpass("Library passphrase: ")
    payload = decrypt(blob, derive(passphrase, base64.b64decode(blob["salt"]), blob["iter"]))

    links = payload.setdefault("links", [])
    idx = next((i for i, l in enumerate(links) if l.get("id") == args.id), None)
    if args.remove:
        if idx is None:
            sys.exit(f"No link with id '{args.id}'. Nothing changed.")
        links.pop(idx)
        action = "removed"
    else:
        link = {"id": args.id, "title": args.title, "addrs": addrs, "desc": args.desc}
        if idx is not None:
            links[idx] = link
            action = "replaced"
        else:
            links.append(link)
            action = "added"

    with open(args.blob, "w", encoding="utf-8") as f:
        json.dump(encrypt(payload, passphrase), f, indent=2)
        f.write("\n")
    print(f"{action} link '{args.id}'; {args.blob} now holds {len(links)} link(s)")


if __name__ == "__main__":
    main()
