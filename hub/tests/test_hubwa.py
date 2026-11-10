"""hubwa poll's stand-in for Zeus (T-929). Run: uv run python -m unittest tests.test_hubwa"""
import importlib.machinery
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

loader = importlib.machinery.SourceFileLoader("hubwa", str(Path(__file__).resolve().parent.parent / "hubwa"))
hubwa = importlib.util.module_from_spec(importlib.util.spec_from_loader("hubwa", loader))
loader.exec_module(hubwa)

ROSTER = [{"name": "Prometheus", "kind": "codex", "session": "hub-prometheus"},
          {"name": "Atlas", "kind": "codex", "session": "hub-atlas"},
          {"name": "Hermes", "kind": "claude", "session": "hub-hermes"},
          {"name": "Zeus", "kind": "claude", "session": "hub-zeus"}]
HEALTHY = {a["name"]: {"cause": "healthy"} for a in ROSTER}
ALL = lambda s: True


class StandIn(unittest.TestCase):
    def test_zeus_answers_while_he_can_even_when_stuck(self):
        self.assertIsNone(hubwa.stand_in(HEALTHY, ROSTER, ALL))
        self.assertIsNone(hubwa.stand_in({**HEALTHY, "Zeus": {"cause": "stuck"}}, ROSTER, ALL))

    def test_a_rate_limited_zeus_hands_over_to_a_healthy_claude_first(self):
        watch = {**HEALTHY, "Zeus": {"cause": "rate limited"}}
        self.assertEqual(hubwa.stand_in(watch, ROSTER, ALL)["name"], "Hermes")
        watch["Hermes"] = {"cause": "rate limited"}
        self.assertEqual(hubwa.stand_in(watch, ROSTER, ALL)["name"], "Prometheus")

    def test_no_zeus_session_hands_over_and_a_dead_session_is_never_picked(self):
        self.assertEqual(hubwa.stand_in(HEALTHY, ROSTER, lambda s: s not in ("hub-zeus", "hub-hermes"))["name"],
                         "Prometheus")

    def test_nobody_healthy_leaves_it_with_zeus(self):
        down = {a["name"]: {"cause": "logged out"} for a in ROSTER}
        self.assertIsNone(hubwa.stand_in(down, ROSTER, ALL))

    def test_an_agent_in_the_off_phase_is_never_the_stand_in(self):
        roster = [{**a, "phase": "off"} if a["name"] == "Hermes" else a for a in ROSTER]
        watch = {**HEALTHY, "Zeus": {"cause": "rate limited"}}
        self.assertEqual(hubwa.stand_in(watch, roster, ALL)["name"], "Prometheus")
        self.assertIsNone(hubwa.stand_in(watch, [a for a in ROSTER if a["name"] == "Zeus"] + [
            {"name": "Atlas", "kind": "codex", "session": "hub-atlas"}], ALL, default_phase="off"))


class LeadMessages(unittest.TestCase):
    def test_a_video_becomes_a_note_asking_for_a_share_link_and_text_is_unchanged(self):
        msgs = [{"id": "v", "role": "user", "type": "video", "text": None},
                {"id": "a", "role": "assistant", "type": "text", "text": {"body": "hi"}},
                {"id": "t", "role": "user", "type": "text", "text": {"body": "status?"}}]
        with mock.patch.object(hubwa, "call", lambda method, path: msgs):
            got = hubwa.lead_messages({"id": "c"})
        self.assertEqual([(m["id"], m["text"]["body"]) for m in got], [
            ("t", "status?"), ("v", "[the lead sent a video; Wassist can't hand it over; reply: Share it as a Drive link "
                   "(anyone with the link) and paste it here.]")])


class Poll(unittest.TestCase):
    """the whole poll, every transport mocked: nothing reaches WhatsApp, tmux or an inbox"""

    def poll(self, queued, cover=("Hermes", "rate limited"), state=None):
        sent, receipts = [], []

        def queue(name, text, secs):
            sent.append((name, secs))
            return queued(name)
        msgs = [{"id": "m1", "createdAt": "2026-10-27T17:00:00Z", "text": {"body": "status?"}}]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(hubwa, "STATE", Path(state or tmp)), mock.patch.object(hubwa, "conversation", lambda: {"id": "c"}), \
                mock.patch.object(hubwa, "lead_messages", lambda c: msgs), mock.patch.object(hubwa, "zeus_cover", lambda: cover), \
                mock.patch.object(hubwa, "queue", queue), mock.patch.object(hubwa, "call", lambda *a: receipts.append(a[2])), \
                mock.patch.object(hubwa.sys, "argv", ["hubwa", "poll"]), mock.patch("builtins.print"):
            hubwa.main()
            d = Path(state or tmp)
            seen = (d / "seen").read_text().split() if (d / "seen").exists() else []
        return sent, receipts, seen

    def test_a_failed_handover_is_not_consumed_or_acknowledged_and_zeus_waits_behind_the_stand_in(self):
        sent, receipts, seen = self.poll(lambda name: False)
        self.assertEqual(([n for n, _ in sent], receipts, seen), (["Hermes"], [], []))

    def test_the_stand_in_gets_it_first_then_zeus_and_the_receipt_names_the_stand_in(self):
        sent, receipts, seen = self.poll(lambda name: True)
        self.assertEqual([n for n, _ in sent], ["Hermes", "Zeus"])
        self.assertTrue(all(secs <= 8 for _, secs in sent))  # inside the service's 30 s poll
        self.assertEqual((seen, receipts[0]["text"]["body"]), (["m1"], "Got it, Hermes is on it (Zeus is rate limited)."))

    def test_with_zeus_up_only_zeus_is_messaged(self):
        sent, receipts, seen = self.poll(lambda name: True, cover=None)
        self.assertEqual(([n for n, _ in sent], seen, receipts[0]["text"]["body"]), (["Zeus"], ["m1"], "Got it, Zeus is on it."))

    def test_a_failed_zeus_copy_is_retried_next_poll_without_a_second_hand_over_or_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            sent, receipts, seen = self.poll(lambda name: name != "Zeus", state=d)
            self.assertEqual(([n for n, _ in sent], len(receipts), seen), (["Hermes", "Zeus"], 1, ["m1"]))
            sent, receipts, seen = self.poll(lambda name: True, state=d)
            self.assertEqual(([n for n, _ in sent], receipts), (["Zeus"], []))
            self.assertEqual(json.loads((Path(d) / "zeus-pending").read_text()), {})
            sent, _, _ = self.poll(lambda name: True, state=d)
            self.assertEqual(sent, [])

    def test_a_crash_after_the_zeus_copy_is_saved_never_hands_the_stand_in_the_message_twice(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "zeus-pending").write_text(json.dumps({"m1": "copy"}))  # saved, then killed before seen
            sent, receipts, seen = self.poll(lambda name: True, state=d)
            self.assertEqual(([n for n, _ in sent], receipts, seen), (["Zeus"], [], ["m1"]))

    def test_copies_saved_by_510b172_as_a_list_still_reach_zeus_and_new_messages_flow(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "zeus-pending").write_text(json.dumps(["old copy"]))
            sent, receipts, seen = self.poll(lambda name: True, state=d)
            self.assertEqual(([n for n, _ in sent], len(receipts), seen), (["Hermes", "Zeus", "Zeus"], 1, ["m1"]))

    def test_queue_counts_the_durable_inbox_even_when_the_wake_times_out(self):
        late = subprocess.TimeoutExpired(["hubmsg"], 8, output=b"queued  -> Hermes inbox\n")
        with mock.patch.object(hubwa.subprocess, "run", side_effect=late):
            self.assertTrue(hubwa.queue("Hermes", "x", 8))
        with mock.patch.object(hubwa.subprocess, "run", side_effect=subprocess.TimeoutExpired(["hubmsg"], 8)):
            self.assertFalse(hubwa.queue("Hermes", "x", 8))


    def test_messages_held_while_the_window_was_closed_follow_the_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "held.jsonl").write_text(json.dumps({"at": "10:00Z 01 Nov", "text": "film ready"}) + "\n")
            _, receipts, _ = self.poll(lambda name: True, cover=None, state=d)
            self.assertEqual([r["text"]["body"] for r in receipts],
                             ["Got it, Zeus is on it.", "(Written 10:00 01 Nov) film ready"])
            self.assertFalse((Path(d) / "held.jsonl").exists())


class Send(unittest.TestCase):
    """2026-11-01: every send failed 09:55Z-16:37Z, 24 h after the lead's last message; reads hit Wassist 502s."""

    def send(self, window):
        posted = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hubwa, "STATE", Path(d)), \
                mock.patch.object(hubwa, "conversation", lambda: {"id": "c", "chatWindowRemainingTime": window}), \
                mock.patch.object(hubwa, "call", lambda *a: posted.append(a[2])), \
                mock.patch.object(hubwa.sys, "argv", ["hubwa", "send", "film ready"]), mock.patch("builtins.print") as out:
            hubwa.main()
            held = (Path(d) / "held.jsonl").read_text() if (Path(d) / "held.jsonl").exists() else ""
        return posted, held, out.call_args[0][0]

    def test_a_closed_window_holds_the_message_instead_of_failing(self):
        posted, held, said = self.send(0)
        self.assertEqual((posted, json.loads(held)["text"]), ([], "film ready"))
        self.assertIn("held", said)

    def test_an_open_window_sends(self):
        posted, held, said = self.send(3600)
        self.assertEqual((posted, held, said), ([{"type": "text", "text": {"body": "film ready"}}], "", "sent"))

    def test_a_get_is_retried_past_a_502_and_a_post_is_not(self):
        import io
        import urllib.error
        gateway = lambda: urllib.error.HTTPError("u", 502, "Bad Gateway", {}, io.BytesIO(b"x"))
        ok = mock.MagicMock()
        ok.__enter__.return_value = io.BytesIO(b'{"ok": 1}')
        with mock.patch.object(hubwa, "cfg", lambda n: "k"), mock.patch.object(hubwa.time, "sleep"):
            with mock.patch.object(hubwa.urllib.request, "urlopen", side_effect=[gateway(), ok]):
                self.assertEqual(hubwa.call("GET", "/x"), {"ok": 1})
            with mock.patch.object(hubwa.urllib.request, "urlopen", side_effect=gateway()) as op, \
                    self.assertRaises(SystemExit):
                hubwa.call("POST", "/x", {})
            self.assertEqual(op.call_count, 1)

if __name__ == "__main__":
    unittest.main()
