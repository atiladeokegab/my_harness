"""The lead's WhatsApp gets plain English only (lead, 2026-11-09: "no watchdogs, percentages, numbers, Linux
commands, quotas or disk space"). Watchdog alerts stay in Zeus's inbox; hubwa refuses technical text.

    env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT -u HUB_HOST_PROJECT HOME=$(mktemp -d) \
        uv run python -m unittest tests.test_whatsapp_plain
"""

import importlib.machinery
import importlib.util
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import test_spend as ts
from tests.test_dispatch import CLAUDE_PERMISSION, CODEX_LIMIT, Factory

loader = importlib.machinery.SourceFileLoader("hubwa", str(Path(__file__).resolve().parent.parent / "hubwa"))
hubwa = importlib.util.module_from_spec(importlib.util.spec_from_loader("hubwa", loader))
loader.exec_module(hubwa)


class WatchdogStaysOffWhatsApp(Factory):
    def test_a_prompt_waiting_3_min_and_a_rate_limit_reach_zeus_not_whatsapp(self):
        self.pane("hub-hermes", CLAUDE_PERMISSION)
        self.pane("hub-prometheus", CODEX_LIMIT)
        self.run_cmd("watch")
        state = json.loads((self.hub / "state" / "watch.json").read_text())
        state["Hermes"]["prompt_since"] = time.time() - 181
        self.write_state("watch.json", state)
        self.run_cmd("watch")
        self.assertEqual(self.calls("hubwa"), [])
        inbox = (self.hub / "inbox" / "Zeus.jsonl").read_text()
        self.assertIn("Hermes has been at a prompt for 3 min", inbox)
        self.assertIn("Prometheus: healthy -> rate limited", inbox)


class SpendAlertIsPlain(unittest.TestCase):
    def test_the_event_budget_used_up_reads_as_two_plain_sentences(self):
        g = ts.FakeGcloud({"my-hub-project": {"pubsub subscriptions pull": [ts.event(85.58)]},
                           "my-events-project": {"run services list": [
                               ts.service("strata", {"revisionName": "live", "percent": 100})]}})
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ts.cc, "STATE", Path(d) / "spend.json"):
            ts.cc.run(False, ts.NOW, g)
            [text] = ts.cc.load_state()["unsent"]
        self.assertEqual(text, "The hackathon event's cloud budget is used up: about £86 of £10 spent. "
                               "To stop the charges, Hub switched off the hackathon event's apps.")
        self.assertIsNone(hubwa.technical(text))


class ChokePoint(unittest.TestCase):
    def send(self, text):
        posted = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hubwa, "STATE", Path(d)), \
                mock.patch.object(hubwa, "conversation", lambda: {"id": "c", "chatWindowRemainingTime": 3600}), \
                mock.patch.object(hubwa, "call", lambda *a: posted.append(a[2])), \
                mock.patch.object(hubwa.sys, "argv", ["hubwa", "send", text]), mock.patch("builtins.print") as out:
            try:
                hubwa.main()
                said = out.call_args[0][0]
            except SystemExit as e:  # a drop exits non-zero, so no caller takes it as delivered
                said = e.code
            dropped = (Path(d) / "dropped.jsonl").read_text() if (Path(d) / "dropped.jsonl").exists() else ""
        return posted, dropped, said

    def test_a_path_or_command_is_dropped_and_logged(self):
        for text in ["Free space: du -hx ~/work is 40G",
                     "Look at tmux hub-hermes",
                     "hub-host root disk is at 86% after janitor run",
                     "Merged 7f55424 into main"]:
            posted, dropped, said = self.send(text)
            self.assertEqual(posted, [], text)
            self.assertEqual(json.loads(dropped)["text"], text)
            self.assertTrue(said.startswith("dropped"), said)

    def test_legacy_budget_alerts_are_translated_in_both_queues_never_lost(self):
        legacy = "Cloud spend guard:\nbudget hub-host: 120.00 of 110.00 GBP spent (100% crossed)"
        posted = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hubwa, "STATE", Path(d)), \
                mock.patch.object(hubwa, "conversation", lambda: {"id": "c"}), \
                mock.patch.object(hubwa, "call", lambda *a: posted.append(a[2]["text"]["body"])):
            (Path(d) / "held.jsonl").write_text(json.dumps({"at": "10:00Z 09 Nov", "text": legacy}) + "\n")
            hubwa.send_held()
            self.assertEqual(json.loads((Path(d) / "dropped.jsonl").read_text())["text"], legacy)  # kept for Zeus
        [held] = posted
        self.assertIn("(Written 10:00 09 Nov) A cloud budget is used up: about £120 of £110 spent.", held)
        with mock.patch("builtins.print"):
            outbox = ts.cc.for_phone(legacy)
        self.assertEqual(outbox, "A cloud budget is used up: about £120 of £110 spent.")
        self.assertIsNone(hubwa.technical(held))
        self.assertIsNone(hubwa.technical(outbox))

    def test_a_shutdown_only_legacy_report_is_translated_not_sent_raw(self):
        """Prometheus on e00b8bd: this passes technical(), so the prefix, not the filter, must route it to rewrite()."""
        legacy = "Cloud spend guard:\ndeleted my-events-project service strata (europe-west2)"
        plain = "To stop the charges, Hub switched off the hackathon event's apps."
        posted = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hubwa, "STATE", Path(d)), \
                mock.patch.object(hubwa, "conversation", lambda: {"id": "c"}), \
                mock.patch.object(hubwa, "call", lambda *a: posted.append(a[2]["text"]["body"])):
            (Path(d) / "held.jsonl").write_text(json.dumps({"at": "10:00Z 09 Nov", "text": legacy}) + "\n")
            hubwa.send_held()
        self.assertEqual(posted, [f"(Written 10:00 09 Nov) {plain}"])
        with mock.patch("builtins.print"):
            self.assertEqual(ts.cc.for_phone(legacy), plain)

    def test_a_plain_message_goes(self):
        posted, dropped, said = self.send("Here's a report on what's going on: the film is ready to watch.")
        self.assertEqual((len(posted), dropped, said), (1, "", "sent"))


if __name__ == "__main__":
    unittest.main()
