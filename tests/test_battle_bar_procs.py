# -*- coding: utf-8 -*-
"""v181 破绽接线验收：content/mech/bar_procs.py（挂敌身条注入 → 触发 → 跳过；★ B18-REPOINT
后宿主同名壳已退役，本测试的观测对象 = 包内实现本体）+
时间制容器（core/battle_bars：effects["bar:*"] / 连续衰减 / 免疫窗口时刻制）。

覆盖：装配（学什么挂什么）/ 命中注入（含多段 per_hit）/ 阈值触发 / 触发落地 mode=skip /
      跳过消费 / 时钟推进结算（time_advance）/ 免疫窗口（期内不积蓄、到期可再触发）/
      阈值递增可多次触发（条上限 125）/ 反震（on_taken 反弹 + 反推条）/
      阶段保留（phase → 积蓄保留 50%，进度遗产）

跑法：python tests/test_battle_bar_procs.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_bar.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle.actors import ActCtx  # noqa: E402
from ext_combat.battle.effect_triggers import fire  # noqa: E402
from content.mech import class_mech as CMP  # ★ P5C-REPOINT：直取包内真源
from content import skills as _SK  # noqa: E402
from ext_combat.gauge import bar_effect_key, bar_gain as _bg# noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_player(cls="cls_wu_seng", learned=None, hp=2000):
    return make_actor(uid="p1", name="勇者", side="player", kind="player",
                      human_controlled=True, class_name=cls, level=20,
                      hp=hp, max_hp=hp, mp=200, max_mp=200,
                      atk=100, matk=80, spd=15, crit=0.05,
                      equipment={}, skills=[], learned_skills=list(learned or []),
                      race=None, evolve_path=0, class_tier=0, attributes={},
                      **{"def": 40, "mdef": 30})


def mk_enemy(hp=50000, atk=1):
    e = make_actor(uid="e1", name="木桩怪", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=atk, matk=1, spd=5, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 10, "mdef": 10})
    e["effects"] = {}
    return e


def new_battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


def bar_of(actor):
    return (actor.get("effects") or {}).get(bar_effect_key("shaken")) or {}


def _bar_trigs(actor):
    return [x for x in ((actor.get("triggers") or {}).get("skill_hit") or [])
            if isinstance(x, dict) and (x.get("type") or x.get("action")) == "bar_gain"]


def _settle_trigs(actor):
    return [x for x in ((actor.get("triggers") or {}).get("time_advance") or [])
            if isinstance(x, dict) and (x.get("type") or x.get("action")) == "bar_time_settle"]


def _phase_trigs(actor):
    return [x for x in ((actor.get("triggers") or {}).get("phase") or [])
            if isinstance(x, dict) and (x.get("type") or x.get("action")) == "bar_phase_preserve"]


def test_install():
    print("【1. 装配：学什么挂什么（BAR_INJECT_FIELDS 扫描）】")
    p = mk_player(cls="cls_wu_seng", learned=["sk_gang_quan"])
    CMP.apply_class_mech(p)
    t = _bar_trigs(p)
    check("拳师（学推条技能）挂 bar_gain/shaken",
          any(x.get("key") == "shaken" and x.get("field") == "shaken_gain" for x in t),
          f"trig={t}")
    check("时钟结算订阅不在装配期（宿主首次挂条时才自安装）", not _settle_trigs(p),
          f"settle={_settle_trigs(p)}")
    # 反向：非拳师职业（不带 shaken_gain 字段的技能）不挂
    zhan_id = list(_SK.PLAYER_SKILLS["cls_zhan_shi"].keys())[0]
    p2 = mk_player(cls="cls_zhan_shi", learned=[zhan_id])
    CMP.apply_class_mech(p2)
    check("战士不挂 bar_gain（零噪音）", not _bar_trigs(p2), f"trig={_bar_trigs(p2)}")
    check("战士也不挂时钟结算订阅", not _settle_trigs(p2), f"settle={_settle_trigs(p2)}")
    # 反向：拳师但没学任何推条技能 → 不挂
    p3 = mk_player(cls="cls_wu_seng", learned=[])
    CMP.apply_class_mech(p3)
    check("拳师未学推条技能不挂", not _bar_trigs(p3), f"trig={_bar_trigs(p3)}")
    # 幂等：重复装配不重复挂
    CMP.apply_class_mech(p)
    check("重复装配幂等（只 1 条）", len(_bar_trigs(p)) == 1, f"n={len(_bar_trigs(p))}")


def test_inject_on_hit():
    print("【2. 命中注入：skill_hit → bar_gain（钢拳 shaken_gain=5）】")
    p = mk_player(cls="cls_wu_seng", learned=["sk_gang_quan"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, e)
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 5}}, logs)
    bs = bar_of(e)
    check("敌方破绽条 val=5（effects[bar:shaken]）", bs.get("val") == 5, f"bs={bs}")
    check("条带结算基准 _at / 免疫 0", "_at" in bs and float(bs.get("immune_until", -1)) == 0.0,
          f"bs={bs}")
    check("旧 buffs 容器不再被创建", not (e.get("buffs") or {}), f"buffs={e.get('buffs')}")
    check("自安装时钟结算订阅", len(_settle_trigs(e)) == 1, f"settle={_settle_trigs(e)}")
    # 无字段技能 → 不注入（无字段=不启用）
    logs2 = []
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"name": "无推条技能"}}, logs2)
    check("无 shaken_gain 字段不注入", bar_of(e).get("val") == 5, f"val={bar_of(e).get('val')}")


def test_threshold_trigger():
    print("【3. 阈值触发：满 50 → 触发（val 清 0 / 阈值 ×1.35 / 免疫 2 刻）】")
    p = mk_player(cls="cls_wu_seng", learned=["sk_gang_quan"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, e)
    logs = []
    _bg(e, "shaken", 45, logs, now=0.0)          # 垫到 45
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 5}}, logs)
    bs = bar_of(e)
    check("触发后 val 清零", float(bs.get("val", -1)) == 0.0, f"bs={bs}")
    check("trigger_count=1", bs.get("trigger_count") == 1, f"bs={bs}")
    check("阈值 50 → 67（×1.35 取整）", bs.get("threshold") == 67, f"thr={bs.get('threshold')}")
    check("免疫窗口 = 触发刻 + 2 刻（immune_until=2.0）",
          abs(float(bs.get("immune_until", -1)) - 2.0) < 1e-9, f"bs={bs}")
    check("落地 mode=skip 控制",
          ((e.get("effects") or {}).get("bar_skip:shaken") or {}).get("mode") == "skip",
          f"eff={e.get('effects')}")
    # 免疫期内：注入被忽略（不积蓄）
    logs2 = []
    _bg(e, "shaken", 30, logs2, now=1.0)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 15}}, logs2)
    check("免疫期内注入忽略（val 仍 0）", float(bar_of(e).get("val", -1)) == 0.0,
          f"bs={bar_of(e)}")
    check("免疫期内不重复触发", bar_of(e).get("trigger_count") == 1, f"bs={bar_of(e)}")
    # 免疫到期后：可再推、可再触发（阈值递增不封死——条上限 125 容得下 67/90/122）
    b._now = 3.0
    logs3 = []
    _bg(e, "shaken", 67, logs3, now=3.0)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 5}}, logs3)
    bs3 = bar_of(e)
    check("免疫到期后可再次触发（trigger_count=2）", bs3.get("trigger_count") == 2, f"bs={bs3}")
    check("第二次阈值 67 → 90", bs3.get("threshold") == 90, f"thr={bs3.get('threshold')}")
    check("第二次免疫窗口 = 3.0 + 2 = 5.0",
          abs(float(bs3.get("immune_until", -1)) - 5.0) < 1e-9, f"bs={bs3}")
    # 第三次：90 → 121（floor(90×1.35)=121）→ 再 ×1.35 = 163 → 封顶 125
    b._now = 6.0
    logs4 = []
    _bg(e, "shaken", 90, logs4, now=6.0)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 5}}, logs4)
    check("第三次阈值 90 → 121", bar_of(e).get("threshold") == 121, f"bs={bar_of(e)}")
    b._now = 9.0
    logs5 = []
    _bg(e, "shaken", 121, logs5, now=9.0)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 5}}, logs5)
    check("第四次阈值封顶 125（121×1.35=163 → 125）", bar_of(e).get("threshold") == 125,
          f"bs={bar_of(e)}")
    check("条上限 125 容得下封顶阈值（可继续触发）", bar_of(e).get("trigger_count") == 4,
          f"bs={bar_of(e)}")


def test_skip_consumed():
    print("【4. 跳过消费：敌方行动被 mode=skip 拦截并消费清条】")
    p = mk_player(cls="cls_wu_seng", learned=["sk_gang_quan"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, e)
    logs = []
    _bg(e, "shaken", 49, logs, now=0.0)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 5}}, logs)
    check("触发已挂 skip", "bar_skip:shaken" in (e.get("effects") or {}), f"eff={e.get('effects')}")
    e_hp0 = e["hp"]
    ctx = ActCtx(caster=e, action="attack", target=p)
    alogs, _ended = b.act(ctx)
    joined = " ".join(str(x) for x in alogs)
    check("敌方行动被跳过", ("控制" in joined) or ("震慑" in joined), f"logs={alogs}")
    check("skip 条目消费即清", "bar_skip:shaken" not in (e.get("effects") or {}),
          f"eff={e.get('effects')}")
    check("跳过时未对玩家造成伤害", p["hp"] == p["max_hp"], f"p_hp={p['hp']}")
    check("跳过不结算敌方普攻（双方未变血）", e_hp0 == e["hp"], f"e_hp={e['hp']}")


def test_time_decay():
    print("【5. 时间衰减：每刻 −1.7 连续结算（小数累计，不取整）】")
    p = mk_player(cls="cls_wu_seng", learned=["sk_gang_quan"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, e)
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 10}}, logs)
    check("注入后 val=10", float(bar_of(e).get("val", 0)) == 10.0, f"bs={bar_of(e)}")
    # 时钟推进 3.0 刻 → 衰减 5.1 → val 4.9（旧实现是「每个宿主行动 −1」）
    b._now = 3.0
    fire(b, "time_advance", {"dt": 3.0, "now": 3.0}, logs)
    v = float(bar_of(e).get("val", -1))
    check("推进 3 刻后 val = 10 − 3×1.7 = 4.9（小数，不是整数）",
          abs(v - 4.9) < 1e-6, f"val={v}")
    check("结算基准 _at 更新到当刻", abs(float(bar_of(e).get("_at", -1)) - 3.0) < 1e-9,
          f"bs={bar_of(e)}")
    # 再推进 5 刻 → 4.9 − 8.5 < 0 → 夹到 0
    b._now = 8.0
    fire(b, "time_advance", {"dt": 5.0, "now": 8.0}, logs)
    check("衰减夹 0（不为负）", float(bar_of(e).get("val", -1)) == 0.0, f"bs={bar_of(e)}")
    # 真实战斗推进（auto_run 内部走 _advance_time → 广播 time_advance）
    # 用真实注入路径创建条（bar_gain 装配动作会自安装时钟订阅）
    p2 = mk_player(cls="cls_wu_seng", learned=["sk_gang_quan"])
    CMP.apply_class_mech(p2)
    e2 = mk_enemy(hp=100)
    b2 = new_battle(p2, e2)
    fire(b2, "skill_hit", {"actor": p2, "target": e2,
                           "info": {"shaken_gain": 30}}, [])
    v0 = float(bar_of(e2).get("val", 0) or 0)
    check("注入后 val=30 且已装时钟订阅", v0 == 30.0 and len(_settle_trigs(e2)) == 1,
          f"val={v0} settle={_settle_trigs(e2)}")
    b2.auto_run([], max_steps=200)
    check("真实战斗推进后条被结算（val 减小或已触发清零）",
          float(bar_of(e2).get("val", 30.0) or 0) < 30.0 or bar_of(e2).get("trigger_count", 0) > 0,
          f"bs={bar_of(e2)} now={b2._now}")


def test_per_hit_multisegment():
    print("【6. 多段推条（v153 §六「多段 +3~+5/段」）：字段值 ×hits 合并注入】")
    p = mk_player(cls="cls_wu_seng", learned=["sk_gang_quan"])
    CMP.apply_class_mech(p)
    t = _bar_trigs(p)
    check("装配条目带 per_hit 声明", bool(t and t[0].get("per_hit")), f"trig={t}")
    e = mk_enemy()
    b = new_battle(p, e)
    logs = []
    # 连环拳口径：4/段 × 4 段 = 16
    fire(b, "skill_hit", {"actor": p, "target": e,
                          "info": {"shaken_gain": 4, "hits": 4}}, logs)
    check("4/段 ×4 = 16", bar_of(e).get("val") == 16, f"bs={bar_of(e)}")
    # 单段技能不受影响：碎颅势口径 15 ×1 = 15
    e2 = mk_enemy()
    b2 = new_battle(p, e2)
    logs2 = []
    fire(b2, "skill_hit", {"actor": p, "target": e2,
                           "info": {"shaken_gain": 15}}, logs2)
    check("单段 15 ×1 = 15", bar_of(e2).get("val") == 15, f"bs={bar_of(e2)}")
    # 多段满阈值触发：垫 45 + 5/段×3 = 触发
    e3 = mk_enemy()
    b3 = new_battle(p, e3)
    logs3 = []
    _bg(e3, "shaken", 45, logs3, now=0.0)
    fire(b3, "skill_hit", {"actor": p, "target": e3,
                           "info": {"shaken_gain": 5, "hits": 3}}, logs3)
    check("45 + 5/段×3 = 触发（val 清 0）",
          float(bar_of(e3).get("val", -1)) == 0.0
          and bar_of(e3).get("trigger_count") == 1, f"bs={bar_of(e3)}")


def test_no_bar_no_op():
    print("【7. 未挂条单位零行为（无字段=不启用）】")
    p = mk_player(cls="cls_zhan_shi", learned=[])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, e)
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 5}}, logs)
    check("未装配的战士不产生条", not bar_of(e), f"effects={e.get('effects')}")
    fire(b, "time_advance", {"dt": 1.0, "now": 1.0}, logs)
    check("敌方无条也不崩", True)


def test_reflect_bar():
    print("【8. 反震（on_taken 装配）：反弹 30% 伤害 + 反推攻击者破绽条】")
    p = mk_player(cls="cls_wu_seng", learned=["反震"], hp=1000)
    CMP.apply_class_mech(p)
    ref = [x for x in ((p.get("triggers") or {}).get("on_taken") or [])
           if isinstance(x, dict) and (x.get("type") or x.get("action")) == "passive_reflect_bar"]
    check("拳师学反震 → 挂 on_taken 反制条目", len(ref) == 1, f"trigs={ref}")
    check("反射率 reflect_pct=0.30（passive dict 并入）",
          bool(ref) and abs(float(ref[0].get("reflect_pct") or 0) - 0.30) < 1e-9, f"trig={ref}")
    check("推条参数由 bar_field 解析（key=shaken / gain=3——数值单源 = 技能 shaken_gain）",
          bool(ref) and ref[0].get("key") == "shaken" and ref[0].get("gain") == 3,
          f"trig={ref}")
    e = mk_enemy(hp=50000, atk=100)
    b = new_battle(p, e)
    logs = []
    p_hp0 = p["hp"]
    # 受击 30 → 反弹 30% = 9（攻击者掉血）；同时攻击者破绽条 +3
    fire(b, "on_taken", {"actor": p, "source": e, "dmg": 30}, logs)
    check("反弹 30 × 30% = 9（攻击者掉 9 血）", e["hp"] == 50000 - 9, f"e_hp={e['hp']}")
    check("自身不掉血（反制不是自伤）", p["hp"] == p_hp0, f"p_hp={p['hp']}")
    check("攻击者破绽条 +3（反推条）", float(bar_of(e).get("val", 0) or 0) == 3.0,
          f"bs={bar_of(e)}")
    check("被推条单位自安装时钟/阶段订阅",
          len(_settle_trigs(e)) == 1 and len(_phase_trigs(e)) == 1,
          f"settle={_settle_trigs(e)} phase={_phase_trigs(e)}")
    check("反制日志落地", any("反震" in str(x) for x in logs), f"logs={logs}")
    # 无来源（DOT/环境伤）：只留伤害来源判定，不反制
    e2 = mk_enemy(hp=50000)
    b2 = new_battle(p, e2)
    logs2 = []
    fire(b2, "on_taken", {"actor": p, "dmg": 30}, logs2)
    check("无攻击来源不反制（不扣血、不推条）",
          e2["hp"] == 50000 and not bar_of(e2), f"e_hp={e2['hp']} bs={bar_of(e2)}")
    # 反向：未学反震 → 零条目（零噪音）
    p2 = mk_player(cls="cls_wu_seng", learned=["钢拳"])
    CMP.apply_class_mech(p2)
    ref2 = [x for x in ((p2.get("triggers") or {}).get("on_taken") or [])
            if isinstance(x, dict) and (x.get("type") or x.get("action")) == "passive_reflect_bar"]
    check("未学反震 → 不挂反制条目", not ref2, f"trigs={ref2}")


def test_phase_preserve():
    print("【9. Boss 阶段保留：phase → 积蓄保留 50%（进度遗产，触发计数不清零）】")
    p = mk_player(cls="cls_wu_seng", learned=["钢拳"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    e2 = mk_enemy()
    b = new_battle(p, e)
    b.sides["enemy"].append(e2)
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 40}}, logs)
    fire(b, "skill_hit", {"actor": p, "target": e2, "info": {"shaken_gain": 40}}, logs)
    check("垫到 40 且阶段订阅自安装（首次挂条时）",
          float(bar_of(e).get("val", 0) or 0) == 40.0 and len(_phase_trigs(e)) == 1,
          f"bs={bar_of(e)} phase={_phase_trigs(e)}")
    fire(b, "phase", {"actor": e, "phase": 1}, logs)
    check("阶段转换后保留 50% = 20", float(bar_of(e).get("val", -1)) == 20.0,
          f"bs={bar_of(e)}")
    check("阈值/触发计数不被阶段洗掉（进度遗产只缩放积蓄）",
          bar_of(e).get("threshold") == 50 and bar_of(e).get("trigger_count") == 0,
          f"bs={bar_of(e)}")
    check("阶段事件只作用于主体（旁观者 e2 条不动 = 40）",
          float(bar_of(e2).get("val", -1)) == 40.0, f"bs2={bar_of(e2)}")
    check("阶段保留日志落地", any("阶段更迭" in str(x) for x in logs), f"logs={logs}")
    # 无条单位收到 phase 不崩（零行为）
    e3 = mk_enemy()
    b3 = new_battle(p, e3)
    logs3 = []
    fire(b3, "phase", {"actor": e3, "phase": 1}, logs3)
    check("无条单位 phase 零行为", not bar_of(e3), f"bs={bar_of(e3)}")


if __name__ == "__main__":
    test_install()
    test_inject_on_hit()
    test_threshold_trigger()
    test_skip_consumed()
    test_time_decay()
    test_per_hit_multisegment()
    test_no_bar_no_op()
    test_reflect_bar()
    test_phase_preserve()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
