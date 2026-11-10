# `hubwa send` fails, or the lead hears nothing on WhatsApp

**Symptom.** `hubwa send` exits 1 for hours while the lead's own WhatsApp messages still reach
Zeus's inbox. On 2026-11-01 every send from 09:55Z to 16:37Z failed; film's `hubwa read` also
failed about once an hour.

**Two causes, check both.**

1. **The 24-hour window.** WhatsApp lets the business number send free text only within 24 h of
   the lead's last message. The lead last wrote 2026-10-31 09:55Z, so the window shut at
   2026-11-01 09:55Z and reopened only when they wrote again at 16:37Z. Inbound is not affected.
   Confirm without sending anything:

   ```bash
   journalctl --user -u hub-whatsapp --since today | grep -c ' new'   # polls that handed messages over
   grep -o '\[whatsapp from the lead, [0-9T:-]*Z\]' ~/hub/inbox/Zeus.jsonl | tail -3
   ```

   If the newest lead message is over 24 h old, the window is shut. Since this fix `hubwa send`
   prints `held` and exits 0 instead of failing; held messages (the latest 10) go out after the
   "Got it" receipt to the lead's next message. The window can only reopen from the lead's
   side: they send any WhatsApp message to the agent. Sending outside the window needs a
   Meta-approved template set up in Wassist, which the hub does not have (the number is a Wassist
   sandbox number).

2. **Wassist 502s.** `backend.wassist.app` answers 502 Bad Gateway a few times a day
   (`journalctl --user -u hub-whatsapp | grep 502`). GETs (`read`, `poll`) now retry twice, 2 s
   apart. A POST is never retried, since a 502 may still have sent it: a `send` that hits one
   exits 1 with `wassist POST ...: 502`, and the caller may resend.

**Not the cause:** the API key. A bad key gives 401 or 403 on every call, the poll included.
Never print `~/.config/hub/wassist.key` to check it.
