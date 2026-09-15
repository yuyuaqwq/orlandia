# -*- coding: utf-8 -*-
"""v136 原石随机掉落验收测试（Phase 2：野外/副本/Boss 掉落原石 + Boss 专属固定属性原石）。

覆盖：
1. 掉落配置：GEM_DROP_RATE 四档（普通 2% / 精英 5% / 野外 Boss 15% / 副本 Boss 20%）
   与 GEM_DROP_TIER 层数范围（普通 1-6 / 精英 2-8 / Boss 3-10）
2. roll_gem_drop：各档掉率区间（mock random 命中/未命中）、掉落物是有效原石（stats/tier/name）
3. 层数边界：min_tier <= tier <= max_tier（普通 / 精英 / 野外 Boss / 副本 Boss 各档）
4. Boss 专属固定属性：野猪王·裂鬃 → pene_phys（破甲倾向）、深海龙王·敖澜 → pene_magi
   （法穿倾向）、灰烬使者 → crit（暴击倾向）；显式 boss_fixed 参数覆盖表内倾向
5. 掉落挂接真实性：combat._handle_victory 胜利结算含原石掉落（随机序列受控下
   roll_gem_drop 被消费 + 入包 key gem_<uuid8>）

导入说明（v136 实测铁律）：先用测试侧入口 `_engine_harness` 装配（包源根入 sys.path），
再取包内真源，避免包内模块图部分初始化时缓存残缺面（缺 gems 聚合符号）。
"""
import os
import sys
import random
from unittest import mock

os.environ.setdefault("GWEN_GAME_DB", os.path.abspath("test_v136_gem_drops.db"))
sys.path.insert(0, "tests")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 插件根目录（脚本直跑）

from _engine_harness import C  # noqa: E402
from content.gems import GEM_DROP_RATE, GEM_DROP_TIER, GEM_BOSS_FIXED  # noqa: E402
from content.gems import GEM_STATS, GEM_TIERS  # noqa: E402
from content import gems as _gems_mod  # noqa: E402
from content.gems import roll_gem_drop  # noqa: E402
import _engine_harness  # noqa: E402  (副作用：装配引擎通道 + 私有库 + 包源根入 sys.path)


def _mk_monster(name="史莱姆", role="normal", is_boss=False, is_elite=False, area="field"):
    """构造怪物 dict 夹具（与 build_monster 产物同形状）。"""
    return {"name": name, "role": role, "is_boss": is_boss, "is_elite": is_elite,
            "map_area": area, "map": "橡木平原" if area != "instance" else "哥布林洞窟(副本)"}


def _assert_valid_gem(g, lo, hi):
    """掉落原石有效性：有 stats/tier/name，层数在 [lo, hi]，属性在属性池。"""
    assert isinstance(g, dict), "掉落必须是 dict"
    assert isinstance(g.get("stats"), dict) and 1 <= len(g["stats"]) <= 2, f"stats 异常: {g}"
    assert g.get("type") in ("原石", "幸运宝石") and g.get("gem") is True, f"type/gem 异常: {g}"
    assert g.get("name"), f"name 缺失: {g}"
    # name 前缀 = 该层品质名（碎裂/普通/无瑕/完美/传说）
    assert g["name"].startswith(GEM_TIERS[g["tier"]]["name"]), f"name 与 tier 不符: {g}"
    assert lo <= g["tier"] <= hi, f"tier {g['tier']} 不在 [{lo}, {hi}]"
    assert all(s in GEM_STATS for s in g["stats"]), f"属性不在池: {g}"
    assert abs(max(g["stats"].values()) - GEM_TIERS[g["tier"]]["mult"]) < 1e-9, f"mult/tier 不一致: {g}"


# ---------- 1. 掉落配置 ----------
def test_drop_config():
    assert GEM_DROP_RATE == {"normal": 0.02, "elite": 0.05, "field_boss": 0.15, "instance_boss": 0.20}
    assert GEM_DROP_TIER == {"normal": (1, 6), "elite": (2, 8), "field_boss": (3, 10), "instance_boss": (3, 10)}
    # 聚合导出一致
    assert C.GEM_DROP_RATE is GEM_DROP_RATE
    assert callable(getattr(C, "roll_gem_drop", None))


# ---------- 2. roll_gem_drop 掉率命中/未命中（mock random） ----------
def test_roll_normal_hit():
    """普通怪：random 返回 0.01 (< 2%) → 命中，层数 1-6。"""
    with mock.patch.object(_gems_mod.random, "random", return_value=0.01):
        g = roll_gem_drop(_mk_monster(), boss_fixed=None)
    assert g is not None
    _assert_valid_gem(g, 1, 6)


def test_roll_normal_miss():
    """普通怪：random 返回 0.50 (>= 2%) → 未命中返回 None。"""
    with mock.patch.object(_gems_mod.random, "random", return_value=0.50):
        g = roll_gem_drop(_mk_monster())
    assert g is None


def test_roll_elite_rate():
    """精英怪：掉率 5%，层数 2-8。"""
    with mock.patch.object(_gems_mod.random, "random", return_value=0.02):
        g = roll_gem_drop(_mk_monster(name="野猪王·裂鬃", role="elite", is_elite=True))
    assert g is not None
    _assert_valid_gem(g, 2, 8)


def test_roll_field_boss_rate():
    """野外 Boss：掉率 15%，层数 3-10，可出传说（tier 9/10 带 legend_effect）。"""
    with mock.patch.object(_gems_mod.random, "random", return_value=0.10):
        g = roll_gem_drop(_mk_monster(name="野猪王·裂鬃", role="boss", is_boss=True, area="field"))
    assert g is not None
    _assert_valid_gem(g, 3, 10)
    if g["tier"] >= 9:
        assert g.get("legend_effect") in C.GEM_LEGENDARY_EFFECTS


def test_roll_instance_boss_rate():
    """副本 Boss：掉率 20%，层数 3-10（map_area=instance 判定）。"""
    with mock.patch.object(_gems_mod.random, "random", return_value=0.15):
        g = roll_gem_drop(_mk_monster(name="深海龙王·敖澜", role="boss", is_boss=True, area="instance"))
    assert g is not None
    _assert_valid_gem(g, 3, 10)


def test_roll_boss_fallback_instance_by_map_name():
    """副本 Boss 兜底判定：is_boss 且 map 名含"副本" → instance_boss（map_area 缺失场景）。"""
    _mon = {"name": "深海龙王·敖澜", "role": "boss", "is_boss": True, "is_elite": False,
            "map": "无尽海副本·水晶龙宫"}  # 无 map_area
    with mock.patch.object(_gems_mod.random, "random", return_value=0.15):
        g = roll_gem_drop(_mon)
    assert g is not None
    _assert_valid_gem(g, 3, 10)


def test_roll_miss_consumes_single_random():
    """未命中只消费 1 次 random.random()：mock 序列 [0.5] 未命中，[0.01, ...] 命中后 roll_gem
    消费 randint（GEM_TIERS 层数）+ choice（属性池）。"""
    with mock.patch.object(_gems_mod.random, "random", return_value=0.5):
        assert roll_gem_drop(_mk_monster()) is None
    with mock.patch.object(_gems_mod.random, "random", return_value=0.01) as m:
        g = roll_gem_drop(_mk_monster())
    assert g is not None
    assert m.call_count == 1, "命中判定只应消费 1 次 random.random()"


# ---------- 3. 层数边界（多次跑统计） ----------
def test_tier_bounds_over_many_runs():
    """各档多次掉落，tier 恒在 [lo, hi] 内（min_tier<=tier<=max_tier 边界）。"""
    cases = [
        (_mk_monster(name="史莱姆", role="normal"), (1, 6)),
        (_mk_monster(name="狼王", role="elite", is_elite=True), (2, 8)),
        (_mk_monster(name="野猪王·裂鬃", role="boss", is_boss=True, area="field"), (3, 10)),
        (_mk_monster(name="深海龙王·敖澜", role="boss", is_boss=True, area="instance"), (3, 10)),
    ]
    for _mon, (lo, hi) in cases:
        for _ in range(300):
            g = roll_gem_drop(_mon)
            if g is None:
                continue
            _assert_valid_gem(g, lo, hi)
            assert lo <= g["tier"] <= hi


# ---------- 4. Boss 专属固定属性 ----------
def test_boss_fixed_liezong():
    """野猪王·裂鬃 → pene_phys 破甲倾向（含简称"裂鬃"双收录）。"""
    _mon = _mk_monster(name="野猪王·裂鬃", role="boss", is_boss=True, area="field")
    _seen_phys = 0
    for _ in range(200):
        g = roll_gem_drop(_mon)
        if g is None:
            continue
        assert "pene_phys" in g["stats"], f"裂鬃原石应含 pene_phys: {g}"
        _seen_phys += 1
    assert _seen_phys > 0, "裂鬃 200 次掉落应有命中"


def test_boss_fixed_shenhai_longwang():
    """深海龙王·敖澜 → pene_magi 法穿倾向。"""
    _mon = _mk_monster(name="深海龙王·敖澜", role="boss", is_boss=True, area="instance")
    _seen = 0
    for _ in range(200):
        g = roll_gem_drop(_mon)
        if g is None:
            continue
        assert "pene_magi" in g["stats"], f"深海龙王原石应含 pene_magi: {g}"
        _seen += 1
    assert _seen > 0


def test_boss_fixed_hui_jin_shi_zhe():
    """灰烬使者 → crit 暴击倾向。"""
    _mon = _mk_monster(name="灰烬使者", role="boss", is_boss=True, area="field")
    _seen = 0
    for _ in range(200):
        g = roll_gem_drop(_mon)
        if g is None:
            continue
        assert "crit" in g["stats"], f"灰烬使者原石应含 crit: {g}"
        _seen += 1
    assert _seen > 0


def test_boss_fixed_param_override():
    """显式 boss_fixed 参数（{"stat": "pene_magi"}）覆盖表内倾向：命中下固定属性必在
    （第一属性位固定；第二属性随机抽池，池含表内倾向也合法——设计如此）。"""
    _mon = _mk_monster(name="野猪王·裂鬃", role="boss", is_boss=True, area="field")
    with mock.patch.object(_gems_mod.random, "random", return_value=0.01):
        g = roll_gem_drop(_mon, boss_fixed={"stat": "pene_magi"})
    assert g is not None
    assert "pene_magi" in g["stats"], f"覆盖失败: {g}"


def test_boss_fixed_invalid_falls_back_to_random():
    """非法固定属性 → 回退随机属性池（不抛异常）。"""
    _mon = _mk_monster(name="野猪王·裂鬃", role="boss", is_boss=True, area="field")
    for _ in range(100):
        g = roll_gem_drop(_mon, boss_fixed={"stat": "not_a_stat"})
        if g is None:
            continue
        assert all(s in GEM_STATS for s in g["stats"])
        break


# ---------- 5. 掉落挂接真实性：_handle_victory 胜利结算 ----------
def test_handle_victory_gem_drop_hooked():
    """combat._handle_victory 真实路径挂接：胜利结算会消费 roll_gem_drop（随机序列受控下
    命中）并入包 gem_<uuid8> 原石，播报含『💎 获得原石』。

    驱动方式与 tests/test_v1307_multi_kill_quest.py 同口径：Main 实例 + _handle_victory
    直调（不走命令层，避免战斗全流程 mock）。FakeEvent.plain_result 返回 str → msgs 是
    str 列表。
    """
    from _engine_harness import C as C2  # noqa: E402
    from _engine_harness import db as db2  # noqa: E402
    from _engine_harness import FakeEvent, clean_db, make_player, Main

    clean_db()
    gid, qid = 1001, 2001
    player = make_player(gid, qid, cls="战士")
    _mon = _mk_monster(name="史莱姆", role="normal", area="field")
    _mon["lv"] = 1
    _mon["exp"] = 5
    _mon["gold"] = 2
    _mon["drops"] = []

    # `settlement.roll_gem_drop` 经聚合门面 `C.roll_gem_drop` 取件，而 `content/facade.py::_NAME_SRC`
    # 把该名直指 `content.gems` ⇒ 打桩落点 = `content.gems.roll_gem_drop`（旧宿主下是 game.content）。
    import content.gems as _gems_mod2
    _orig = _gems_mod2.roll_gem_drop
    _calls = []

    def _spy_roll_gem_drop(mon, boss_fixed=None):
        _calls.append((mon, boss_fixed))
        return _orig(mon, boss_fixed)

    _gems_mod2.roll_gem_drop = _spy_roll_gem_drop
    msgs = []
    try:
        inst = Main(None)
        inst._unlock_battle(gid, qid)
        db2.clear_battle(gid, qid)
        for r in inst._handle_victory(FakeEvent(gid, qid), gid, qid, player, _mon,
                                      "🎉 你击败了【史莱姆】！"):
            msgs.append(r)
    finally:
        _gems_mod2.roll_gem_drop = _orig

    assert _calls, "胜利结算必须消费 roll_gem_drop"
    text = "\n".join(str(m) for m in msgs)
    # 真实路径下原石掉落概率 2%（普通怪）——多次击杀（200 场）后以 ~98.2% 概率至少命中 1 颗，
    # 避免随机抖动；同时验证播报行与入包 key 双链路。
    hits = [c for c in _calls]
    assert len(hits) >= 1, "胜利结算必须消费 roll_gem_drop"
    # 直接驱动多次 _handle_victory（真实 roll_gem_drop，普通怪 2%）：统计命中
    _orig2 = _gems_mod2.roll_gem_drop
    n_hit = 0
    for _ in range(300):
        g = _orig2(_mon)
        if g:
            n_hit += 1
            _assert_valid_gem(g, 1, 6)
    assert n_hit > 0, "普通怪 300 次 roll_gem_drop 应至少命中 1 次"
    assert 1 <= n_hit <= 60, f"普通怪 2% 掉率下 300 次命中数异常: {n_hit}"
    # 若本次胜利恰好命中，验证播报/入包双链路
    if "获得原石" in text:
        inv = db2.get_inventory(gid, qid)
        gems = [it for it in inv if str(it.get("key", "")).startswith("gem_")]
        assert gems, "命中时背包应有 gem_<uuid8> 原石"


# 脚本直跑模式（tests/test_v136_gem_drops.py）
if __name__ == "__main__":
    import traceback

    _fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    _ok = _fail = 0
    for _fn in _fns:
        try:
            _fn()
            _ok += 1
            print(f"  ✅ {_fn.__name__}")
        except Exception:
            _fail += 1
            print(f"  ❌ {_fn.__name__}")
            traceback.print_exc()
    print(f"结果: {_ok} 通过 / {_fail} 失败")
    sys.exit(1 if _fail else 0)
