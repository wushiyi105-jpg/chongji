"""命令行入口:python -m chongji <命令>。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, agent, llm, rules
from . import db as dbmod
from .llm import LLMError

BANNER = ("⚠️  当前为离线模式(未配置 LLM_API_KEY):喂食量、免疫日历、体重趋势与症状分级由本地给出。\n"
          "   填入 LLM_API_KEY 后,照护解释与提醒由模型撰写(克数与卡路里仍以本地为准)。\n")


def render(r):
    mode = "模型" if r["mode"] == "model" else "离线模式"
    lines = ["🐾 宠物照护  [%s]" % mode, "", "📌 " + r["verdict"], ""]
    for n in r["notes"]:
        lines.append("注:" + n)
    if r["notes"]:
        lines.append("")

    lines.append("🔎 基本信息")
    lines.append("  物种:%s  体重:%s kg  月龄:%s  绝育:%s"
                 % (r["species"]["name"] if r["species"] else "未识别",
                    r["weight"] or "—", r["months"] if r["months"] is not None else "—",
                    "是" if r["neutered"] else "否/未写"))
    lines.append("  阶段:%s(系数 %.1f,每天 %d 顿)" % (r["stage"]["name"], r["stage"]["factor"],
                                                    r["stage"]["meals"]))
    lines.append("")

    if r["plan"]:
        p = r["plan"]
        lines.append("🍚 喂食量")
        lines.append("  RER %.1f kcal → DER %.1f kcal(%s)" % (p["rer"], p["der"], p["food"]))
        lines.append("  每日 %d g,分 %d 顿,每顿约 %d g" % (p["grams"], p["meals"], p["per_meal"]))
        lines.append("  公式:" + p["formula"])
        lines.append("")

    if r["trend"]:
        t = r["trend"]
        lines.append("⚖️  体重趋势")
        lines.append("  上次 %.2f kg → 现在 %.2f kg(%.1f%%)" % (t["previous"], t["current"], t["change_pct"]))
        if t["alert"]:
            lines.append("  ⚠️ " + t["alert"])
        lines.append("")

    tri = r["triage"]
    lines.append("🚦 症状分级:%s" % tri["level"])
    lines.append("  " + tri["why"])
    if tri["hits"]:
        lines.append("  命中:" + "、".join("%s(%s)" % (h["item"], h["level"]) for h in tri["hits"][:8]))
    lines.append("")

    lines.append("💉 免疫与驱虫日历")
    for v in r["vaccines"]:
        lines.append("  · %s:%s,下次 %s(%s)" % (v["name"], v["status"], v["next"] or "—", v["note"]))
    lines.append("")

    if r["summary"]:
        lines.append("🧭 照护要点")
        lines.append("  " + r["summary"])
        lines.append("")
    if r["care_tips"]:
        lines.append("💡 日常建议")
        for t in r["care_tips"]:
            lines.append("  · " + t)
        lines.append("")
    if r["risks"]:
        lines.append("🚩 必须注意")
        for t in r["risks"]:
            lines.append("  · " + t)
        lines.append("")
    lines.append("🏥 就诊带上")
    for c in r["checklist"]:
        lines.append("  %s %s —— %s" % ("✅" if c["ok"] else "❌", c["item"], c["how"]))
    return "\n".join(lines)


def _text(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def cmd_care(args):
    text = _text(args)
    if not text.strip():
        print("❌ 没有描述:用 --text、--file 或管道输入。", file=sys.stderr)
        sys.exit(2)
    db = dbmod.Database(args.db) if args.db else dbmod.Database()
    r = agent.care(text, config=llm.config_from_args(args), db=db, force_mock=args.mock, save=args.save)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(render(r))
    if r.get("saved_id"):
        print("\n已入库(#%d),`python -m chongji history` 可回看。" % r["saved_id"])


def cmd_foods(args):
    rows = rules.load("species.json")["foods"]
    print("🍚 食物热量密度(千卡/100g)")
    for f in rows:
        print("  · %s:%d" % (f["name"], f["kcal_per_100g"]))
    print("\n阶段系数:")
    for s in rules.load("species.json")["stages"]:
        print("  · %s:×%.1f,每天 %d 顿" % (s["name"], s["factor"], s["meals"]))


def cmd_symptoms(args):
    rows = rules.load("species.json")["symptoms"]
    print("🚦 症状三级分流")
    for s in rows:
        print("\n【%s】" % s["level"])
        print("  " + "、".join(s["items"]))
    print("\n红旗(直接就医):" + "、".join(rules.load("species.json")["red_flags"]))


def cmd_history(args):
    rows = dbmod.Database(args.db).latest(args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("还没有记录。`python -m chongji care --text \"猫 4kg 2岁\" --save` 存一条。")
        return
    print("🐾 照护记录")
    for r in rows:
        print("  #%d  %s  %s kg  %s  %s  每日 %s g  %s"
              % (r["id"], r["species"] or "—", r["weight"] or "—", r["stage"],
                 r["triage"], r["grams"] or "—", r["created_at"]))


def cmd_web(args):
    from . import web
    web.serve(host=args.host, port=args.port, db_path=args.db, force_mock=args.mock)


def build_parser():
    p = argparse.ArgumentParser(prog="chongji", description="宠记 · 宠物照护:喂食量、免疫、体重与症状分级。")
    p.add_argument("--version", action="version", version="chongji %s" % __version__)
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true", help="输出原始 JSON")
    p.add_argument("--model", help="覆盖 LLM_MODEL")
    p.add_argument("--base-url", help="覆盖 LLM_BASE_URL")
    p.add_argument("--api-key", help="覆盖 LLM_API_KEY")
    p.add_argument("--db", help="SQLite 路径")
    sub = p.add_subparsers(dest="command", required=True)

    cp = sub.add_parser("care", help="评估一只宠物")
    cp.add_argument("--text", help="描述:物种、体重、月龄、症状、上次体重")
    cp.add_argument("--file", help="从文件读")
    cp.add_argument("--save", action="store_true")
    cp.set_defaults(func=cmd_care)

    fp = sub.add_parser("foods", help="热量密度与阶段系数")
    fp.set_defaults(func=cmd_foods)

    sp = sub.add_parser("symptoms", help="症状三级分流")
    sp.set_defaults(func=cmd_symptoms)

    hp = sub.add_parser("history", help="历史记录")
    hp.add_argument("--limit", type=int, default=10)
    hp.set_defaults(func=cmd_history)

    wp = sub.add_parser("web", help="启动 Web 界面")
    wp.add_argument("--host", default="127.0.0.1")
    wp.add_argument("--port", type=int, default=8000)
    wp.add_argument("--mock", action="store_true", default=argparse.SUPPRESS)
    wp.set_defaults(func=cmd_web)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.mock and args.command == "care" and not llm.config_from_args(args).get("api_key"):
        print(BANNER, file=sys.stderr)
    try:
        args.func(args)
    except LLMError as e:
        print("❌ %s" % e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
