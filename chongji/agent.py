"""编排:喂食量、免疫日历、体重趋势、症状分级全在本地;模型只写照护解释与提醒。

克数与卡路里一律本地算:模型输出里的「N g」「N kcal」会被剥掉。
"""

from __future__ import annotations

import re

from . import llm, mock, rules

JSON_ONLY = "只输出 JSON,不要输出解释或多余文字。"
NUM_RE = re.compile(r"(¥|￥)?\s*\d+(?:\.\d+)?\s*(?:g|克|kcal|千卡|大卡|kg|公斤)")


def _use_model(config, force_mock):
    if force_mock:
        return False
    return bool({**llm.default_config(), **(config or {})}.get("api_key"))


def _cfg(config):
    return {**llm.default_config(), **(config or {})}


def strip_units(text):
    return NUM_RE.sub("相应份量", text)


def verdict(r):
    parts = []
    if r["species"]:
        parts.append(r["species"]["name"])
    if r["weight"]:
        parts.append("%.2f kg" % r["weight"])
    if r["plan"]:
        parts.append("每天 %d g,分 %d 顿,每顿约 %d g" % (r["plan"]["grams"], r["plan"]["meals"],
                                                          r["plan"]["per_meal"]))
    head = ",".join(parts[:2]) + "。" if parts else ""
    if r["plan"]:
        head += "按 %s 阶段,建议 %s。" % (r["stage"]["name"], parts[2])
    if r["triage"]["level"] != "无明确症状":
        head += "症状分级:%s。" % r["triage"]["level"]
    if r["trend"] and r["trend"]["alert"]:
        head += r["trend"]["alert"] + "。"
    return head or "信息不足:至少给物种、体重、月龄中的两项。"


def _model_advice(r, config):
    plan = r["plan"] or {}
    raw = llm.chat([{
        "role": "system",
        "content": ("你是宠物照护助手,不是兽医。只根据给定的喂食量、疫苗日历、体重趋势与症状分级说话;"
                    "不要写克数与千卡数字;不做诊断、不推荐处方药;红旗症状一律建议立即就医。"),
    }, {
        "role": "user",
        "content": ("物种:%s 体重:%s 月龄:%s 阶段:%s 每日克数:%s\n症状分级:%s(%s)\n体重趋势:%s\n"
                    "%s\n输出格式:{\"summary\":\"三句话内的照护要点\",\"care_tips\":[\"喂养/环境/日常 3-5 条\"],"
                    "\"risks\":[\"必须就医或必须避免的事项\"]}"
                    % (r["species"]["name"] if r["species"] else "未知", r["weight"], r["months"],
                       r["stage"]["name"], plan.get("grams"), r["triage"]["level"], r["triage"]["why"],
                       r["trend"]["alert"] if r["trend"] else "无", JSON_ONLY)),
    }], config=_cfg(config), temperature=0.3, max_tokens=1800)
    d = llm.extract_json(raw)
    return {"summary": strip_units(str(d.get("summary") or "")),
            "care_tips": [strip_units(str(x)) for x in d.get("care_tips", [])][:6],
            "risks": [strip_units(str(x)) for x in d.get("risks", [])][:6]}


def care(text, config=None, db=None, force_mock=False, save=False):
    r = rules.analyze(text)
    r["text"] = text
    if _use_model(config, force_mock):
        layers = _model_advice(r, config)
        mode = "model"
    else:
        layers = mock.offline(r)
        mode = "offline"
    r.update({"verdict": verdict(r), "mode": mode, "saved_id": None, **layers})
    if db is not None and save:
        r["saved_id"] = db.save(r)
    return r
