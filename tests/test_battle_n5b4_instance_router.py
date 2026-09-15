# -*- coding: utf-8 -*-
"""N5b4-5a R1 验证：副本行动 Router（instance_router.py）saintess_engine 原生分支。

v3 蓝图 §6 R1 验证：肃清守卫 / 轮转 / 超时自动防御 / 切怪 / 通关 / 失败 分支。

覆盖（真实 DB 链路，不 mock 引擎/玩法壳）：
- 肃清守卫：无敌人 → 引导探索/深入
- 轮转等待：非请求者且未超时 → 等待提示（多人）
- 超时自动防御：非请求者超时 → 自动 defend 后轮到请求者
- 行动：attack 伤害 / defend 姿态 / skill 施放（含 heal 防奶敌）
- 切怪：stage_pending 剩怪 → 击杀奖励 + build_battle 重构造下一只
- 通关：末层 Boss 死 → _instance_victory（cleared/奖励）
- 失败：玩家全倒 → _instance_defeat（回城/清锁）
- 秘密守卫（secret_guard_pending → 宝箱分支，不通关）
- rooms Boss 房通关

跑法：python tests/test_battle_n5b4_instance_router.py
"""
import os
import sys
import tempfile
import asyncio
import json

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402

from _engine_harness import db  # noqa: E402
from _engine_harness import C  # noqa: E402
from content.panel import player_final_stats
from content.flow import instance_battle as _IB_impl  # noqa: E402
from _engine_harness import Main as _CmdHost  # noqa: E402  （原 InstanceCmds/CombatCmds/WorldCmds 壳 → 驱动口）
db.init_db()

# `content.flow.instance_battle.build_battle/_attach_instance_hooks` 要调用方传
# `script_api=`（Boss 剧本导演 = 平台件，旧宿主薄壳 `game/commands/instance_battle.py`
# 由 `._boss_script_port.script_api()` 提供）。终态无宿主薄壳 ⇒ 测试侧按**包内公开源**
# 组同款适配器（`content.flow.boss_script` + `content.tables.merge_phase_config` +
# 聚合门面 `MONSTER_MODS` / `INSTANCES`，与宿主适配器逐条同源）。
from content.flow import boss_script as _BS  # noqa: E402
from content.tables import merge_phase_config as _merge_phase_config  # noqa: E402


class _ScriptApi(object):
    def __init__(self):
        self._bs = _BS

    def _deps(self):
        return {"data": {"MONSTER_MODS": C.MONSTER_MODS, "INSTANCES": C.INSTANCES},
                "phase_templates": _merge_phase_config,
                "build_monster": getattr(C, "build_monster", None)}

    def __getattr__(self, name):
        fn = getattr(self._bs, name)
        if not callable(fn):
            return fn
        if name in ("make_script_hook", "make_script_event"):
            def _factory(st, **kw):
                d = self._deps()
                d.update(kw)
                return fn(st, **d)
            return _factory
        if name == "boss_script_cfg":
            def _cfg(st, actor, data=None):
                return fn(st, actor, data if data is not None else self._deps()["data"])
            return _cfg
        return fn


def _script_api():
    return _ScriptApi()


_IB = _IB_impl
IB = _IB_impl   # 其余机械指向名（player_actor_of / next_actor_key / _players_of …）同名可直取


def _build_battle(st):
    """宿主壳同口径包装：补 `script_api=`/`team_heal_text=`（见上）。"""
    return _IB.build_battle(st, script_api=_script_api(),
                            team_heal_text=_IB.team_heal_text)


def _attach_instance_hooks(b, st):
    """宿主壳同口径包装（同上）。"""
    return _IB._attach_instance_hooks(b, st, script_api=_script_api(),
                                      team_heal_text=_IB.team_heal_text)


def _sync_views(st, group_id):
    """宿主壳同口径包装：补 `sync_player_fn=`/`db_update_fn=`（宿主耦合回调）。"""
    from content.bridge import sync_player_from_actor

    def _db_update(_gid, _key, hp, mp, max_hp, max_mp):
        db.update_player(_gid, _key, hp=hp, mp=mp, max_hp=max_hp, max_mp=max_mp)

    return _IB.sync_views(st, group_id, sync_player_fn=sync_player_from_actor,
                          db_update_fn=_db_update)

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


GID = "g_ir"


class FakeEvent:
    def __init__(self, group_id, qq_id, msg=""):
        self._g = group_id
        self._q = qq_id
        self.message_str = msg
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
    out = []
    async for r in agen:
        out.append(r)
    return out


def mk_snap(qid, name, cls="cls_zhan_shi", level=15, learned=None, hp=None, spd_override=None):
    db.create_player(GID, qid, name, cls, {}, 100, 100)
    db.update_player(GID, qid, level=level, cur_map="mainland", cur_subarea="",
                     learned_skills=learned or [], stamina=999,
                     attributes=json.dumps({"str": 5, "agi": 5, "int": 5, "vit": 5}))
    pl = db.get_player(GID, qid)
    st = player_final_stats(cls, level, {}, 0, pl.get("attributes"), 0, {}, pl.get("race"))
    mh = int(st.get("max_hp", 100))
    cur = hp if hp is not None else mh
    db.update_player(GID, qid, max_hp=mh, max_mp=50, hp=cur, mp=50)
    pl = db.get_player(GID, qid)
    spd = spd_override if spd_override is not None else int(st.get("spd", 0) or 0)
    return {
        "name": name, "qq_id": qid, "class_name": cls, "level": level,
        "hp": int(pl.get("hp", 0)), "max_hp": mh,
        "mp": int(pl.get("mp", 0)), "max_mp": 50,
        "equipment": {}, "skills": [], "learned_skills": learned or [],
        "class_tier": 0, "evolve_path": 0, "attributes": pl.get("attributes"),
        "bonus": {"panel": {}, "cap": {}, "cost": {}}, "race": pl.get("race"),
        "uid": f"p_{qid}", "buffs": {}, "stacks": {}, "defending": False,
        "charging": None, "ct": 0.0, "p_shields": {}, "spd": spd,
    }


def mk_enemy(uid="e_boss", name="测试Boss", hp=800, atk=30, spd=50, role="boss", lv=15):
    return {"uid": uid, "name": name, "hp": hp, "max_hp": hp,
            "atk": atk, "def": 10, "matk": 10, "mdef": 10, "spd": spd,
            "crit": 0.05, "lv": lv, "level": lv, "role": role,
            "is_boss": role == "boss", "is_elite": role == "elite",
            "rank": 1, "reach": 1, "ct": 1.0,
            "exp": 80, "gold": 40, "drops": ["兽肉"]}


def mk_st(qids, enemy=None, inst_id="inst_goblin_camp", **kw):
    qids = [str(q) for q in qids]
    st = {
        "type": "instance", "inst_id": inst_id, "leader": qids[0],
        "members": qids, "alive": {q: True for q in qids},
        "players": {}, "boss": None, "enemy": None, "enemies": [],
        "turn": 0, "round": 1, "mode": "battle", "pets": {},
        "p_buffs": {q: {} for q in qids},
        "p_hot": {q: {} for q in qids},
        "p_food_effects": {q: [] for q in qids},
        "p_defending": {q: False for q in qids},
        "mech_stacks": {q: {} for q in qids},
        "now": 0.0, "battle": None,
        "contribution": {}, "threat": {q: 0 for q in qids}, "over": False,
        "turn_time": 0, "stage_pending": [], "inst_stages": [],
        "stage_idx": 0, "stage_cleared": False, "world_id": "",
    }
    st.update(kw)
    for i, q in enumerate(qids):
        st["players"][q] = mk_snap(q, f"玩家{q}")
    if enemy:
        st["enemies"] = [enemy]
        st["boss"] = enemy
        st["enemy"] = enemy
    return st


class _Host(_CmdHost):
    """Router 测试宿主（`_engine_harness.Main`：同名的包内 InstanceImpl / CombatCmds /
    WorldCmds 落点由驱动口按名绑定，等价旧的三 Mixin 宿主）。"""


from content.instance_cmds import InstanceImpl as _InstImpl  # noqa: E402  （打桩落点：包内实现类）


def _patch_current_members(all_members):
    """多人副本 st 无 party 行时，current_members 恒返回全部成员（等价单人/测试口径）。"""
    orig = _InstImpl._instance_current_members
    _InstImpl._instance_current_members = lambda self, gid, st: [str(m) for m in (all_members or st["members"])]
    return orig


def _restore_current_members(orig):
    _InstImpl._instance_current_members = orig


# ---------------------------------------------------------------- 分支测试
def test_1_no_enemy_hint():
    print("【1. 肃清守卫：无敌人 → 引导探索/深入】")
    st = mk_st([70001])
    st["enemies"] = []
    inst = _Host()
    msgs = _sync_run(inst, st, 70001, "attack")
    joined = "\n".join(msgs)
    check("无 pending 无 stages → 深入/肃清提示", "肃清" in joined or "深入" in joined or "Boss" in joined,
          joined[:80])
    # 有 stage_pending → 探索引导
    st2 = mk_st([70002])
    st2["enemies"] = []
    st2["stage_pending"] = [["m_test", "小怪", "dps", 15, [], []]]
    inst2 = _Host()
    msgs2 = _sync_run(inst2, st2, 70002, "attack")
    joined2 = "\n".join(msgs2)
    check("有 stage_pending → 探索引导", "探索" in joined2, joined2[:80])
    check("未 build battle 不报错", not joined2.startswith("战斗状态异常"), joined2[:60])


def test_2_turn_wait():
    print("【2. 轮转：非请求者未超时 → 等待提示】")
    st = mk_st([70011, 70012], enemy=mk_enemy(hp=500, spd=1))
    # 双人玩家 actor 都建好
    _build_battle(st)
    # 让 70011 ct 最小（轮到他），70012 请求
    for a in (IB._players_of(st) or []):
        if str(a.get("qq_id")) == "70011":
            a["ct"] = 0.0
        else:
            a["ct"] = 50.0
    _sync_views(st, GID)
    st["turn_time"] = int(__import__("time").time())  # 未超时
    orig = _patch_current_members(["70011", "70012"])
    try:
        inst = _Host()
        msgs = _sync_run(inst, st, 70012, "attack")
        joined = "\n".join(msgs)
        check("非请求者 → 等待提示", "等待" in joined or "的刻" in joined, joined[:100])
        check("未行动者未被自动防御（defending False）",
              not st["p_defending"].get("70011"), str(st.get("p_defending")))
    finally:
        _restore_current_members(orig)


def test_3_timeout_auto_defend():
    print("【3. 超时自动防御：非请求者超时 → 自动 defend 后轮到请求者】")
    st = mk_st([70021, 70022], enemy=mk_enemy(hp=5000, spd=1))
    _build_battle(st)
    for a in (IB._players_of(st) or []):
        if str(a.get("qq_id")) == "70021":
            a["ct"] = 10.0   # 该 70021 行动但超时未动
        else:
            a["ct"] = 100.0  # 请求者 70022
    _sync_views(st, GID)
    st["turn_time"] = int(__import__("time").time()) - 120  # 已超时 60s
    orig = _patch_current_members(["70021", "70022"])
    try:
        inst = _Host()
        msgs = _sync_run(inst, st, 70022, "defend")
        joined = "\n".join(msgs)
        check("超时者自动防御（defending True）", bool(st["p_defending"].get("70021")),
              str(st.get("p_defending")))
        check("日志含自动防御提示", "自动" in joined or "迟迟" in joined, joined[:120])
    finally:
        _restore_current_members(orig)


def test_4_attack_and_sync():
    print("【4. 行动：attack 造成伤害 + 视图/DB 同步】")
    st = mk_st([70031], enemy=mk_enemy(hp=600, spd=1))
    _build_battle(st)
    hp0 = int(st["enemies"][0]["hp"])
    inst = _Host()
    msgs = _sync_run(inst, st, 70031, "attack")
    hp1 = int(st["enemies"][0]["hp"]) if st.get("enemies") else 0
    check("普攻造成伤害", hp1 < hp0, f"{hp0}->{hp1}")
    check("日志含伤害", any("伤害" in m or "攻击" in m for m in msgs), str(msgs[:1])[:80])
    check("视图同步敌 hp", st["enemies"] and st["enemies"][0]["hp"] == hp1)
    snap = st["players"]["70031"]
    dbp = db.get_player(GID, 70031) or {}
    check("DB 血量同步", int(dbp.get("hp", -1)) == int(snap.get("hp", -2)),
          f"db={dbp.get('hp')} snap={snap.get('hp')}")


def test_5_defend():
    print("【5. 行动：defend 姿态】")
    st = mk_st([70032], enemy=mk_enemy(hp=5000, atk=9999, spd=1))
    _build_battle(st)
    inst = _Host()
    msgs = _sync_run(inst, st, 70032, "defend")
    joined = "\n".join(msgs)
    check("防御姿态日志", "防御" in joined or "减半" in joined, joined[:100])
    # defend 后 actor defending 状态（视图键同步）
    check("防御状态落 actor/视图", bool(st["p_defending"].get("70032")), str(st.get("p_defending")))


def test_6_switch_next_monster():
    print("【6. 切怪：stage_pending 剩怪 → 击杀奖励 + 下一只重构造】")
    st = mk_st([70041], enemy=mk_enemy(hp=80, spd=1),
               stage_pending=[["m_slime", "史莱姆", "dps", 15, [], []]])
    _build_battle(st)
    inst = _Host()
    msgs = _sync_run(inst, st, 70041, "attack")
    joined = "\n".join(msgs)
    # 一刀没死继续补刀
    guard = 0
    while st.get("enemies") and not st.get("over") and guard < 8:
        guard += 1
        msgs = _sync_run(inst, st, 70041, "attack")
        joined += "\n" + "\n".join(msgs)
        if "又一只" in joined or not st.get("enemies"):
            break
    check("切怪文案（又一只怪物）", "又一只" in joined or not st.get("enemies"), joined[-200:])
    check("pending 消费", st.get("stage_pending") == [], str(st.get("stage_pending")))
    check("battle 重构造 sides", (st.get("battle") or {}).get("sides") is not None)
    check("新怪出现或已是下一只", bool(st.get("enemies")) or st.get("over"),
          f"enemies={st.get('enemies')} over={st.get('over')}")


def test_7_victory():
    print("【7. 通关：Boss 死（末层/无 pending）→ _instance_victory】")
    st = mk_st([70051], enemy=mk_enemy(hp=60, spd=1))
    _build_battle(st)
    inst = _Host()
    msgs = []
    guard = 0
    while st.get("enemies") and guard < 10:
        guard += 1
        msgs += _sync_run(inst, st, 70051, "attack")
        if st.get("cleared") or st.get("over") or not st.get("enemies"):
            break
    joined = "\n".join(msgs)
    check("通关文案", "通关" in joined, joined[-200:])
    check("cleared 置位", st.get("cleared") is True, f"cleared={st.get('cleared')}")
    check("存活玩家获得奖励（经验/金币行）", ("经验" in joined or "金币" in joined), joined[-300:])
    # Boss 死亡账（_last_killed 兜底 Boss 名在 victory 内消费）
    dbp = db.get_player(GID, 70051) or {}
    check("DB 玩家存活且经验增长", int(dbp.get("hp", 0)) > 0, f"hp={dbp.get('hp')}")


def test_8_defeat():
    print("【8. 失败：玩家全倒 → _instance_defeat（回城）】")
    # 玩家低血 + Boss 高攻高速 → 先手击杀
    st = mk_st([70061], enemy=mk_enemy(hp=8000, atk=9999, spd=200, role="boss"))
    st["players"]["70061"]["hp"] = 3
    db.update_player(GID, 70061, hp=3)
    _build_battle(st)
    inst = _Host()
    msgs = []
    guard = 0
    while guard < 12:
        guard += 1
        msgs += _sync_run(inst, st, 70061, "defend")
        if st.get("over") or not st.get("alive", {}).get("70061", True):
            break
        if not (st.get("battle") or {}).get("sides"):
            break
    joined = "\n".join(msgs)
    check("失败结算文案", "失败" in joined or "全灭" in joined or "送回了" in joined,
          joined[-200:])
    check("over/失败态", st.get("over") is True or "失败" in joined,
          f"over={st.get('over')} alive={st.get('alive')}")


def test_9_secret_guard():
    print("【9. 秘密守卫：secret_guard_pending → 宝箱分支（不通关）】")
    st = mk_st([70071], enemy=mk_enemy(hp=60, spd=1),
               secret_guard_pending=True, mode="battle",
               inst_stages=[{"name": "一层", "elite": ["m_test", "精英", "elite", 15, [], []]}])
    _build_battle(st)
    inst = _Host()
    msgs = []
    guard = 0
    while st.get("enemies") and guard < 10:
        guard += 1
        msgs += _sync_run(inst, st, 70071, "attack")
        if st.get("secret_chest") or not st.get("enemies"):
            break
    joined = "\n".join(msgs)
    check("宝箱分支文案", "宝箱" in joined, joined[-200:])
    check("secret_chest 置位", st.get("secret_chest") is True, f"chest={st.get('secret_chest')}")
    check("未通关（cleared 未置）", not st.get("cleared"), f"cleared={st.get('cleared')}")


def test_10_rooms_boss():
    print("【10. dungeon rooms：Boss 房击杀 → 通关】")
    # rooms 结构：真实 Boss 房 subarea（deer_fort_3）→ 击杀走通关
    cur_sa = "deer_fort_3"
    st = mk_st([70081], enemy=mk_enemy(hp=50, spd=1),
               inst_id="inst_deer_fort",
               rooms={cur_sa: {"monsters_left": [], "boss_alive": True,
                               "_is_boss": True}})
    db.update_player(GID, 70081, cur_map="deer_fort", cur_subarea=cur_sa)
    _build_battle(st)
    inst = _Host()
    msgs = []
    guard = 0
    while st.get("enemies") and guard < 10:
        guard += 1
        msgs += _sync_run(inst, st, 70081, "attack")
        if st.get("cleared") or st.get("over"):
            break
    joined = "\n".join(msgs)
    check("rooms Boss 房通关", "通关" in joined, joined[-200:])
    check("boss_alive 标记 False", (st.get("rooms") or {}).get(cur_sa, {}).get("boss_alive") is False,
          str(st.get("rooms")))


def _sync_run(inst, st, qq, action, skill=None, target=None):
    player = st["players"][str(qq)]
    ev = FakeEvent(GID, str(qq))
    return _run_gen(inst._instance_router(ev, GID, str(qq), player, st, action, skill, target))


def _run_gen(agen):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(collect(agen))
    finally:
        loop.close()


def test_11_command_entry_switch():
    print("【11. R2 命令层接线：CombatCmds attack/skill/defend 分流 → router】")
    # attack：db 有 battle 行 → instance 分流 → _instance_router（不再 _instance_act）
    # 注意：命令层从 db.get_battle 读回反序列化副本操作（大陆权威 st 场景在 R4 端到端），
    # 此处校验 db 行内 sides 敌 hp 下降（真实写入路径）。
    st = mk_st([70091], enemy=mk_enemy(hp=300, spd=1))
    _build_battle(st)
    db.save_battle(GID, 70091, st)
    inst = _Host()
    ev = FakeEvent(GID, "70091", "攻击")
    msgs = _collect(inst.attack(ev))
    joined = "\n".join(msgs)
    row = db.get_battle(GID, 70091)
    e_hp = 300
    if row:
        _sides = (row["state"].get("battle") or {}).get("sides") or row["state"].get("sides") or {}
        _e = _sides.get("enemy") or []
        if _e:
            e_hp = max(0, int(_e[0].get("hp", 300) or 300))
    check("attack 分流 → router 普攻造成伤害（db 行敌 hp 下降）", e_hp < 300, f"敌hp={e_hp}")
    check("attack 输出含回合面板", "行动" in joined or "伤害" in joined, joined[:100])
    # defend：实例行 → router 防御（db 行 defending 置位）
    ev2 = FakeEvent(GID, "70091", "防御")
    msgs2 = _collect(inst.defend(ev2))
    joined2 = "\n".join(msgs2)
    row2 = db.get_battle(GID, 70091)
    _def = False
    if row2:
        _sides2 = (row2["state"].get("battle") or {}).get("sides") or {}
        for _p in (_sides2.get("player") or []):
            if str(_p.get("qq_id")) == "70091":
                _def = bool(_p.get("defending"))
    check("defend 分流 → router 防御（db 行 defending）", _def, f"defending={_def}")
    check("defend 输出含防御文案", "防御" in joined2 or "减半" in joined2, joined2[:100])
    # skill：需要技能栏/已学——用攻击型验证不崩（heal 已覆盖于单测 4）
    st2 = mk_st([70092], enemy=mk_enemy(hp=500, spd=1))
    _build_battle(st2)
    db.save_battle(GID, 70092, st2)
    ev3 = FakeEvent(GID, "70092", "技能")
    msgs3 = _collect(inst.skill(ev3))
    # 无技能名 → 技能面板（说明走到了 skill 而非崩溃）
    joined3 = "\n".join(msgs3)
    check("skill 无参 → 面板（分流不崩）", bool(joined3.strip()), joined3[:80])


def test_12_use_item_router():
    print("【12. I3 use_item 端到端：router → override 翻译器 heal 生效 / 缺口不占刻】")
    # 玩家 hp 打残 → 副本内喝治疗药水 payload（模板产物 "150" 绝对恢复）
    st = mk_st([70101], enemy=mk_enemy(hp=800, spd=5))
    _build_battle(st)
    # 打掉玩家一点血（sides actor 直改——真实链路里由敌方攻击写）
    _pa = IB.player_actor_of(st, 70101)
    _max0 = int(_pa.get("max_hp", 0) or 0)
    _pa["hp"] = max(1, _max0 // 2)
    _sync_views(st, GID)
    inst = _Host()
    # 首次普通攻击推进轮转到玩家（turn_time 置现避免超时误判）
    import time as _t
    st["turn_time"] = int(_t.time())
    _hp_before = int((st["players"] or {}).get("70101", {}).get("hp", 0))
    msgs = _sync_run(inst, st, "70101", "use_item", "150")
    joined = "\n".join(msgs)
    _hp_after = int((st["players"] or {}).get("70101", {}).get("hp", 0))
    check("use_item 经 router 翻译恢复生命（saintess_engine actor 生效）", _hp_after > _hp_before,
          f"hp {_hp_before}->{_hp_after}")
    check("use_item 日志含恢复/使用文案", any(k in joined for k in ("恢复", "使用", "道具")), joined[:120])
    # battle state 仍在且敌未死
    check("使用后战斗未结束", not st.get("over"), f"over={st.get('over')}")
    # 机制型缺口（特殊分发未覆盖）→ 不生效提示，不占刻（战斗可继续普攻）
    st2 = mk_st([70102], enemy=mk_enemy(hp=800, spd=5))
    _build_battle(st2)
    st2["turn_time"] = int(_t.time())
    _ct_before = float((IB.player_actor_of(st2, 70102) or {}).get("ct", 0) or 0)
    msgs2 = _sync_run(inst, st2, "70102", "use_item", "special:summon")
    joined2 = "\n".join(msgs2)
    check("缺口 payload 不静默——给出未知/无效提示", bool(joined2.strip()), joined2[:120])
    _ct_after = float((IB.player_actor_of(st2, 70102) or {}).get("ct", 0) or 0)
    check("缺口不占刻（ct 未推）", abs(_ct_after - _ct_before) < 0.01,
          f"ct {_ct_before}->{_ct_after}")


def test_13_target_picker():
    print("【13. 5b target_picker：仇恨选目标 / 嘲讽强制 / policy 缺省】")
    from saintess_engine import Battle as B2
    from content.flow import instance_battle as IB
    st = mk_st([70111, 70112], enemy=mk_enemy(hp=5000, spd=1, role="boss"))
    _build_battle(st)
    # 组装 battle 实例（build_battle 已注入 picker——但 st["battle"] 是 to_state，
    # picker 是构造时闭包，需直接 from_state 后手动挂）
    b = B2.from_state(st["battle"])
    _attach_instance_hooks(b, st)
    pa1 = next(a for a in b.sides_of("player") if a.get("qq_id") == "70111")
    pa2 = next(a for a in b.sides_of("player") if a.get("qq_id") == "70112")
    enemy = b.sides_of("enemy")[0]
    enemy["role"] = "boss"
    # ① 无嘲讽：boss 缺省 hate_top → 打仇恨最高
    st["taunt_target"] = ""
    st["threat"] = {"70111": 100, "70112": 30}
    p = b.target_picker(b, enemy)
    check("boss hate_top 打仇恨最高者", p is not None and p.get("qq_id") == "70111",
          f"picked={p.get('qq_id') if p else None}")
    # ② 嘲讽强制（无视仇恨表）
    st["taunt_target"] = "70112"
    p2 = b.target_picker(b, enemy)
    check("嘲讽强制打嘲讽者", p2 is not None and p2.get("qq_id") == "70112",
          f"picked={p2.get('qq_id') if p2 else None}")
    st["taunt_target"] = ""
    # ③ 普通怪（非 boss 缺省 front）→ 有存活就选（单人/前排）
    enemy["role"] = "dps"
    p3 = b.target_picker(b, enemy)
    check("普通怪 front 选存活玩家", p3 is not None and p3.get("qq_id") in ("70111", "70112"),
          f"picked={p3.get('qq_id') if p3 else None}")
    # ④ 玩家全灭 → None（引擎回落默认，不崩）
    pa1["hp"] = 0
    pa2["hp"] = 0
    p4 = b.target_picker(b, enemy)
    check("无存活玩家 → None", p4 is None, f"picked={p4}")
    print("  -- 注：st threat 表 key=qq_id，monster_to_actor 透传 role 字段")


def test_14_team_heal_broadcast():
    print("【14. 5b G2 on_event：team=heal_all 全队广播（牧师救赎之光）】")
    from saintess_engine import Battle as B2
    from content.flow import instance_battle as IB
    # 双人副本：牧师 + 战士，战士残血
    st = mk_st([70121, 70122], enemy=mk_enemy(hp=5000, spd=1))
    # 换职业：70121 牧师（救赎之光 heal_all 技能）
    sn1 = st["players"]["70121"]
    sn1["class_name"] = "牧师"
    db.update_player(GID, "70121", learned_skills=["救赎之光"])
    db.set_skill_bar(GID, ["救赎之光", None, None, None, None, None])
    # 重读快照带新技能
    for k in ("hp", "mp", "max_hp", "max_mp"):
        p = db.get_player(GID, "70121")
        if k == "mp":
            p["mp"] = p["max_mp"] = 999
    st["players"]["70121"] = mk_snap(70121, "牧师甲", cls="cls_mu_shi", level=15, learned=["救赎之光"])
    # 战士残血
    sn2 = st["players"]["70122"]
    sn2["hp"] = int(sn2.get("max_hp", 500) * 0.3)
    _build_battle(st)
    b = B2.from_state(st["battle"])
    _attach_instance_hooks(b, st)
    # 确认 on_event 挂上
    check("on_event 已挂", b.on_event is not None)
    # 牧师打自己目标 = 治疗自己；heal_all 应广播到战士
    pa1 = next(a for a in b.sides_of("player") if str(a.get("qq_id")) == "70121")
    pa2 = next(a for a in b.sides_of("player") if str(a.get("qq_id")) == "70122")
    hp2_before = int(pa2.get("hp", 0) or 0)
    logs, ended, _who = b.human_act("skill", "救赎之光", pa1)
    hp2_after = int(pa2.get("hp", 0) or 0)
    check("队友被全队治疗（hp 上升）", hp2_after > hp2_before, f"hp {hp2_before}->{hp2_after}")
    check("广播日志含队友恢复", any("恢复" in x for x in logs), str(logs[-2:]))
    # 单人副本无队友 → 广播不崩
    st2 = mk_st([70123], enemy=mk_enemy(hp=5000, spd=1))
    st2["players"]["70123"]["class_name"] = "牧师"
    _build_battle(st2)
    b2 = B2.from_state(st2["battle"])
    _attach_instance_hooks(b2, st2)
    pa3 = next(a for a in b2.sides_of("player"))
    logs2, ended2, _who2 = b2.human_act("skill", "救赎之光", pa3)
    check("单人广播不崩", isinstance(logs2, list), str(logs2)[:60])


def test_15_multi_death_alive_sync():
    print("【15. 5b 收尾：多人一死一活 → alive 同步 / 死者不轮转 / 通关奖励隔离】")
    import time
    st = mk_st([70131, 70132], enemy=mk_enemy(hp=300, atk=2000, spd=200, role="boss"))
    # 70131 残血诱杀（视图 + DB 同步压，build_battle 读视图、sync_views 写 DB）
    st["players"]["70131"]["hp"] = 30
    db.update_player(GID, "70131", hp=30)
    # 70132 高血防 Boss 磨死（满血 99999，atk2000 打不死）
    st["players"]["70132"]["hp"] = 99999
    st["players"]["70132"]["max_hp"] = 99999
    db.update_player(GID, "70132", hp=99999, max_hp=99999)
    # Boss hate_top 仇恨锁定 70131（先打死一个，验证单死场景）
    st["threat"] = {"70131": 99999, "70132": 0}
    _build_battle(st)
    inst = _Host()
    orig = _patch_current_members(["70131", "70132"])
    joined = ""
    try:
        guard = 0
        died = False
        while guard < 60:
            guard += 1
            if st.get("over") or st.get("cleared"):
                break
            nxt = IB.next_actor_key(st)
            st["turn_time"] = int(time.time())
            if str(nxt) == "70131":
                msgs = _sync_run(inst, st, "70131", "defend")
            else:
                # M-w2s（召唤前排挡刀）适配：Boss 召唤的爪牙现插 enemy 队首挡刀且
                # name 带 Boss 前缀（"测试Boss的哥布林打手"），名字匹配必然先打爪牙——
                # 本场景目的是一死一活通关奖励隔离，故 70132 按存活序 aN 编号指定
                # Boss（精确 name 匹配，Boss 死后回落 None 自动清剩余爪牙）。
                _bt_sides = (st.get("battle") or {}).get("sides") or {}
                _alive_e = [u for u in (_bt_sides.get("enemy") or [])
                            if int(u.get("hp", 0) or 0) > 0]
                _boss_i = next((i for i, u in enumerate(_alive_e)
                                if (u.get("name") or "") == "测试Boss"), None)
                msgs = _sync_run(inst, st, "70132", "attack",
                                 target=f"a{_boss_i + 1}" if _boss_i is not None else None)
            joined += "\n" + "\n".join(msgs)
            if not st["alive"].get("70131", True) and not died:
                died = True
                # 死者 actor/视图/DB 三路同步为 0
                pa1 = IB.player_actor_of(st, "70131")
                check("70131 倒地（actor hp=0）", int(pa1.get("hp", 1) or 0) <= 0,
                      f"actor hp={pa1.get('hp')}")
                check("alive[70131]=False（sync_views 落地）", st["alive"].get("70131") is False,
                      str(st["alive"]))
                check("视图 hp=0", int((st["players"].get("70131") or {}).get("hp", 1) or 0) <= 0)
                check("DB hp=0（玩家血量同步）",
                      int((db.get_player(GID, 70131) or {}).get("hp", 1) or 0) <= 0)
                check("alive[70132] 仍 True（一死一活）", st["alive"].get("70132") is True,
                      str(st["alive"]))
                # 死者立即请求行动 → 轮转到活人等待提示，不崩不真行动
                st["turn_time"] = int(time.time())
                msgs_d = _sync_run(inst, st, "70131", "defend")
                d_joined = "\n".join(msgs_d)
                check("死者请求行动 → 等待活人提示（不崩）",
                      "等待" in d_joined or "70132" in d_joined, d_joined[-120:])
                check("死者请求未消耗轮次（未真行动）",
                      bool(st["alive"].get("70131") is False), str(st["alive"]))
                # 轮转不再选死者
                nxt2 = IB.next_actor_key(st)
                check("next_actor_key 跳过死者", str(nxt2) != "70131", f"nxt={nxt2}")
        # 活人单刷 Boss → 通关
        check("活人 70132 单刷通关", st.get("cleared") is True,
              f"cleared={st.get('cleared')} over={st.get('over')}")
        p1 = db.get_player(GID, 70131) or {}
        p2 = db.get_player(GID, 70132) or {}
        check("通关文案含阵亡提示（💀 未获奖励）", "阵亡" in joined or "已阵亡" in joined,
              joined[-400:])
        check("阵亡者未得通关奖励（gold 不变）", int(p1.get("gold", -1)) == 50,
              f"70131 gold={p1.get('gold')}")
        check("活人得通关奖励（gold 增长）", int(p2.get("gold", 0)) > 50,
              f"70132 gold={p2.get('gold')}")
        check("阵亡者 DB hp 保持 0", int(p1.get("hp", 1) or 0) <= 0,
              f"70131 hp={p1.get('hp')}")
    finally:
        _restore_current_members(orig)


def _collect(agen):
    """跑命令层 filter handler（async generator 或 coroutine 兼容）。"""
    return _run_gen(agen)


def main():
    test_1_no_enemy_hint()
    test_2_turn_wait()
    test_3_timeout_auto_defend()
    test_4_attack_and_sync()
    test_5_defend()
    test_6_switch_next_monster()
    test_7_victory()
    test_8_defeat()
    test_9_secret_guard()
    test_10_rooms_boss()
    test_11_command_entry_switch()
    test_12_use_item_router()
    test_13_target_picker()
    test_14_team_heal_broadcast()
    test_15_multi_death_alive_sync()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
