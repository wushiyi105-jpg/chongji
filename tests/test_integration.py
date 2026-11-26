"""集成测试:真起 HTTP 服务、真跑子进程 CLI、按住本仓修过的四个 bug。

对应 issue:
- #6 「2岁3个月」被算成 3 个月
- #7 「上次 14.6kg,今天 13.4kg」当前体重被取成上次值
- #8 正文克数与公式克数不一致
- #9 「吐毛球」判成无明确症状
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from chongji import agent, cli, rules, web
from chongji import db as dbmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def case(name):
    with open(os.path.join(ROOT, "examples", name), encoding="utf-8") as f:
        return f.read().strip()


def run_cli(args, stdin_text=None):
    cmd = [PY, "-m", "chongji"] + args
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", input=stdin_text, timeout=120)


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.dbpath = os.path.join(cls.tmp, "chongji.db")
        cls.db = dbmod.Database(cls.dbpath)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), web._handler(cls.db, {}, True))
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.db.close()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def post(self, path, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url(path), data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_index_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("宠记", body)
        self.assertIn("开始评估", body)

    def test_status_is_mock(self):
        status, body = self.get("/api/status")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["mock"])
        self.assertIsNone(payload["model"])

    def test_care_reads_current_weight(self):
        """#7:同一份描述里「上次」在前,当下体重不能被吃掉。"""
        status, r = self.post("/api/care", {"text": case("case-03.txt")})
        self.assertEqual(status, 200)
        self.assertAlmostEqual(r["weight"], 13.4, places=1)
        self.assertIn("掉秤", r["trend"]["alert"])
        self.assertGreater(r["saved_id"], 0)

    def test_care_empty_text(self):
        status, r = self.post("/api/care", {"text": "   "})
        self.assertEqual(status, 200)
        self.assertIn("信息不足", r["verdict"])

    def test_unknown_get_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_records_persisted(self):
        self.post("/api/care", {"text": case("case-01.txt")})
        rows = self.db.latest(20)
        self.assertTrue(rows)
        self.assertTrue(any(row["species"] == "猫" for row in rows))


class TestRules(unittest.TestCase):
    def test_age_years_plus_months(self):
        """#6:「2岁3个月」= 27 个月,不是 3 个月。"""
        self.assertEqual(rules.age_months("2岁3个月"), 27)
        r = rules.analyze("猫 2岁3个月 4.2kg 已绝育")
        self.assertEqual(r["months"], 27)
        self.assertEqual(r["stage"]["key"], "adult_neutered")

    def test_age_single_forms_unchanged(self):
        """#6 反方向:单写岁或单写月都不能被改坏。"""
        self.assertEqual(rules.age_months("3个月"), 3)
        self.assertEqual(rules.age_months("2岁"), 24)
        self.assertEqual(rules.age_months("1.5岁"), 18)
        self.assertIsNone(rules.age_months("不知道多大"))

    def test_previous_weight_is_not_current(self):
        """#7:「上次」只当基准,不当当下。"""
        text = "柯基复诊,上次 14.6kg,今天 13.4kg"
        self.assertAlmostEqual(rules.weight_kg(text), 13.4, places=1)
        self.assertAlmostEqual(rules.prev_weight(text), 14.6, places=1)
        t = rules.weight_trend(text, rules.weight_kg(text))
        self.assertAlmostEqual(t["change_pct"], -8.2, places=1)
        self.assertIn("掉秤", t["alert"])

    def test_previous_only_falls_back_with_note(self):
        """#7:只给上次体重时不假装有趋势,但要提示。"""
        r = rules.analyze("柯基 上次 12.3kg 精神一般")
        self.assertAlmostEqual(r["weight"], 12.3, places=1)
        self.assertIsNone(r["trend"])
        self.assertTrue(any("上次体重" in n for n in r["notes"]))

    def test_grams_match_formula(self):
        """#8:正文克数与公式克数必须是同一个数。"""
        r = agent.care(case("case-04.txt"), force_mock=True)
        shown = re.search(r"= (\d+) g$", r["plan"]["formula"])
        self.assertIsNotNone(shown)
        self.assertEqual(int(shown.group(1)), r["plan"]["grams"])
        self.assertIn("每日 %d g" % r["plan"]["grams"],
                      cli.render(r))

    def test_hairball_is_observe(self):
        """#9:吐毛球进「先观察」,但不能把红旗带歪。"""
        t = rules.triage("最近偶尔吐毛球,一周一两次")
        self.assertEqual(t["level"], "先观察")
        self.assertIn("吐毛球", [h["item"] for h in t["hits"]])
        self.assertEqual(rules.triage("吐血了")["level"], "立即就医")
        self.assertEqual(rules.triage("吐了两次")["level"], "24 小时内")

    def test_offline_layers_by_schema(self):
        """模型层 schema 是本仓自己的 summary/care_tips/risks。"""
        r = agent.care(case("case-02.txt"), force_mock=True)
        self.assertEqual(r["mode"], "offline")
        self.assertTrue(r["summary"] and r["care_tips"] and r["risks"])


class TestCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.dbarg = os.path.join(cls.tmp, "cli.db")

    def test_case01_stage_is_adult(self):
        r = run_cli(["--mock", "--db", self.dbarg, "care", "--file", "examples/case-01.txt"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("月龄:27", r.stdout)
        self.assertIn("成体已绝育", r.stdout)
        self.assertIn("每日 91 g", r.stdout)

    def test_case03_weight_loss_alert(self):
        r = run_cli(["--mock", "--db", self.dbarg, "care", "--file", "examples/case-03.txt"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("13.40 kg", r.stdout)
        self.assertIn("掉秤 8.2%", r.stdout)

    def test_json_output(self):
        r = run_cli(["--mock", "--db", self.dbarg, "--json", "care",
                     "--file", "examples/case-04.txt"])
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["triage"]["level"], "立即就医")
        self.assertEqual(payload["mode"], "offline")

    def test_stdin_input(self):
        r = run_cli(["--mock", "--db", self.dbarg, "care"], stdin_text="猫 3.5kg 4岁 绝育")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("成体已绝育", r.stdout)

    def test_empty_input_exit_2(self):
        r = run_cli(["--mock", "--db", self.dbarg, "care"], stdin_text="")
        self.assertEqual(r.returncode, 2)
        self.assertIn("没有描述", r.stderr)

    def test_foods_and_symptoms(self):
        r = run_cli(["foods"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("干粮", r.stdout)
        self.assertIn("阶段系数", r.stdout)
        r = run_cli(["symptoms"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("立即就医", r.stdout)
        self.assertIn("红旗", r.stdout)

    def test_history_empty_hint(self):
        dbpath = os.path.join(self.tmp, "empty.db")
        r = run_cli(["--db", dbpath, "history"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("还没有记录", r.stdout)


if __name__ == "__main__":
    unittest.main()
