# Cap takes never reach the film pipeline

**Symptom:** the lead records a Studio take on the laptop in the Cap fork, and `gs://<takes bucket>/takes/`
stays empty. Cap shows no error. (At one event this cost about 30 minutes before the first live take.)

**Why:** Cap uploads to the bucket named in the laptop's `mirror.json` (on Windows
`%APPDATA%\so.cap.desktop\mirror.json`), and it never overwrites an existing file with a newer download.
A laptop that still has an older `mirror.json` keeps uploading to the old bucket, often with a key that
cannot write to the new one. If the file cannot load at all, the only trace is a warning in Cap's log
("Mirror could not open its outbox").

**Check, in this order:**
1. `gcloud storage ls gs://<old bucket>/takes/`: if the take is there, it is the wrong bucket.
2. Was it a Studio recording? Instant mode never uploads.
3. Is the take's `outbox\` stuck? Restarting Cap resumes pending uploads.

**Fix:** a new HMAC key for the mirror's service account (the only account that can write to the takes
bucket; see [docs/optional/cap.md](../docs/optional/cap.md)), written into the laptop's `mirror.json`
with `"bucket": "<takes bucket>"` and no `prefix`, after deleting the old file; then restart Cap. Creating
a key is the lead's call. To rescue a take already in the old bucket:
`gcloud storage cp --recursive "gs://<old bucket>/takes/<take>.cap" gs://<takes bucket>/takes/`.

**Proof:** a new take folder appears under `takes/`, with `take-manifest.json` written last.
