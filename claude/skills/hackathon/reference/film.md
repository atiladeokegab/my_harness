# The demo film

Read at §0 (the film kickoff), at approval 1 (the storyboard becomes the film's story), when writing
the recording task (§3), and in the take window (§7). The film's content rules are the demo bar:
[demo-bar.md](demo-bar.md). Everything here is optional: an event without a film pipeline records its
video by hand and still follows the demo bar.

## Contents
- The pipeline
- Film kickoff (§0): the seven items
- At approval 1: the storyboard becomes the film's story
- Recording on the pipeline (§3)
- In the take window (§7)

## The pipeline

Two repos outside this harness: the film pipeline
([atiladeokegab/film](https://github.com/atiladeokegab/film); its README covers install and every
setting) and the Cap fork the lead records in ([atiladeokegab/Cap](https://github.com/atiladeokegab/Cap)).
The lead records a Studio take in Cap, the take streams to the takes bucket, and the render machine cuts
it and sends the film back on the lead's chat channel (`hubwa`, when set up) and Drive. The pipeline's
gate (the `pitch` profile by default) fails a film on the pitch, voice, frame and shot rules and names
each red rule. The renderer underneath is a cut list (`build.py`): split screens with right/wrong
badges, animated charts, captions, chapters and a music bed; a hand cut list is how stock cutaways and
anything the take job does not plan get in. Laptop, bucket and setting names:
[docs/optional/cap.md](../../../../docs/optional/cap.md) in the harness repo.

## Film kickoff (§0): the seven items

As soon as the event is known, before any team or idea, put one `film kickoff` task on the board for
Zeus with these seven items as its Acceptance, and send the lead items 3, 4 and 7 as one checklist:

1. **Film deadlines**, added to the deadlines table and hackathon.json: `film freeze` = submit − 30
   min; `harsh rehearsal` = film freeze − 4 h (demo bar rule 8, scored on a real take); the `take
   window` runs from the rehearsal to the film freeze, the last take stopped by film freeze − 10 min so
   its film is back before it. Harsh rehearsal, film freeze and submit go into event.json as
   `rehearsal_at`, `freeze_at` and `submission_at` (item 2).
2. **The film event folder** (`<film home>/event`, or `FILM_EVENT_DIR`):
   - `brief.md`: the filed brief.
   - `event.json` with `name`; `deadlines` (`rehearsal_at`, `freeze_at` and `submission_at`, ISO times
     with an explicit timezone; `freeze_at` is required); `criteria` (when known); `limit` (the video
     limit in seconds; the pipeline defaults to 180); and `team`, `project`, `url` and `product_url`
     left as `""`, with a TODO for each in the kickoff task.
   - Team and project come at approval 1, and the take job refuses to build while either is empty.
     Never write a literal `"TODO"`, which passes and tags the film "TODO".
   - The pipeline reads both: `deadlines` drives the lead's reminder 30 minutes before the freeze;
     `criteria` (`[{id, name, looks_for, weight}]`), when set, replaces the criteria it would otherwise
     take from the folder's HACKATHON.md (else brief.md). Without it, copy HACKATHON.md in once §6
     writes it.
3. **The lead's laptop**: the Cap fork from its latest release, `mirror.json` written and any
   downloaded copy deleted once Cap starts, a test Studio take that reaches the bucket; Settings,
   Recording quality, **Smaller files**; a clean browser profile with only the product open; the mic
   tested; a phone hotspot as backup ([docs/optional/cap.md](../../../../docs/optional/cap.md)).
4. **The chat window**: WhatsApp lets `hubwa` reply only within 24 h of the lead's last message, so the
   lead messages the hub the evening before and the morning of the event.
5. **The render machine**: `uv run python -m film.watch <home> --after "$(date -u +%FT%TZ)"` running with
   its `.env` loaded (in `tmux new -d -s film-watch`, or a service). `--after` goes on a fresh home's
   first start, or every take already in the bucket joins the new event. `CAP_CLI` set; `uv sync` and
   `make smoke` once, so the cache is warm; no heavy runs on that machine during the take window.
6. **Pre-made assets**: the look (`look`, `tagline` in event.json; the title and end cards are drawn
   from event.json's names at render); a cutaway library with a `licences.json` (source and licence per
   file), used in hand cut lists; the interview questions, as `interview` shots in the shot list, with
   consent recorded in `event/clip-consent.json`.
7. **A rehearsal take the day before**: the lead records a stand-in shot list end to end, timing Stop
   to the film arriving; whatever breaks goes on the board that evening.

## At approval 1: the storyboard becomes the film's story

1. Fill `team`, `project`, `url` and `product_url` in event.json. `product_url` is the deployed app's
   URL, which the frame gate checks the screen's source host against (unverified without it).
2. Copy IDEA.md (and facts.json, judges.md if any) into the film event folder, and run
   `FILM_EVENT_DIR=<event> uv run python -m film.story prepare <home>`. It writes story.json (beats
   hook, problem, demo, proof, ask), shotlist.json, criteria.json and judges.json, and publishes the
   shot list to the teleprompter.
3. Check every shot is typed `demo` (the product on screen), `talk` (the lead to camera) or
   `interview`.
4. Write `criteria-map.md` beside it: each judging criterion and the shot ids that prove it. A
   criterion with no shot goes back into the storyboard.
5. Apply the lesson that the film is the pitch: problem first, the spark filmed by 0:45, the product
   playing clean with no narration, promise and ask at the end. The story step does not read the
   lessons ledger, so Zeus checks every [film] and [demo] lesson in
   `$HUB_DIR/projects/hackathon-lessons.md` against IDEA.md's storyboard, story.json and the shot list
   by hand, and again before the first take (the harsh rehearsal); a lesson the story fails is a script
   fix.
6. The approval-1 window shows the beats, the shot list and criteria-map.

Prepare refuses once a take has landed, since a new story renumbers the sentence ids; `--force` only
before the take window.

## Recording on the pipeline (§3)

The recording task's brief says `Record the deployed URL from main's head after the last fix; put that
sha in the video description`. The lead records in Cap (Studio mode) with the teleprompter: a take goes
Stop → upload → film → the lead's phone in about 10 minutes, and each one republishes the teleprompter's
list with only the shots still missing (pick-ups), so the lead records those until every shot and
criterion is ticked. Joining a take set is `film.take event`.

The pipeline does not know the event's submit time: at the film freeze the recording task submits the
last-green film (`<home>/last-green.json`), never a newer red one.

**Before the first take:**
- Every beat in the script works on the deployed URL, said through the real model, before anyone
  records it. A take of a beat that does not work yet is wasted; record one take per beat.
- Screen-record the phone itself; never film a phone or UI on a laptop screen. Captions sit on a dark
  box. The end card shows the name and URL large, held 3 s.
- The film's URL is versioned (`?v=`) from the first upload, so a new cut never hides behind a cache.
- Cut on the pipeline, never a one-off ffmpeg script; a blind judge checks it before the lead sees it.

## In the take window (§7)

The lead records; the render machine builds. Zeus watches each take's message (`Final film:` within
10 minutes, `gate PASS` or `gate RED` with each red rule, the Drive link). No film 10 minutes after a
stop: check `tmux has-session -t film-watch` and the watcher's output, and tell the lead what is late.

A take that fails the gate:
- **A missing, fluffed or clipped sentence or shot:** the pick-up list already holds only those; the
  lead presses Reload and records just them.
- **A fault across the take** (wrong screen, no mic, the product not loaded, OS chrome or pop-ups):
  re-record that clip, never patch it.
- **A pitch rule** (no promise, the spark after 0:45, a criterion with no shot): a script fix; Zeus
  changes that shot's lines and the lead re-records the shot. Re-running prepare after the first take
  needs `--force` and orphans the marked takes, so only before the take window.

Before submit, someone who did not cut it frame-checks the last-green film (demo bar rule 6).
