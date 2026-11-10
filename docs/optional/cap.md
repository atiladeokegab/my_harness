# Optional: recording demo takes with the Cap fork

The demo film for an event (see the hackathon skill's [film reference](../../claude/skills/hackathon/reference/film.md))
is recorded on the lead's laptop in a fork of [Cap](https://github.com/CapSoftware/Cap), the open
source screen recorder: [atiladeokegab/Cap](https://github.com/atiladeokegab/Cap). The fork adds a shot
list in the teleprompter, shot marks (`shots.json`), a foreground-window log, and an upload mirror that
streams each Studio take to S3-compatible storage while it records, writing `take-manifest.json` last.
The film pipeline ([atiladeokegab/film](https://github.com/atiladeokegab/film)) watches that bucket,
cuts the take and sends the film back.

This harness ships none of Cap's code (Cap is AGPL-3.0; the fork keeps that licence). What is here is
the glue: the laptop setup, the bucket, and the names the pipeline reads.

## The bucket

One Google Cloud Storage bucket for takes (any S3-compatible store works; GCS needs path-style
addressing, which the pipeline already uses). Names below are placeholders.

```bash
PROJECT=my-film-project; BUCKET=my-film-takes
gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --uniform-bucket-level-access
gcloud iam service-accounts create film-mirror --project "$PROJECT"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member "serviceAccount:film-mirror@$PROJECT.iam.gserviceaccount.com" --role roles/storage.objectUser
gcloud storage hmac create "film-mirror@$PROJECT.iam.gserviceaccount.com" --project "$PROJECT"
```

Bind the role on the bucket only, so the laptop's key can touch nothing else. The last command prints
an HMAC access id and secret once: they go into the laptop's `mirror.json` and nowhere else. Creating a
key is the lead's call.

## The lead's laptop

1. Install the fork from its latest release: `gh release list -R atiladeokegab/Cap -L 1`. The Windows
   installer is unsigned (More info, Run anyway).
2. Write `mirror.json` in Cap's app data folder (on Windows `%APPDATA%\so.cap.desktop\`). Without it
   the mirror stays off. Fields:

   | Field | What |
   |---|---|
   | `bucket` | the takes bucket, e.g. `my-film-takes` |
   | `access_key`, `secret_key` | the HMAC id and secret (`hmac_access_id` and `hmac_secret` are accepted too) |
   | `region` | default `auto` |
   | `endpoint` | optional; for GCS `https://storage.googleapis.com` |
   | `prefix` | optional; leave it out so takes land under `takes/`, where the pipeline looks |

   Cap never replaces an existing `mirror.json`, so a stale one stays in force: delete the old file
   before writing a new one, and delete any downloaded copy once Cap has started.
3. Record a test take in **Studio** mode (Instant mode never uploads) and check it reaches
   `gs://<bucket>/takes/`.
4. Settings, Recording quality, **Smaller files**. A clean browser profile with only the product open,
   the mic tested, a phone hotspot as backup.

## The machine that cuts the film

The pipeline's own README covers installing it. The names it reads, all from the environment (put them
in its `.env`, never in a repo):

| Name | What |
|---|---|
| `FILM_TAKES_BUCKET` | the takes bucket |
| `FILM_S3_KEY_ID`, `FILM_S3_SECRET` | the pipeline's own HMAC key for the bucket (not the laptop's) |
| `FILM_S3_ENDPOINT` | default `https://storage.googleapis.com` |
| `CAP_CLI` | path to the fork's `cap` CLI, used for `cap events <take> --json` |
| `FILM_EVENT_DIR` | the film event folder (default `<film home>/event`) |

The pipeline's README lists the rest (voice, Drive delivery). Delivery to the lead's phone goes through
`hubwa send` ([WhatsApp](whatsapp.md)) when that module is set up.

When takes never arrive: [runbooks/cap-takes-wrong-bucket.md](../../runbooks/cap-takes-wrong-bucket.md).
