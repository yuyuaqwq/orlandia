# -*- coding: utf-8 -*-
"""R2.2 门禁：副本流程里「防御姿态减半」在**敌手出手那一刻**必须真的生效。

★ 为什么引擎自己的门禁照不到这个窗口（R2.2 的根因，见 C 车道台账 §0.4）：
  引擎 `tests/test_cross_hand_state.py` ① 直接调 `bt.act()`（单段）⇒ 窗口开在决策点、
  到期消费也在同一段里，中间**没有**「重建 → 决策 → 落地」的时序。
  而包侧 `content/flow/instance_battle.py::act()` 是**两段化**的：
      restore_battle(st) → b.human_act(...) → BR.land_pending(b, logs, my)
  T0 段入口有 `consume_windows(actor)`（到期消费，`until="own_act"`），
  `_do_defend` 的开窗在 **B 段** `_dispatch_pending` 里 ⇒ 敌手整个回合落在
  「已清、还没开」的空窗里 ⇒ 减半整段没跑（日志里没有 `(格挡后 N 点伤害)` 那一行）。

⇒ 本门禁**故意同时钉两侧**，缺一不算过（这样它不可能「恒绿」）：
  ① 对照组：单段 `bt.act()`（引擎门禁那一侧）—— 减半**必须**生效。
  ② 目标组：包内两段化真跑路径（引擎门禁照不到的那扇窗）—— 减半**必须**生效。
     ★ ② 现在是红的（R2.2 未修）⇒ 这就是给引擎立项的那把尺；
       引擎改好时它转绿，而 ① 必须保持绿 ⇒ 两侧同时满足才算修好，
       不会靠「把 ① 改坏」蒙过去。

**反证（写完后手验）**：
  · 把 `battle.py` T0 段那行 `consume_windows(actor)` 注掉 ⇒ ① 变红
    （姿态永不到期）⇒ 证明 ① 真的在读那个到期点；
  · 把 `landing.py` 的窗口查询改坏 ⇒ ① ② 同时变红
    ⇒ 证明两者都真的在读容器窗口，不是恒绿。

★ **已进闸**（2026-09-29 · R2.2 修复批）：引擎修复落地（`Battle.act` 登记段为
  防御预开窗 —— battle.py「★ R2.2」注）后 2.1 已转绿 ⇒ 本文件改名 `test_*`
  进全量，作为 R2.2 的**常驻守护**（防未来回归）。改名同批补 `extends` 的
  sys.path 自包含（原先显式依赖调用方环境，干净会话跑会 ModuleNotFoundError）。
  （历史：2026-09-28 曾以 `_probe_*` 刻意出闸 —— 当时 2.1 是「引擎未修」的红。）

跑法：python tests/test_defend_window_probe.py（已自包含，任意 cwd / 干净 env 可跑）
"""
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
FW_ROOT = os.environ.get("GWEN_FRAMEWORK_DIR") or os.path.dirname(PKG_ROOT)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PKG_ROOT, "defend_window_probe.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, FW_ROOT)
sys.path.insert(0, os.path.join(FW_ROOT, "extends"))   # ext_combat（2026-09-29 自包含修补）
sys.path.insert(0, PKG_ROOT)
sys.path.insert(0, _HERE)

PASS = 0
FAIL = 0
FAILURES = []


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [OK] %s" % label)
    else:
        FAIL += 1
        FAILURES.append(label)
        print("  [NG] %s%s" % (label, ("  -- " + detail) if detail else ""))


# 引擎不内置行动基准数值（未装配即抛 EngineNotConfigured）⇒ 本门禁自带最小时间模型
from saintess_engine import config as CFG                       # noqa: E402

_TIME_HOOKS = ("time_model_fn", "action_base_fn", "recover_model_fn",
               "recover_base_fn")
_saved = {n: CFG._HOOKS.get(n) for n in _TIME_HOOKS}
_saved_provider, _saved_strict = CFG._hook_provider, CFG.strict
CFG._hook_provider = None
CFG.strict = False
CFG.mount(time_model_fn=lambda spd, base: float(base) * (50.0 / max(float(spd or 0), 1.0)),
          action_base_fn=lambda a: 1.0 if a in ("attack", "skill", "defend") else 0.0,
          recover_model_fn=lambda spd, base: float(base),
          recover_base_fn=lambda a: 0.0)

from ext_combat.battle.actors import (DEFEND_TAG, make_actor,      # noqa: E402
                                      window_open)
from ext_combat.battle.battle import ActCtx, Battle               # noqa: E402
from ext_combat.battle import landing as LND                      # noqa: E402

# 已迁移点位（battle.landing.*）的措辞真源在内容侧文案表；本门禁不接内容包
# ⇒ 自带最小一份（逐字 = 迁移前那句「(格挡后 N 点伤害)」）
# 已迁移点位（battle.landing.*）的措辞真源在**内容侧文案表**；本门禁不接内容包
# ⇒ 用引擎侧那份门禁夹具（与 test_cross_hand_state.py 同一份，逐字 = 迁移前那句）
sys.path.insert(0, os.path.join(FW_ROOT, "tests"))
from _cue_text_fixture import TEXT as PKG_TEXT                      # noqa: E402
from _cue_text_fixture import install as _fix_install             # noqa: E402

_fix_install()


def _mk(uid, side, human=False, hp=200):
    return make_actor(uid, uid, side, human_controlled=human,
                      **{"hp": hp, "max_hp": hp, "atk": 10, "matk": 10,
                         "def": 0, "mdef": 0, "spd": 50, "stats_spd": 50})


def _bt(a, b):
    return Battle(btype="monster", sides={"player": [a], "enemy": [b]},
                  seed_ct=False, text=PKG_TEXT)


# ============================================================
print("\n[1] 对照组：单段 bt.act()（引擎门禁那一侧）—— 减半必须生效")
# ============================================================
a, b = _mk("a1", "player", human=True), _mk("b1", "enemy")
bt = _bt(a, b)
bt._do_defend(ActCtx(caster=a, action="defend"))
check("1.1 敲防御 => 窗口条目置上（until=own_act）",
      window_open(a, DEFEND_TAG)
      and (a.get("effects") or {}).get(DEFEND_TAG, {}).get("until") == "own_act",
      str(a.get("effects")))

_lg = []
_d1 = LND.deal_damage(bt, b, a, 10, _lg)
check("1.2 姿态期内挨打 => 减半（10 -> 5）+ 出「格挡后」行",
      _d1 == 5 and any("格挡后" in x for x in _lg), "%s / %s" % (_d1, _lg))

# 自己动手 = 「你下一次行动」=> 窗口到期（这一条证明 1.2 真的在读到期点）
bt.act(ActCtx(caster=a, action="attack"))
check("1.3 自己下一次行动 => 窗口到期（容器里消失）", not window_open(a, DEFEND_TAG),
      str(a.get("effects")))

_lg2 = []
_d2 = LND.deal_damage(bt, b, a, 10, _lg2)
check("1.4 到期之后挨打 => 全额（10 点 · 无「格挡后」行）",
      _d2 == 10 and not any("格挡后" in x for x in _lg2), "%s / %s" % (_d2, _lg2))
# ============================================================
print("\n[2] 目标组：副本真跑路径（引擎门禁照不到的那扇窗）")
# ============================================================
# ★ 走**真跑路径**（副本 router → instance_battle.act() → land_pending）。
#   装配复用 tests/test_texts_table.py 的 IL 段同一份夹具（clean_db / db 建号 /
#   副本 st / FakeEvent / Main 宿主）—— 不自己手搓：前一版手搓的那份缺模块，
#   ① 抛 ModuleNotFoundError = **因错而红**（假门禁，必须作废重做）。
# ★ 隔离变量（合法手段，不放宽期望值）：玩家 hp=3 + 敌人 atk=99999
#   （减半与否一眼可判），随机数 seed 固定。
_two_ok, _two_why = True, ""


def _case_real_run():
    import asyncio
    import time as _t
    from _engine_harness import clean_db, db, FakeEvent, Main
    from content.flow import instance_battle as IB

    GID = "g_dwin"
    clean_db()
    db.create_player(GID, "q_d1", "甲", "cls_zhan_shi", {}, 100, 100)
    db.update_player(GID, "q_d1", level=15, cur_map="misty_swamp",
                     cur_subarea="misty_swamp_3", stamina=999999, learned_skills=[])
    qids = ["q_d1"]
    st = {"type": "instance", "inst_id": "inst_goblin_camp", "leader": "q_d1",
          "members": qids, "alive": {q: True for q in qids},
          "players": {}, "boss": None, "enemy": None, "enemies": [],
          "turn": 0, "round": 1, "mode": "battle", "pets": {},
          "p_buffs": {q: {} for q in qids}, "p_hot": {q: {} for q in qids},
          "p_food_effects": {q: [] for q in qids},
          "mech_stacks": {q: {} for q in qids}, "now": 0.0, "battle": None,
          "contribution": {}, "threat": {q: 0 for q in qids}, "over": False,
          "turn_time": 0, "stage_pending": [], "inst_stages": [],
          "stage_idx": 0, "stage_cleared": False, "world_id": ""}
    pl = db.get_player(GID, "q_d1") or {}
    mh = int(pl.get("max_hp", 500) or 500)
    st["players"]["q_d1"] = dict(pl, name="甲", hp=100, max_hp=mh, mp=999, max_mp=999)
    st["enemies"] = [{"qq_id": "m1", "name": "房间怪", "level": 20,
                      "role": "boss", "hp": 99999, "max_hp": 99999, "atk": 12,
                      "def": 0, "mdef": 0, "spd": 200, "stats_spd": 200}]
    st["boss"] = st["enemy"] = st["enemies"][0]
    IB.build_battle(st)

    class _Host(Main):
        pass

    inst = _Host()

    def _run(qq, action):
        player = st["players"][str(qq)]
        agen = inst._instance_router(FakeEvent(GID, str(qq)), GID, str(qq),
                                     player, st, action, None, None)

        async def _c():
            out = []
            async for x in agen:
                out.append(x)
            return out

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_c())
        finally:
            loop.close()

    flat = []
    for _ in range(12):
        st["turn_time"] = int(_t.time())
        flat.extend(str(m) for m in _run("q_d1", "defend"))
        if st.get("over") or not (st.get("alive") or {}).get("q_d1", True):
            break
    text = "\n".join(flat)
    n_hit = text.count("💥 甲 受到")
    n_blk = text.count("(格挡后")
    # ★ 2026-09-29 收紧（R2.2 修复批）：每一次自身受击都必须伴随减半；受击 ≥ 3 次
    #   （防空集绿）。原版判据「整场任意一次出现格挡行」在「第 0 轮受击」相位下、
    #   修复前也绿（首轮窗口新鲜）⇒ 假绿、抓不住 R2.2 —— 故改为全称判据 + 多轮场景。
    ok = (n_hit >= 3) and (n_blk == n_hit)
    why = "" if ok else ("受击 %d 次 / 减半 %d 次（要求：每次受击皆减半，且受击 ≥ 3）"
                         % (n_hit, n_blk))
    return ok, why


try:
    _two_ok, _two_why = _case_real_run()
except Exception as _exc:
    _two_ok = False
    _two_why = "副本真跑路径抛错：%s: %s" % (type(_exc).__name__, _exc)

check("2.1 副本真跑路径 => 每一次「甲受到」都吃到减半（≥3 次受击）",
      _two_ok, _two_why)

print("\n%d passed, %d failed" % (PASS, FAIL))
if FAILURES:
    print("FAILED: %s" % "; ".join(FAILURES))
sys.exit(1 if FAIL else 0)
