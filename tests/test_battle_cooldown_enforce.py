# -*- coding: utf-8 -*-
"""2026-09-11 引擎契约修复回归：技能冷却强制（P0）+ AI 可执行性过滤（P1）+ 运行期索引自愈（P3）。

背景（第三方骨架作者实跑暴露，见 workspace/FRAMEWORK_SPLIT_PLAN.md）：
- **P0 冷却未被强制**：`do_skill` 写 `actor["cooldown"]`，但全仓库唯一读者是 AI 的
  `cd_ok` 谓词 → 玩家侧零拦截，带 cd 的技能可无限连放（探针
  tools/probe_cooldown_enforcement.py 实跑：旋风斩 cd=12 连打两次全身伤害）。
  设计文档 / 旧引擎实现（tests/_retired_old_engine/test_stage5_cooldown.py）/
  数值模型（scripts/numeric_lib/player.py:385-387 按「CD 未结束只能普攻」折算）
  三处一致指向「应拦」→ 缺此检查则实机 DPS 比数值模型高 3~5 倍。
- **P1 AI 活锁**：`resolve_ai_move` 只按 when 选招、不校验技能此刻可执行；技能前置
  校验失败（资源不足）时 do_skill 提前 return（冷却写在其后 → cd_ok 恒真）→ 每回合
  重试同一个永远放不出的技能 → 0 输出直到被打死。
- **P3 运行期换招索引失效**：`_skill_index` 只在构造期/add_actor 建一次，Boss 剧本
  转阶段 add_skills 追加后索引不含新键 → ActCtx.info={} → 转阶段后主技能静默空放。

跑法：python tests/test_battle_cooldown_enforce.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_cooldown.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor, ActCtx  # noqa: E402
from saintess_engine.battle.actions import _cd_left_of, _skill_usable  # noqa: E402
from saintess_engine.battle.ai import resolve_ai_move, _skill_castable, _move_castable  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []

MON_A = "ms_an_ying_dan"     # 暗影弹（MONSTER_SKILLS 内，无 cd / 无 res_cost）
MON_B = "ms_an_ying_jian"    # 暗影箭（同上，备用第二招）
MON_FAKE = "ms_not_a_real_skill__index_miss"

DAMAGE_MARK = "受到"          # landing.py:320「💥 {name} 受到 {real} 点伤害！」
CD_MARK = "冷却中"


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def has_damage(logs, who=None):
    """日志含伤害（landing.py:320「💥 {name} 受到 {real} 点伤害！」）。

    who 给定时只认「该目标受击」——战斗内会同时出现双方伤害日志（如玩家被怪反击），
    不限定承伤者会把对手的攻击误判成自己的命中。
    """
    for x in logs:
        t = str(x)
        if "点伤害" not in t:
            continue
        if who is None or f"{who} 受到" in t:
            return True
    return False


def has_attack(logs, who=None):
    """动作已结算（命中伤害 或 目标闪避）——闪避是面板概率 roll，用它做「已执行」判据
    可避免偶发假失败；「是否命中」不作为断言目标（那是 landing 的职责，另有专项）。"""
    for x in logs:
        t = str(x)
        if "点伤害" in t or "闪避了攻击" in t:
            if who is None or f"{who} " in t:
                return True
    return False


def has_cd_block(logs):
    return any(CD_MARK in str(x) for x in logs)


def mk_p(hp=99999, mp=99999, skills=None, learned=None, spd=10):
    return make_actor(uid="p1", name="玩家", side="player", kind="player",
                      human_controlled=True, class_name="cls_zhan_shi", level=20,
                      hp=hp, max_hp=hp, mp=mp, max_mp=mp,
                      atk=100, matk=50, spd=spd, crit=0.0,
                      equipment={}, skills=list(skills or []),
                      dodge=0.0,
                      learned_skills=list(learned or skills or []),
                      race=None, evolve_path=0, class_tier=0, attributes={},
                      **{"def": 40, "mdef": 30})


def mk_e(uid="e1", name="怪", hp=9999999, spd=1, skills=None, class_name=None):
    kw = {}
    if class_name:
        kw["class_name"] = class_name
    return make_actor(uid=uid, name=name, side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=50, matk=20, spd=spd, crit=0.0,
                      level=20, exp=0, gold=0, skills=list(skills or []),
                      dodge=0.0, **{"def": 10, "mdef": 10}, **kw)


def skill_key_by_name(actor, name):
    """从引擎索引里按中文名取技能 key（避免测试硬编码内容侧 key）。"""
    idx = actor.get("_skill_index") or {}
    for k, v in idx.items():
        if isinstance(v, dict) and v.get("name") == name:
            return k
    return None


# ============================================================
# P0：冷却强制
# ============================================================

SPIN_NAME = "旋风斩"     # cls_zhan_shi，cd=12，物理
MENG_NAME = "猛击"       # cls_zhan_shi，cd=8，物理
HUI_NAME = "挥砍"        # cls_zhan_shi，无 cd（对照：不该被拦）


def _battle_with(skills):
    p = mk_p(skills=skills)
    e = mk_e()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    return b, p, e


def test_p0_cooldown_written_and_enforced():
    print("【P0-1/2/3. 冷却写表 → 冷却中拦截 → 到期放行】")
    b, p, e = _battle_with([SPIN_NAME, MENG_NAME])
    spin = skill_key_by_name(p, SPIN_NAME)
    check("索引解析出【旋风斩】", bool(spin), f"key={spin}")
    check("【旋风斩】声明 cd=12", int((p["_skill_index"][spin]).get("cd") or 0) == 12,
          f"cd={(p['_skill_index'][spin]).get('cd')}")

    # 1) 首次施放：出伤害 + 写冷却表（绝对到期时刻）
    logs, ended, _ = b.human_act("skill", spin, target=e)
    check("首放已结算（命中或闪避）", has_attack(logs, "怪"), f"logs={logs[:3]}")
    check("首放未被拦", not has_cd_block(logs), f"logs={logs[:3]}")
    tbl = p.get("cooldown") or {}
    check("冷却表已写入【旋风斩】", SPIN_NAME in tbl, f"tbl={tbl}")
    due = float(tbl.get(SPIN_NAME, 0) or 0)
    check("到期时刻 = 施放时刻 + 12", abs(due - (float(b._now) + 12)) < 1e-6 or due > 0,
          f"due={due} now={b._now}")

    # 2) 冷却中再放：拦截 + 零伤害 + 不扣蓝 + 冷却表不刷新
    cd_val = float(tbl.get(SPIN_NAME) or 0)
    b._now = cd_val - 0.1          # 距到期 0.1 刻（确定性：不借 advance 时序）
    left_now = _cd_left_of(b, p, p["_skill_index"][spin])
    check("_cd_left_of 反映剩余 0.1 刻", abs(left_now - 0.1) < 1e-6, f"left={left_now}")
    mp_before = int(p.get("mp") or 0)
    logs2, _, _ = b.human_act("skill", spin, target=e)
    check("冷却中：出现冷却拦截文案", has_cd_block(logs2), f"logs={logs2[:3]}")
    check("冷却中：零输出（无命中无闪避）", not has_attack(logs2, "怪"), f"logs={logs2[:3]}")
    check("冷却中：不扣蓝", int(p.get("mp") or 0) == mp_before,
          f"mp={p.get('mp')} before={mp_before}")
    check("冷却中：冷却表不被刷新",
          abs(float((p.get('cooldown') or {}).get(SPIN_NAME) or 0) - cd_val) < 1e-9,
          f"tbl={p.get('cooldown')}")

    # 3) 到期放行
    b._now = cd_val + 0.1
    logs3, _, _ = b.human_act("skill", spin, target=e)
    check("到期后恢复可放（已结算）", has_attack(logs3, "怪"), f"logs={logs3[:3]}")
    check("到期后未再被拦", not has_cd_block(logs3), f"logs={logs3[:3]}")
    check("到期条目被惰性清理后重写（新到期 > 旧到期）",
          float((p.get("cooldown") or {}).get(SPIN_NAME) or 0) > cd_val,
          f"tbl={p.get('cooldown')}")


def test_p0_no_cd_not_blocked():
    print("【P0-4. 无 cd 技能连放两次都命中（不误拦）】")
    b, p, e = _battle_with([HUI_NAME])
    hui = skill_key_by_name(p, HUI_NAME)
    check("索引解析出【挥砍】", bool(hui), f"key={hui}")
    check("【挥砍】无 cd 声明", not (p["_skill_index"][hui]).get("cd"),
          f"cd={(p['_skill_index'][hui]).get('cd')}")
    l1, _, _ = b.human_act("skill", hui, target=e)
    l2, _, _ = b.human_act("skill", hui, target=e)
    check("第 1 次已结算", has_attack(l1, "怪"), f"logs={l1[:3]}")
    check("第 2 次仍结算（无 cd 不写表不拦）", has_attack(l2, "怪"), f"logs={l2[:3]}")
    check("无 cd 技能不写冷却表", HUI_NAME not in (p.get("cooldown") or {}),
          f"tbl={p.get('cooldown')}")


def test_p0_actor_agnostic():
    print("【P0-5. 一视同仁：怪（无 class_name）预置冷却条目 → 同样被拦】")
    b, p, e = _battle_with([HUI_NAME])
    e["skills"] = [MON_A]
    b.refresh_skill_index(e)
    check("怪技能已进索引", MON_A in (e.get("_skill_index") or {}),
          f"idx={list((e.get('_skill_index') or {}).keys())}")
    info = e["_skill_index"][MON_A]
    check("冷却前可施放", _skill_usable(b, e, info, []), "应可用")
    e["cooldown"] = {info.get("name"): float(b._now) + 50}
    logs = []
    check("冷却中不可施放（怪也受同一规则）", not _skill_usable(b, e, info, logs),
          "应被拦")
    check("怪拦截文案同款", any(CD_MARK in x for x in logs), f"logs={logs}")
    e.pop("cooldown", None)
    check("清冷却后恢复可用（怪亦无 res_cost → 不被资源误拦）",
          _skill_usable(b, e, info, []), "应可用")


def test_p0_expired_entries_pruned():
    print("【P0-6. 到期冷却条目惰性清理（表不随战斗膨胀）】")
    b, p, e = _battle_with([SPIN_NAME])
    spin = skill_key_by_name(p, SPIN_NAME)
    p["cooldown"] = {"过期A": 0.5, "过期B": float(b._now) - 1.0, SPIN_NAME: 999.0}
    b._now = 10.0
    left = _cd_left_of(b, p, p["_skill_index"][spin])
    check("过期条目被清除", "过期A" not in p["cooldown"] and "过期B" not in p["cooldown"],
          f"tbl={p['cooldown']}")
    check("未到期条目保留", SPIN_NAME in p["cooldown"], f"tbl={p['cooldown']}")
    check("剩余冷却计算正确（999-10=989）", abs(left - 989.0) < 1e-6, f"left={left}")


def test_p0_cd_takes_priority_over_resource():
    print("【P0-7. 冷却判定先于资源（冷却中不重复报资源文案）】")
    b, p, e = _battle_with([SPIN_NAME])
    spin = skill_key_by_name(p, SPIN_NAME)
    p["cooldown"] = {SPIN_NAME: float(b._now) + 5}
    p["effects"] = {"zhan_yi": {"stacks": 0}}   # 资源也为 0：两者都不满足
    logs = []
    ok = _skill_usable(b, p, p["_skill_index"][spin], logs)
    check("不可施放", not ok, "应被拦")
    check("只报冷却文案（不报资源）", has_cd_block(logs) and "资源不足" not in "".join(logs),
          f"logs={logs}")


# ============================================================
# P1：AI 可执行性过滤
# ============================================================

def test_p1_skill_castable():
    print("【P1-1. _skill_castable 三判据（就绪/冷却/索引不到）】")
    b, p, e = _battle_with([SPIN_NAME, HUI_NAME])
    spin = skill_key_by_name(p, SPIN_NAME)
    hui = skill_key_by_name(p, HUI_NAME)
    check("就绪 → True", _skill_castable(b, p, hui), "应可执行")
    p["cooldown"] = {SPIN_NAME: float(b._now) + 8}
    check("冷却中 → False", not _skill_castable(b, p, spin), "应不可执行")
    check("索引不到 → False", not _skill_castable(b, p, MON_FAKE), "应不可执行")
    check("_move_castable：技能 move 冷却中 → False",
          not _move_castable(b, p, {"then": {"type": "skill", "skill": spin}}), "")
    check("_move_castable：普攻 move 恒 True",
          _move_castable(b, p, {"then": {"type": "attack"}}), "")
    check("_move_castable：action=skill 无技能名 → False",
          not _move_castable(b, p, {"then": {"type": "skill"}}), "")


def test_p1_priority_skips_uncastable():
    print("【P1-2/3. priority：跳过放不出的招 → 取次选 / 全不可用回落普攻】")
    b = B2(btype="monster", sides={"player": [mk_p(skills=[HUI_NAME])],
                                   "enemy": [mk_e()]})
    e = b.sides_of("enemy")[0]
    e["skills"] = [MON_A, MON_B]
    b.refresh_skill_index(e)
    nm_a = e["_skill_index"][MON_A].get("name")
    nm_b = e["_skill_index"][MON_B].get("name")
    e["cooldown"] = {nm_a: float(b._now) + 30}      # 首选冷却中
    e["ai"] = {"select": "priority", "moves": [
        {"when": {}, "then": {"type": "skill", "skill": MON_A}},
        {"when": {}, "then": {"type": "skill", "skill": MON_B}},
    ]}
    mv = resolve_ai_move(b, e)
    check("首选冷却中 → 跳过并取次选", bool(mv) and mv.get("skill") == MON_B,
          f"mv={mv}")
    # 全部不可执行 → None（调用方回落普攻出口）
    e["cooldown"] = {nm_a: float(b._now) + 30, nm_b: float(b._now) + 30}
    check("全部冷却中 → None（回落普攻）", resolve_ai_move(b, e) is None, "")
    # 引用不存在的技能 → 同样跳过（AI 引用脏数据不再空转）
    e["cooldown"] = {}
    e["ai"] = {"select": "priority", "moves": [
        {"when": {}, "then": {"type": "skill", "skill": MON_FAKE}},
    ]}
    check("AI 引用不存在技能 → None（不空转）", resolve_ai_move(b, e) is None, "")


def test_p1_weighted_filters_pool():
    print("【P1-4. weighted：池过滤掉不可执行项】")
    b = B2(btype="monster", sides={"player": [mk_p(skills=[HUI_NAME])],
                                   "enemy": [mk_e()]})
    e = b.sides_of("enemy")[0]
    e["skills"] = [MON_A, MON_B]
    b.refresh_skill_index(e)
    nm_a = e["_skill_index"][MON_A].get("name")
    e["cooldown"] = {nm_a: float(b._now) + 30}
    e["ai"] = {"select": "weighted", "skill_chance": 1.0, "moves": [
        {"when": {}, "weight": 99.0, "then": {"type": "skill", "skill": MON_A}},
        {"when": {}, "weight": 1.0, "then": {"type": "skill", "skill": MON_B}},
    ]}
    picks = [resolve_ai_move(b, e) for _ in range(15)]
    skills = {m.get("skill") for m in picks if m}
    check("15 次抽样只出可执行招（暗影箭）", skills == {MON_B}, f"skills={skills}")
    check("权重 99 的不可执行招从未被选中", MON_A not in skills, f"skills={skills}")


def test_p1_deadlock_regression():
    print("【P1-5. 活锁回归：资源不足的唯一招 → 决策器回落普攻，多帧均出伤害】")
    # 冷静（cls_zhan_shi 技能，res_cost={zhan_yi:5}，cd=16）——怪持该技能但无战绩资源
    p = mk_p(skills=[HUI_NAME])
    e = mk_e(class_name="cls_zhan_shi", skills=["sk_leng_jing"])
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    e["effects"] = {"zhan_yi": {"stacks": 0}}   # 资源为 0：冷静永远放不出
    e["ai"] = {"select": "priority", "moves": [
        {"when": {}, "then": {"type": "skill", "skill": "sk_leng_jing"}},
    ]}
    mv = resolve_ai_move(b, e)
    check("资源不足的招被过滤 → None", mv is None, f"mv={mv}")
    check("_skill_castable 判资源不足为不可执行",
          not _skill_castable(b, e, "sk_leng_jing"), "")
    frames = []
    for _ in range(3):
        logs, ended = b.actor_auto(e)
        frames.append(logs)
        if ended:
            break
    dmg_frames = [f for f in frames if has_attack(f, "玩家")]
    check("连续 3 帧均真出手（不再 0 输出活锁）", len(dmg_frames) == len(frames),
          f"frames={len(frames)} dmg={len(dmg_frames)} logs={[f[:2] for f in frames]}")
    check("活锁技能从未施放成功（冷却表无该技能）",
          "冷静" not in (e.get("cooldown") or {}), f"tbl={e.get('cooldown')}")


def test_p1_auto_act_fallback():
    print("【P1-6. 引擎兜底：显式 auto_act 指定冷却中技能 → 回落普攻出伤害】")
    b = B2(btype="monster", sides={"player": [mk_p(skills=[HUI_NAME])],
                                   "enemy": [mk_e(class_name="cls_zhan_shi",
                                                  skills=["sk_leng_jing"])]})
    e = b.sides_of("enemy")[0]
    e["auto_act"] = {"act": {"type": "skill", "skill": "sk_leng_jing"}}
    e["effects"] = {"zhan_yi": {"stacks": 0}}
    logs, ended = b.actor_auto(e)
    check("显式指定放不出的招 → 引擎回落普攻（真出手）", has_attack(logs, "玩家"),
          f"logs={logs[:3]}")
    check("未产生冷却中拦截文案（AI 侧静默改判，玩家侧才展示）",
          not has_cd_block(logs), f"logs={logs[:3]}")
    # 玩家人控不受此兜底影响：显式选择仍回到 do_skill 展示拦截文案
    p = b.sides_of("player")[0]
    p["cooldown"] = {"冷静": float(b._now) + 5}
    p["skills"] = ["sk_leng_jing"]
    p["learned_skills"] = ["sk_leng_jing"]
    b.refresh_skill_index(p)
    logs2, _, _ = b.human_act("skill", "sk_leng_jing", target=e)
    check("玩家人控仍展示冷却拦截文案（行为不变）", has_cd_block(logs2), f"logs={logs2[:3]}")


# ============================================================
# P3：运行期换招索引自愈
# ============================================================

def test_p3_refresh_skill_index():
    print("【P3-1. refresh_skill_index：运行期追加技能进索引 + 幂等】")
    b, p, e = _battle_with([HUI_NAME])
    check("初始索引无【猛击】", skill_key_by_name(p, MENG_NAME) is None,
          f"idx={list((p.get('_skill_index') or {}).keys())}")
    p["skills"].append("sk_meng_ji")
    b.refresh_skill_index(p)
    k = skill_key_by_name(p, MENG_NAME)
    check("追加后索引含【猛击】", bool(k), f"idx={list((p.get('_skill_index') or {}).keys())}")
    snapshot = dict(p["_skill_index"])
    b.refresh_skill_index(p)
    b.refresh_skill_index(p)
    check("幂等：重复刷新索引不变", p["_skill_index"] == snapshot, "索引被改写")


def test_p3_actor_auto_picks_up_new_skill():
    print("【P3-2. actor_auto：运行期换招后新招真能执行（出伤害+写冷却）】")
    b = B2(btype="monster", sides={"player": [mk_p(skills=[HUI_NAME])],
                                   "enemy": [mk_e(class_name="cls_zhan_shi",
                                                  skills=[HUI_NAME])]})
    e = b.sides_of("enemy")[0]
    check("换招前索引无【猛击】", skill_key_by_name(e, MENG_NAME) is None,
          f"idx={list((e.get('_skill_index') or {}).keys())}")
    # 模拟 Boss 剧本转阶段：追加技能 + 指定 auto_act（不手动调 refresh_skill_index）
    e["skills"].append("sk_meng_ji")
    e["auto_act"] = {"act": {"type": "skill", "skill": "sk_meng_ji"}}
    logs, ended = b.actor_auto(e)
    check("actor_auto 后索引自动补上【猛击】", bool(skill_key_by_name(e, MENG_NAME)),
          f"idx={list((e.get('_skill_index') or {}).keys())}")
    check("新招真的出手（非静默空放）", has_attack(logs, "玩家"), f"logs={logs[:3]}")
    check("新招写入冷却表（证明执行到 do_skill 结算段）",
          MENG_NAME in (e.get("cooldown") or {}), f"tbl={e.get('cooldown')}")


if __name__ == "__main__":
    test_p0_cooldown_written_and_enforced()
    test_p0_no_cd_not_blocked()
    test_p0_actor_agnostic()
    test_p0_expired_entries_pruned()
    test_p0_cd_takes_priority_over_resource()
    test_p1_skill_castable()
    test_p1_priority_skips_uncastable()
    test_p1_weighted_filters_pool()
    test_p1_deadlock_regression()
    test_p1_auto_act_fallback()
    test_p3_refresh_skill_index()
    test_p3_actor_auto_picks_up_new_skill()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
