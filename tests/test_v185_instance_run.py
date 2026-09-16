# -*- coding: utf-8 -*-
"""门禁：v185 副本「进度/名单」接线（路线图 #8 内容侧）—— 行为冻结比对 + 旧实现对账。

背景：`game/core/instance_run.py`（适配层）把副本的**名单 / 分层进度 / 房间剩余池 / 资源池 /
清空块**五种形状从 `game/commands/instance*.py` 的手写散读散写里收口出来。本门禁守两件事：

  A. ★ **行为冻结**（接线只许搬家）：真跑一条副本流程（开本 → 副本地图 → 调查 POI →
     深入各分支 → 撤退 → 重新开本 → 离开），把每一步的「命令输出 + battle.state 快照」
     与 `tests/_v185run_baseline.json`（**接线前**采自 commit 851913a 的实测值）逐字比对。
     · 随机固定 seed（开箱/掉落走 stdlib random）；`world_id`（inst:<uuid>）等易变字段已归一化
     · `--write` 只在接线前生成基线用（在**接线前的代码**上跑）

  B. **旧实现对账**（纯函数矩阵）：把**旧实现**（从 851913a 冻结的源码片段，带来源自检）
     与适配层在同一批 st 状态上逐格比对 —— 证的是「同一语义」，不是「看起来差不多」。

跑法：python tests/test_v185_instance_run.py            （exit=0 全绿）
      python tests/test_v185_instance_run.py --write    （仅接线前生成基线）
"""
import asyncio
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile

# 独立私有库（绝不碰生产库 / 其它测试的库）
os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "v185run.db")
os.environ.setdefault("GWEN_TEST_MODE", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
PLUGIN_DIR = _paths.HOST_ROOT      # 宿主插件根（旧语义；旧实现对账的 git 仓库根）
PKG_ROOT = _paths.PKG_ROOT         # 包根（内容真源）
ENGINE_ROOT = _paths.ENGINE_ROOT
_TESTS = _paths.TESTS_DIR

from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run   # noqa: E402
from content.flow import instance_battle as IB                              # noqa: E402

BASELINE = os.path.join(_TESTS, "_v185run_baseline.json")
WIRE_COMMIT = "851913a"          # 接线前的最后一个提交（基线来源）

GID, QID = "gcap1", "qcap1"
GOBLIN_ENTRY = ("misty_swamp", "misty_swamp_3")

ST_KEYS = ("leader", "members", "alive", "stage_idx", "stage_pending", "stage_count",
           "inst_key", "mode", "over", "cleared", "retreated", "rooms", "resources_pool",
           "boss", "enemy", "enemies", "world_id")
VOLATILE = ("world_id", "started_at", "created_at", "updated_at", "ts", "at")
UUID_RE = re.compile(r"inst:[0-9a-fA-F-]{8,}")

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


# ============================================================
# A. 行为冻结
# ============================================================

def _norm(v):
    """纯数据化 + 易变值归一（dict 键排序 / set 排序 / inst:<uuid> 归一）。"""
    if isinstance(v, dict):
        return {str(k): _norm(v[k]) for k in sorted(v, key=str)}
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, set):
        return sorted(_norm(x) for x in v)
    if isinstance(v, str):
        return UUID_RE.sub("inst:<uuid>", v)
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return repr(v)


async def _cmd(m, handler_name, msg):
    res = await run(getattr(m, handler_name), FakeEvent(GID, QID, msg))
    return res[-1] if res else ""


async def scenario():
    """真跑一条副本流程，返回每一步的（输出 + st 快照）。"""
    random.seed(20260912)          # ★ 固定随机：开箱/掉落走 stdlib random
    steps = []

    def snap(tag, out):
        row = (db.get_battle(GID, QID) or {}).get("state") or {}
        row = {k: v for k, v in row.items() if k not in VOLATILE}
        steps.append({"tag": tag,
                      "out": out if isinstance(out, str) else "\n".join(out),
                      "st": {k: _norm(row.get(k)) for k in ST_KEYS if k in row},
                      "st_has": sorted(row.keys())})

    clean_db()
    make_player(GID, QID, name="基线", cls="战士", level=60)
    db.update_player(GID, QID, cur_map=GOBLIN_ENTRY[0], cur_subarea=GOBLIN_ENTRY[1],
                     stamina=999999)
    m = Main(None)

    snap("00-初始", "")
    snap("01-开本", await _cmd(m, "instance_cmd", "副本 哥布林营地"))
    snap("02-副本地图", await _cmd(m, "instance_map_view_cmd", "副本地图"))
    # 02b：调查入口房间 POI（消耗 pois_left；走 loot 链路扣 resources_pool）
    # ★ 不引战：进怪房（『移动』）会开战，战斗是时间驱动的 → 不可比对
    snap("02b-调查铁箱", await _cmd(m, "instance_investigate", "调查 生锈的铁箱"))
    snap("03-深入未清层", await _cmd(m, "instance_advance", "深入"))
    # 03b：把当前层「假装打完」（stage_cleared=True + 清空 stage_pending）→ 反复『深入』，
    # 走真推进分支（pending 组装 / stage_idx 前进 / 末层判定）
    for i in range(3):
        st = (db.get_battle(GID, QID) or {}).get("state")
        if st:
            st["stage_cleared"] = True
            st["stage_pending"] = []
            m._instance_save(GID, st)
        snap(f"03b-清层后深入#{i + 1}", await _cmd(m, "instance_advance", "深入"))
    snap("04-调查", await _cmd(m, "instance_investigate", "调查"))
    snap("05-撤退一次", await _cmd(m, "instance_retreat", "撤退"))
    snap("06-确认撤退", await _cmd(m, "instance_retreat_confirm", "确认撤退"))
    db.update_player(GID, QID, cur_map=GOBLIN_ENTRY[0], cur_subarea=GOBLIN_ENTRY[1])
    snap("07-开本2", await _cmd(m, "instance_cmd", "副本 哥布林营地"))
    snap("08-离开副本", await _cmd(m, "instance_leave", "离开副本"))
    return steps


def capture():
    return {"steps": asyncio.run(scenario()), "room_clear": _room_case(),
            "build_state": _build_state_cases()}


def test_A_behavior_frozen():
    print("【A. 行为冻结：接线前后逐步逐字一致（基线采自接线前 %s）】" % WIRE_COMMIT)
    now = capture()
    if not os.path.exists(BASELINE):
        check("基线文件存在", False, BASELINE)
        return
    with open(BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    check(f"步骤数一致（{len(base['steps'])} 步）", len(base["steps"]) == len(now["steps"]),
          (len(base["steps"]), len(now["steps"])))
    bad = []
    for b, n in zip(base["steps"], now["steps"]):
        if b != n:
            why = []
            if b["tag"] != n["tag"]:
                why.append("tag")
            if b["out"] != n["out"]:
                why.append(f"输出: 基线 {b['out'][:60]!r} → 现在 {n['out'][:60]!r}")
            if b["st"] != n["st"]:
                keys = sorted(set(b["st"]) | set(n["st"]))
                d = [k for k in keys if b["st"].get(k) != n["st"].get(k)]
                why.append(f"st 字段变了: {d[:4]}")
            if b["st_has"] != n["st_has"]:
                why.append(f"st 键集变了: {sorted(set(b['st_has']) ^ set(n['st_has']))[:4]}")
            bad.append((b["tag"], " · ".join(why)))
    check("每一步逐字一致（输出 + st 快照 + 键集）", not bad, bad[:3])


# ============================================================
# B. 旧实现对账（冻结源码片段 → 矩阵逐格比对）
# ============================================================

def _git_show(path):
    out = subprocess.run(["git", "show", f"{WIRE_COMMIT}:{path}"], cwd=PLUGIN_DIR,
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        return ""
    return out.stdout


_OLD_CURRENT_MEMBERS = '''
def _old_current_members(self, group_id, st):
    party = [str(m) for m in db.party_members(group_id, st["leader"])]
    if party:
        return [str(m) for m in st["members"] if str(m) in party]
    members = st.get("members") or []
    if len(members) == 1 and str(members[0]) == str(st["leader"]):
        return [str(members[0])]
    return []
'''

_OLD_LIVING = '''
def _old_has_living(self, group_id, st):
    cur = _old_current_members(self, group_id, st)
    for k in cur:
        if st.get("alive", {}).get(str(k), True) and \\
                int((st.get("players") or {}).get(str(k), {}).get("hp", 0) or 0) > 0:
            return True
    return False
'''


def _load_old():
    ns = {"db": db}
    exec(_OLD_CURRENT_MEMBERS, ns)          # noqa: S102（测试内冻结旧实现）
    exec(_OLD_LIVING, ns)                   # noqa: S102
    return ns


def test_B_adapter_matches_old():
    print("【B. 旧实现对账：适配层 == 接线前那份语义（矩阵逐格）】")
    old_probe = _git_show("game/commands/instance.py")
    old_router = _git_show("game/commands/instance_router.py")
    check(f"能取到接线前源码（{WIRE_COMMIT}）", bool(old_probe and old_router))
    # 冻结自检：内嵌的旧实现片段确实来自那个提交（防「凭记忆重写」）
    frag = 'party = [str(m) for m in db.party_members(group_id, st["leader"])]'
    check("旧实现片段来自 %s（逐字）" % WIRE_COMMIT, frag in old_probe)
    frag2 = 'if st.get("alive", {}).get(str(k), True) and'
    check("router 旧判定片段来自 %s（逐字）" % WIRE_COMMIT, frag2 in old_router)

    # ★ 用**包内规范名**导入：`game.*` 与 `data.plugins.dragonfall.game.*` 是两份模块对象，
    #   走后者才是 conftest/生产用的那一份（走前者会重新执行包 __init__ 撞上 core↔data 历史循环导入）
    import content.flow.instance_run as IR   # 包内真源（REPOINT_MAP: game.core.instance_run → content.flow.instance_run）

    ns = _load_old()
    old_cm, old_hl = ns["_old_current_members"], ns["_old_has_living"]
    self_stub = object()

    # ---- 构造矩阵：队伍形态 × 成员/存活/血量 ----
    clean_db()
    for q in ("mA", "mB", "mC", "mD"):
        make_player(GID, q, name=q, cls="战士", level=50)

    cases = []
    # ① 单人副本（无队伍）：st["members"] == [leader]
    cases.append(("单人-唯一成员=队长", "mA", ["mA"], {"mA": True}, {"mA": {"hp": 100}}))
    # ② 单人副本但 members 为空 → 旧实现返回 []
    cases.append(("单人-members 空", "mA", [], {}, {}))
    # ③ 无队伍但 members 多人（脏数据）→ 旧实现返回 []
    cases.append(("无队伍-members 多人", "mA", ["mA", "mB"], {}, {}))
    # ④ 有队伍：leader 与队员都在 members
    db.party_create(GID, "mA", "mB")
    cases.append(("队伍-两人在场", "mA", ["mA", "mB"], {"mA": True, "mB": True},
                  {"mA": {"hp": 100}, "mB": {"hp": 80}}))
    # ⑤ 退队者还在 members 里（结算过滤的关键场景）
    cases.append(("队伍-退队者残留 members", "mA", ["mA", "mB", "mC"],
                  {"mA": True, "mB": True, "mC": True},
                  {"mA": {"hp": 100}, "mB": {"hp": 80}, "mC": {"hp": 70}}))
    # ⑥ 在场但阵亡（hp 0）
    cases.append(("队伍-一人阵亡", "mA", ["mA", "mB"], {"mA": True, "mB": True},
                  {"mA": {"hp": 100}, "mB": {"hp": 0}}))
    # ⑦ alive=False
    cases.append(("队伍-一人 alive=False", "mA", ["mA", "mB"], {"mA": True, "mB": False},
                  {"mA": {"hp": 100}, "mB": {"hp": 50}}))
    # ⑧ alive 缺键（默认视为存活）
    cases.append(("队伍-alive 缺键", "mA", ["mA", "mB"], {"mA": True},
                  {"mA": {"hp": 100}, "mB": {"hp": 50}}))

    cm_bad, hl_bad = [], []
    for tag, leader, members, alive, players in cases:
        st = {"leader": leader, "members": members, "alive": alive, "players": players}
        want_cm = old_cm(self_stub, GID, st)
        # 包内真源签名 `current_members(st, party)`（宿主壳旧签名 `(group_id, st)` 把队伍
        # 从 `db.party_members` 取好传入 —— 见 content/flow/instance_run.py:81-83）
        got_cm = [str(x) for x in IR.current_members(
            st, db.party_members(GID, st["leader"]))]
        if want_cm != got_cm:
            cm_bad.append((tag, want_cm, got_cm))
        want_hl = old_hl(self_stub, GID, st)
        got_hl = bool(IR.living_players(st))
        if want_hl != got_hl:
            hl_bad.append((tag, want_hl, got_hl))
    check(f"current_members：{len(cases)} 个状态逐格一致", not cm_bad, cm_bad[:3])
    check(f"living_players（在场且有活人）：{len(cases)} 个状态逐格一致", not hl_bad, hl_bad[:3])


def _ir():
    """适配层模块（包内规范名，见 §B 的说明）。"""
    import content.flow.instance_run as IR
    return IR


# ---------------------------------------------------------------- 合成房间战
# 复用 tests/test_battle_n5b4_instance_router.py 的合成手法（那一支在现有测试里**没人覆盖**：
# 实测把旧代码里清空块的 `stage_cleared = True` 改成 False，全量里 59/19/101 个断言仍全绿）。

def _mk_snap(qid, name="玩家", cls="战士", level=60):
    db.create_player(GID, qid, name, cls, {}, 100, 100)
    db.update_player(GID, qid, level=level, cur_map="mainland", cur_subarea="", stamina=999)
    pl = db.get_player(GID, qid)
    return {"name": name, "qq_id": qid, "class_name": cls, "level": level,
            "hp": 500, "max_hp": 500, "mp": 50, "max_mp": 50, "equipment": {},
            "skills": [], "learned_skills": [], "class_tier": 0, "evolve_path": 0,
            "attributes": pl.get("attributes"), "bonus": {"panel": {}, "cap": {}, "cost": {}},
            "race": pl.get("race"), "uid": f"p_{qid}", "buffs": {}, "stacks": {},
            "defending": False, "charging": None, "ct": 0.0, "p_shields": {}, "spd": 30}


def _mk_enemy(hp=1, spd=1, role="dps"):
    return {"uid": "e_room", "name": "房间怪", "hp": hp, "max_hp": hp, "atk": 1, "def": 0,
            "matk": 1, "mdef": 0, "spd": spd, "crit": 0.0, "lv": 15, "level": 15,
            "role": role, "is_boss": role == "boss", "is_elite": role == "elite",
            "rank": 1, "reach": 1, "ct": 1.0, "exp": 10, "gold": 5, "drops": []}


def _mk_room_st(qid, cur_sa, inst_id="inst_goblin_camp", rooms=None, stage_pending=None):
    st = {"type": "instance", "inst_id": inst_id, "leader": qid, "members": [qid],
          "alive": {qid: True}, "players": {qid: _mk_snap(qid)}, "boss": None, "enemy": None,
          "enemies": [], "turn": 0, "round": 1, "mode": "battle", "pets": {},
          "p_buffs": {qid: {}}, "p_hot": {qid: {}}, "p_food_effects": {qid: []},
          "p_defending": {qid: False}, "mech_stacks": {qid: {}}, "now": 0.0, "battle": None,
          "contribution": {}, "threat": {qid: 0}, "over": False, "turn_time": 0,
          "stage_pending": list(stage_pending or []), "inst_stages": [{"name": "L1"}, {"name": "L2"}],
          "stage_idx": 0, "stage_cleared": False, "world_id": "",
          "rooms": dict(rooms or {}), "resources_pool": {"gold_left": 0, "mats_left": {},
                                                         "equip_left": []}}
    st["enemies"] = [_mk_enemy()]
    st["boss"] = st["enemies"][0]
    st["enemy"] = st["enemies"][0]
    return st


class _RoomHost(Main):
    """router 测试宿主（`_engine_harness.Main`：包内 InstanceImpl / CombatCmds / WorldCmds 同名落点）。"""


def _sync_run(inst, st, qq, action):
    player = st["players"][str(qq)]
    ev = FakeEvent(GID, str(qq))
    agen = inst._instance_router(ev, GID, str(qq), player, st, action, None, None)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_collect(agen))
    finally:
        loop.close()


async def _collect(agen):
    out = []
    async for x in agen:
        out.append(x)
    return out


ROOM_FIELDS = ("mode", "stage_cleared", "over", "boss", "enemy", "enemies",
               "stage_idx", "stage_pending", "rooms", "pets")


def _room_case():
    """普通房（非 Boss 房）清怪 → 回地图模式那一支。"""
    qid, cur_sa = "qroom1", "goblin_camp_1"
    random.seed(20260912 + 1)      # ★ 本用例自己的固定随机（与场景 A 解耦：crit 等走 stdlib random）
    clean_db()
    st = _mk_room_st(qid, cur_sa,
                     rooms={cur_sa: {"monsters_left": [], "pois_left": [],
                                     "boss_alive": False}})
    db.update_player(GID, qid, cur_map="misty_swamp", cur_subarea=cur_sa)
    IB.build_battle(st)
    inst = _RoomHost()
    msgs, guard = [], 0
    while st.get("enemies") and guard < 12:
        guard += 1
        st["turn_time"] = int(__import__("time").time())      # 未超时（防走超时自动防御分支）
        msgs += _sync_run(inst, st, qid, "attack")
        if st.get("cleared") or st.get("over"):
            break
    return {"msgs": chr(10).join(str(m) for m in msgs),
            "st": {k: _norm(st.get(k)) for k in ROOM_FIELDS}}


# ------------------------------------------------------- 状态构造（三支分支）
_BUILD_CASES = (
    ("有怪层", {"lv": 15, "stages": [{"name": "L1", "monsters": [["m_goblin_guard", "哥布林守卫", "tank", 15, [], []]]}]}),
    ("单层Boss房", {"lv": 20, "stages": [{"name": "L1", "boss": ["b_warden", "守望者", "boss", 20, [], []]}]}),
    ("无stages老副本", {"lv": 15}),
)
_BUILD_KEYS = ("mode", "boss", "enemy", "enemies", "stage_pending", "stage_idx",
               "stage_cleared", "inst_stages", "rooms", "resources_pool")


def _build_state_cases():
    """三支分支各造一次 st（纯构造，无随机、无 DB 依赖）→ 键集 + 关键字段快照。"""
    host = _RoomHost()
    out = []
    for tag, inst in _BUILD_CASES:
        st = host._instance_build_state("inst_goblin_camp", inst, [QID], None, 1234567, QID)
        out.append({"tag": tag,
                    "keys": sorted(str(k) for k in st.keys()),
                    "snap": {k: _norm(st.get(k)) for k in _BUILD_KEYS if k in st}})
    return out


def test_E_build_state_branches():
    print("【E. 状态构造三支分支：键集 + 关键字段逐字一致】")
    if not os.path.exists(BASELINE):
        check("基线文件存在", False, BASELINE)
        return
    base = json.load(open(BASELINE, encoding="utf-8")).get("build_state")
    check("基线含 build_state 段", bool(base))
    if not base:
        return
    now = _build_state_cases()
    check(f"分支数一致（{len(base)} 支）", len(base) == len(now), (len(base), len(now)))
    bad = []
    for b, n in zip(base, now):
        if b != n:
            why = []
            if b["keys"] != n["keys"]:
                why.append("键集: " + str(sorted(set(b["keys"]) ^ set(n["keys"]))[:6]))
            if b["snap"] != n["snap"]:
                why.append("字段: " + str([k for k in _BUILD_KEYS if b["snap"].get(k) != n["snap"].get(k)]))
            bad.append((b["tag"], "; ".join(why)))
    check("三支分支键集与关键字段逐字一致（三份 dict 合一未丢键/未多键）", not bad, bad)


def test_D_room_clear_block():
    print("【D. 合成房间战：普通房清怪 → 回地图模式（清空块那一支）】")
    if not os.path.exists(BASELINE):
        check("基线文件存在", False, BASELINE)
        return
    base = json.load(open(BASELINE, encoding="utf-8")).get("room_clear")
    check("基线含 room_clear 段", bool(base))
    if not base:
        return
    now = _room_case()
    check("清怪后回地图模式（mode=map）", now["st"].get("mode") == "map", now["st"].get("mode"))
    check("房间清空块标志（stage_cleared=True / over=False）",
          now["st"].get("stage_cleared") is True and now["st"].get("over") is False,
          (now["st"].get("stage_cleared"), now["st"].get("over")))
    diff = [k for k in ROOM_FIELDS if base["st"].get(k) != now["st"].get(k)]
    check("与接线前基线逐字一致（字段 + 输出）",
          not diff and base["msgs"] == now["msgs"],
          {"变了": diff, "基线": str(base["st"])[:120], "现在": str(now["st"])[:120]})


def test_C_adapter_contract():
    """适配层契约：资源池「不足只给剩余」/ 房间池扣减 / 清空块的标志语义。"""
    print("【C. 适配层契约：资源池 / 房间池 / 清空块】")
    IR = _ir()

    st = {"resources_pool": {"gold_left": 30, "mats_left": {"铁片": 2}, "equip_left": ["eq1"]}}
    check("金币足够 → 扣满并写回", IR.spend_gold(st, 20) == 20
          and st["resources_pool"]["gold_left"] == 10)
    check("金币不足 → 只给剩余（返回实扣量）", IR.spend_gold(st, 999) == 10
          and st["resources_pool"]["gold_left"] == 0)
    check("金币已空 → 0（不抛）", IR.spend_gold(st, 5) == 0)
    check("材料扣 1（同名计数）", IR.spend_mat(st, "铁片") is True
          and st["resources_pool"]["mats_left"]["铁片"] == 1)
    check("材料兜底那一件也扣得掉", IR.spend_mat(st, "铁片") is True
          and st["resources_pool"]["mats_left"].get("铁片", 0) == 0)
    check("材料已空 → False", IR.spend_mat(st, "铁片") is False)
    check("装备移出池", IR.spend_equip(st, "eq1") is True
          and st["resources_pool"]["equip_left"] == [])
    check("装备不在池中 → False", IR.spend_equip(st, "eq1") is False)

    st2 = {"rooms": {"r1": {"monsters_left": [{"id": "m1"}, {"id": "m2"}],
                            "pois_left": ["p1", "p2"]}}}
    check("房间剩余怪数", IR.monsters_left(st2, "r1") == 2)
    first = IR.take_monster(st2, "r1")
    check("take_monster 弹一只并写回", first == {"id": "m1"}
          and IR.monsters_left(st2, "r1") == 1)
    check("POI 在池中", IR.poi_left(st2, "r1", "p1") is True)
    check("take_poi 移出", IR.take_poi(st2, "r1", "p1") is True
          and IR.poi_left(st2, "r1", "p1") is False)
    check("take_poi 重复调用 → False", IR.take_poi(st2, "r1", "p1") is False)
    IR.mark_boss_room_done(st2, "r1")
    check("标记 Boss 房已清（boss_alive=False + _boss_room=True）",
          st2["rooms"]["r1"]["boss_alive"] is False and st2["rooms"]["r1"]["_boss_room"] is True)

    st3 = {"mode": "battle", "boss": {"x": 1}, "enemy": {"y": 1}, "enemies": [1, 2],
           "pets": {"p1": {"_last_hit_at": 123, "name": "阿黄"}}}
    IR.clear_battle_view(st3, stage_cleared=True, over=False)
    check("清空块：mode→map + 战斗视图字段清空 + 调用方标志原样写入",
          st3["mode"] == "map" and not st3["boss"] and not st3["enemy"] and st3["enemies"] == []
          and st3["stage_cleared"] is True and st3["over"] is False)
    IR.clear_pet_hits(st3)
    check("清宠物最近被击中时间戳（其余字段不动）",
          "_last_hit_at" not in st3["pets"]["p1"] and st3["pets"]["p1"]["name"] == "阿黄")


def main():
    if "--write" in sys.argv:
        data = capture()
        with open(BASELINE, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        print(f"基线已写入 {BASELINE}（{len(data['steps'])} 步）—— 只应在**接线前**的代码上执行")
        return
    test_A_behavior_frozen()
    test_B_adapter_matches_old()
    test_C_adapter_contract()
    test_D_room_clear_block()
    test_E_build_state_branches()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
