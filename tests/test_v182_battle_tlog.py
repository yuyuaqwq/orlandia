#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v182 战斗流水落地验收：采集 / 可拔插 / 不干扰 / **能回放复现同一场**。

跑法：python tests/test_v182_battle_tlog.py（exit=0 全绿）

硬验收（对应 `docs/REFACTOR_tlog_landing.md` §七）：
  ① 打完一场 → 有 start/act…/end，且 act 条数 == p_acts
  ② **replay(records) 的 result/rounds/p_acts == battle.end 记录**（复现同一场）
  ③ 开采集 / 不开采集：同 seed 下 result + rounds 一致（**采集不改变行为**）
  ④ 不启用时零行为（不链观察者、不包 human_act、不写一个字段）
"""
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PD = os.path.dirname(_HERE)
for _p in (_HERE, _PD):
    sys.path.insert(0, _p)

from _engine_harness import C  # noqa: E402,F401

import numeric_sim as NS  # noqa: E402
from saintess_engine import Battle as B2  # noqa: E402
from saintess_engine.tlog import JSONLSink, MemorySink, TLog  # noqa: E402
from _engine_harness import human_land  # noqa: E402  T15 两段化：落地推进
from content import tlog_collect as BT  # noqa: E402
from content.tlog_replay import replay  # noqa: E402
from content.bridge import (apply_battle_loadout, build_sides,  # noqa: E402
                            prepare_player_for_battle)

SEED = 1234
passed = failed = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


def build_battle(*, seed=SEED, tlog=None, pre_observer=None, cls="战士", mlv=11):
    """按生产口径建一场战斗；`tlog` 给定时挂采集（seed = 重演起点，构造之后取）。"""
    random.seed(999)                                  # 构造期随机（与重演无关）
    player = NS.build_player(cls, 11, NS.STD_ATTR[cls], {}, [])
    m = NS.monster_of("dps", mlv)
    prepare_player_for_battle(player, None, None)
    sides = build_sides(player, [dict(m)])
    for a in sides.get("player", []):
        apply_battle_loadout(a, None)
    b = B2("monster", sides=sides)
    if pre_observer is not None:
        b.on_event = pre_observer
    bt = BT.BattleTLog(tlog)
    random.seed(seed)                                 # ★ 重演起点
    bt.attach(b, btype="monster", seed=seed, player=player, enemies=[dict(m)])
    return b, bt


def run_battle(b, max_turns=300):
    """打到结束；返回 (result, 玩家出手次数)。"""
    n = 0
    while b.result is None and n < max_turns:
        human_land(b, "attack", None, b.focus())
        n += 1
    return b.result, n


# ---------------------------------------------------------------- 1 默认关
def t1_default_off():
    print("\n[1] 默认关：零行为")
    from _engine_harness import tlog_setup
    os.environ.pop(tlog_setup.ENV_FLAG, None)
    tlog_setup.disable()
    check("未启用时 tlog() 返回 None", tlog_setup.tlog() is None)
    check("enabled() 为假", tlog_setup.enabled() is False)

    b, bt = build_battle(tlog=None)
    check("tlog=None 的采集器 enabled=False", bt.enabled is False)
    check("零行为：不链观察者（on_event 仍为 None）", b.on_event is None)
    check("零行为：不包 human_act",
          not getattr(b.human_act, "_battle_tlog_wrapped", False))
    run_battle(b)
    check("零行为：整场打完也没写任何记录", bt.acts == 0 and bt.events == 0)


# ---------------------------------------------------------------- 2 采集
def t2_collect():
    print("\n[2] 采集：一场战斗的流水")
    mem = MemorySink()
    b, bt = build_battle(tlog=TLog(sinks=[mem]))
    _, n_player = run_battle(b)
    # ⚠️ 先**不**手动补发：这一节要验的是「自动收尾自己发得出 battle.end」
    # （2026-09-13 之前这条路一条都发不出来，测试里全用 force=True 补发 → 一直没被发现）
    recs = list(mem.read_records())
    kinds = [r.kind for r in recs]
    check("有 battle.start", kinds[0] == "battle.start", str(kinds[:3]))
    check("有 battle.end", kinds[-1] == "battle.end")
    n_act = kinds.count("battle.act")
    check("act 条数 == 玩家出手次数（行动没漏记）", n_act == n_player,
          f"act={n_act} player={n_player}")
    # ⚠️ 引擎 `_p_acts` 是「全量行动数」（act() 是统一入口，怪物也 +1）——不是玩家出手数
    check("引擎 p_acts（全量，含怪物行动）≥ 玩家出手数", int(b._p_acts) >= n_act,
          f"p_acts={b._p_acts} act={n_act}")
    check("有战斗事件（hit/taken 至少其一）",
          any(k in kinds for k in ("battle.hit", "battle.taken")), str(sorted(set(kinds))))
    start = recs[0]
    check("start 带重建输入（player + enemies）",
          start.fields.get("player") and start.fields.get("enemies"))
    check("start 带 seed 且 reproducible", start.fields.get("seed") == SEED
          and start.fields.get("reproducible") is True)
    ends = [r for r in recs if r.kind == "battle.end"]
    check("★ 自动收尾（不手动补发）就发出 battle.end，且只发一条", len(ends) == 1, f"n={len(ends)}")
    end = ends[-1]
    check("end 带 result/rounds/p_acts/acts_recorded/events_recorded（回放判据齐全）",
          end.fields.get("result") and "rounds" in end.fields and "p_acts" in end.fields
          and "acts_recorded" in end.fields and "events_recorded" in end.fields, str(end.fields))
    check("自动收尾记的就是这场的结果（与战斗对象一致）",
          str(end.fields.get("result")) == str(getattr(b, "result", "")), str(end.fields.get("result")))
    # `force=True` = **显式补发**（要带自定义 extra 的场景）：允许追加一条，且 extra 只进这一条
    bt.on_end(b, extra={"gold": 12}, force=True)
    ends2 = [r for r in mem.read_records() if r.kind == "battle.end"]
    check("force=True 显式补发：追加一条（自动那条不受影响）", len(ends2) == 2, f"n={len(ends2)}")
    check("补发那条带自定义 extra（gold）", ends2[-1].fields.get("gold") == 12, str(ends2[-1].fields))
    bt.on_end(b)                                     # 非 force：应被幂等挡掉
    check("非 force 的重复 on_end 被幂等挡掉",
          len([r for r in mem.read_records() if r.kind == "battle.end"]) == 2)
    hit = next((r for r in recs if r.kind in ("battle.hit", "battle.taken")), None)
    check("事件记录带 caster/subject", hit is not None and "subject" in hit.fields,
          str(hit.fields if hit else None))


# ---------------------------------------------------------------- 3 ★ 回放复现
def t3_replay():
    print("\n[3] ★ 回放复现同一场（硬验收）")
    mem = MemorySink()
    b, bt = build_battle(tlog=TLog(sinks=[mem]))
    _, _n = run_battle(b)
    bt.on_end(b)
    recs = list(mem.read_records())
    res = replay(recs)
    check("回放能跑完并给出结果", res["result"] != "")
    check("★ matched（result/rounds/p_acts 与记录逐项一致）", res["matched"],
          f"got={(res['result'], res['rounds'], res['p_acts'])} exp={res['expected']}")
    # 缺 start / 缺重建输入 → 明确报错，不静默
    try:
        replay([r for r in recs if r.kind == "battle.act"])
        ok = False
    except ValueError:
        ok = True
    check("缺 battle.start 时明确报错", ok)

    # 逆改一次行动 → 结果应不同（证明 matched 不是"恒真"）
    acts = [r for r in recs if r.kind == "battle.act"]
    if len(acts) > 2:
        mutated = [r for r in recs if r.kind != "battle.act"]
        mutated += [r for r in acts[:-1]]
        try:
            res2 = replay(mutated)
            check("抽掉最后一次行动 → 结果与记录不符（判据有效）",
                  not res2["matched"], str(res2))
        except Exception as e:                                # noqa: BLE001
            check("抽掉最后一次行动 → 结果与记录不符（判据有效）", False, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- 4 不干扰
def t4_no_side_effect():
    print("\n[4] 采集不改变行为（同 seed 同结果）")
    b1, _ = build_battle(seed=77, tlog=None)
    r1, _ = run_battle(b1)
    b2, _ = build_battle(seed=77, tlog=TLog(sinks=[MemorySink()]))
    r2, _ = run_battle(b2)
    check("result 一致", r1 == r2, f"{r1} vs {r2}")
    check("rounds 一致", int(b1._now) == int(b2._now), f"{b1._now} vs {b2._now}")
    check("p_acts 一致", int(b1._p_acts) == int(b2._p_acts))


# ---------------------------------------------------------------- 5 观察者串联
def t5_observer_chain():
    print("\n[5] 与既有观察者串联（不覆盖）")
    seen = []

    def pre(battle, evt_name, ctx, logs):
        seen.append(evt_name)

    mem = MemorySink()
    b, bt = build_battle(seed=5, tlog=TLog(sinks=[mem]), pre_observer=pre)
    _, _ = run_battle(b)
    check("既有观察者仍被调用（未被覆盖）", len(seen) > 0, f"n={len(seen)}")
    check("采集也照常记账", bt.events > 0)


# ---------------------------------------------------------------- 6 JSONL 落盘
def t6_jsonl():
    print("\n[6] 落盘出口（JSONLSink）")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "tlog.jsonl")
        tl = TLog(sinks=[JSONLSink(p)])
        b, bt = build_battle(seed=9, tlog=tl)
        _, _ = run_battle(b)
        bt.on_end(b)
        tl.close()
        raw = open(p, encoding="utf-8").read().strip().split("\n")
        check("一条一行落盘", len(raw) == bt.acts + 2 + bt.events,
              f"lines={len(raw)} acts={bt.acts} events={bt.events}")
        back = list(JSONLSink(p).read_records())
        check("读回一致", len(back) == len(raw))
        res = replay(back)
        check("★ 从落盘流水回放同样能复现", res["matched"], str(res["expected"]))


# ---------------------------------------------------------------- 7 声明表
def t7_kinds():
    print("\n[7] 声明表（content/data/tlogs.json）")
    from _engine_harness import tlog_setup
    kt = tlog_setup.kinds()
    check("声明表可装载", kt is not None and len(kt) > 8, f"n={len(kt) if kt else 0}")
    check("声明表自身无问题", kt.validate() == [], str(kt.validate()))
    check("含战斗与行为两类 kind",
          kt.has("battle.start") and kt.has("shop.buy"))
    check("battle.end 字段含复现判据",
          set(("result", "rounds", "p_acts")) <= set(kt.fields_of("battle.end")))


def main():
    print("== v182 战斗流水：采集 / 可拔插 / 回放复现 / 不干扰 ==")
    t1_default_off()
    t2_collect()
    t3_replay()
    t4_no_side_effect()
    t5_observer_chain()
    t6_jsonl()
    t7_kinds()
    print(f"\n===== 结果：通过 {passed} / {passed + failed} =====")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
