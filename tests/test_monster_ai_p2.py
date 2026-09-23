# -*- coding: utf-8 -*-
"""N5B P2/P3 验证：旧 ai 数据全覆盖 + 导演共存。

P2：MONSTER_MODS 全部带 ai 的 boss → normalize_ai 后 moves 非空（旧数据全覆盖）。
P3：导演（script_hook）+ actor.ai 并存——auto_act 显式（导演换招）压过 AI；
    无 auto_act 时 AI 生效。

跑法：python tests/test_monster_ai_p2.py
"""
import os
import sys
import tempfile
import json
import random

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from _engine_harness import auto_land  # noqa: E402  T15 两段化：落地推进（一次出手 = 落地后返回）
from content.persistence.handles import init_db  # noqa: E402
init_db()

from _engine_harness import C  # noqa: E402
from ext_combat.battle import ai as AI  # noqa: E402
from ext_combat import Battle as B2  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def test_1_all_ai_bosses_normalize():
    print("【1. P2：MONSTER_MODS 全部带 ai 的 boss 可 normalize】")
    mods = C.MONSTER_MODS or {}
    ai_bosses = []
    for bid, bcfg in mods.items():
        if not bid.startswith("b_"):
            continue
        ai = bcfg.get("ai") or {}
        if ai.get("weights"):
            ai_bosses.append(bid)
    check("带 weights 的 boss 数 ≥21", len(ai_bosses) >= 21, f"n={len(ai_bosses)}")
    bad = []
    dangling = []
    for bid in ai_bosses:
        src = dict((mods.get(bid) or {}).get("ai") or {})
        actor = {"ai": src}
        try:
            ai = AI.normalize_ai(actor)
            if not ai or not ai.get("moves"):
                bad.append(bid)
        except Exception as e:
            bad.append(f"{bid}:{e}")
        # 技能悬空检查：所有技能 key（含 ms_*）必须能在怪表/玩家表查获
        # （索引解析 = 怪表 MONSTER_SKILLS → 玩家 skill_by_key——与 _index_skills 同款）
        from content.skills import skill_by_key
        for m in (ai or {}).get("moves") or []:
            sk = (m.get("then") or {}).get("skill")
            if not sk:
                continue
            if sk in (C.MONSTER_SKILLS or {}):
                continue
            try:
                if skill_by_key(sk):
                    continue
            except Exception:
                pass
            dangling.append(f"{bid}:{sk}")
    check("全部 normalize 成功（moves 非空）", not bad, f"bad={bad}")
    check("无悬空技能 key（怪表/玩家表双查）", not dangling,
          f"dangling={sorted(set(dangling))[:10]}")


def test_2_director_and_ai_coexist():
    print("【2. P3：导演 auto_act 压过 AI；无 auto_act 时 AI 生效】")
    src = dict((C.MONSTER_MODS.get("b_goblin_chief") or {}).get("ai") or {})
    mon = {"uid": "e_g", "id": "b_goblin_chief", "name": "咕噜", "role": "boss",
           "is_boss": True, "side": "enemy",
           "hp": 99999, "max_hp": 99999, "atk": 200, "matk": 150, "def": 50,
           "mdef": 50, "spd": 80, "lv": 20, "skills": ["ms_lve_duo_h_ling",
                                                        "ms_lian_zhan",
                                                        "ms_zhao_huan"],
           "effects": {}, "shields": {}, "cooldown": {}, "auto_act": None,
           "ai": dict(src), "act_count": 0, "ct": 0.0}
    b = B2("instance", sides={
        "enemy": [mon],
        "player": [{"uid": "p1", "name": "勇者", "side": "player",
                    "hp": 999999, "max_hp": 999999, "atk": 100, "matk": 100,
                    "def": 50, "mdef": 50, "spd": 50, "lv": 20, "effects": {},
                    "shields": {}, "ct": 0.0}]})
    b._now = 0.0
    random.seed(3)
    # 场景 A：auto_act 显式指定 → 必用显式招（导演换招/连招链语义）
    # 注：物理技能（连斩）伤害日志不带技能名前缀 → 用"玩家掉血=技能真实结算"验证
    mon["auto_act"] = {"act": {"type": "skill", "skill": "ms_lian_zhan"}}
    _pa = b.sides_of("player")[0]
    hp_a0 = int(_pa.get("hp"))
    for _ in range(10):
        auto_land(b, mon)
    hp_a1 = int(_pa.get("hp"))
    check("auto_act 显式招真实结算（连斩 ×1.4 伤害掉血）", hp_a1 < hp_a0,
          f"{hp_a0}->{hp_a1}")
    # 场景 B：清 auto_act → AI weights 生效（掠夺号令权重最高 → 战斗多样）
    mon["auto_act"] = None
    mon["act_count"] = 0
    used_b = set()
    for _ in range(30):
        logs, ended = auto_land(b, mon)
        for l in logs:
            for nm in ("掠夺", "连斩"):
                if nm in str(l):
                    used_b.add(nm)
    check("无 auto_act 时 AI 生效（至少一类技能）", len(used_b) > 0, f"used={used_b}")
    # 场景 C：导演 script_hook 演出刻 skip 优先于 AI
    mon["auto_act"] = None
    st = {"boss_script": AI._new_script_state() if hasattr(AI, "_new_script_state")
          else None}
    # 简化：直接验证 skip 返回时 actor_auto 无伤害（已有 5c P1 覆盖演出刻）——
    # 此处验证决策顺序不因 AI 存在破坏演出刻
    # ★ B8.2 线5：Boss 剧本导演宿主副本已移出仓 → 读**包内端口** content.flow.boss_script
    from content.flow import boss_script as BS
    st["boss_script"] = BS._new_script_state()
    b.script_hook = BS.make_script_hook(st)
    # 压 boss 血到 50%（咕噜 60% 触发阶段 2）→ 下帧导演演出刻 skip
    mon["hp"] = int(mon["max_hp"] * 0.50)
    hp0 = int((b.sides_of("player")[0]).get("hp"))
    logs_c, ended_c = auto_land(b, mon)
    joined = "\n".join(logs_c)
    bs = st.get("boss_script") or {}
    check("导演演出刻触发（phase_count>=1）", int(bs.get("phase_count", 0) or 0) >= 1,
          f"bs={bs.get('phase_count')}")
    check("演出刻 skip 优先于 AI（本帧玩家未被打）",
          int(b.sides_of("player")[0].get("hp")) == hp0,
          f"{hp0}->{int(b.sides_of('player')[0].get('hp'))}")


def test_3_target_hint():
    print("【3. target_hint：AI 战术目标（lowest_hp 残血收割）优先于仇恨，一次性】")
    from content.flow.instance_battle import _instance_target_picker
    st = {"threat": {"p_a": 0, "p_b": 99999}, "taunt_target": ""}
    pa = {"uid": "p_a", "qq_id": "p_a", "name": "残血甲", "side": "player",
          "hp": 1000, "max_hp": 5000, "atk": 100, "matk": 100, "def": 50,
          "mdef": 50, "spd": 50, "lv": 20, "effects": {}, "shields": {},
          "ct": 0.0}
    pb = {"uid": "p_b", "qq_id": "p_b", "name": "满血乙", "side": "player",
          "hp": 5000, "max_hp": 5000, "atk": 100, "matk": 100, "def": 50,
          "mdef": 50, "spd": 50, "lv": 20, "effects": {}, "shields": {},
          "ct": 0.0}
    mon = {"uid": "e_m", "id": "b_goblin_chief", "name": "咕噜", "side": "enemy",
           "role": "boss", "is_boss": True, "hp": 99999, "max_hp": 99999,
           "atk": 300, "matk": 150, "def": 50, "mdef": 50, "spd": 80, "lv": 20,
           "skills": ["ms_lian_zhan"], "effects": {}, "shields": {},
           "cooldown": {}, "auto_act": None,
           "ai": {"select": "priority", "moves": [
               {"when": {}, "then": {"type": "skill", "skill": "ms_lian_zhan",
                                     "target_hint": "lowest_hp"}}]},
           "act_count": 0, "ct": 0.0}
    b = B2("instance", sides={"enemy": [mon], "player": [pa, pb]})
    b.target_picker = _instance_target_picker(st)
    b._now = 0.0
    # A 残血（20%）→ lowest_hp 收割 A（无视 B 仇恨最高）
    for _ in range(6):
        auto_land(b, mon)
    check("残血 A 被收割（掉血）", int(pa.get("hp")) < 1000, f"A={pa.get('hp')}")
    # A 1000 血 3 刀死 → 死后怪才打 B；收割语义 = A 被打得比 B 更狠（比例更低）
    ra = int(pa.get("hp")) / max(1, int(pa.get("max_hp", 1)))
    rb = int(pb.get("hp")) / max(1, int(pb.get("max_hp", 1)))
    check("A 受创比例 > B（收割优先 A）", ra < rb, f"A={ra:.2f} B={rb:.2f}")
    # hint 一次性：actor_auto 尾部清 _target_hint
    check("hint 消费即弃", mon.get("_target_hint") is None,
          str(mon.get("_target_hint")))
    # 无 hint 的普通 AI → 回落仇恨（B 仇恨 99999 → 打 B）
    mon["ai"]["moves"][0]["then"].pop("target_hint", None)
    mon["act_count"] = 0
    hp_a0 = int(pa.get("hp"))
    hp_b0 = int(pb.get("hp"))
    for _ in range(6):
        auto_land(b, mon)
    check("无 hint → 仇恨系统打 B（B 掉血）", int(pb.get("hp")) < hp_b0,
          f"B {hp_b0}->{pb.get('hp')}")
    check("A 不再被优先打", int(pa.get("hp")) >= hp_a0 - 0,
          f"A {hp_a0}->{pa.get('hp')}")


def main():
    print("N5B P2/P3 通用怪 AI：数据全覆盖 + 导演共存 + target_hint")
    test_1_all_ai_bosses_normalize()
    test_2_director_and_ai_coexist()
    test_3_target_hint()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
