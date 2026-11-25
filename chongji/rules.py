"""宠物照护本地规则:RER/DER 喂食量、免疫与驱虫日历、体重趋势、症状分级、就诊清单。"""

import json
import os
import re
from datetime import date, timedelta

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
KG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|公斤|千克)", re.I)
JIN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*斤")
AGE_M_RE = re.compile(r"(\d+)\s*个?月")
AGE_Y_RE = re.compile(r"(\d+(?:\.\d+)?)\s*岁")
PREV_RE = re.compile(r"上次\s*(\d+(?:\.\d+)?)\s*(kg|公斤|斤)")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def species(text):
    low = (text or "").lower()
    for s in load("species.json")["species"]:
        if any(k.lower() in low for k in s["keywords"]):
            return s
    return None


def weight_kg(text):
    m = KG_RE.search(text or "")
    if m:
        return float(m.group(1))
    m = JIN_RE.search(text or "")
    if m:
        return round(float(m.group(1)) / 2, 2)
    return None


def age_months(text):
    m = AGE_M_RE.search(text or "")
    if m:
        return int(m.group(1))
    m = AGE_Y_RE.search(text or "")
    if m:
        return int(float(m.group(1)) * 12)
    return None


def stage(sp, months, neutered=False, diet=False):
    stages = {s["key"]: s for s in load("species.json")["stages"]}
    if diet:
        return stages["diet"]
    if months is None:
        return stages["adult_neutered"] if neutered else stages["adult_intact"]
    if months < 4:
        return stages["puppy"]
    if months < 12:
        return stages["junior"]
    if sp and months >= sp["senior_years"] * 12:
        return stages["senior"]
    return stages["adult_neutered"] if neutered else stages["adult_intact"]


def rer(bw):
    return 70 * (bw ** 0.75)


def der(rer_value, factor):
    return rer_value * factor


def food_plan(bw, st, food_key="dry"):
    r = rer(bw)
    d = der(r, st["factor"])
    food = [f for f in load("species.json")["foods"] if f["key"] == food_key][0]
    grams = d / (food["kcal_per_100g"] / 100)
    per_meal = grams / st["meals"]
    return {"rer": round(r, 1), "der": round(d, 1), "food": food["name"],
            "kcal_per_100g": food["kcal_per_100g"], "grams": round(grams),
            "meals": st["meals"], "per_meal": round(per_meal),
            "formula": "RER = 70 × %.2f^0.75 = %.1f kcal;DER = RER × %.1f = %.1f kcal;"
                       "克数 = DER ÷ (%.0f kcal/100g) = %d g" % (bw, r, st["factor"], d,
                                                                 food["kcal_per_100g"], grams)}


def weight_trend(text, bw):
    m = PREV_RE.search(text or "")
    if not m or not bw:
        return None
    prev = float(m.group(1))
    if m.group(2) == "斤":
        prev = round(prev / 2, 2)
    change = (bw - prev) / prev
    pct = round(change * 100, 1)
    alert = None
    if pct <= -5:
        alert = "掉秤 %.1f%%,两周内复查;持续下降要查原因(牙口、消化、甲亢、肾病)" % abs(pct)
    elif pct >= 8:
        alert = "涨秤 %.1f%%,先按减重系数喂,别继续加量" % pct
    return {"previous": prev, "current": bw, "change_pct": pct, "alert": alert}


def vaccine_plan(sp, months, today=None):
    today = today or date.today()
    rows = []
    for v in load("species.json")["vaccines"]:
        if months is None:
            rows.append({"name": v["name"], "status": "缺月龄", "next": None, "note": "补一句「3个月」或「2岁」"})
            continue
        if months < 4 and v["puppy_doses"]:
            weeks = months * 4
            nxt = next((w for w in v["puppy_age_weeks"] if w > weeks), None)
            if nxt:
                days = (nxt - weeks) / 4 * 30
                rows.append({"name": v["name"], "status": "幼年基础免疫",
                             "next": (today + timedelta(days=int(days))).isoformat(),
                             "note": "第 %d 针在 %d 周龄左右" % (v["puppy_doses"], nxt)})
            else:
                rows.append({"name": v["name"], "status": "基础免疫完成",
                             "next": (today + timedelta(days=365)).isoformat(), "note": "满 1 年加强"})
        else:
            rows.append({"name": v["name"], "status": "年度加强",
                         "next": (today + timedelta(days=int(v["booster_months"] * 30))).isoformat(),
                         "note": "按上次接种日顺延 %d 个月" % v["booster_months"]})
    return rows


def triage(text):
    hits = []
    low = (text or "").lower()
    for s in load("species.json")["symptoms"]:
        for item in s["items"]:
            if item in low:
                hits.append({"level": s["level"], "color": s["color"], "item": item})
    flags = [f for f in load("species.json")["red_flags"] if f in low]
    if flags:
        return {"level": "立即就医", "flags": flags, "hits": hits,
                "why": "命中红旗症状:%s,不要在家观察" % "、".join(flags)}
    mild = [h for h in hits if h["level"] == "先观察"]
    if mild and ("偶尔" in (text or "") or "轻微" in (text or "")):
        return {"level": "先观察", "flags": [], "hits": hits,
                "why": "描述为「偶尔/轻微」,可先观察 24 小时并记录变化"}
    if any(h["level"] == "24 小时内" for h in hits):
        return {"level": "24 小时内", "flags": [], "hits": hits, "why": "症状需要 24 小时内面诊,先禁食观察精神"}
    if hits:
        return {"level": "先观察", "flags": [], "hits": hits, "why": "可先观察 24 小时,记录精神、食欲、排便"}
    return {"level": "无明确症状", "flags": [], "hits": [], "why": "描述里没有可分级症状,补充「吐了几次/精神如何」"}


def vet_checklist(text):
    checks = [
        ("体重与品种", ["kg", "公斤", "斤", "品种", "猫", "狗"], "带上最近三个月的体重记录"),
        ("症状时间线", ["开始", "几天", "昨天", "今天", "次"], "什么时候开始、频率、诱因"),
        ("食欲饮水", ["不吃", "食欲", "喝水", "饮水"], "近 24 小时吃多少、喝多少"),
        ("排便排尿", ["便", "尿", "拉稀", "呕吐"], "颜色、形状、次数,最好拍照"),
        ("用药与疫苗", ["疫苗", "驱虫", "吃药", "用药"], "近一个月用过什么药、上次疫苗时间"),
        ("既往病史", ["以前", "做过手术", "过敏", "慢性"], "手术、过敏、慢性病与正在吃的药"),
    ]
    return [{"item": n, "ok": any(k in (text or "").lower() for k in keys), "how": how}
            for n, keys, how in checks]


def analyze(text, today=None):
    sp = species(text)
    bw = weight_kg(text)
    months = age_months(text)
    neutered = "绝育" in (text or "")
    diet = "减肥" in (text or "") or "减重" in (text or "")
    notes = []
    if sp is None:
        notes.append("没识别到猫/狗,按狗估算;补一句「猫」或「狗」更准")
    if bw is None:
        notes.append("没写体重,算不出喂食量;补「8.5kg」或「12斤」")
    st = stage(sp, months, neutered, diet)
    plan = food_plan(bw, st) if bw else None
    trend = weight_trend(text, bw)
    tri = triage(text)
    return {"species": sp, "weight": bw, "months": months, "neutered": neutered,
            "stage": st, "plan": plan, "trend": trend, "triage": tri,
            "vaccines": vaccine_plan(sp, months, today),
            "checklist": vet_checklist(text), "notes": notes}
