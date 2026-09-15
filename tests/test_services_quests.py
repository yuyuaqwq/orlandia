# -*- coding: utf-8 -*-
"""v181 P4-1 试点：services/quests 每日任务域服务直测（不依赖 Main/FakeEvent——service 可独立测）。

覆盖：常量导出、daily_repeat_pct 衰减档、settle_daily_quest 结算（DB 入账 + lines 文案）、
bump_daily_progress 非击杀推进（达标发奖 + 移除）、daily_pool 等级过滤、draw_daily 发布
（seed 固定：抽取/衰减乘算/面板行 + 防刷上限守卫 + 已有任务守卫）。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, db, clean_db  # noqa: E402
from content import profession_quests as S  # noqa: E402

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def make_player(qq, lv=10, gold=10000, exp=0):
    db.create_player("g", qq, f"测试{qq}", "cls_warrior", {}, 100, 50, race="human", gender="男")
    db.update_player("g", qq, level=lv, gold=gold, exp=exp, hp=500, max_hp=500, mp=100, max_mp=200,
                     stamina=999999, cur_map="oak_town", cur_subarea="oak_town_4")
    return db.get_player("g", qq)


def main():
    clean_db()
    # ---- 常量 ----
    check("DAILY_LIMIT==10", S.DAILY_LIMIT == 10)
    check("DAILY_META_KEYS 元数据键", S.DAILY_META_KEYS == ("_date", "_completed", "_repeat"))
    check("DAILY_REPEAT_FACTORS 四档", S.DAILY_REPEAT_FACTORS == (1.0, 0.6, 0.3, 0.1))

    # ---- daily_repeat_pct 衰减档（面板/文案百分比） ----
    check("首刷 100%", S.daily_repeat_pct(0) == 100)
    check("第 2 次 60%", S.daily_repeat_pct(1) == 60)
    check("第 3 次 30%", S.daily_repeat_pct(2) == 30)
    check("第 4 次起 10%（含 ≥3）", S.daily_repeat_pct(3) == 10 and S.daily_repeat_pct(9) == 10)

    # ---- settle_daily_quest：结算入账 + 文案 ----
    qq = "sv1"
    make_player(qq, lv=10)
    p0 = db.get_player("g", qq)
    dq = dict(C.DAILY_QUESTS[0])
    daily = {}
    lines = []
    S.settle_daily_quest("g", qq, daily, dq, lines)
    p1 = db.get_player("g", qq)
    check("_completed +1", daily.get("_completed") == 1)
    check("_repeat 按任务名 +1", daily.get("_repeat", {}).get(dq["name"]) == 1)
    check("金币入账", p1["gold"] == p0["gold"] + dq["reward_gold"], f"{p0['gold']}->{p1['gold']}")
    check("经验入账", p1["exp"] == p0["exp"] + dq["reward_exp"])
    check("完成文案行", any("完成" in l for l in lines), str(lines))
    # 二次结算：dq 本身 repeat=0（无衰减标记）→ 正常文案；重复衰减文案走 dq 带 repeat 档（手工塞）
    dq_rep = dict(dq)
    dq_rep["repeat"] = 1  # 今日已重复完成 1 次 → 衰减档 60%
    lines2 = []
    S.settle_daily_quest("g", qq, daily, dq_rep, lines2)
    check("二次结算重复衰减文案", any("衰减 60%" in l for l in lines2), str(lines2))
    check("lines=None 不输出", S.settle_daily_quest("g", qq, daily, dq_rep, None) is None)

    # ---- bump_daily_progress：collect_any 推进达标发奖 + 移除 ----
    qq2 = "sv2"
    make_player(qq2)
    # 手工塞一个 collect_any:1 的任务（进度 0 → bump 一次即达标）
    q = db.get_quests("g", qq2)
    q["daily"] = {"_date": "2026-09-07", "_completed": 0, "_repeat": {},
                  "d1": {"name": "采集任务", "desc": "采集 1 份材料", "objective": {"collect_any": 1},
                         "reward_exp": 50, "reward_gold": 30, "repeat": 0, "progress": 0}}
    db.save_quests("g", qq2, q)
    g0 = db.get_player("g", qq2)["gold"]
    out = S.bump_daily_progress("g", qq2, "collect_any", [])
    q2 = db.get_quests("g", qq2)
    check("达标任务被移除", "d1" not in (q2.get("daily") or {}), str(q2.get("daily")))
    check("发奖入账", db.get_player("g", qq2)["gold"] == g0 + 30)
    check("bump 无任务返回 None", S.bump_daily_progress("g", qq2, "collect_any", []) is None)

    # ---- daily_pool 等级过滤 ----
    def pl(lv):
        return {"level": lv}
    dq_any = {"objective": {"kill_any": 10}, "reward_exp": 100}
    check("kill_any 全等级可做", S.daily_pool(pl(1), dq_any))
    dq_elite = {"objective": {"kill_elite": 3}, "reward_exp": 200}
    check("kill_elite Lv.5 不可", not S.daily_pool(pl(5), dq_elite))
    check("kill_elite Lv.6 可", S.daily_pool(pl(6), dq_elite))
    dq_mlv = {"min_lv": 50, "objective": {"kill_any": 20}, "reward_exp": 800}
    check("min_lv 50 Lv.49 不可", not S.daily_pool(pl(49), dq_mlv))
    check("min_lv 50 Lv.50 可", S.daily_pool(pl(50), dq_mlv))

    # ---- draw_daily：发布（seed 固定）+ 守卫 ----
    qq3 = "sv3"
    make_player(qq3, lv=10)
    random.seed(42)
    ok, txt = S.draw_daily("g", qq3, db.get_player("g", qq3))
    q3 = db.get_quests("g", qq3)
    d3 = q3.get("daily") or {}
    check("发布成功 ok=True", ok)
    check("面板含发布头", "今日任务已发布" in txt)
    active = {k: v for k, v in d3.items() if k not in S.DAILY_META_KEYS}
    check("抽到 2 个任务", len(active) == 2, str(active))
    check("元数据 _date 写入", "_date" in d3 and "_completed" in d3)
    # 已有任务守卫
    ok2, txt2 = S.draw_daily("g", qq3, db.get_player("g", qq3))
    check("已有任务拒绝", not ok2 and "已经有每日任务了" in txt2, txt2)
    # 上限守卫（_completed=10 → 拒绝）
    import datetime as _dt9
    _today9 = _dt9.date.today().isoformat()
    qq4 = "sv4"
    make_player(qq4)
    q4 = db.get_quests("g", qq4)
    q4["daily"] = {"_date": _today9, "_completed": 10, "_repeat": {}}
    db.save_quests("g", qq4, q4)
    ok3, txt3 = S.draw_daily("g", qq4, db.get_player("g", qq4))
    check("上限守卫拒绝", not ok3 and "10/10" in txt3, txt3)
    # 完成过 2 个再抽 → 面板带"今日已完成 2/10" + _completed 保留（防刷衰减持续）
    qq5 = "sv5"
    make_player(qq5)
    q5 = db.get_quests("g", qq5)
    q5["daily"] = {"_date": _today9, "_completed": 2, "_repeat": {}}
    db.save_quests("g", qq5, q5)
    ok4, txt4 = S.draw_daily("g", qq5, db.get_player("g", qq5))
    check("完成 2 个后再抽成功", ok4 and "已完成 2/10" in txt4, txt4)
    check("_completed 保留不归零", (db.get_quests("g", qq5).get("daily") or {}).get("_completed") == 2)

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
