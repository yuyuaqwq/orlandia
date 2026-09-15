# -*- coding: utf-8 -*-
"""P2 迁移补强：老库 schema 自愈（connection.py:_ensure_legacy_columns 的 ALTER）

背景：connection.py:256-353 用 PRAGMA table_info + ALTER TABLE ADD COLUMN 对存量
旧库"补列自愈"。本测试用 sqlite3 直接构造一个只含基础列的"老版"库、插入 1 行存量
玩家数据，再调用 db.init_db()（会建全表并 ALTER 补列），验证：
  1) players 表补入全部新列（class_tier … faction）且数据完好；
  2) stats/feedback/market/professions/pets 各补列同样生效；
  3) 幂等性：再次 init_db() 不报错、不丢数据。

遵循 conftest 库隔离模式：私有独立库，跑完清理。不依赖未落地的 game/ 代码。
"""
import os
import sys
import sqlite3

# 私有独立库（遵守 conftest 库隔离；setdefault 尊重外层已预置的 GWEN_GAME_DB）
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("GWEN_GAME_DB", os.path.join(HERE, "test_legacy_schema_migration.db"))
sys.path.insert(0, HERE)
from conftest import db  # noqa: E402   (db.DB_PATH = connection.DB_PATH = 隔离库)

OLD_DB = db.DB_PATH
_passed = _failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print("  ✅ %s" % name)
    else:
        _failed += 1
        print("  ❌ %s %s" % (name, detail))


def _cols(conn, table):
    return [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table).fetchall()]


def _build_legacy_db(tmp_path):
    """直接构造一个"老版"库：只建最小列的表 + 插入 1 行存量玩家数据。

    保证重跑干净：先把所有相关表 DROP 掉再重建，模拟从零到旧的 schema。
    返回 conn（调用方负责 close）。
    """
    conn = sqlite3.connect(tmp_path)
    # 只保核心旧列（无 class_tier/attr_pts/attributes/... 等新列）
    conn.execute("DROP TABLE IF EXISTS players")
    conn.execute("""CREATE TABLE players (
        qq_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        class_name TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        exp INTEGER DEFAULT 0,
        gold INTEGER DEFAULT 0,
        hp INTEGER, mp INTEGER, max_hp INTEGER, max_mp INTEGER,
        cur_map TEXT DEFAULT 'vila', equipment TEXT DEFAULT '{}', skills TEXT DEFAULT '[]'
    )""")
    conn.execute(
        "INSERT INTO players (qq_id, name, class_name, level, exp, gold, hp, mp, max_hp, max_mp, cur_map) "
        "VALUES ('legacy_1', '老玩家', 'cls_zhan_shi', 7, 1234, 8888, 500, 200, 500, 200, 'vila')"
    )
    # 缺列的其他表（ALTER 自愈的补列对象）
    conn.execute("DROP TABLE IF EXISTS stats")
    conn.execute("""CREATE TABLE stats (
        qq_id TEXT PRIMARY KEY, kills INTEGER DEFAULT 0, deaths INTEGER DEFAULT 0
    )""")
    conn.execute("DROP TABLE IF EXISTS feedback")
    conn.execute("""CREATE TABLE feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT, qq_id TEXT NOT NULL,
        group_id TEXT DEFAULT '', content TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT DEFAULT 'new'
    )""")
    conn.execute("DROP TABLE IF EXISTS market")
    conn.execute("""CREATE TABLE market (
        id INTEGER PRIMARY KEY AUTOINCREMENT, group_id TEXT NOT NULL, seller TEXT NOT NULL,
        item_key TEXT NOT NULL, item_data TEXT NOT NULL, price INTEGER NOT NULL, listed_at INTEGER
    )""")
    conn.execute("DROP TABLE IF EXISTS professions")
    conn.execute("""CREATE TABLE professions (
        qq_id TEXT PRIMARY KEY,
        gather_lv INTEGER DEFAULT 1, gather_exp INTEGER DEFAULT 0,
        mining_lv INTEGER DEFAULT 1, mining_exp INTEGER DEFAULT 0,
        fishing_lv INTEGER DEFAULT 1, fishing_exp INTEGER DEFAULT 0,
        alchemy_lv INTEGER DEFAULT 1, alchemy_exp INTEGER DEFAULT 0,
        craft_lv INTEGER DEFAULT 1, craft_exp INTEGER DEFAULT 0,
        cooking_lv INTEGER DEFAULT 1, cooking_exp INTEGER DEFAULT 0,
        fish_king INTEGER DEFAULT 0
    )""")
    conn.execute("DROP TABLE IF EXISTS pets")
    conn.execute("""CREATE TABLE pets (
        qq_id TEXT PRIMARY KEY, pet_key TEXT NOT NULL, name TEXT NOT NULL,
        level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0, satiety INTEGER DEFAULT 100, bond INTEGER DEFAULT 0
    )""")
    # 刻意删除当前实例可能残留的其它表，使 init_db 从全新建表跑一遍，收敛到标准 schema
    for t in ("inventory", "quests", "battle_state", "achievements", "reputation", "signin",
              "props_use", "fishing", "bestiary", "visited", "visited_subareas",
              "player_groups", "world_event", "event_state", "party", "guilds",
              "guild_members", "pet_dex"):
        conn.execute("DROP TABLE IF EXISTS %s" % t)
    conn.commit()
    return conn


def main():
    tmp = OLD_DB
    # 1. 构造旧库
    conn = _build_legacy_db(tmp)
    conn.close()
    print("【旧库已构造】 players 旧列:", _cols(sqlite3.connect(tmp), "players"))

    # 2. init_db() 自愈：建全表 + ALTER 补列
    db.init_db()
    d = sqlite3.connect(tmp)
    d.row_factory = sqlite3.Row

    print("【players 补列】")
    expected_new = [
        "class_tier", "attr_pts", "attributes", "skill_points", "learned_skills",
        "hidden_class_unlock", "portals", "skill_bar", "skill_spent", "shortcuts",
        "explore_wandering", "evolve_path", "skill_levels", "mounts",
        "learned_blueprints", "lucky_until", "stamina", "stamina_ts", "race", "gender",
        "equipped_title", "deed_lv", "cur_subarea", "apprentices", "deed", "faction",
    ]
    pcols = _cols(d, "players")
    missing = [c for c in expected_new if c not in pcols]
    check("players 补入全部 %d 个新列" % len(expected_new), not missing, "缺列: %s" % missing)

    print("【存量玩家数据完好】")
    row = d.execute("SELECT * FROM players WHERE qq_id='legacy_1'").fetchone()
    r = dict(row)
    check("type: 存量行仍存在", row is not None)
    check("name 完好", r["name"] == "老玩家", r.get("name"))
    check("level 完好", r["level"] == 7, r.get("level"))
    check("gold 完好", r["gold"] == 8888, r.get("gold"))
    check("新列默认值(attributes)", '"str":0' in (r.get("attributes") or ""), r.get("attributes"))
    check("新列默认值(stamina=100)", r.get("stamina") == 100, r.get("stamina"))
    check("新列默认值(race=human)", r.get("race") == "human", r.get("race"))

    print("【store 读回一致性】")
    # 注：get_player 读档会触发 exp 惰性升级（存量档 exp=1234 已超 exp_to_next(7)），
    # level 会在读回时合法增加——这里只断言 name/gold 完好（原始 level 已在上节用裸读核验）。
    p = db.get_player("legacy_g", "legacy_1")
    check("get_player 读回 name/gold 完好", p and p["name"] == "老玩家" and p["gold"] == 8888,
          None if p is None else str(p.get("name")))
    check("get_player 读回兼容惰性升级（level>=7）", p and p["level"] >= 7,
          None if p is None else "level=%s" % p.get("level"))

    print("【stats/feedback/market/professions/pets 补列】")
    scols = _cols(d, "stats")
    expected_stats = ["visited_areas", "inst_clears", "party_count", "fish_count", "gather_count",
                      "mine_count", "cook_count", "alchemy_count", "craft_count", "enhance_count",
                      "enchant_count", "world_events", "catch_collect"]
    check("stats 补 full-count 列", all(c in scols for c in expected_stats),
          "缺: %s" % [c for c in expected_stats if c not in scols])
    check("feedback 补 reply", "reply" in _cols(d, "feedback"))
    check("market 补 map_id", "map_id" in _cols(d, "market"))
    prcols = _cols(d, "professions")
    # 注：explore_wandering 是 players 列（见 _ensure_legacy_columns line 280），非 professions 列
    check("professions 补 activated/enhance_lv/enchant_lv",
          all(c in prcols for c in ("activated", "enhance_lv", "enchant_lv")),
          "缺: %s" % [c for c in ("activated", "enhance_lv", "enchant_lv") if c not in prcols])
    check("pets 补 last_sat_time", "last_sat_time" in _cols(d, "pets"))

    print("【幂等性：再 init_db()】")
    db.init_db()  # 不抛异常即通过
    row2 = d.execute("SELECT * FROM players WHERE qq_id='legacy_1'").fetchone()
    check("再次 init_db 后数据不丢", row2 is not None and dict(row2)["gold"] == 8888)
    p2 = db.get_player("legacy_g", "legacy_1")
    check("再次 init_db 后 get_player 正常", p2 and p2["name"] == "老玩家")

    d.close()
    # 清理私有库文件（conftest 库隔离模式：跑完清理）
    for f in (tmp, tmp + "-journal", tmp + "-wal", tmp + "-shm"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    print("\n结果: %d 通过, %d 失败" % (_passed, _failed))
    return _failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
