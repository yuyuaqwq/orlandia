# -*- coding: utf-8 -*-
"""N5b4-4 验证：PVP 命令层 saintess_engine 切换（双人真人轮流闭环）。

覆盖：
- _pvp_start 发起 → db 双方 battle 行 = saintess_engine state（type=pvp / sides / meta{attacker_qq, actor}）
- _pvp_act 轮流行动（攻击者=player side、防守方=enemy side 显式定位）+ 胜负按 actor 存活
- 终局：胜者 hp 写回 db、双方 battle 清空（unlock+clear）、轮到翻转
- defend：自己的 defending 持久化；非 defend 行动后双方 defending 消耗清 False
- skill（挥砍）走 saintess_engine 施放
- 超时清理（旧 updated_at）与旧档（无 sides）清档重开

跑法：python tests/test_battle_n5b4_pvp.py
"""
import os
import sys
import tempfile
import asyncio

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from content.persistence.handles import init_db  # noqa: E402
init_db()

from _engine_harness import db  # noqa: E402
from _engine_harness import Main  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


class FakeEvent:
    """模拟 AstrBot 消息事件（plain_result 返回文本）。"""

    def __init__(self, group_id, qq_id):
        self._g = group_id
        self._q = qq_id
        self.message_str = ""
        self._stopped = False

    def get_group_id(self):
        return self._g

    def get_sender_id(self):
        return self._q

    def get_message_str(self):
        return self.message_str

    def plain_result(self, text):
        return text

    def stop_event(self):
        self._stopped = True


async def collect(agen):
    """跑 async generator，收集全部 yield 结果（plain_result 文本）。"""
    out = []
    try:
        while True:
            out.append(await agen.__anext__())
    except StopAsyncIteration:
        pass
    return out


GID = "g_pvp"


def mk_db_player(qid, name, level=15, cls="战士", learned=None, hp=None):
    """真实 DB 玩家行（PVP 需要 db.get_player 双人）。

    attributes 给非全 0 值（create_player 默认全 0 会让 player_final_stats 走
    无默认加点路径，与 None 的默认加点面板不一致）——max_hp 用同一 attributes
    口径重算后写库，保证 _pvp_start 防守方实时化结果与库值一致。
    """
    import json
    attrs = {"str": 5, "agi": 5, "int": 5, "vit": 5}
    db.create_player(GID, qid, name, cls, {}, 100, 100)
    db.update_player(GID, qid, level=level, cur_map="pvp_field", cur_subarea="",
                     learned_skills=learned or [], stamina=999,
                     attributes=json.dumps(attrs))
    pl = db.get_player(GID, qid)
    max_hp = max_hp_of(cls, level, pl.get("attributes"), pl.get("race"))
    cur = hp if hp is not None else max_hp
    db.update_player(GID, qid, max_hp=max_hp, max_mp=50, hp=cur, mp=50)
    return db.get_player(GID, qid)


def max_hp_of(cls, level, attributes=None, race=None):
    """职业实时面板 max_hp（重算口径，对齐 _pvp_start 防守方实时化：race 需与
    create_player 默认 human 一致，否则差种族加成）。"""
    from content.panel import player_final_stats
    st = player_final_stats(cls, level, {}, 0, attributes, 0, {}, race)
    return int(st.get("max_hp", 100) or 100)


async def pvp_start(cmds, att_qq, def_qq, att_player):
    ev = FakeEvent(GID, att_qq)
    msgs = []
    async for r in cmds._pvp_start(ev, GID, att_qq, att_player, str(def_qq)):
        msgs.append(r)
    return msgs


def pvp_state_of(qid):
    row = db.get_battle(GID, qid)
    return row["state"] if row else None


async def test_pvp_start_state():
    print("【N5b4-4 发起 → saintess_engine state 结构】")
    cmds = Main(None)
    att_qq, def_qq = "1002001", "1002002"
    att_player = mk_db_player(att_qq, "攻击者", level=15)
    def_player = mk_db_player(def_qq, "防守者", level=12)
    msgs = await pvp_start(cmds, att_qq, def_qq, att_player)
    joined = "\n".join(msgs)
    check("发起成功文案", "发起攻击" in joined and "你先手" in joined, joined[:120])

    st = pvp_state_of(att_qq)
    check("攻击方 battle 行存在 saintess_engine state", st is not None and st.get("type") == "pvp",
          f"type={st and st.get('type')}")
    st2 = pvp_state_of(def_qq)
    check("防守方 battle 行同 state", st2 is not None and st2 == st)

    meta = (st or {}).get("meta") or {}
    check("meta attacker_qq/actor", meta.get("attacker_qq") == att_qq and meta.get("actor") == "attacker",
          f"meta={meta}")
    sides = (st or {}).get("sides") or {}
    p_acts, e_acts = sides.get("player") or [], sides.get("enemy") or []
    check("player side = 攻击者", len(p_acts) == 1 and str(p_acts[0].get("qq_id")) == att_qq,
          f"player={[a.get('qq_id') for a in p_acts]}")
    check("enemy side = 防守方(human_controlled)", len(e_acts) == 1
          and str(e_acts[0].get("qq_id")) == def_qq
          and e_acts[0].get("human_controlled") is True
          and e_acts[0].get("side") == "enemy",
          f"enemy qq={[a.get('qq_id') for a in e_acts]} hc={[a.get('human_controlled') for a in e_acts]}")
    check("攻击方 actor 满血进战斗", int(p_acts[0].get("hp", 0)) > 0
          and int(p_acts[0].get("max_hp", 0)) > 0)
    check("防守方 max_hp 已实时化", int(e_acts[0].get("max_hp", 0)) == def_player.get("max_hp"),
          f"actor={e_acts[0].get('max_hp')} db={def_player.get('max_hp')}")
    # 鱼鱼拍板方案 A：双方 actor 各自携带 bonus 容器（v181.M-bonus 统一数值容器；
    # per-actor 外部增幅 = bonus.panel；测试玩家无增幅 → 空 panel dict）
    check("双方 actor 带 bonus 容器（panel 空 dict）",
          isinstance(p_acts[0].get("bonus"), dict)
          and isinstance((p_acts[0].get("bonus") or {}).get("panel"), dict)
          and isinstance(e_acts[0].get("bonus"), dict)
          and isinstance((e_acts[0].get("bonus") or {}).get("panel"), dict),
          f"p={p_acts[0].get('bonus')} e={e_acts[0].get('bonus')}")
    check("双方锁战斗", cmds._in_battle(GID, att_qq) and cmds._in_battle(GID, def_qq))
    # 灰名标记
    check("攻击者灰名 10 分钟", int(db.get_event_state(f"grey_{att_qq}") or 0) > 0)
    # 清理
    cmds._unlock_battle(GID, att_qq)
    db.clear_battle(GID, att_qq)
    cmds._unlock_battle(GID, def_qq)
    db.clear_battle(GID, def_qq)


async def run_pvp_duel(cmds, att_qq, def_qq, att_learned=None, def_learned=None):
    """发起 PVP 并轮流驱动到终局。返回 (att_msgs, def_msgs, winner_qq, loser_qq)。

    驱动规则：每轮读 meta.actor 找该行动的人（attacker=att_qq / defender=def_qq），
    由该玩家执行 _pvp_act(attack)。战斗结束（双方 battle 行被清）即停。
    """
    att_player = mk_db_player(att_qq, "攻击者", level=15, learned=att_learned)
    def_player = mk_db_player(def_qq, "防守者", level=12, learned=def_learned)
    await pvp_start(cmds, att_qq, def_qq, att_player)
    atk_msgs, def_msgs = [], []
    guard = 0
    winner_qq, loser_qq = None, None
    while guard < 60:
        guard += 1
        row_att = db.get_battle(GID, att_qq)
        row_def = db.get_battle(GID, def_qq)
        if row_att is None and row_def is None:
            break  # 终局（双方已清）
        # 用仍在的战斗行判断轮到谁
        row = row_att or row_def
        st = row["state"]
        meta = st.get("meta") or {}
        cur_key = meta.get("actor", "attacker")
        cur_qq = att_qq if cur_key == "attacker" else def_qq
        if db.get_battle(GID, cur_qq) is None:
            # 轮到的人行已清（对方进程结算过）→ 以残留行再跑一次当前行动者
            cur_qq = def_qq if cur_qq == att_qq else att_qq
        player = db.get_player(GID, cur_qq)
        ev = FakeEvent(GID, cur_qq)
        st_now = pvp_state_of(cur_qq)
        if st_now is None:
            break
        msgs = await collect(cmds._pvp_act(ev, GID, cur_qq, player, st_now, "attack", None))
        joined = "\n".join(msgs)
        if cur_qq == att_qq:
            atk_msgs.append(joined)
        else:
            def_msgs.append(joined)
        # 终局判定：某方 battle 记录消失 + 有"被击败"结算文案 → 对方胜
        if "被击败了" in joined:
            winner_qq = cur_qq
            loser_qq = def_qq if cur_qq == att_qq else att_qq
    return atk_msgs, def_msgs, winner_qq, loser_qq


async def test_pvp_duel_to_finish():
    print("【N5b4-4 轮流攻击 → 终局结算】")
    cmds = Main(None)
    att_qq, def_qq = "2003001", "2003002"
    atk_msgs, def_msgs, winner_qq, loser_qq = await run_pvp_duel(cmds, att_qq, def_qq)
    check("有行动日志", any("攻击" in m for m in atk_msgs + def_msgs) or len(atk_msgs + def_msgs) > 0,
          f"atk={len(atk_msgs)} def={len(def_msgs)}")
    check("分出胜负", winner_qq is not None, f"winner={winner_qq}")
    check("终局双方 battle 清空", db.get_battle(GID, att_qq) is None and db.get_battle(GID, def_qq) is None)
    check("双方锁解除", not cmds._in_battle(GID, att_qq) and not cmds._in_battle(GID, def_qq))
    # 胜者 hp 写回 db（胜者可能受伤）；败者 db 由 _pvp_finish 回城 HP=1
    loser = db.get_player(GID, loser_qq)
    check("败者回城 HP=1", int(loser.get("hp", 0)) == 1, f"hp={loser.get('hp')}")
    winner = db.get_player(GID, winner_qq)
    check("胜者受伤状态写回", int(winner.get("hp", 0)) >= 1
          and int(winner.get("hp", 0)) <= int(winner.get("max_hp", 0)),
          f"hp={winner.get('hp')}/{winner.get('max_hp')}")


async def test_pvp_round_switch_and_defend():
    print("【N5b4-4 轮到翻转 + 防御持久化/消耗】")
    cmds = Main(None)
    att_qq, def_qq = "3004001", "3004002"
    att_player = mk_db_player(att_qq, "攻击者", level=15)
    def_player = mk_db_player(def_qq, "防守者", level=12)
    await pvp_start(cmds, att_qq, def_qq, att_player)

    # ① 攻击者普攻（不打死的量级——等级差 3 伤害不足以秒杀）
    pl_att = db.get_player(GID, att_qq)
    msgs = await collect(cmds._pvp_act(FakeEvent(GID, att_qq), GID, att_qq, pl_att,
                                       pvp_state_of(att_qq), "attack", None))
    st = pvp_state_of(att_qq)
    meta = (st or {}).get("meta") or {}
    check("攻击后轮到 defender", meta.get("actor") == "defender", f"meta={meta}")
    e_actor = ((st or {}).get("sides") or {}).get("enemy", [{}])[0]
    check("防守方仍存活", int(e_actor.get("hp", 0)) > 0, f"hp={e_actor.get('hp')}")

    # ② 防守方防御 → 自己 defending True 且持久化
    pl_def = db.get_player(GID, def_qq)
    msgs = await collect(cmds._pvp_act(FakeEvent(GID, def_qq), GID, def_qq, pl_def,
                                       pvp_state_of(def_qq), "defend", None))
    st = pvp_state_of(def_qq)
    meta = (st or {}).get("meta") or {}
    e_actor = ((st or {}).get("sides") or {}).get("enemy", [{}])[0]
    check("defend 后 meta 轮到 attacker", meta.get("actor") == "attacker", f"meta={meta}")
    check("防守方 defending=True 持久化", e_actor.get("defending") is True,
          f"defending={e_actor.get('defending')}")
    # ③ 攻击者行动（攻击）→ 非 defend 行动消耗双方 defending（防守方减半结算后清 False）
    pl_att2 = db.get_player(GID, att_qq)
    msgs = await collect(cmds._pvp_act(FakeEvent(GID, att_qq), GID, att_qq, pl_att2,
                                       pvp_state_of(att_qq), "attack", None))
    st = pvp_state_of(att_qq)
    e_actor = ((st or {}).get("sides") or {}).get("enemy", [{}])[0]
    p_actor = ((st or {}).get("sides") or {}).get("player", [{}])[0]
    check("攻击后防守方 defending 被消耗清 False", e_actor.get("defending") is False,
          f"defending={e_actor.get('defending')}")
    check("攻击者自身 defending 也清 False", p_actor.get("defending") is False)

    # 清理
    for q in (att_qq, def_qq):
        cmds._unlock_battle(GID, q)
        db.clear_battle(GID, q)


async def test_pvp_skill_and_turn_guard():
    print("【N5b4-4 skill 施放 + 非行动方拦截】")
    cmds = Main(None)
    att_qq, def_qq = "4005001", "4005002"
    att_player = mk_db_player(att_qq, "攻击者", level=15, learned=["挥砍"])
    def_player = mk_db_player(def_qq, "防守者", level=12)
    await pvp_start(cmds, att_qq, def_qq, att_player)

    # 非行动方（防守方）先动 → 拦截
    pl_def = db.get_player(GID, def_qq)
    msgs = await collect(cmds._pvp_act(FakeEvent(GID, def_qq), GID, def_qq, pl_def,
                                       pvp_state_of(def_qq), "attack", None))
    check("非行动方被拦截", any("还没轮到你" in m for m in msgs), f"{msgs}")

    # 未学会技能 → 拦截（轮次未消耗，仍轮到攻击者）
    pl_att0 = db.get_player(GID, att_qq)
    msgs = await collect(cmds._pvp_act(FakeEvent(GID, att_qq), GID, att_qq, pl_att0,
                                       pvp_state_of(att_qq), "skill", "旋风斩"))
    check("未学会技能被拦截", any("需要" in m or "还没学会" in m for m in msgs), f"{msgs}")

    # 攻击者用技能『挥砍』（learned 已含）
    pl_att = db.get_player(GID, att_qq)
    msgs = await collect(cmds._pvp_act(FakeEvent(GID, att_qq), GID, att_qq, pl_att,
                                       pvp_state_of(att_qq), "skill", "挥砍"))
    st = pvp_state_of(att_qq)
    e_actor = ((st or {}).get("sides") or {}).get("enemy", [{}])[0]
    joined = "\n".join(msgs)
    check("挥砍造成伤害", int(e_actor.get("hp", 0)) < int(e_actor.get("max_hp", 1)),
          f"hp={e_actor.get('hp')} msg={joined[:100]}")

    for q in (att_qq, def_qq):
        cmds._unlock_battle(GID, q)
        db.clear_battle(GID, q)


async def test_pvp_stat_bonus_per_actor():
    print("【N5b4-4 per-actor 面板增幅 bonus.panel（v181.M-bonus 统一容器）】")
    from saintess_engine import make_actor, Battle as B2
    from saintess_engine.battle.stats import actor_stats
    _base = dict(class_name="战士", level=15, equipment={}, skills=[], learned_skills=[])

    def _mk(uid, side):
        return make_actor(uid=uid, name=uid, side=side, kind="player",
                          human_controlled=True, **_base)

    # 基础对照（battle.title_bonus 空、actor 无 bonus 容器）
    a0 = _mk("t0", "player")
    e0 = _mk("t0e", "enemy")
    b0 = B2("pvp", sides={"player": [a0], "enemy": [e0]}, title_bonus={})
    s0 = actor_stats(b0, a0)

    # A 带 panel atk+20、E 带 panel spd+30 → 面板各自精确、互不污染
    a = _mk("t1", "player")
    e = _mk("t1e", "enemy")
    a["bonus"] = {"panel": {"atk": 20}, "cap": {}, "cost": {}}
    e["bonus"] = {"panel": {"spd": 30}, "cap": {}, "cost": {}}
    b = B2("pvp", sides={"player": [a], "enemy": [e]}, title_bonus={})
    sa, se = actor_stats(b, a), actor_stats(b, e)
    check("A 面板 atk = 基础 + 20", int(sa.get("atk", 0)) == int(s0.get("atk", 0)) + 20,
          f"A={sa.get('atk')} 基础={s0.get('atk')}")
    check("E 面板 spd = 基础 + 30", int(se.get("spd", 0)) == int(s0.get("spd", 0)) + 30,
          f"E={se.get('spd')} 基础={s0.get('spd')}")
    check("E 面板 atk 不被 A 加成污染", int(se.get("atk", 0)) == int(s0.get("atk", 0)),
          f"E atk={se.get('atk')} 基础={s0.get('atk')}")
    check("A 面板 spd 不被 E 加成污染", int(sa.get("spd", 0)) == int(s0.get("spd", 0)),
          f"A spd={sa.get('spd')} 基础={s0.get('spd')}")

    # actor 无 tb → 回落 battle.title_bonus（野外语义保持）
    a2 = _mk("t2", "player")
    e2 = _mk("t2e", "enemy")
    b2 = B2("pvp", sides={"player": [a2], "enemy": [e2]}, title_bonus={"atk": 5})
    s2 = actor_stats(b2, a2)
    check("无 actor tb → 回落 battle.title_bonus", int(s2.get("atk", 0)) == int(s0.get("atk", 0)) + 5,
          f"battle 级={s2.get('atk')} 基础={s0.get('atk')}")

    # 序列化保留（PVP 续战恢复后 actor 仍带自己增幅 bonus.panel）
    st = b.to_state()
    b3 = B2.from_state(st)
    a3 = b3.sides_of("player")[0]
    e3 = b3.sides_of("enemy")[0]
    check("恢复后 A 的 bonus.panel 保留", ((a3.get("bonus") or {}).get("panel") or {}).get("atk") == 20,
          f"{a3.get('bonus')}")
    check("恢复后 E 的 bonus.panel 保留", ((e3.get("bonus") or {}).get("panel") or {}).get("spd") == 30,
          f"{e3.get('bonus')}")


async def test_pvp_timeout_and_legacy():
    print("【N5b4-4 超时解除 + 旧档清档】")
    cmds = Main(None)
    att_qq, def_qq = "5006001", "5006002"
    att_player = mk_db_player(att_qq, "攻击者", level=15)
    def_player = mk_db_player(def_qq, "防守者", level=12)
    await pvp_start(cmds, att_qq, def_qq, att_player)

    # 超时：伪造旧 updated_at
    import time as _t
    _conn = db  # 直接更新 battle_state 行 updated_at
    from content.persistence import battle_state as _bs
    with _bs._lock:
        conn = _bs._connect()
        try:
            conn.execute("UPDATE battle_state SET updated_at=? WHERE qq_id IN (?,?)",
                         (int(_t.time()) - 400, att_qq, def_qq))
            conn.commit()
        finally:
            conn.close()
    row_att = db.get_battle(GID, att_qq)
    timed = cmds._pvp_handle_timeout(row_att, GID, att_qq)
    check("超时判定 True", timed is True)
    check("超时后双方清档+解锁", db.get_battle(GID, att_qq) is None
          and db.get_battle(GID, def_qq) is None
          and not cmds._in_battle(GID, att_qq) and not cmds._in_battle(GID, def_qq))

    # 旧档（type=pvp 无 sides/meta）→ _pvp_act 清档重开
    db.save_battle(GID, att_qq, {"type": "pvp", "actor": "attacker",
                                 "attacker": {"qq_id": att_qq}, "defender": {"qq_id": def_qq}})
    cmds._lock_battle(GID, att_qq)
    pl_att = db.get_player(GID, att_qq)
    msgs = await collect(cmds._pvp_act(FakeEvent(GID, att_qq), GID, att_qq, pl_att,
                                       pvp_state_of(att_qq), "attack", None))
    check("旧档清档提示", any("旧存档已失效" in m for m in msgs), f"{msgs}")
    check("旧档已清", db.get_battle(GID, att_qq) is None and not cmds._in_battle(GID, att_qq))


async def main():
    # v181 flaky 修复：玩家真实面板含 ~3% 基础闪避（职业成长走 player_final_stats
    # 公式，actor["dodge"] 覆盖不了）——「挥砍造成伤害」断言偶发被防守方闪避打成假红。
    import random as _r
    _r.seed(20260910)
    await test_pvp_start_state()
    await test_pvp_duel_to_finish()
    await test_pvp_round_switch_and_defend()
    await test_pvp_skill_and_turn_guard()
    await test_pvp_stat_bonus_per_actor()
    await test_pvp_timeout_and_legacy()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        print("失败明细：")
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
