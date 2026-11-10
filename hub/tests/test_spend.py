"""The hourly spend guard against fake gcloud JSON: it scales warm revisions down, reports stray VMs and long
jobs, and at 100% of the hackathon-starter budget deletes that project's services (T-1101)."""

import base64
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("cloudrun_check", Path(__file__).resolve().parent.parent / "cloudrun_check.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)
LOC = {"cloud.googleapis.com/location": "europe-west2"}


def service(name, *traffic):
    return {"metadata": {"name": name, "labels": LOC}, "status": {"traffic": list(traffic)}}


def rev(name, created, min_scale="1"):
    return {"metadata": {"name": name, "creationTimestamp": created,
                         "annotations": {"autoscaling.knative.dev/minScale": min_scale}}}


def vm(name, gpus=0):
    return {"name": name, "zone": "https://x/zones/europe-west2-a", "status": "RUNNING",
            **({"guestAccelerators": [{"acceleratorCount": gpus}]} if gpus else {})}


def budget(name, cost, amount=10, start="2026-11-01T00:00:00Z", bid="b1"):
    data = {"budgetDisplayName": name, "costAmount": cost, "budgetAmount": amount, "currencyCode": "GBP",
            "costIntervalStart": start}
    return {"ackId": "a", "message": {"data": base64.b64encode(json.dumps(data).encode()).decode(),
                                      "attributes": {"budgetId": bid}}}


def event(cost):
    return budget("hackathon-starter £10", cost, bid=cc.EVENT_BUDGET_ID)


class FakeGcloud:
    def __init__(self, world):
        self.world, self.calls = world, []

    def __call__(self, *args, parse=True):
        self.calls.append(args)
        project = args[args.index("--project") + 1]
        key = " ".join(a for a in args[:3] if not a.startswith("-"))
        if not parse:
            return ""
        for prefix, value in self.world.get(project, {}).items():
            if key.startswith(prefix):
                return value
        return []

    def changes(self):
        return [c for c in self.calls if c[1] in ("services",) and c[2] in ("update", "update-traffic", "delete")]


class SpendGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = mock.patch.object(cc, "STATE", Path(self.tmp.name) / "spend.json")
        self.state.start()

    def tearDown(self):
        self.state.stop()
        self.tmp.cleanup()

    def world(self, budgets=()):
        return FakeGcloud({
            "my-events-project": {
                "run services list": [service("strata", {"revisionName": "live", "percent": 100},
                                              {"revisionName": "stale", "tag": "pr1"},
                                              {"revisionName": "fresh", "tag": "pr2"}),
                                      service("other", {"revisionName": "cold", "percent": 100})],
                "run revisions list": [rev("live", "2026-11-09T11:00:00Z"), rev("stale", "2026-11-08T12:00:00Z"),
                                       rev("fresh", "2026-11-09T09:00:00Z"), rev("cold", "2026-11-01T00:00:00Z", "0")],
                "compute instances list": [vm("render-box", gpus=1)],
            },
            "my-hub-project": {
                "compute instances list": [vm("hub-host")],
                "run jobs list": [{"metadata": {"name": "demo-film-render", "labels": LOC}}],
                "run jobs executions": [
                    {"metadata": {"name": "render-a", "labels": LOC}, "status": {"startTime": "2026-11-09T09:00:00Z"}},
                    {"metadata": {"name": "render-b", "labels": LOC}, "status": {"startTime": "2026-11-09T11:00:00Z"}},
                    {"metadata": {"name": "render-c", "labels": LOC},
                     "status": {"startTime": "2026-11-08T09:00:00Z", "completionTime": "2026-11-08T09:05:00Z"}}],
                "pubsub subscriptions pull": list(budgets),
            }})

    def test_a_stale_min_instance_tag_is_scaled_down_and_a_fresh_one_left(self):
        g = self.world()
        text, log = cc.run(False, NOW, g)
        self.assertEqual(g.changes(), [("run", "services", "update-traffic", "strata", "--region", "europe-west2",
                                        "--project", "my-events-project", "--remove-tags", "pr1")])
        self.assertIn("--remove-tags pr1", text)

    def test_only_a_vm_other_than_hub_host_is_reported_and_only_once(self):
        text, _ = cc.run(False, NOW, self.world())
        self.assertIn("VM render-box in my-events-project (europe-west2-a, RUNNING, 1 GPU)", text)
        self.assertNotIn("hub-host ", text.replace("my-hub-project", ""))
        g = self.world()
        text, _ = cc.run(False, NOW, g)
        self.assertNotIn("render-box", text)
        self.assertFalse(any(c[1] == "instances" and c[2] not in ("list",) for c in g.calls))  # never deletes a VM

    def test_a_job_running_over_two_hours_is_reported(self):
        text, _ = cc.run(False, NOW, self.world())
        self.assertIn("render-a in my-hub-project/europe-west2 has run 3.0h", text)
        self.assertNotIn("execution render-b", text)
        self.assertNotIn("execution render-c", text)

    def test_budget_thresholds_are_reported_once_each(self):
        text, _ = cc.run(False, NOW, self.world([budget("hub-host", 56, 110)]))
        self.assertIn("budget hub-host: 56.00 of 110.00 GBP spent (50% crossed)", text)
        text, _ = cc.run(False, NOW, self.world([budget("hub-host", 57, 110)]))
        self.assertNotIn("budget", text)
        text, _ = cc.run(False, NOW, self.world([budget("hub-host", 100, 110), budget("hub-host", 30, 110)]))
        self.assertIn("(90% crossed)", text)

    def test_hackathon_starter_at_100_percent_deletes_its_services_in_dry_run_only_as_a_plan(self):
        g = self.world([event(10.4)])
        text, log = cc.run(True, NOW, g)
        self.assertIn("would delete my-events-project service strata (europe-west2)", text)
        self.assertIn("would delete my-events-project service other (europe-west2)", text)
        self.assertIn("dry-run: gcloud run services delete strata --region europe-west2 --project my-events-project",
                      log)
        self.assertEqual([c for c in g.calls if "delete" in c or "update-traffic" in c or "update" in c[:3]], [])
        self.assertFalse(cc.STATE.exists())  # a dry run remembers nothing
        pull = next(c for c in g.calls if c[:3] == ("pubsub", "subscriptions", "pull"))
        self.assertNotIn("--auto-ack", pull)  # nor consumes the notifications
        self.assertFalse(any(c[:3] == ("pubsub", "subscriptions", "ack") for c in g.calls))

    def test_a_failed_event_delete_is_retried_every_hour_until_it_succeeds(self):
        g = self.world([event(10.4)])

        def delete_fails(*args, parse=True):
            if args[:3] == ("run", "services", "delete"):
                raise cc.subprocess.CalledProcessError(1, "gcloud", stderr="UNAVAILABLE")
            return g(*args, parse=parse)

        text, log = cc.run(False, NOW, delete_fails)
        self.assertNotIn("deleted my-events-project service", text)
        self.assertIn("not all deleted yet", text)
        self.assertTrue(any(line.startswith("could not delete strata") for line in log))
        g.world["my-hub-project"]["pubsub subscriptions pull"] = []  # acked: the notification does not come back
        g.calls.clear()
        text, _ = cc.run(False, NOW, g)
        self.assertIn("deleted my-events-project service strata (europe-west2)", text)
        g.calls.clear()
        cc.run(False, NOW, g)  # done once, it is not repeated
        self.assertFalse(any("delete" in c for c in g.calls))

    def test_a_budget_named_like_the_event_one_deletes_nothing(self):
        g = self.world([budget("hub-host / not hackathon-starter", 120, 110, bid="hub-budget")])
        text, _ = cc.run(False, NOW, g)
        self.assertIn("(100% crossed)", text)
        self.assertFalse(any("delete" in c for c in g.calls))

    def test_an_alert_that_fails_to_send_is_sent_with_the_next_run(self):
        sends = []

        def hubwa(argv, **kw):
            sends.append(argv[4])
            return cc.subprocess.CompletedProcess(argv, 1 if len(sends) == 1 else 0)

        g, real_run = self.world(), cc.run
        with mock.patch.object(cc, "run", side_effect=lambda dry: real_run(dry, NOW, g)), \
                mock.patch.object(cc.subprocess, "run", side_effect=hubwa), \
                mock.patch.object(cc.sys, "argv", ["cloudrun_check.py"]), \
                mock.patch("builtins.print"):
            cc.main()  # send fails
            cc.main()  # the VM is already seen, but the unsent alert goes out now
            cc.main()  # once delivered, it is not sent again
        self.assertIn("unexpected cloud machine", sends[0])
        self.assertIn("unexpected cloud machine", sends[1])
        self.assertEqual(len(sends), 2)  # the fake's stale tag, re-fixed each run, reaches only the journal

    def test_notifications_are_acked_only_after_the_state_is_on_disk(self):
        g = self.world([event(10.4)])
        with mock.patch.object(cc, "save_state", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cc.run(False, NOW, g)
        self.assertFalse(any(c[:3] in (("pubsub", "subscriptions", "ack"), ("run", "services", "delete"))
                             for c in g.calls))  # left on the subscription for the next run
        cc.run(False, NOW, g)
        self.assertIn(("pubsub", "subscriptions", "ack", "hub-spend", "--project", "my-hub-project", "--ack-ids", "a"),
                      g.calls)

    def test_two_budgets_sharing_a_display_name_are_told_apart(self):
        g = self.world([budget("hackathon-starter £10", 10.4, bid="other")])
        cc.run(False, NOW, g)
        g.world["my-hub-project"]["pubsub subscriptions pull"] = [event(10.4)]
        text, _ = cc.run(False, NOW, g)
        self.assertIn("deleted my-events-project service strata", text)

    def test_hub_host_at_100_percent_deletes_nothing(self):
        g = self.world([budget("hub-host", 120, 110)])
        text, _ = cc.run(False, NOW, g)
        self.assertIn("(100% crossed)", text)
        self.assertFalse(any("delete" in c for c in g.calls))

    def test_a_failing_check_is_logged_and_the_rest_still_runs(self):
        g = self.world()

        def broken(*args, parse=True):
            if args[:2] == ("compute", "instances"):
                raise cc.subprocess.CalledProcessError(1, "gcloud", stderr="PERMISSION_DENIED")
            return g(*args, parse=parse)

        text, log = cc.run(False, NOW, broken)
        self.assertTrue(any("PERMISSION_DENIED" in l for l in log), log)
        self.assertIn("--remove-tags pr1", text)

    def test_an_interrupted_state_write_keeps_the_previous_pending_delete(self):
        cc.save_state({"seen": [], "pending_delete": "earlier-hour"})
        real = Path.write_text

        def torn(path, data, *a, **kw):  # the write dies half way
            real(path, data[:1])
            raise OSError("power cut")

        with mock.patch.object(Path, "write_text", torn), self.assertRaises(OSError):
            cc.save_state({"seen": []})
        self.assertEqual(cc.load_state()["pending_delete"], "earlier-hour")

    def test_a_corrupt_state_file_warns_and_quarantines_but_deletes_nothing(self):
        cc.STATE.write_text("{")
        g = self.world()
        cc.run(False, NOW, g)
        self.assertFalse(any(c[:3] == ("run", "services", "delete") for c in g.calls))
        state = cc.load_state()
        self.assertNotIn("pending_delete", state)
        self.assertTrue(state["quarantined"])
        self.assertTrue(any("saved notes damaged" in u for u in state["unsent"]))
        self.assertEqual(cc.STATE.with_name("spend.json.corrupt").read_text(), "{")

    def test_a_dry_run_writes_nothing_even_over_corrupt_state(self):
        cc.STATE.write_text("{")
        cc.run(True, NOW, g := self.world())
        self.assertEqual([p.name for p in cc.STATE.parent.iterdir()], ["spend.json"])
        self.assertEqual(cc.STATE.read_text(), "{")
        self.assertFalse(any(c[:3] == ("run", "services", "delete") for c in g.calls))

    def test_the_legacy_corrupt_state_marker_is_neutralized_and_a_real_one_kept(self):
        cc.save_state({"seen": [], "pending_delete": "corrupt-state"})  # left by 572734b
        cc.run(False, NOW, g := self.world())
        self.assertFalse(any(c[:3] == ("run", "services", "delete") for c in g.calls))
        state = cc.load_state()
        self.assertNotIn("pending_delete", state)
        self.assertTrue(any("old, mistaken shutdown instruction" in u for u in state["unsent"]))
        cc.save_state({"seen": [], "pending_delete": "b1|2026-11-01T00:00:00Z|1.0"})
        cc.run(False, NOW, g := self.world())
        self.assertTrue(any(c[:3] == ("run", "services", "delete") for c in g.calls))

    def test_an_acked_budget_alert_is_already_queued_to_send(self):
        g = self.world([budget("hub-host", 56, 110)])

        def stop_after_ack(*args, parse=True):
            if args[:3] == ("run", "services", "list"):
                raise SystemExit("killed after the ack")
            return g(*args, parse=parse)

        with self.assertRaises(SystemExit):
            cc.run(False, NOW, stop_after_ack)
        self.assertIn(("pubsub", "subscriptions", "ack", "hub-spend", "--project", "my-hub-project", "--ack-ids", "a"),
                      g.calls)
        self.assertIn("The hub's cloud budget is over half used: about £56 of £110 spent.",
                      cc.load_state()["unsent"])

    def test_a_seen_vm_is_queued_to_send_in_the_same_write(self):
        cc.run(False, NOW, self.world())  # main() never gets to send
        state = cc.load_state()
        self.assertIn("vm|my-events-project|render-box", state["seen"])
        self.assertTrue(any("unexpected cloud machine" in u for u in state["unsent"]))

    def test_one_delivery_repeated_in_a_pull_is_one_alert(self):
        self.assertEqual(len(cc.budget_alerts([event(10.4), event(10.4)], set())), 1)


if __name__ == "__main__":
    unittest.main()
