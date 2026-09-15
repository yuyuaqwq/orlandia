# -*- coding: utf-8 -*-
"""v136 原石系统验收测试（数据层 + 核心逻辑 + engine 属性结算接入）。

覆盖：
1. roll_gem：随机生成结构正确（有 stats、tier 在范围、传说带特效、boss_fixed 固定属性）
2. gem_combine：3 同级 → 上级，层数+1
3. gem_socket_cost / sockets_capacity：拆卸费 & 孔位表
4. engine.player_stats_detail：带 sockets 的装备属性含原石加成（百分比 & 数值）
5. 数据层聚合导出：C.GEM_TIERS / C.roll_gem 可从 game.content 访问
"""
import os
import sys
import random

os.environ.setdefault("GWEN_GAME_DB", os.path.abspath("test_v136_gems.db"))
sys.path.insert(0, "tests")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 插件根目录（脚本直跑）

# ⚠️ 导入顺序铁律：先用测试侧入口装配引擎通道（包源根入 sys.path），再取包内真源；
# 否则包内模块图部分初始化时会缓存残缺面（缺 gems 聚合符号）。
from _engine_harness import C  # noqa: E402
from content.gems import GEM_TIERS, GEM_STATS, GEM_SOCKETS, GEM_TIER_NAMES  # noqa: E402
from content.catalog_b143 import GEM_DRILL, RUNE_REMOVE_COST  # noqa: E402  （REPOINT_MAP: game.data.gems 常量 → catalog_b143）
from content.gems import GEM_REMOVE_COST  # noqa: E402
from content.gems import GEM_LEGENDARY_EFFECTS, GEM_DROP_RATE, GEM_DROP_TIER, GEM_BOSS_FIXED  # noqa: E402
from content.gems import roll_gem, gem_combine, gem_socket_cost, sockets_capacity  # noqa: E402
from content.panel import player_stats_detail


def _mk_gem(stats, tier):
    """构造一颗指定 stats/tier 的幸运宝石 dict（测试夹具）。"""
    return {"name": "测试幸运宝石", "type": "幸运宝石", "gem": True, "stats": stats, "tier": tier, "icon": "💎"}


# ---------- 1. 数据表 ----------
def test_data_tables():
    assert len(GEM_TIERS) == 10
    assert abs(GEM_TIERS[10]["mult"] - 0.06) < 1e-9
    assert abs(GEM_TIERS[1]["mult"] - 0.01) < 1e-9
    assert len(GEM_TIER_NAMES) == 10
    assert GEM_TIER_NAMES[1] == "碎裂的幸运宝石" and GEM_TIER_NAMES[10] == "神话的幸运宝石"
    assert len(GEM_STATS) == 23
    assert len(set(GEM_STATS)) == len(GEM_STATS)
    assert GEM_REMOVE_COST == 500
    assert RUNE_REMOVE_COST == 1000
    assert len(GEM_LEGENDARY_EFFECTS) == 4
    # 属性池三类齐全：面板7 + 百分比14 + 成长2
    for s in ("hp", "atk", "crit", "dodge", "exp_bonus", "gold_bonus"):
        assert s in GEM_STATS, s


# ---------- 2. roll_gem ----------
def test_roll_gem_structure():
    random.seed(42)
    for _ in range(200):
        g = roll_gem(1, 10)
        assert isinstance(g.get("stats"), dict) and 1 <= len(g["stats"]) <= 2
        assert g.get("type") == "幸运宝石" and g.get("gem") is True
        assert 1 <= g.get("tier", 0) <= 10
        assert all(s in GEM_STATS for s in g["stats"])
        assert all(0.01 <= v <= 0.06 for v in g["stats"].values())
        # stats 值 = 层数 mult（最高属性对应 tier 的 mult 一致）
        assert abs(max(g["stats"].values()) - GEM_TIERS[g["tier"]]["mult"]) < 1e-9
        assert g["name"].startswith(GEM_TIER_NAMES[g["tier"]].rstrip("I").rstrip("II") or "碎裂")


def test_roll_gem_legendary():
    seen = False
    for _ in range(300):
        g = roll_gem(9, 10)
        if g["tier"] >= 9:
            seen = True
            assert g.get("legend_effect") in GEM_LEGENDARY_EFFECTS
    assert seen, "传说级原石应可生成"
    # 非传说无特效
    for _ in range(50):
        g = roll_gem(1, 5)
        assert g["tier"] < 9
        assert "legend_effect" not in g


def test_roll_gem_boss_fixed():
    for _ in range(100):
        g = roll_gem(3, 6, boss_fixed={"stat": "pene_phys"})
        assert "pene_phys" in g["stats"]
    for _ in range(50):
        g = roll_gem(1, 10, boss_fixed={"stat": "crit"})
        assert "crit" in g["stats"]


def test_roll_gem_tier_range():
    # 指定区间内层数
    for _ in range(100):
        g = roll_gem(1, 2)
        assert g["tier"] <= 2
        assert all(v <= GEM_TIERS[2]["mult"] + 1e-9 for v in g["stats"].values())
    for _ in range(50):
        g = roll_gem(9, 10)
        assert g["tier"] >= 9


# ---------- 3. gem_combine ----------
def test_gem_combine_same_tier():
    g1 = _mk_gem({"atk": GEM_TIERS[3]["mult"]}, 3)
    g2 = _mk_gem({"crit": GEM_TIERS[3]["mult"]}, 3)
    g3 = _mk_gem({"crit": GEM_TIERS[3]["mult"]}, 3)
    up = gem_combine([g1, g2, g3])
    assert up["tier"] == 4
    assert set(up["stats"].keys()) == {"atk", "crit"}
    assert abs(up["stats"]["atk"] - GEM_TIERS[4]["mult"]) < 1e-9
    assert "明亮的幸运宝石" in up["name"]


def test_gem_combine_rejects_mixed():
    g1 = _mk_gem({"atk": GEM_TIERS[3]["mult"]}, 3)
    g2 = _mk_gem({"crit": GEM_TIERS[3]["mult"]}, 3)
    g3 = _mk_gem({"dodge": GEM_TIERS[5]["mult"]}, 5)
    try:
        gem_combine([g1, g2, g3])
        assert False, "不同级合成应被拒绝"
    except ValueError:
        pass


def test_gem_combine_tier_cap():
    # 10 层满级不再升
    g = _mk_gem({"atk": GEM_TIERS[10]["mult"]}, 10)
    up = gem_combine([g, _mk_gem({"crit": GEM_TIERS[10]["mult"]}, 10),
                      _mk_gem({"def": GEM_TIERS[10]["mult"]}, 10)])
    assert up["tier"] == 10


# ---------- 4. 拆卸费 & 孔位 ----------
def test_gem_socket_cost():
    g_high = roll_gem(9, 10)
    assert gem_socket_cost(g_high) == 500 * g_high["tier"]
    g_low = _mk_gem({"atk": GEM_TIERS[1]["mult"]}, 1)
    assert gem_socket_cost(g_low) == 500
    assert gem_socket_cost({}) == 0
    assert gem_socket_cost(None) == 0


def test_sockets_capacity():
    cap = sockets_capacity("blue")
    assert cap["count"] == 1 and cap["tier"] == "S1" and cap["min_tier"] == 1 and cap["max_tier"] == 2
    cap2 = sockets_capacity("purple")
    assert cap2["count"] == 2 and cap2["tier"] == "S2" and cap2["min_tier"] == 2 and cap2["max_tier"] == 4
    cap3 = sockets_capacity("orange")
    assert cap3["count"] == 3 and cap3["tier"] == "S3"
    assert cap3["max_tier"] == 10, f"橙孔应允许传说(3-10层)，got {cap3['max_tier']}"
    assert sockets_capacity("white")["count"] == 0
    assert sockets_capacity("green")["count"] == 0
    assert sockets_capacity("nope")["count"] == 0


def test_gem_drill_table():
    assert GEM_DRILL["blue"]["cost"] == 500 and GEM_DRILL["blue"]["craft_lv"] == 1
    assert GEM_DRILL["purple"]["cost"] == 1500 and GEM_DRILL["purple"]["craft_lv"] == 3
    assert GEM_DRILL["orange"]["cost"] == 4000 and GEM_DRILL["orange"]["craft_lv"] == 5


# ---------- 5. engine 属性结算（原石乘区接入） ----------
def test_engine_gem_pct_and_flat():
    st0, _ = player_stats_detail("cls_zhan_shi", 1, {}, 0, None, 0, None, "human")
    gem_atk = _mk_gem({"atk": 0.01}, 1)
    gem_crit = _mk_gem({"crit": 0.035}, 6)
    eq = {
        "slot": "weapon", "lv": 20, "quality": "blue", "name": "🔵·铁剑",
        "stats": {"atk": 10}, "affixes": [], "enchant": [],
        "sockets": {"孔位1": gem_atk, "孔位2": gem_crit},
    }
    st1, srcs = player_stats_detail("cls_zhan_shi", 1, {"weapon": eq}, 0, None, 0, None, "human")
    atk_diff = st1.get("atk", 0) - st0.get("atk", 0)
    assert abs(atk_diff - (10 + 0.01)) < 1e-9, f"atk diff={atk_diff}"
    crit_diff = st1.get("crit", 0) - st0.get("crit", 0)
    assert abs(crit_diff - 0.035) < 1e-9, f"crit diff={crit_diff}"
    # 来源明细含原石属性（装备来源项聚合 stats+原石）
    eq_src = next((s for s in srcs if s["name"].startswith("🔵·铁剑")), None)
    assert eq_src is not None
    assert abs(eq_src["stats"].get("atk", 0) - 10.01) < 1e-9
    assert abs(eq_src["stats"].get("crit", 0) - 0.035) < 1e-9


def test_engine_gem_hp():
    st2, _ = player_stats_detail("cls_zhan_shi", 1, {}, 0, None, 0, None, "human")
    gem_hp = _mk_gem({"hp": 0.01}, 1)
    eq2 = {"slot": "armor", "lv": 20, "quality": "blue", "name": "🔵·铁甲",
           "stats": {"hp": 100}, "affixes": [], "enchant": [],
           "sockets": {"孔位1": gem_hp}}
    st3, _ = player_stats_detail("cls_zhan_shi", 1, {"armor": eq2}, 0, None, 0, None, "human")
    hp_diff = st3.get("max_hp", 0) - st2.get("max_hp", 0)
    assert abs(hp_diff - 100.01) < 1e-9, f"hp diff={hp_diff}"


def test_engine_gem_empty_sockets_safe():
    # 无 sockets / 空 sockets / 非 dict 值都安全（老档兼容）
    eq = {"slot": "weapon", "lv": 1, "quality": "white", "name": "⚪·木剑",
          "stats": {"atk": 5}, "affixes": [], "enchant": []}
    st_a, _ = player_stats_detail("cls_zhan_shi", 1, {"weapon": eq}, 0, None, 0, None, "human")
    eq["sockets"] = {}
    st_b, _ = player_stats_detail("cls_zhan_shi", 1, {"weapon": eq}, 0, None, 0, None, "human")
    eq["sockets"] = {"孔位1": "not_a_dict"}
    st_c, _ = player_stats_detail("cls_zhan_shi", 1, {"weapon": eq}, 0, None, 0, None, "human")
    assert st_a == st_b == st_c


# ---------- 6. 聚合导出 ----------
def test_content_aggregation():
    assert C.GEM_TIERS is GEM_TIERS
    assert len(C.GEM_STATS) == 23
    assert C.GEM_SOCKETS["orange"]["max_tier"] == 10
    assert callable(getattr(C, "roll_gem", None))
    assert callable(getattr(C, "gem_combine", None))
    assert callable(getattr(C, "gem_socket_cost", None))
    assert callable(getattr(C, "sockets_capacity", None))
    # v136 Phase 2：掉落配置升格为分档 dict（普通 2% / 精英 5% / 野外 Boss 15% / 副本 Boss 20%）
    assert isinstance(C.GEM_DROP_RATE, dict)
    assert C.GEM_DROP_RATE == {"normal": 0.02, "elite": 0.05, "field_boss": 0.15, "instance_boss": 0.20}
    assert C.GEM_DROP_TIER == {"normal": (1, 6), "elite": (2, 8), "field_boss": (3, 10), "instance_boss": (3, 10)}
    assert callable(getattr(C, "roll_gem_drop", None))
    assert "裂鬃" in C.GEM_BOSS_FIXED and C.GEM_BOSS_FIXED["裂鬃"] == "pene_phys"
    assert "野猪王·裂鬃" in C.GEM_BOSS_FIXED and C.GEM_BOSS_FIXED["野猪王·裂鬃"] == "pene_phys"
    assert "深海龙王·敖澜" in C.GEM_BOSS_FIXED and C.GEM_BOSS_FIXED["深海龙王·敖澜"] == "pene_magi"
    assert "灰烬使者" in C.GEM_BOSS_FIXED and C.GEM_BOSS_FIXED["灰烬使者"] == "crit"


# 脚本直跑模式（tests/test_v136_gems.py）
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
