"""Prometheus's delivery probes on 6381ca8 (T-1101 review): no budget or shutdown alert is ever lost. Real spend+hubwa control flow, fake cloud/API and temporary files only."""
import contextlib,importlib.machinery,importlib.util,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from tests import test_spend as ts
loader=importlib.machinery.SourceFileLoader("review_hubwa",str(Path(__file__).resolve().parent.parent/"hubwa"))
h=importlib.util.module_from_spec(importlib.util.spec_from_loader("review_hubwa",loader));loader.exec_module(h)

class Delivery(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="whatsapp-review-");self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.posted=[]
        for obj,name,value in [(ts.cc,"STATE",root/"spend.json"),(h,"STATE",root/"phone"),
              (h,"conversation",lambda:{"id":"fake-chat","chatWindowRemainingTime":3600}),
              (h,"call",lambda *a:self.posted.append(a[2]["text"]["body"]))]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)

    def run_hour(self,name="event apps",legacy=None):
        msg=ts.event(11)
        data=json.loads(ts.base64.b64decode(msg["message"]["data"]))
        data["budgetDisplayName"]=name
        msg["message"]["data"]=ts.base64.b64encode(json.dumps(data).encode()).decode()
        g=ts.FakeGcloud({"my-hub-project":{"pubsub subscriptions pull":[msg]},
                        "my-events-project":{"run services list":[ts.service("event-app")]}})
        if legacy is not None:ts.cc.save_state({"seen":[],"unsent":[legacy]})
        real_run=ts.cc.run
        def transport(argv,**kwargs):
            self.assertEqual(argv[:4],["timeout","60","hubwa","send"])
            code=0
            try:
                with patch.object(h.sys,"argv",["hubwa","send",argv[4]]):
                    result=h.main()
                    code=result if isinstance(result,int) else 0
            except SystemExit as e:
                code=e.code if isinstance(e.code,int) else int(bool(e.code))
            return subprocess.CompletedProcess(argv,code)
        with patch.object(ts.cc,"run",side_effect=lambda dry:real_run(dry,ts.NOW,g)), \
             patch.object(ts.cc.subprocess,"run",side_effect=transport), \
             patch.object(ts.cc.sys,"argv",["cloudrun_check.py"]),contextlib.redirect_stdout(io.StringIO()):
            ts.cc.main()
        return ts.cc.load_state(),g

    def assert_critical_alert_not_lost(self,state):
        self.assertTrue(self.posted or state.get("unsent"),
                        "critical budget/shutdown alert was neither posted nor retained; drop treated as successful delivery")

    def test_budget_named_disk_is_not_silently_consumed(self):
        state,g=self.run_hour("disk backups")
        self.assertTrue(any(c[:3]==("run","services","delete") for c in g.calls))
        self.assert_critical_alert_not_lost(state)

    def test_budget_name_with_a_percentage_is_not_silently_consumed(self):
        state,_=self.run_hour("Event budget 100%")
        self.assert_critical_alert_not_lost(state)

    def test_a_legacy_technical_alert_cannot_poison_the_new_shutdown_batch(self):
        state,_=self.run_hour(legacy="Cloud spend guard: budget event 11.00 of 10.00 GBP spent (100% crossed)")
        self.assert_critical_alert_not_lost(state)

    def test_old_held_budget_alert_is_not_silently_erased(self):
        h.STATE.mkdir(parents=True)
        held=h.STATE/"held.jsonl"
        held.write_text(json.dumps({"at":"2026-11-09T12:00:00Z", "text":"Cloud spend guard: budget event 11.00 of 10.00 GBP spent (100% crossed)"})+"\n")
        h.send_held()
        self.assertTrue(self.posted or held.exists(),"held critical budget alert was neither posted nor retained")

    def test_stopped_vm_is_not_described_as_running(self):
        v=ts.vm("spare-box");v["status"]="TERMINATED"
        g=ts.FakeGcloud({"my-events-project":{"compute instances list":[v]}})
        ts.cc.run(False,ts.NOW,g)
        state=ts.cc.load_state()
        self.assertTrue(state["unsent"])
        self.assertNotIn(" is running", " ".join(state["unsent"]))

    def test_plain_budget_shutdown_alert_still_posts(self):
        state,_=self.run_hour()
        self.assertEqual(len(self.posted),1)
        self.assertIn("budget is used up",self.posted[0])
        self.assertEqual(state["unsent"],[])

if __name__=="__main__":unittest.main(defaultTest="Delivery")
