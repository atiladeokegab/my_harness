"""cloudrun_check flags old routed revisions (live or tagged) that keep a min instance."""

import importlib.util
import unittest
from datetime import UTC, datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("cloudrun_check", Path(__file__).resolve().parent.parent / "cloudrun_check.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

NOW = datetime(2026, 11, 6, tzinfo=UTC)  # "fresh" (4h old) is under MAX_AGE


def rev(name, created, min_scale="1"):
    ann = {"autoscaling.knative.dev/minScale": min_scale} if min_scale else {}
    return {"metadata": {"name": name, "creationTimestamp": created, "annotations": ann}}


SERVICE = {"metadata": {"name": "strata", "labels": {"cloud.googleapis.com/location": "europe-west2"}},
           "status": {"traffic": [
               {"revisionName": "live", "tag": "next25", "percent": 100},
               {"revisionName": "old", "tag": "next"},
               {"revisionName": "fresh", "tag": "next24"},
               {"revisionName": "cold", "tag": "next23"},
               {"revisionName": "old"},
           ]}}
REVISIONS = [rev("live", "2026-11-01T00:00:00Z"), rev("old", "2026-11-02T13:24:00.5Z"),
             rev("fresh", "2026-11-05T20:00:00Z"), rev("cold", "2026-11-01T00:00:00Z", min_scale=None)]


class CloudRunCheck(unittest.TestCase):
    def test_flags_old_warm_live_and_tagged(self):
        self.assertEqual(cc.stale_tags([SERVICE], REVISIONS, NOW),
                         [("strata", "europe-west2", None), ("strata", "europe-west2", "next")])

    def test_a_tag_fresher_than_six_hours_is_left(self):
        young = [rev("live", "2026-11-05T19:00:00Z"), rev("old", "2026-11-05T17:59:00Z")]
        self.assertEqual(cc.stale_tags([SERVICE], young, NOW), [("strata", "europe-west2", "next")])

    def test_fixes_scale_live_down_and_drop_old_tags(self):
        cmds = cc.fixes([("strata", "europe-west2", None), ("strata", "europe-west2", "next"),
                         ("strata", "europe-west2", "next2")], "p")
        where = ["--region", "europe-west2", "--project", "p"]
        self.assertEqual(cmds, [["run", "services", "update", "strata", *where, "--min-instances", "0"],
                                ["run", "services", "update-traffic", "strata", *where, "--to-latest"],
                                ["run", "services", "update-traffic", "strata", *where, "--remove-tags", "next,next2"]])


if __name__ == "__main__":
    unittest.main()
