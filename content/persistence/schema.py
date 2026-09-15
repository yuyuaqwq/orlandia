# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 存档层**表结构声明**（B17，2026-09-14；PKG-A，2026-09-16 改声明式）。

**改前**（B17 ~ PKG-A 前）：4 段手写建表 SQL 常量（`_SQL_CORE_TABLES` / `_SQL_SOCIAL_TABLES` /
`_SQL_PROF_TABLES` / `_SQL_IDENTITY_TABLES`）+ `install(db)` 把它们注册到注入的连接骨架 +
61 行老库补列自愈清单（引擎 `ensure_columns`）。

**改后**（PKG-A）：同一份表结构压成**声明**（引擎 `saintess_engine.store` 的
`Column` / `TableSpec` / `declare`）——建表 SQL 与「老库缺列自愈」迁移都从**同一份声明**派生，
表结构不再在「首建」和「补列清单」两处各写一遍。

注册动作仍是 `install(db)`（宿主工厂 / 包内 `handles.get_db()` 调一次；幂等）：
逐表 `declare(db, spec)`。声明序 = 改前 4 段 DDL 的表序（core → social → professions →
identity），故建表语句的执行序与改前**逐序相同**。

★ **行为保持**（PKG-A 铁律）：
* 列名 / 类型 / notnull / 默认 / pk 与改前**逐列相同**；对全新库连列序也相同（补列清单里的
  列并入声明尾部，位置正是改前首建之后 `ALTER TABLE ADD COLUMN` 追加的位置）。
* 改前老库补列清单要补的列**全部并入**各表声明（同一份列定义既建表又补列），
  老库缺列自愈仍在（`out/LANDING.md` §4.2 原始输出）。
* `identity_map` 的 `idx_identity_qq` 索引走 `TableSpec(migrations=…)`（形状自带的附加迁移口）。
* **业务查询一字未动**：本文件只有表结构；`players.py` / `inventory.py` / … 的手写 SQL 原样。
"""
from __future__ import annotations

# ★ PKG-A：改前的手写建表常量 / 注册调用 / 老库补列清单已**删净**（无壳、无开关、无双路径），
#   换引擎的声明式建表（Column / TableSpec / declare）。
from saintess_engine.store import Column, TableSpec, declare

from .handles import flush_log
# ★ W2a：内容聚合面取自**包内门面**（原 `from .handles import C` → 宿主 `game.content`）。
from ..facade import C  # noqa: F401  （`content.facade` 零 import 依赖，EAGER 窗口安全）

# v135 装配期循环解除：connection 不再顶层依赖 content（data._assembly → core →
# smith_stock → db → store.connection → content 未完成初始化）。C_MAP_IDS 改为
# 惰性求值——首次访问时 content 必已完成装配（消费端都在命令层运行期）。
_C_MAP_IDS_CACHE = None


def _map_ids() -> set:
    global _C_MAP_IDS_CACHE
    if _C_MAP_IDS_CACHE is None:
        _C_MAP_IDS_CACHE = set(C.MAP_BY_ID.keys())
    return _C_MAP_IDS_CACHE


# 兼容旧引用（store 层内部使用 C_MAP_IDS 做集合运算）
C_MAP_IDS = _map_ids()


def _identity_index(conn):
    """`identity_map(qq_id)` 索引 —— 改前在 `_SQL_IDENTITY_TABLES` 里跟建表一起建。

    `TableSpec(migrations=…)` 是形状给的「附加迁移」口：在形状自带的补列迁移之后执行。
    `IF NOT EXISTS` 保持幂等（`Database.init()` 可重复调）。
    """
    conn.execute("CREATE INDEX IF NOT EXISTS idx_identity_qq ON identity_map(qq_id)")


# ============================================================================
# 表结构声明（声明序 = 改前 4 段 DDL 的表序）
#
# 列序：改前首建的列 + 改前老库补列清单里**只补列、不在首建**的那些列（`# 老库补列` 标注）
# ——后者并入声明尾部，正是改前在全新库上 `ALTER ADD COLUMN` 追加的位置，
# 故全新库的列序与改前完全一致。
# ============================================================================
_SPECS = [
    # ---------------------------------------------- core：players
    TableSpec("players", [
        Column("qq_id", "TEXT", pk=True),
        Column("name", "TEXT", notnull=True),
        Column("class_name", "TEXT", notnull=True),
        Column("level", "INTEGER", default=1),
        Column("exp", "INTEGER", default=0),
        Column("gold", "INTEGER", default=0),
        Column("hp", "INTEGER"),
        Column("mp", "INTEGER"),
        Column("max_hp", "INTEGER"),
        Column("max_mp", "INTEGER"),
        Column("cur_map", "TEXT", default="vila"),
        Column("cur_subarea", "TEXT", default=""),               # v86 子区域
        Column("equipment", "TEXT", default="{}"),
        Column("skills", "TEXT", default="[]"),
        Column("class_tier", "INTEGER", default=0),              # 转职系统
        Column("attr_pts", "INTEGER", default=0),
        Column("attributes", "TEXT", default='{"str":0,"agi":0,"int":0,"vit":0}'),
        Column("skill_points", "INTEGER", default=0),
        Column("learned_skills", "TEXT", default="[]"),
        Column("hidden_class_unlock", "TEXT", default="[]"),
        Column("shortcuts", "TEXT", default="{}"),
        Column("evolve_path", "INTEGER", default=0),
        Column("skill_levels", "TEXT", default="{}"),
        Column("learned_blueprints", "TEXT", default="[]"),
        Column("lucky_until", "INTEGER", default=0),
        Column("stamina", "INTEGER", default=100),               # v94 体力系统
        Column("stamina_ts", "INTEGER", default=0),
        Column("created_at", "INTEGER"),
        Column("last_active", "INTEGER"),
        Column("race", "TEXT", default="human"),                 # 阶段九 种族系统
        Column("gender", "TEXT", default=""),                    # v95.24 性别系统
        Column("faction", "TEXT", default=""),                   # v116 阵营国战
        Column("battle_prefs", "TEXT", default="{}"),            # v139 职业融合：战前指令偏好
        Column("investigate_date", "TEXT", default=""),          # v140 波2：副本通关后调查
        Column("investigate_count", "INTEGER", default=0),
        Column("portals", "TEXT", default="[]"),                 # 老库补列
        Column("skill_bar", "TEXT", default="[]"),               # 老库补列
        Column("skill_spent", "INTEGER", default=0),             # 老库补列
        Column("explore_wandering", "INTEGER", default=0),       # 老库补列
        Column("mounts", "TEXT", default="{}"),                  # 老库补列
        Column("equipped_title", "TEXT", default=""),            # 老库补列 · 阶段九 成就系统
        Column("deed_lv", "INTEGER", default=1),                 # 老库补列 · v84 房屋升级
        Column("world_id", "TEXT", default="mainland"),          # 老库补列 · v141 大陆隔离
        Column("apprentices", "TEXT", default="[]"),             # 老库补列 · 导师进修
        Column("deed", "TEXT", default=""),                      # 老库补列 · v68 地契
    ]),
    TableSpec("inventory", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("item_key", "TEXT", pk=True, notnull=True),
        Column("item_data", "TEXT", notnull=True),
        Column("count", "INTEGER", default=1),
    ]),
    TableSpec("quests", [
        Column("qq_id", "TEXT", pk=True),
        Column("main_quest", "TEXT"),
        Column("main_status", "TEXT", default="pending"),
        Column("main_progress", "TEXT", default="{}"),
        Column("daily", "TEXT", default="{}"),
        Column("completed_main", "TEXT", default="[]"),
        Column("side", "TEXT", default="{}"),
    ]),
    TableSpec("battle_state", [
        Column("qq_id", "TEXT", pk=True),
        Column("monster", "TEXT", notnull=True),
        Column("state", "TEXT", notnull=True),
        Column("updated_at", "INTEGER"),
    ]),
    TableSpec("achievements", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("ach_key", "TEXT", pk=True, notnull=True),
        Column("progress", "INTEGER", default=0),
        Column("claimed", "INTEGER", default=0),
    ]),
    TableSpec("stats", [
        Column("qq_id", "TEXT", pk=True),
        Column("kills", "INTEGER", default=0),
        Column("elite_kills", "INTEGER", default=0),
        Column("boss_kills", "INTEGER", default=0),
        Column("deaths", "INTEGER", default=0),
        Column("day_kills", "INTEGER", default=0),
        Column("day_date", "TEXT", default=""),
        Column("visited_areas", "INTEGER", default=0),           # 阶段九成就计数（老库补列）
        Column("inst_clears", "INTEGER", default=0),             # 阶段九成就计数（老库补列）
        Column("party_count", "INTEGER", default=0),             # 阶段九成就计数（老库补列）
        Column("fish_count", "INTEGER", default=0),              # 阶段九成就计数（老库补列）
        Column("gather_count", "INTEGER", default=0),            # 阶段九成就计数（老库补列）
        Column("mine_count", "INTEGER", default=0),              # 阶段九成就计数（老库补列）
        Column("cook_count", "INTEGER", default=0),              # 阶段九成就计数（老库补列）
        Column("alchemy_count", "INTEGER", default=0),           # 阶段九成就计数（老库补列）
        Column("craft_count", "INTEGER", default=0),             # 阶段九成就计数（老库补列）
        Column("enhance_count", "INTEGER", default=0),           # 阶段九成就计数（老库补列）
        Column("enchant_count", "INTEGER", default=0),           # 阶段九成就计数（老库补列）
        Column("world_events", "INTEGER", default=0),            # 阶段九成就计数（老库补列）
        Column("catch_collect", "INTEGER", default=0),           # 阶段九成就计数（老库补列）
        Column("chests_opened", "INTEGER", default=0),           # 阶段九成就计数（老库补列）
    ]),
    TableSpec("reputation", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("faction", "TEXT", pk=True, notnull=True),
        Column("points", "INTEGER", default=0),
    ]),
    TableSpec("signin", [
        Column("qq_id", "TEXT", pk=True),
        Column("last_date", "TEXT", default=""),
        Column("streak", "INTEGER", default=0),
        Column("total", "INTEGER", default=0),
    ]),
    TableSpec("props_use", [
        Column("qq_id", "TEXT", pk=True),
        Column("used", "TEXT", default="{}"),
    ]),
    TableSpec("fishing", [
        Column("qq_id", "TEXT", pk=True),
        Column("total", "INTEGER", default=0),
    ]),
    TableSpec("bestiary", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("monster", "TEXT", pk=True, notnull=True),
        Column("kills", "INTEGER", default=0),
    ]),
    TableSpec("visited", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("map_id", "TEXT", pk=True, notnull=True),
    ]),
    TableSpec("visited_subareas", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("map_id", "TEXT", pk=True, notnull=True),
        Column("sa_id", "TEXT", pk=True, notnull=True),
        Column("first_at", "INTEGER"),
    ]),
    TableSpec("player_groups", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("group_id", "TEXT", pk=True, notnull=True),
        Column("first_seen", "INTEGER"),
        Column("last_active", "INTEGER"),
    ]),
    TableSpec("possessed", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("item_key", "TEXT", pk=True, notnull=True),
        Column("got_at", "INTEGER"),
    ]),

    # ---------------------------------------------- social
    TableSpec("world_event", [
        Column("id", "INTEGER", pk=True),
        Column("etype", "TEXT", notnull=True),
        Column("starts_at", "INTEGER"),
        Column("ends_at", "INTEGER"),
        Column("data", "TEXT", default="{}"),
    ]),
    TableSpec("event_state", [
        Column("key", "TEXT", pk=True),
        Column("value", "TEXT"),
    ]),
    # ★ `id INTEGER PRIMARY KEY AUTOINCREMENT` 是本形状**唯一**表达不了的性质（`Column` 只有
    #   主键/非空/默认三个性质，且主键一律渲染成表级 `PRIMARY KEY (…)`）——AUTOINCREMENT 必须
    #   内联。按形状的类型串口（`_TYPE` 白名单收 `INTEGER PRIMARY KEY AUTOINCREMENT`）逐字透传，
    #   生成的 DDL 与改前**一字不差**；同见 guilds.gid / feedback.id。
    TableSpec("market", [
        Column("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        Column("group_id", "TEXT", notnull=True),
        Column("seller", "TEXT", notnull=True),
        Column("item_key", "TEXT", notnull=True),
        Column("item_data", "TEXT", notnull=True),
        Column("price", "INTEGER", notnull=True),
        Column("listed_at", "INTEGER"),
        Column("map_id", "TEXT", default=""),                    # 老库补列 · v66 摆摊
    ]),
    TableSpec("party", [
        Column("group_id", "TEXT", pk=True, notnull=True),
        Column("leader", "TEXT", notnull=True),
        Column("member", "TEXT", pk=True, notnull=True),
        Column("created_at", "INTEGER"),
    ]),
    # ★ `name TEXT UNIQUE NOT NULL`：UNIQUE 同样是 `Column` 没有的性质，故并进类型串
    #   （`TEXT UNIQUE`）——生成的 DDL 与改前一字不差，guilds 重名仍由库拒绝。
    TableSpec("guilds", [
        Column("gid", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        Column("name", "TEXT UNIQUE", notnull=True),
        Column("leader", "TEXT", notnull=True),
        Column("icon", "TEXT", default="🏰"),
        Column("desc", "TEXT", default=""),
        Column("level", "INTEGER", default=1),
        Column("exp", "INTEGER", default=0),
        Column("created_at", "INTEGER"),
    ]),
    TableSpec("guild_members", [
        Column("gid", "INTEGER", pk=True, notnull=True),
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("role", "TEXT", default="member"),
        Column("joined_at", "INTEGER"),
        Column("contribute", "INTEGER", default=0),
        Column("sign_date", "TEXT", default=""),
        Column("task_date", "TEXT", default=""),
        Column("task_progress", "INTEGER", default=0),
    ]),
    TableSpec("pets", [
        Column("qq_id", "TEXT", pk=True),
        Column("pet_key", "TEXT", notnull=True),
        Column("name", "TEXT", notnull=True),
        Column("level", "INTEGER", default=1),
        Column("exp", "INTEGER", default=0),
        Column("satiety", "INTEGER", default=100),
        Column("bond", "INTEGER", default=0),
        Column("last_sat_time", "INTEGER", default=0),           # 24 章宠物系统（老库补列）
    ]),
    TableSpec("pet_dex", [
        Column("qq_id", "TEXT", pk=True, notnull=True),
        Column("pet_key", "TEXT", pk=True, notnull=True),
        Column("hatched", "INTEGER", default=0),
    ]),
    TableSpec("feedback", [
        Column("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        Column("qq_id", "TEXT", notnull=True),
        Column("group_id", "TEXT", default=""),
        Column("content", "TEXT", notnull=True),
        Column("created_at", "TEXT", notnull=True),
        Column("status", "TEXT", default="new"),
        Column("reply", "TEXT", default=""),                     # 老库补列 · 意见回复
    ]),

    # ---------------------------------------------- professions
    TableSpec("professions", [
        Column("qq_id", "TEXT", pk=True),
        Column("gather_lv", "INTEGER", default=1),
        Column("gather_exp", "INTEGER", default=0),
        Column("mining_lv", "INTEGER", default=1),
        Column("mining_exp", "INTEGER", default=0),
        Column("fishing_lv", "INTEGER", default=1),
        Column("fishing_exp", "INTEGER", default=0),
        Column("alchemy_lv", "INTEGER", default=1),
        Column("alchemy_exp", "INTEGER", default=0),
        Column("craft_lv", "INTEGER", default=1),
        Column("craft_exp", "INTEGER", default=0),
        Column("cooking_lv", "INTEGER", default=1),
        Column("cooking_exp", "INTEGER", default=0),
        Column("enhance_lv", "INTEGER", default=1),              # 导师进修独立副业
        Column("enhance_exp", "INTEGER", default=0),
        Column("enchant_lv", "INTEGER", default=1),
        Column("enchant_exp", "INTEGER", default=0),
        Column("fish_king", "INTEGER", default=0),
        Column("explore_wandering", "INTEGER", default=0),
        Column("activated", "TEXT", default="[]"),               # 老库补列 · v67 双副业
    ]),

    # -------------------------------- identity：平台身份映射（2026-09-07 QQ官方 bot 迁移）
    # 场景：AstrBot 从 NapCat(OneBot/QQ号体系) 切到 QQ 官方 API(botpy/openid 体系)。
    # 官方 API 只给 openid，不给 QQ 号 → dragonfall 玩家表仍以 QQ 号为主键，
    # 建 openid ↔ qq_id 双向映射，命令层拿到 openid 时翻译回 QQ 号（改库/改命令皆不用动）。
    TableSpec("identity_map", [
        Column("openid", "TEXT", pk=True),
        Column("qq_id", "TEXT", notnull=True),
        Column("platform", "TEXT", default="qq_official"),
        Column("bind_time", "INTEGER", default=0),
    ], migrations=[_identity_index]),
]


# ================= 建表注册（逐表 declare：建表 + 缺列自愈 + init）=================
def install(db):
    """把表结构声明注册到**注入的连接骨架**上（宿主工厂调一次；幂等）。

    改前：注册 4 段手写 DDL + 一个老库补列迁移器，由调用方的 `init_db()` 建表。
    改后：逐表 `declare(db, spec)` —— 引擎从同一份声明派生建表 SQL 与补列迁移，
    并当场 `db.init()`（自带幂等；调用方随后的 `init_db()` 是重复无害）。
    """
    for spec in _SPECS:
        declare(db, spec)
    flush_log("persistence.schema：已声明 %d 张表（Column/TableSpec/declare；db=%s）"
              % (len(_SPECS), _db_path_of(db)))
    return db


def _db_path_of(db):
    return getattr(db, "path", "?")
