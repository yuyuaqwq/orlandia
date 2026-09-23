# -*- coding: utf-8 -*-
"""包内公会域（`content/social_guild.py`）—— 公会编排逻辑 + 公会面板，真源搬入。

真源（游戏仓 `qqbot/data/plugins/dragonfall`，**只读**）
--------------------------------------------------------
| 真源 | 行数 | 本文件搬什么 |
|---|---:|---|
| `game/services/guild.py` | 275 | **全文件**：建会/入会/退会/解散/签到/任务/捐献/排行/任命/免职/击杀推进 |
| `game/commands/social.py:620-652 guild_info` | — | 面板主体（成员分页行；tip/记账留在命令层） |
| `game/commands/social.py:734-804 guild_shop + _guild_shop_buy` | — | 商店面板 + 购买（扣积分/限购/发货） |
| `game/commands/social.py:809-827 guild_skill_view` | — | 技能面板（展示） |

宿主耦合替身（**只改两类东西**：① 存储层/读表口 ② 配置读口）
--------------------------------------------------------------
| 真源写法 | 包内写法 | 说明 |
|---|---|---|
| `from .. import db` + `db.xxx(...)` | 模块级 `db` = **惰性宿主代理** `_HostDB`（属性访问时才解析宿主模块） | 正文里 `db.xxx(...)` **一行未改**；宿主由 `bind_host(db)` 注入，或按 `sys.modules` 找**已加载**的宿主模块（绝不 import，防包侧另起一份宿主模块树） |
| `from ..store.social import guild_get_member / guild_set_role / guild_spend_contribute`（不在 `db` 门面上） | `_store_social()`（注入优先 → ★ REPOINT-PKG 起兜底**包内直取** `content/persistence/social.py`） | 这三个原语在宿主 `game/store/social.py`（= `from content.persistence.social import *` 的委托薄壳 ⇒ 同一批函数对象）；`game/db.py` 聚合面没导出 |
| `from .. import content as C` + `C.GUILD_CONFIG` | `_cfg()`（`bind_host(config=…)` 注入优先 → ★ W4 兜底改**包内门面** `content/catalog_b143.py:GUILD_CONFIG`） | 数值配置仍由宿主薄壳注入（L7 配置面）；原兜底读宿主 `game.data.guild.GUILD_CONFIG` 已切门面（门禁逐键逐值相等）⇒ `game/data` 删后本模块仍可活 |
| `from ..data import guild as _G` + `_G.GUILD_ROLES / GUILD_SHOP_ITEMS / GUILD_SKILLS` | 读包内 `content/data/guild.json`（`guild_roles()` / `guild_shop_items()` / `guild_skills()`） | 域真源 = `game/data/guild.py`，单向导出器 `scripts/export_domains/b9_social.py:derive_guild` |
| 真源手写「公会任务进度跨天归零」（读 task_date，不等于今天就当 0；面板与击杀推进**两处各写一遍**） | `_task_window(gid, qq_id)` = 引擎 `ext_social.membership.Contribution`（`window="day"`，`period_key=_today`） | ★ PKG-G：**按日窗口累计**的换桶语义归引擎 —— 跨天自然读不到旧桶，不用再手写 if；账本 = 内容侧给的 MutableMapping |

⚠️ 读表坑：`guild.json` 的 `shop_items` 键是**字符串化整数**（JSON 只有字符串键，真源是 int 1..6）→
`guild_shop_items()` 读时**还原 int**。不还原 = `get(编号)` 恒 None = 「公会商店 1」全部报
「没有第 N 件商品」（与 `content/tables.py:ENHANCE_TABLE` 同族坑）。

返回结构（与真源逐字段/逐字一致）
----------------------------------
`guild_create_check(player)` → `(ok, err)`；`guild_create(...)` → `(ok, gid, err)`；
`guild_join(...)` → `(ok, g, err)`；`guild_leave_check(g, qq_id)` → `(blocked, msg)`；
`guild_sign(...)` → `(ok, lines, err)`；`guild_task_view(...)` → `(ok, lines, err)`；
`guild_donate(...)` → `(ok, lines, err, need, total)`；`guild_rank_lines()` → `list[str]`；
`guild_find_member(...)` → `(member, target, err)`；`guild_appoint(...)` → `(label, icon)`；
`guild_kill_progress(...)` → `(changed_lines, rewarded)`（combat 击杀结算侧消费）。
本包新搬的三个命令级函数返回**待 yield 的消息 list**（命令层只做「取玩家 → 调包 → yield」）：
`guild_shop_buy(...)` → `list[str]`；`guild_info_lines(...)` / `guild_shop_lines(...)` /
`guild_skill_lines(...)` → 面板行 `list[str]`（tip / `_record_list_state` 由命令层补）。

用法::

    from content import social_guild as SG
    SG.bind_host(db, config=C.GUILD_CONFIG)          # 宿主薄壳在 import 期注入
    ok, gid, err = SG.guild_create(group_id, qq_id, player, name)
"""
from __future__ import annotations

import datetime

# ★ W4（2026-09-14）：`C.GUILD_CONFIG` 兜底 → 包内门面（真源 `game/data/guild.py:3`）
from . import catalog_b143 as _cat_b143
from . import texts as _T          # 文案表（C 档 12）

# ★ PKG-G：贡献账本形状（引擎 `membership.Contribution`）——按日窗口累计 / 跨窗口换桶
from ext_social.membership import Contribution

# ============================================================
# ① 宿主替身口（存储层 / 公会原语 / 数值配置）
# ============================================================
from saintess_engine.wire import Wire

#: 注入句柄面（`bind_host()` 写；`None` = 没给）——槽名 = `bind_host` 形参名
_WIRE = Wire()

from ._hostref import make_bound_host  # 取件工厂单源（P0-3；常量本身不再被本文件引用）
from ._domainio import int_keys as _int_keys          # P0-4 域读口单源
from ._domainio import read_data_json_strict


def bind_host(db=None, config=None, store_social=None):
    """宿主替身注入（幂等；宿主薄壳在 import 期调用）。

    - `db`：存储层模块（`game/db.py` 门面）
    - `config`：`GUILD_CONFIG` dict（L7 配置面，本域不搬）
    - `store_social`：`game.store.social` 模块（公会原语不在 `db` 门面上）
    """
    _WIRE.bind(db=db, config=config, store_social=store_social)


_bound_host = make_bound_host(_WIRE, "social_guild")


class _HostDB:
    """惰性宿主存储层代理（真源 `from .. import db`）——`db.xxx` 正文不动，属性访问时解析。"""

    def __getattr__(self, name):
        return getattr(_bound_host("db"), name)


db = _HostDB()


def _store_social():
    """公会三个原语（`guild_get_member` / `guild_set_role` / `guild_spend_contribute`）。

    ★ REPOINT-PKG（2026-09-15，B4R B 组第 5 项）：兜底由「宿主子模块 `game.store.social`」
      改为**包内直取** `content/persistence/social.py`（B17 已整域进包；宿主
      `game/store/social.py` 只剩 `from content.persistence.social import *` 的委托薄壳
      ⇒ 同一批函数对象）。注入槽 `bind_host(store_social=…)` 原样保留；
      取件时机 = 调用时（与旧取件口口径一致）。
    """
    _ss = _WIRE.handles().get("store_social")
    if _ss is not None:
        return _ss
    from .persistence import social as _pkg_social   # 包内直取（调用时取件，与旧口径同时机）
    return _pkg_social


def _cfg():
    """`GUILD_CONFIG`（注入优先 → 包内门面 `content/catalog_b143.py`；真源 `game/data/guild.py:3`）。"""
    _inj = _WIRE.handles().get("config")
    if _inj is not None:
        return _inj
    return _cat_b143.GUILD_CONFIG


# ============================================================
# ② 读表口：包内 `guild` 域（真源 `game/data/guild.py`）
# ============================================================
_DOMAIN = None

# 职位词 → role key（真源 `game/services/guild.py:195 ROLE_MAP`，逻辑常量，不是数据表）
ROLE_MAP = {"副会长": "vice_leader", "精英": "elite"}
# 可任命目标职位（真源同名单：真源 `game/services/guild.py:196 APPOINTABLE_ROLES`；
# 与域里 `roles.appointable` 同源，域是权威 → 本常量只作无域时的兜底说明，不在判定里用）
APPOINTABLE_ROLES = ("vice_leader", "elite")


def _domain() -> dict:
    global _DOMAIN
    if _DOMAIN is None:
        _DOMAIN = read_data_json_strict("guild.json", "guild", "静默无职位/无商店")
    return _DOMAIN


def guild_roles() -> dict:
    """`{role: [职位名, 图标]}`（真源 `GUILD_ROLES`；真源是 tuple，JSON 落 list —— 解包语义同）。"""
    return dict((_domain().get("roles") or {}).get("map") or {})


def guild_shop_items() -> dict:
    """公会商店 `{编号(int): 条目}`（⚠️ 键还原 int，见模块 docstring）。"""
    return _int_keys(_domain().get("shop_items") or {})


def guild_skills() -> dict:
    """公会技能 `{技能 key: 条目}`（真源 `GUILD_SKILLS`）。"""
    return dict(_domain().get("skills") or {})


# ============================================================
# ③ 公会编排（真源 `game/services/guild.py` 逐字；只把 import 换成上面的替身）
# ============================================================

def _today():
    return datetime.date.today().isoformat()


def _task_window(gid, qq_id) -> Contribution:
    """公会任务进度的账本（引擎 `membership.Contribution`）——按**日窗口**累计。

    真源手写「跨天归零」（读 `task_date`，不等于今天就当 0），面板与击杀推进**两处各写一遍**；
    引擎的窗口语义把「换桶」交给 `period_key()`（= 今天）——跨天自然读不到旧桶，
    不用再写 if（`Contribution` 的窗口语义，见引擎 `membership/contribution.py`）。
    账本 = 内容侧给的 MutableMapping：此处由存档行（`task_date` / `task_progress`）投影而来；
    `task_date` 不是今天 → 今天的桶不存在 → 读到 0（与旧「归零」同义）。
    """
    tdate, tprog = db.guild_get_task(gid, qq_id)
    return Contribution({"day": {str(tdate): {str(qq_id): tprog}}}, _today)


def _is_leader(g, qq_id):
    return str(g.get("leader")) == str(qq_id)


def guild_get_member(gid, qq_id):
    """公会成员行取值（包内 `content/persistence/social.py` 直取；不在 `db` 门面上）。"""
    return _store_social().guild_get_member(gid, qq_id)


def guild_create_check(player):
    """创建公会前置校验（纯读）：返回 (ok, err)。已入会/等级/金币门槛在调用方查完再进。

    注意：『已在一个公会』校验依赖 db.guild_get_by_member(qq_id)，由命令层先查后调
    （本函数收 player 快照避免重复读）。返回 ok=False 时 err 为可直接 yield 的拒绝文案。
    """
    cfg = _cfg()
    if player["level"] < cfg["create_level"]:
        return False, _T.text("guild.err_level", need=cfg['create_level'], cur=player['level'])
    if player["gold"] < cfg["create_cost"]:
        return False, _T.text("guild.err_gold", need=cfg['create_cost'], have=player['gold'])
    return True, None


def guild_create(group_id, qq_id, player, name):
    """创建公会：扣金币 → 建会。返回 (ok, gid, err)。

    - guild_create 重名返回 None → err='已存在' 文案。
    - 成功后扣 create_cost 金币（v105 M18 P2：成就判定由命令层在成功后做）。
    """
    cfg = _cfg()
    gid = db.guild_create(name, qq_id, desc=_T.text("guild.default_desc", name=player['name']))
    if not gid:
        return False, None, _T.text("guild.name_taken", name=name)
    db.update_player(group_id, qq_id, gold=player["gold"] - cfg["create_cost"])
    return True, gid, None


def guild_join(group_id, qq_id, name):
    """加入公会：按名查会 → 入会。返回 (ok, g, err)。成功 g=公会 dict（命令层取 g['name'] 拼文案）。"""
    g = db.guild_get_by_name(name)
    if not g:
        return False, None, _T.text("guild.not_found", name=name)
    db.guild_join(g["gid"], qq_id)
    return True, g, None


def guild_leave_check(g, qq_id):
    """退出公会前置守卫：会长不能直接退会（须解散）。返回 (blocked, msg)。"""
    if _is_leader(g, qq_id):
        # v105 M18 P2：全仓无『转让会长』命令，提示只指向真实命令，避免误导
        return True, _T.static("guild.leader_leave")
    return False, None


def guild_leave(g, qq_id):
    """退出公会（db.guild_leave：leader 离开即解散，由 store 原语处理）。"""
    db.guild_leave(g["gid"], qq_id)


def guild_disband(g, qq_id):
    """解散公会（leader 离开即解散）。"""
    db.guild_leave(g["gid"], qq_id)  # leader 离开即解散


def guild_sign(group_id, qq_id, g):
    """公会签到（每日一次）：写签到日期 → 公会经验/个人贡献/金币。

    返回 (ok, lines, err)。ok=False 时 err=拒绝文案（今日已签/无公会由调用方先查）。
    数值全部来自 GUILD_CONFIG（sign_exp/sign_contribute/sign_gold）。
    """
    cfg = _cfg()
    today = _today()
    if db.guild_get_sign(g["gid"], qq_id) == today:
        return False, None, _T.static("guild.sign_done")
    db.guild_set_sign(g["gid"], qq_id, today)
    db.guild_add_exp(g["gid"], cfg["sign_exp"], member_qq=qq_id, contribute=cfg["sign_contribute"])
    player = db.get_player(group_id, qq_id)
    db.update_player(group_id, qq_id, gold=(player or {}).get("gold", 0) + cfg["sign_gold"])
    return True, [
        _T.text("guild.sign_ok", name=g['name'], exp=cfg['sign_exp'], contrib=cfg['sign_contribute'],
            gold=cfg['sign_gold'])
    ], None


def guild_task_view(group_id, qq_id, g):
    """公会任务面板（击杀型，跨天重置）：返回 (ok, lines, err)。

    击杀自动推进由 combat 侧调 guild_kill_progress；此处仅读当前进度。
    跨天重置 = `_task_window`（引擎 `Contribution` 的日窗口换桶），不再手写日期比较。
    """
    need = _cfg()["kill_task"]
    tprog = _task_window(g["gid"], qq_id).of(qq_id, window="day")
    if tprog >= need:
        return False, None, _T.static("guild.task_done")
    return True, [
        _T.text("guild.task_panel", need=need, cur=tprog, need2=need)
    ], None


def guild_donate_inventory(group_id, qq_id):
    """公会捐献可上交材料清单（v46 材料统一 mat_ 前缀；v104R3 P1-3 排除任务道具）。"""
    return [it for it in db.get_inventory(group_id, qq_id)
            if it["key"].startswith("mat_") and it["data"].get("type") != "任务道具"]


def guild_donate_total(mats):
    return sum(it["count"] for it in mats)


def guild_donate(group_id, qq_id, g):
    """公会捐献（每日一次，event_state 记日期）：够料则扣料 → 公会经验/贡献/金币。

    返回 (ok, lines, err, need, total)：ok=False 时 err=拒绝/不足文案（含 need/total 供面板）。
    扣料顺序：从背包靠前的材料开始扣（与旧命令层逐项 remove_item 等价）。
    """
    cfg = _cfg()
    need = cfg["donate_items"]
    key = f"guild_donate:{g['gid']}:{qq_id}"
    if db.get_event_state(key) == _today():
        return False, None, _T.static("guild.donate_done"), need, None
    mats = guild_donate_inventory(group_id, qq_id)
    total = guild_donate_total(mats)
    if total < need:
        return False, None, _T.text("guild.donate_need", need=need, cur=total, need2=need), need, total
    remain = need
    for it in mats:
        if remain <= 0:
            break
        take = min(it["count"], remain)
        db.remove_item(group_id, qq_id, it["key"], take)
        remain -= take
    db.guild_add_exp(g["gid"], cfg["task_exp"], member_qq=qq_id, contribute=cfg["task_contribute"])
    player = db.get_player(group_id, qq_id)
    db.update_player(group_id, qq_id, gold=(player or {}).get("gold", 0) + cfg["task_gold"])
    db.set_event_state(key, _today())
    return True, [
        _T.text("guild.donate_ok", need=need, exp=cfg['task_exp'], contrib=cfg['task_contribute'],
            gold=cfg['task_gold'])
    ], None, need, total


def guild_rank_lines():
    """公会排行榜行（db.guild_top(10)）。无公会时返回 []（命令层给空榜文案）。"""
    tops = db.guild_top(10)
    if not tops:
        return []
    lines = [_T.static("guild.rank_title"), "━━━━━━━━━━━━"]
    for i, g in enumerate(tops, 1):
        lines.append(_T.text("guild.rank_row", i=i, icon=g['icon'], name=g['name'], lv=g['level'],
                         members=g['members']))
    return lines


def guild_appoint_check_role(role_arg):
    """职位词 → role key；不支持返回 None（命令层给『可任命职位』文案）。"""
    return ROLE_MAP.get(role_arg)


def guild_appoint_level_ok(g, role):
    """任命等级门槛：副会长需公会 Lv.3（GUILD_CONFIG.vice_leader_level），精英无门槛。

    返回 (ok, err)：ok=False 时 err 为可直接 yield 的文案（含门槛值与当前公会等级）。
    """
    cfg = _cfg()
    if role == "vice_leader" and g["level"] < cfg.get("vice_leader_level", 3):
        return False, _T.text("guild.vice_lv", need=cfg.get('vice_leader_level', 3), cur=g['level'])
    return True, None


def guild_find_member(g, target_name):
    """按玩家名查公会成员。返回 (member, target, err)：

    - 查无此玩家 → err='没找到玩家' 文案；
    - 玩家不在本公会 → err='不在本公会' 文案（member=None, target 有值）。
    """
    target = db.find_player_by_name(target_name)
    if not target:
        return None, None, _T.text("guild.no_player", name=target_name)
    tm = guild_get_member(g["gid"], target["qq_id"])
    if not tm:
        return None, target, _T.text("guild.not_in_guild", name=target['name'])
    return tm, target, None


def guild_appoint(g, target, role):
    """执行任命（写 role）。返回 (label, icon)（命令层拼晋升文案）。"""
    _store_social().guild_set_role(g["gid"], target["qq_id"], role)
    return tuple(guild_roles()[role])


def guild_demote(g, target):
    """执行免职（降回 member）。"""
    _store_social().guild_set_role(g["gid"], target["qq_id"], "member")


# ---- 公会任务击杀推进（combat 击杀结算侧消费；跨天重置 v43）----


def guild_kill_progress(group_id, qq_id, g, lines=None):
    """击杀推进公会任务：跨天重置 → +1 → 达标发奖（公会经验/贡献/金币）。

    返回 (changed_lines, rewarded)：changed_lines 为击杀侧要追加的战斗结算行
    （进度行或完成行），rewarded=True 表示本次击杀达成任务并已发奖。
    无公会成员资格（g=None）返回 ([], False)。v43：跨天重置而非跳过。
    """
    cfg = _cfg()
    _win = _task_window(g["gid"], qq_id)
    tprog = _win.of(qq_id, window="day")     # 跨天：今天的桶为空 → 0（换桶归引擎）
    if tprog < cfg["kill_task"]:
        tprog = _win.add(qq_id, 1, window="day")
        db.guild_set_task(g["gid"], qq_id, _today(), tprog)
        if tprog >= cfg["kill_task"]:
            db.guild_add_exp(g["gid"], cfg["task_exp"], member_qq=qq_id, contribute=cfg["task_contribute"])
            # v105 M18 P2：先刷新 player 再写金币——player dict 在战斗结算中段刷新后，
            # _rule_fire("battle_win")（Boss 巢穴私藏金币等 loot_gold 彩蛋）可能已落库加金币，
            # 直接用旧 dict 值覆盖会丢掉同场彩蛋金币
            player = db.get_player(group_id, qq_id)
            db.update_player(group_id, qq_id, gold=(player or {}).get("gold", 0) + cfg["task_gold"])
            return [_T.text("guild.kill_done", need=cfg['kill_task'], exp=cfg['task_exp'],
                        contrib=cfg['task_contribute'], gold=cfg['task_gold'])], True
        return [_T.text("guild.kill_progress", cur=tprog, need=cfg['kill_task'])], False
    return [], False


# ============================================================
# ④ 面板/购买（真源 `game/commands/social.py` 的公会命令编排）
# ============================================================

def guild_info_lines(group_id, g, members, page_items, page, pages, player_lookup,
                     exp_need, per_page=5):
    """公会面板**主体行**（真源 `social.py:633-649`）。

    真源在命令层用 `self._player` 查成员名、`self._page_items` 分页、`self._tip` 补提示、
    `self._record_list_state` 记账 —— 分页/提示/记账留在命令层（通用底座 + IO），
    本函数收「已分页好的 page_items」与 `player_lookup` 回调，只拼主体行。

    `exp_need` = 升级所需经验（真源命令层 `g["level"] * GUILD_EXP_BASE`；该常量包内**已有门面**
    `content/catalog_core.py:GUILD_EXP_BASE`，但按 B14-2 L6 派工本域不搬数据 → 由命令层算好传入）。

    返回 `list[str]`（未含 tip 行）。
    """
    roles = guild_roles()
    count = len(members)
    lines = [
        _T.text("guild.title", icon=g['icon'], name=g['name'], level=g['level']),
        "━━━━━━━━━━━━",
        _T.text("guild.members", count=count, exp=g['exp'], need=exp_need),
        _T.text("guild.desc", desc=g['desc'] or '暂无宣言'),
        _T.text("guild.exp_bonus", pct=guild_exp_bonus_pct(g)),
        "━━━━━━━━━━━━",
        _T.text("guild.member_head", page=page, pages=pages),
    ]
    for i, m in enumerate(page_items, (page - 1) * per_page + 1):
        p = player_lookup(group_id, m["qq_id"])
        _label, _icon = roles.get(m["role"], ("成员", "⚔️"))
        name = p["name"] if p else m["qq_id"]
        lines.append(_T.text("guild.member_row", i=i, icon=_icon, name=name, label=_label,
                         lv=p['level'] if p else '?', contribute=m['contribute']))
    lines.append("")
    if pages > 1 and page < pages:
        lines.append(_T.text("guild.next_tip", next=page+1, pages=pages))
    return lines


def guild_exp_bonus_pct(g):
    """公会等级 → 打怪经验加成百分比（真源 `social.py:638` 的 min(int(…), int(…)) 原式）。

    真源：`min(int(g['level'] * C.GUILD_CONFIG['exp_bonus_per_level'] * 100), int(C.GUILD_CONFIG['max_bonus'] * 100))`
    —— 浮点乘算与取整次序**逐字保留**（改次序会改变边界等级上的取值）。
    """
    cfg = _cfg()
    return min(int(g["level"] * cfg["exp_bonus_per_level"] * 100), int(cfg["max_bonus"] * 100))


def guild_shop_lines(g, member):
    """公会商店面板行（真源 `social.py:755-763`；`_tip` 由命令层补）。"""
    contribute = member.get("contribute", 0)
    lines = [_T.text("guild.shop_title", lv=g['level'], points=contribute), "━━━━━━━━━━━━"]
    for i, it in guild_shop_items().items():
        locked = g["level"] < it["min_level"]
        tag = "🔒" if locked else _T.text("guild.shop_cost", cost=it['cost'])
        lines.append(_T.text("guild.shop_row", i=i, name=it['name'], tag=tag))
        limit = _T.text("guild.shop_limit_daily", n=it['daily_limit']) if it.get("daily_limit") else _T.static("guild.shop_no_limit")
        lines.append(_T.text("guild.shop_row2", desc=it['item_data'].get('desc', ''), lv=it['min_level'],
                         limit=limit))
    lines.append("━━━━━━━━━━━━")
    return lines


def guild_shop_buy(group_id, qq_id, g, member, num):
    """公会商店购买：扣成员贡献积分 → 发包件物品。返回**待 yield 的消息 list**（真源逐字）。

    真源 `game/commands/social.py:766-804 _guild_shop_buy`（每个分支 yield 一条 → 本函数返回
    单元素 list，命令层 `for ln in …: yield`）。每日限购用 event_state 记录 key（非 schema 改动）。
    """
    _dt = datetime
    it = guild_shop_items().get(num)
    if not it:
        return [_T.text("guild.shop_no_item", num=num)]
    if not member:
        return [_T.static("guild.not_member")]
    if g["level"] < it["min_level"]:
        return [_T.text("guild.shop_lv_low", name=it['name'], need=it['min_level'], cur=g['level'])]
    contribute = member.get("contribute", 0)
    if contribute < it["cost"]:
        return [_T.text("guild.shop_points_low", name=it['name'], need=it['cost'], have=contribute)]
    # 每日限购（用 event_state 记录 key，非 schema 改动）
    if it.get("daily_limit"):
        today = _dt.date.today().isoformat()
        key = f"guild_shop:{g['gid']}:{qq_id}:{num}"
        if db.get_event_state(key) == today:
            return [_T.text("guild.shop_limit_hit", name=it['name'], limit=it['daily_limit'])]
    # 正式扣积分（贡献充足性在事务内复核）
    if not _store_social().guild_spend_contribute(g["gid"], qq_id, it["cost"]):
        return [_T.static("guild.shop_spend_fail")]
    # v116 审计修复 A0-A1：直接使用 GUILD_SHOP_ITEMS 的稳定 item_key（gs_*），
    # 去掉随机 uuid 后缀——否则 stackable 商品每次购买生成新 key，永不合并堆叠。
    # 商品 key 全表唯一，此处直接引用即可（add_item 按其 key 堆叠合并）。
    item_key = it.get("item_key", "gs_")
    db.add_item(group_id, qq_id, item_key, it["item_data"], count=1)
    if it.get("daily_limit"):
        db.set_event_state(f"guild_shop:{g['gid']}:{qq_id}:{num}", _dt.date.today().isoformat())
    return [
        _T.text("guild.shop_buy_ok", name=it['name'], cost=it['cost'], msg=it.get('msg', ''))
    ]


def guild_skill_lines(g):
    """公会技能面板行（真源 `social.py:819-826`；`_tip`/开发中提示由命令层补）。"""
    lines = [_T.text("guild.skill_title", lv=g['level']), "━━━━━━━━━━━━"]
    for key, sk in guild_skills().items():
        lines.append(_T.text("guild.skill_row", name=sk['name'], desc=sk['desc'], max=sk['max_level']))
        costs = " → ".join(str(c) for c in sk["level_costs"][1:])
        requires = " → ".join(f"Lv.{l}" for l in sk["level_guild_lv"][1:])
        lines.append(_T.text("guild.skill_req", costs=costs, requires=requires))
    lines.append("━━━━━━━━━━━━")
    return lines
