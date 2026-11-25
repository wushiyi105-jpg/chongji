import unittest

from chongji import agent, rules


def cat():
    return "猫,4.2kg,2岁,已绝育,今天吐了两次,精神还行,上次 4.5kg"


class TestBasics(unittest.TestCase):
    def test_species_cat(self):
        self.assertEqual(rules.species("布偶猫 4kg")["key"], "cat")

    def test_species_dog(self):
        self.assertEqual(rules.species("柯基 12kg")["key"], "dog")

    def test_species_none(self):
        self.assertIsNone(rules.species("4kg 两岁"))

    def test_weight_kg(self):
        self.assertEqual(rules.weight_kg("猫 4.2kg"), 4.2)

    def test_weight_jin(self):
        self.assertEqual(rules.weight_kg("狗 20斤"), 10.0)

    def test_weight_none(self):
        self.assertIsNone(rules.weight_kg("不知道多重"))

    def test_age_months(self):
        self.assertEqual(rules.age_months("3个月"), 3)

    def test_age_years(self):
        self.assertEqual(rules.age_months("2岁"), 24)

    def test_age_years_float(self):
        self.assertEqual(rules.age_months("1.5岁"), 18)


class TestStage(unittest.TestCase):
    def test_puppy(self):
        self.assertEqual(rules.stage(rules.species("狗"), 3)["key"], "puppy")

    def test_junior(self):
        self.assertEqual(rules.stage(rules.species("狗"), 8)["key"], "junior")

    def test_adult_neutered(self):
        sp = rules.species("狗")
        self.assertEqual(rules.stage(sp, 36, neutered=True)["key"], "adult_neutered")

    def test_adult_intact(self):
        sp = rules.species("狗")
        self.assertEqual(rules.stage(sp, 36, neutered=False)["key"], "adult_intact")

    def test_senior(self):
        sp = rules.species("狗")
        self.assertEqual(rules.stage(sp, 120)["key"], "senior")

    def test_diet(self):
        self.assertEqual(rules.stage(rules.species("猫"), 24, diet=True)["key"], "diet")


class TestFood(unittest.TestCase):
    def test_rer(self):
        self.assertAlmostEqual(rules.rer(5), 70 * 5 ** 0.75, places=1)

    def test_der(self):
        self.assertAlmostEqual(rules.der(234.1, 1.6), 374.6, places=1)

    def test_plan_dry_cat(self):
        plan = rules.food_plan(4.2, {"factor": 1.6, "meals": 2})
        self.assertEqual(plan["grams"], round(rules.rer(4.2) * 1.6 / 3.6))
        self.assertEqual(plan["per_meal"], round(plan["grams"] / 2))

    def test_plan_wet_more_grams(self):
        dry = rules.food_plan(4.2, {"factor": 1.6, "meals": 2}, "dry")
        wet = rules.food_plan(4.2, {"factor": 1.6, "meals": 2}, "wet")
        self.assertGreater(wet["grams"], dry["grams"])

    def test_formula_text(self):
        plan = rules.food_plan(4.2, {"factor": 1.6, "meals": 2})
        self.assertIn("RER", plan["formula"])


class TestTrend(unittest.TestCase):
    def test_loss_alert(self):
        t = rules.weight_trend("上次 4.5kg", 4.2)
        self.assertLess(t["change_pct"], 0)
        self.assertIn("掉秤", t["alert"])

    def test_gain_alert(self):
        t = rules.weight_trend("上次 4.0kg", 4.5)
        self.assertIn("涨秤", t["alert"])

    def test_stable(self):
        t = rules.weight_trend("上次 4.2kg", 4.2)
        self.assertIsNone(t["alert"])

    def test_no_previous(self):
        self.assertIsNone(rules.weight_trend("4.2kg", 4.2))


class TestTriage(unittest.TestCase):
    def test_red(self):
        t = rules.triage("猫尿闭了,一直蹲")
        self.assertEqual(t["level"], "立即就医")
        self.assertIn("尿闭", t["flags"])

    def test_amber(self):
        t = rules.triage("吐了两次,有点拉稀")
        self.assertEqual(t["level"], "24 小时内")

    def test_green(self):
        t = rules.triage("偶尔挠耳朵")
        self.assertEqual(t["level"], "先观察")

    def test_none(self):
        self.assertEqual(rules.triage("今天挺正常")["level"], "无明确症状")


class TestVaccineAndAgent(unittest.TestCase):
    def test_puppy_next(self):
        rows = rules.vaccine_plan(rules.species("狗"), 3)
        self.assertTrue(any(r["next"] for r in rows))

    def test_adult_booster(self):
        rows = rules.vaccine_plan(rules.species("猫"), 24)
        self.assertTrue(all(r["status"] == "年度加强" for r in rows))

    def test_offline_structure(self):
        r = agent.care(cat(), force_mock=True)
        self.assertEqual(r["mode"], "offline")
        for k in ("summary", "care_tips", "risks", "plan", "triage", "vaccines"):
            self.assertTrue(r[k])

    def test_verdict_has_grams(self):
        r = agent.care(cat(), force_mock=True)
        self.assertIn("每天", r["verdict"])

    def test_strip_units(self):
        self.assertNotIn("90 g", agent.strip_units("每天 90 g"))

    def test_cat_not_eating_risk(self):
        r = agent.care("猫 4kg 不吃东西两天", force_mock=True)
        self.assertTrue(any("脂肪肝" in x for x in r["risks"]))

    def test_unknown(self):
        r = agent.care("不知道", force_mock=True)
        self.assertTrue(r["notes"])


if __name__ == "__main__":
    unittest.main()
