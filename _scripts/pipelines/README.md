# Pipelines

Scheduled jobs that run on the apartment Mac (`apt.tail258803.ts.net`) and feed
the two stores: **Anytype** for objects, **Paperless** for documents.

These scripts live here so they are under version control. They run from
`~/pipelines/` on the server; nothing in this directory is used by the website.

## Why launchd and not cron

Both `osascript` against Apple Reminders and the Anytype Local API need a
logged-in GUI session. launchd agents run in that context and survive reboots.
A cron entry does not, and fails in ways that are tedious to diagnose.

## Freshness reporting

Every job ends by calling `heartbeat.py`, which writes into the `scrapers`
array of the `status.json` that `/server` already renders:

```json
{"name": "supernote-ingest", "cadence": "every 10m", "last": 1756800000, "expect_h": 1}
```

`server/index.html` colours each row by age, so a job that stops running goes
red on its own. There is deliberately no "failed" state to report — call
`heartbeat.py` only on success and let staleness speak for failure.

```sh
./heartbeat.py --name supernote-ingest --cadence "every 10m" --expect-h 1 \
               --status-file ~/pipelines/status.json
```

Several jobs write that file, so the script takes an exclusive lock and
replaces the file atomically. A reader never sees a partial write.

---

## Supernote → Paperless + Anytype

### 1. Serve WebDAV from the Mac

The Supernote's **NetVirtualDisk** app (firmware 3.25+; confirmed working on
Chauvet 3.29.42) speaks WebDAV to any server, so the tablet can write straight
into a directory here instead of going through Supernote Cloud or Dropbox.

Supernote's own documentation uses Nextcloud, but a groupware suite is a lot of
machinery for one synced folder. `rclone` is enough:

```sh
brew install rclone
mkdir -p ~/pipelines/inbox/supernote

rclone serve webdav ~/pipelines/inbox/supernote \
  --addr 127.0.0.1:8085 \
  --user supernote --pass 'CHOOSE-A-STRONG-ONE'
```

Bind it to `127.0.0.1`, not `0.0.0.0`. This holds your notebooks and should
not be reachable from the apartment LAN, let alone the internet.

### 2. Expose it over the tailnet with a real certificate

The device wants HTTPS. Tailscale already terminates TLS for
`apt.tail258803.ts.net`, so let it front the local rclone listener:

```sh
tailscale serve status                                   # SEE THE WARNING BELOW
tailscale serve --bg --https=443 --set-path=/webdav http://127.0.0.1:8085
```

> **Check `tailscale serve status` first.** Port 443 on this host already
> serves the library at `/`, `/weave/`, and `/status.json`. Confirm what is
> mounted there before adding a path, so the new mount does not displace an
> existing one. If those are fronted by nginx or Caddy rather than
> `tailscale serve`, add a WebDAV location block to that config instead and
> skip this step.

Tailnet-only is the default; do not enable Funnel.

### 3. Pair the device

On the Supernote, the WebDAV form takes:

| Field | Value |
|---|---|
| Name | anything — e.g. `Apartment` |
| Address | tick the shield (HTTPS), host `apt.tail258803.ts.net`, port `443` |
| Path | `/webdav` |
| Username | `supernote` |
| Password | whatever you set in `--pass` above |

Write a test page, then confirm it lands:

```sh
ls -la ~/pipelines/inbox/supernote/
```

Stop here until a file actually appears. Everything downstream is a file
watcher and none of it is worth debugging against an empty directory.

### 4. Turn on Real-time Recognition

The highest-leverage setting in this whole pipeline. With it on, the device
writes a text layer inside the `.note` file and `supernotelib` extracts it
directly. With it off there is nothing to extract, and Paperless's OCR
(Tesseract) is built for printed text — it does poorly on handwriting.

Enable it before writing anything you want searchable. Older notebooks written
without it need a vision-model transcription pass instead.

### 5. Convert and route

```sh
pip install supernotelib

./supernote_ingest.py \
  --inbox ~/pipelines/inbox/supernote \
  --work  ~/pipelines/work/supernote \
  --paperless-consume ~/paperless/consume \
  --dry-run
```

`--dry-run` lists what it would pick up. Drop it to convert. Each note yields a
PDF (copied into the Paperless consume directory, where it is ingested and
OCR'd automatically) and, when a text layer exists, a transcript plus a JSON
sidecar for the Anytype step.

Processed files are tracked by size and mtime, so re-runs are cheap and an
edited note is picked up again.

### 6. Anytype — not yet implemented

`create_anytype_object()` in `supernote_ingest.py` raises `NotImplementedError`
on purpose. Anytype's **Local API** (desktop app 0.46.x and later, bound to
localhost, works fully offline) is the right target, but its port and pairing
handshake could not be verified from the environment that wrote this file —
`doc.anytype.io` and `developers.anytype.io` are both blocked by that
environment's egress proxy.

Finish it from the Mac, where those docs are reachable. It needs to:

- create a Page in the **Maxs 2nd brain** space from the transcript
- set a relation pointing at the Paperless document for the PDF
- carry the notebook name and write date as properties
- write the object id back into the sidecar so re-runs skip it

### 7. Action items → Apple Reminders

Once the Anytype step works: have `claude -p` read the transcript, pull out
anything that reads like a commitment, and create it as an Anytype Task with
`apple_list` set. The existing two-way Reminders sync carries it to the phone
and watch within the hour — handwriting on the tablet becomes a reminder in
your pocket without retyping.

---

## Installing the launchd jobs

```sh
cp com.maxgoodstein.*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.maxgoodstein.webdav.plist
launchctl load ~/Library/LaunchAgents/com.maxgoodstein.supernote-ingest.plist
```

Edit the paths and the WebDAV password in the plists first — they ship with
placeholders. To check on a job:

```sh
launchctl list | grep maxgoodstein
tail -f ~/pipelines/logs/supernote-ingest.err
```

## Still to move here

The two-way Apple Reminders ↔ Anytype sync currently lives only on that Mac,
in no repository, with no history. It is the oldest and most load-bearing
pipeline in the system and the one most worth version-controlling. Copy it into
this directory.
