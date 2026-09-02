#!/usr/bin/env python3
"""Convert Supernote .note files into a PDF for Paperless and a transcript for Anytype.

Runs from launchd against the directory the Supernote writes to over WebDAV.
For each new .note file it produces:

    <work>/pdf/<stem>.pdf   archival render, copied into the Paperless consume dir
    <work>/txt/<stem>.txt   transcript, when the note carries a recognition layer
    <work>/meta/<stem>.json sidecar describing both, for the Anytype step

Conversion is delegated to supernotelib (`pip install supernotelib`), which
reads the text layer the device writes when Real-time Recognition is enabled.
Without that layer the .txt comes out empty: Tesseract, which Paperless uses,
is built for printed text and does poorly on handwriting, so the transcript
has to come from the device rather than from OCR afterwards.

Files already handled are tracked in a manifest keyed by path, size and mtime,
so a re-run is cheap and an edited note is picked up again.

    supernote_ingest.py --inbox ~/pipelines/inbox/supernote \
                        --work  ~/pipelines/work/supernote \
                        --paperless-consume ~/paperless/consume
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

MANIFEST = "manifest.json"


def run(cmd):
    """Run a command, returning (ok, combined output)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        return False, "%s: not installed" % cmd[0]
    except subprocess.TimeoutExpired:
        return False, "%s: timed out" % cmd[0]
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


def fingerprint(path):
    """Identify a file by size and mtime -- cheap, and enough to spot an edit."""
    st = os.stat(path)
    return "%d:%d" % (st.st_size, int(st.st_mtime))


def load_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_manifest(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def find_notes(inbox):
    for root, dirs, files in os.walk(inbox):
        # Supernote leaves its own bookkeeping directories in the sync tree.
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in sorted(files):
            if name.lower().endswith(".note") and not name.startswith("."):
                yield os.path.join(root, name)


def stem_for(inbox, note_path):
    """A stable, filesystem-safe name that keeps notebooks distinct.

    Two notebooks can hold a page with the same name, so the relative path is
    hashed in rather than dropped.
    """
    rel = os.path.relpath(note_path, inbox)
    base = os.path.splitext(os.path.basename(rel))[0]
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in base).strip("-")
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:8]
    return "%s-%s" % (safe or "note", digest)


def convert(note_path, stem, work):
    """Render the note to PDF and, where possible, extract its transcript."""
    pdf = os.path.join(work, "pdf", stem + ".pdf")
    txt = os.path.join(work, "txt", stem + ".txt")

    ok, out = run(["supernote-tool", "convert", "-t", "pdf", "-a", note_path, pdf])
    if not ok:
        return None, None, "pdf conversion failed: %s" % out

    # A note written without Real-time Recognition has no text layer. That is
    # expected, not an error -- the PDF still goes to Paperless.
    text_ok, text_out = run(["supernote-tool", "convert", "-t", "txt", "-a", note_path, txt])
    if not text_ok:
        txt = None
    elif os.path.exists(txt) and os.path.getsize(txt) == 0:
        os.unlink(txt)
        txt = None

    return pdf, txt, None


def process(note_path, inbox, work, consume):
    stem = stem_for(inbox, note_path)
    pdf, txt, err = convert(note_path, stem, work)
    if err:
        return None, err

    if consume:
        # Paperless watches this directory and ingests whatever lands in it.
        shutil.copy2(pdf, os.path.join(consume, os.path.basename(pdf)))

    meta = {
        "stem": stem,
        "source_note": os.path.relpath(note_path, inbox),
        "notebook": os.path.basename(os.path.dirname(note_path)),
        "pdf": pdf,
        "transcript": txt,
        "has_text_layer": txt is not None,
        "ingested_at": int(time.time()),
        # Set once the Anytype step has created the object, so it is not
        # created twice. See create_anytype_object() below.
        "anytype_object_id": None,
    }
    meta_path = os.path.join(work, "meta", stem + ".json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)

    return meta, None


def create_anytype_object(meta):
    """Create the Anytype Page for a processed note.

    NOT IMPLEMENTED. Anytype's Local API (desktop app 0.46.x and later, bound
    to localhost) is the right target, but its port and pairing handshake were
    not verifiable from the session that wrote this file -- the documentation
    hosts are blocked by that environment's egress proxy. Rather than guess an
    endpoint shape and ship something that looks right and fails at runtime,
    this is left for whoever has the docs open on the machine itself.

    What it needs to do, per the design in the pipeline README:
      - create a Page in the "Maxs 2nd brain" space from meta["transcript"]
      - set a relation pointing at the Paperless document for meta["pdf"]
      - carry the notebook name and write date as properties
      - write the new object id back into the sidecar so re-runs skip it
    """
    raise NotImplementedError("Anytype Local API step -- see docstring")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inbox", required=True, help="directory the Supernote syncs into")
    parser.add_argument("--work", required=True, help="directory for converted output")
    parser.add_argument("--paperless-consume", help="Paperless consume directory")
    parser.add_argument("--dry-run", action="store_true", help="list new notes and stop")
    args = parser.parse_args(argv)

    inbox = os.path.expanduser(args.inbox)
    work = os.path.expanduser(args.work)
    consume = os.path.expanduser(args.paperless_consume) if args.paperless_consume else None

    if not os.path.isdir(inbox):
        print("inbox does not exist: %s" % inbox, file=sys.stderr)
        return 1

    for sub in ("pdf", "txt", "meta"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)

    manifest_path = os.path.join(work, MANIFEST)
    manifest = load_manifest(manifest_path)

    pending = []
    for note_path in find_notes(inbox):
        rel = os.path.relpath(note_path, inbox)
        if manifest.get(rel) != fingerprint(note_path):
            pending.append(note_path)

    if args.dry_run:
        for note_path in pending:
            print(os.path.relpath(note_path, inbox))
        print("%d new or edited note(s)" % len(pending), file=sys.stderr)
        return 0

    done = failed = 0
    for note_path in pending:
        rel = os.path.relpath(note_path, inbox)
        meta, err = process(note_path, inbox, work, consume)
        if err:
            print("%s: %s" % (rel, err), file=sys.stderr)
            failed += 1
            continue
        manifest[rel] = fingerprint(note_path)
        done += 1
        note = "" if meta["has_text_layer"] else "  (no text layer -- recognition off?)"
        print("%s -> %s%s" % (rel, meta["stem"], note))

    save_manifest(manifest_path, manifest)
    print("%d converted, %d failed" % (done, failed), file=sys.stderr)

    # Leave a non-zero exit for launchd when nothing succeeded but work existed,
    # so the heartbeat is not written and the row on /server goes stale.
    return 1 if failed and not done else 0


if __name__ == "__main__":
    sys.exit(main())
