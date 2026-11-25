"""离线模式:照护要点、提醒与风险,结构与模型模式一致。"""

from __future__ import annotations


def offline(r):
    tips, risks = [], []
    plan = r["plan"]
    if plan:
        tips.append("每日总量 %d g,分 %d 顿,每顿 %d g;换粮用 7 天过渡。" % (plan["grams"], plan["meals"],
                                                                     plan["per_meal"]))
        tips.append("固定称重喂食,零食不超过每日热量的 10%。")
    else:
        tips.append("先给体重,喂食量才能算;没有体重只能给方法。")
    if r["stage"]["key"] in ("puppy", "junior"):
        tips.append("幼年阶段少量多餐,吃完 30 分钟内别剧烈运动。")
    if r["stage"]["key"] == "senior":
        tips.append("老年建议每半年一次体检,关注牙口、肾指标与体重。")
    if r["months"] is not None and r["months"] < 4:
        tips.append("未满 4 个月不要带去人多狗多的地方,疫苗未齐。")

    tri = r["triage"]
    if tri["level"] == "立即就医":
        risks.append("红旗症状:%s——现在就联系医院,别等明天。" % "、".join(tri["flags"]))
        risks.append("送医途中保持安静保温,不要自行喂药或催吐。")
    elif tri["level"] == "24 小时内":
        risks.append("症状需要 24 小时内面诊:先记录呕吐/排便次数与照片,禁食不禁水。")
    else:
        risks.append("观察期内出现精神差、拒食、尿量变化,立即升级就医。")

    if r["trend"] and r["trend"]["alert"]:
        risks.append(r["trend"]["alert"])
    risks.append("不要给人用药:对乙酰氨基酚、布洛芬对猫狗有毒。")
    if r["species"] and r["species"]["key"] == "cat":
        risks.append("猫超过 24 小时不吃东西有脂肪肝风险,必须就医。")

    return {"summary": ("%s,%s 阶段,重点看喂食量与症状分级。"
                        % (r["species"]["name"] if r["species"] else "宠物", r["stage"]["name"])),
            "care_tips": tips[:6], "risks": risks[:6]}
