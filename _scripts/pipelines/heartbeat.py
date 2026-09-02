#!/usr/bin/env python3
"""Record a pipeline's freshness in status.json.

The /server page renders every entry of the top-level "scrapers" array as a
row with a status dot, using the contract the existing scrapers already use:

    {"name": str, "cadence": str, "last": <unix seconds>, "expect_h": <hours>}

server/index.html computes the dot from age: a row is green while
(now - last) <= expect_h and red past it. That means a job which stops
running goes red on its own, so there is no "failed" state to report --
call this only on success and let staleness speak for failure. Use --note
to leave a message on a row without claiming a fresh run.

Usage:
    heartbeat.py --name supernote-ingest --cadence "every 10m" --expect-h 1
    heartbeat.py --name supernote-ingest --note "webdav unreachable" --no-touch

The status file is taken from --status-file or $STATUS_JSON.
"""

import argparse
import errno
import fcntl
import json
import os
import sys
import tempfile
import time


def load(path):
    """Read status.json, tolerating a missing or empty file."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return {}
        raise
    if not text:
        return {}
    return json.loads(text)


def save(path, data):
    """Replace status.json atomically so a reader never sees a partial write."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".status-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def upsert(data, name, cadence, expect_h, note, touch):
    """Insert or update one scrapers row, leaving every other key alone."""
    rows = data.setdefault("scrapers", [])
    if not isinstance(rows, list):
        raise SystemExit("status.json: 'scrapers' exists but is not a list")

    row = next((r for r in rows if isinstance(r, dict) and r.get("name") == name), None)
    if row is None:
        row = {"name": name}
        rows.append(row)

    if touch:
        row["last"] = int(time.time())
    if cadence is not None:
        row["cadence"] = cadence
    if expect_h is not None:
        # Keep whole numbers as ints, matching the rows the existing scrapers write.
        row["expect_h"] = int(expect_h) if float(expect_h).is_integer() else expect_h
    if note is not None:
        # An empty --note clears a previous message rather than storing "".
        if note:
            row["note"] = note
        else:
            row.pop("note", None)

    rows.sort(key=lambda r: r.get("name", ""))
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True,
                        help="pipeline name, as it should appear on /server")
    parser.add_argument("--cadence", help='human-readable schedule, e.g. "every 10m"')
    parser.add_argument("--expect-h", type=float,
                        help="hours before this row should go red")
    parser.add_argument("--note", help="message for the row; empty string clears it")
    parser.add_argument("--no-touch", action="store_true",
                        help="update metadata without recording a run")
    parser.add_argument("--status-file", default=os.environ.get("STATUS_JSON"),
                        help="path to status.json (default: $STATUS_JSON)")
    args = parser.parse_args(argv)

    if not args.status_file:
        parser.error("--status-file is required when $STATUS_JSON is unset")

    # Several launchd jobs share this file, so serialise on a sibling lock.
    # A lock beside the file (rather than on it) keeps the atomic replace above
    # from swapping the inode out from under a waiting writer.
    lock_path = args.status_file + ".lock"
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = load(args.status_file)
        row = upsert(data, args.name, args.cadence, args.expect_h,
                     args.note, touch=not args.no_touch)
        save(args.status_file, data)

    print(json.dumps(row, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
