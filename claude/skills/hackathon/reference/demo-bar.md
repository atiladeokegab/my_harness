# The demo bar: never go easy on the demo

Read when writing IDEA.md's demo line and storyboard (approval 1), the demo script and recording
tasks (§3), and before calling the film done. Why it exists: at Night Shift (2026-10-25) the judges
called the build great, but it placed 4th overall and missed the top three. Their words: the demo had
"no sparkle". It had no side-by-side against anything else and not enough visualisation, and good
audio earned no points. Remember that loss.

The demo script's Acceptance includes every rule below (1 to 8), and IDEA.md's demo line names rules 1 and 2 at
approval 1, so they get built rather than bolted on at freeze.

## Contents
- Rules 1 to 8
- The outside viewer
- Sources

## Rules

1. **One hero comparison.** Our product beside a baseline (a plain LLM, the incumbent tool or the
   manual way) on the same input, with measured differences on screen. Build the baseline path as a
   P1 task, because it is a build task, not an editing trick. Make it fair, or a judge will see
   through it:
   - the baseline is the same model and inputs minus our layer, so the gap is what we add, not a
     strawman;
   - freeze the sample before any model call;
   - the test owner labels the lines blind (no side, model or cost shown), never with our own checker;
   - define the metric with its n, and count missing and unverifiable lines;
   - word it neutrally, and show every outcome, including a tie or a loss.
2. **One chart that proves the track's claim**, using real numbers from the live system, shown large,
   and only where it proves a claim the narration just made. A chart is never decoration or an opener.
3. **The problem first, then the spark.** Open on the problem statement: whose problem it is and why it
   matters, in a few seconds. Then the spark (the comparison or the most striking live moment), then
   the tour. A tour of features is not a story.
4. **Production polish is table stakes.** Good mic, captions and music are expected and earn nothing on
   their own. Spend the effort on rules 1 to 3.
5. **Film it on the film pipeline** (your film pipeline's notes (not shipped): the kickoff, the recording task, the take
   window). Its gate and renderer are described there.
6. **Record clean, then have someone else frame-check it**, independent of the gate. Record with
   notifications off, the taskbar hidden, the cursor parked off the player and embeds already playing.
   Before the film is called done, a checker who did not cut it pulls a frame every second plus each
   cut, and fails it on any half-word, OS chrome, pop-up, tooltip, overlap or blank frame. Why: at Night
   Shift, the cutter's own 2 s pass called clean a cut that the independent pass then failed on six
   problems.
7. **Sell it: the pitch checklist.** We keep losing on the pitch, not the build (the lead, 26 Oct). The
   Night Shift film had the spark built but never filmed, the narrator talking over the product, and an
   ending with no ask. Before submission, all of these pass:
   - one promise sentence about the user ("gives a blind fan the match nobody described"), said in the
     first 15 s and again in the last 10 s; a cold viewer can say who it is for after 0:10;
   - the spark is named with its timestamp and lands before 0:45;
   - the product's own output plays clean for at least 5 s, with no narration over it;
   - re-transcribe the final cut and check every sentence and number against the facts file; strike
     anything the product does not do today (trained, live, any input);
   - why now and who pays, one sentence each with a real figure, before the last 15 s;
   - the last spoken words are the promise and the ask (a pilot, a user, a buyer); an end card with
     URL, team and event holds 4 s or more; nothing on screen sits still for 6 s outside it.
8. **Score every criterion, not just the build.** Engineering is one criterion of several; we beat
   Quell on it and still lost.
   - The idea's corrector must already do the correcting today and gain from it.
   - Ship one "teach it" action and one before/after number on held-out cases, shown in the product, in
     the README's first screen and in the film's first 30 s.
   - The README is under 200 lines: promise, embedded video, five steps, results table, then the honest
     limits once, at the end. Never open a section with what the product does not do; never claim what
     it does not.
   - At freeze minus 4 h, a rehearsal (the harsh rehearsal) scores us on every criterion against the
     strongest entry we can picture, and the gaps it names come before any polish.

## The outside viewer

At the rough cut and at freeze minus 4 hours (or earlier if the event is shorter), have someone outside
the build watch without an explanation. Ask who it is for, what changed, what proves it and why it
beats a strong rival. Score only evidence they could see against the actual criteria, update IDEA.md's
evidence table, and fix missing proof or scope before spending time on editing polish.

## Sources

The full judge feedback, film review and a 2:00 rewrite are in the event's notes (not shipped).
