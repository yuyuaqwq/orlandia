# -*- coding: utf-8 -*-
"""《奥兰迪亚·余烬纪年》GM/运营指令（`content/gm.py`）—— B9 线 L6 宿主薄壳化落点

真源（游戏仓 `dragonfall/`，**只读，本批零改动**）：`game/commands/gm.py`（857 行）。

搬了什么（逐字搬真源正文，只动「宿主取件」一类）
------------------------------------------------
    权限判定 gm_auth（真源 `GmCmds._gm_auth`）           ·
    目标解析 resolve_target（`_resolve_target`）         · 物品查找 find_item（`_find_item`）
    地图查找 find_map（`_find_map`）                     · 传送落点 default_subarea（`_default_subarea`）
    停服/开服/状态/广播 maintenance·open_server·status_text·broadcast
    玩家列表 players_text（`gm_players`）                · 玩家详情 query_text（`gm_query`）
    发金币/发物品/发经验/设等级/传送/体力/改名（`gm_give_*`·`gm_set_*`·`gm_teleport`·`gm_stamina`·`gm_rename`）
    GM 白名单 add_gm·del_gm（`gm_加GM`/`gm_删GM` + `_load_wl`/`_save_wl`）
    世界 Boss 伤害倍率 boss_dmg（`gm_伤害`）             · 帮助串 help_text（`gm_帮助`，逐字整段）

**没搬（宿主边界，逐条给理由）**
------------------------------------------------
| 真源 | 为什么不搬 |
|---|---|
| `_gm_auth` 的**调用点**（每条指令开头的 4 行守卫） | 命令层注册/守卫形状，属宿主（`_is_gm`/`_gm_whitelist` 真源在共享的 `commands/base.py`，禁改） |
| `gm_play`（`_run_shortcut` 转发指令） | 走宿主注册表/平台事件回环，非游戏内容 |
| `gm_spy` + `_chunk_text`/`_spy_to_role_cards`/`_spy_to_forward_nodes` | **调试/运维管道**：读 playtest 实录 md、拼 NapCat 合并转发节点、`context.send_message` 投递、写 `.spy_forward_state.json` —— 平台接人层（BRIEF §2.8：调试逻辑不进包） |
| `gm_bind_identity` / `gm_identity_table` | **平台身份**接人层：`event.get_sender_id()` 的 openid ↔ QQ 映射（`commands/_identity.py`），与游戏内容无关 |
| `GM_OWNER_QQ` / `_OWNER_GROUP` / `_PLATFORM_PREFIX` / `_SPY_DIR` | 平台配置常量（同上） |

宿主侧薄壳 = `game/commands/gm.py`：只留「命令注册（`@declared`）+ 取玩家/取参数（`_uid`/
`_strip_cmd`）+ 守卫 + 调包 + `yield event.plain_result(...)` 渲染」，含上面四类接人层。

宿主服务句柄 `host`（= 调用方传入，宿主薄壳 `_host()` 构造）
------------------------------------------------------------
    host.db                 宿主 `game.db`（存储层）
    host.C                  宿主 `game.content` 薄聚合层（B14-2 起只剩 `display` 函数；
                            ITEMS / MAPS / MAP_BY_ID 已切包内门面 catalog_{items,space}）
    host.player_final_stats 宿主 `game/content_rules/panel.player_final_stats`（`gm_设等级` 重算）
    host.panel_bonus        `(group_id, qq_id) -> dict`（宿主壳 `_panel_bonus`）

分页器直接用引擎 `saintess_engine.command.page_items`（真源 `self._page_items` 即它的转发壳）。
"""
from __future__ import annotations

import json
import time

from saintess_engine.command import page_items
from saintess_engine.records import rebuild_views

# B14-2（L7 线）：数据名读点切包内门面 —— 原 `host.C.<名>` 直取换成门面同名绑定；
# `host.C` 仍保留给 `display`（函数，无门面，见头注）。
from .catalog_items import ITEMS            # 真源 `host.C.ITEMS`
from .catalog_space import MAPS, MAP_BY_ID  # 真源 `host.C.MAPS` / `host.C.MAP_BY_ID`
from . import texts as _T                   # 文案表（C 档 12）


# ============ 权限 / 目标解析 / 查找（真源 GmCmds 内部方法） ============

def gm_auth(is_gm, whitelist, qq_id):
    """返回 (ok, 错误消息)。白名单命中(库∪env)或 gm_ 测试身份放行。
    v104.1 M24 修复：白名单为空(库∪env 均未配置)时默认拒绝一切 GM 指令，
    不再回退私聊放行——防止任意私聊用户 gm_发金币/gm_设等级/gm_加GM 自举提权。"""
    if is_gm(qq_id):
        return True, ""
    if whitelist():
        return False, _T.static("gm.auth_deny")
    return False, _T.static("gm.auth_unset")


def resolve_target(host, raw: str):
    """解析 GM 指令的目标玩家：纯数字 → qq_id；否则先按角色名、再按 qq_id 精确匹配。
    返回 (qq_id, 显示名) 或 (None, 错误消息)。"""
    db = host.db
    raw = (raw or "").strip()
    if not raw:
        return None, _T.static("gm.usage_target")
    if raw.isdigit():
        p = db.get_player("", raw)
        if not p:
            return None, _T.text("gm.target_no_qq", raw=raw)
        return raw, p.get("name") or raw
    hit = db.find_player_by_name(raw)
    if hit:
        return hit["qq_id"], hit["name"]
    # 名字查不到 → 回退按 qq_id 精确匹配（测试号/特殊 ID 场景）
    p = db.get_player("", raw)
    if p:
        return raw, p.get("name") or raw
    return None, _T.text("gm.target_no_name", raw=raw)


def find_item(host, name: str):
    """按名称查找物品定义(材料/消耗品)，返回 (item_key, item_data) 或 None。"""
    for k, v in ITEMS.items():
        if v.get("name") == name:
            return k, dict(v)
    # 模糊包含匹配（唯一时才用）
    hits = [(k, v) for k, v in ITEMS.items() if name in (v.get("name") or "")]
    if len(hits) == 1:
        return hits[0][0], dict(hits[0][1])
    return None, None


def find_map(host, name: str):
    """按名称/别名查找地图，返回 map_id 或 None。"""
    for m in MAPS:
        if m.get("name") == name or name in (m.get("alias") or []):
            return m["id"]
    hits = [m for m in MAPS if name in (m.get("name") or "")]
    if len(hits) == 1:
        return hits[0]["id"]
    return None


def default_subarea(host, mid: str) -> str:
    """gm_传送落点：优先广场，其次第一个非出口子区域；无子区域 → 空。"""
    m = MAP_BY_ID.get(mid, {})
    subs = m.get("subareas") or []
    for sa in subs:
        if sa.get("type") != "城镇出口" and "广场" in sa.get("name", ""):
            return sa["id"]
    for sa in subs:
        if sa.get("type") != "城镇出口":
            return sa["id"]
    return ""


# ============ 停服 / 开服 / 状态 / 广播 ============

def maintenance(host, raw: str):
    """gm_停服：写停服状态 + 返回 (玩家回执, 全服广播文本)。"""
    db = host.db
    db.set_event_state("server_maintenance", "1")
    db.set_event_state("server_maintenance_msg", raw)
    text = (
        _T.static("gm.maint_head") + (_T.text("gm.notice_prefix", text=raw) if raw else "") +
        _T.static("gm.maint_tail")
    )
    broadcast = (
        _T.static("gm.maint_bc_head")
        + (f"📢 {raw}\n" if raw else "")
        + _T.static("gm.maint_bc_tail")
    )
    return text, broadcast


def open_server(host, was_down: bool):
    """gm_开服：清停服状态 + 返回 (玩家回执, 全服广播文本或 None)。"""
    db = host.db
    db.delete_event_state("server_maintenance")
    db.delete_event_state("server_maintenance_msg")
    text = (_T.static("gm.open_ok")
            if was_down else _T.static("gm.open_noop"))
    return text, (_T.static("gm.open_bc") if was_down else None)


def status_text(host, group_id, down: bool, msg: str, gms) -> str:
    """gm_状态：服务器状态/玩家数/最高等级/GM 名单。"""
    db = host.db
    players = db.all_players(group_id)
    gm_names = []
    for g in sorted(gms):
        p = db.get_player("", g)
        gm_names.append(f"{p.get('name') or g}({g})" if p else g)
    lines = [
        _T.static("gm.status_title"),
        _T.text("gm.status_state", state='🔧 维护中' if down else '✅ 运行中'),
        _T.text("gm.status_notice", msg=msg) if msg else None,
        _T.text("gm.status_players", n=len(players)),
        _T.text("gm.status_top", name=players[0]['name'], level=players[0]['level']) if players else None,
        _T.text("gm.status_gm_list", names='、'.join(gm_names) if gm_names else '(未配置，默认拒绝)'),
    ]
    return "\n".join(x for x in lines if x)


def broadcast(host, raw: str):
    """gm_广播：返回 (玩家回执, 全服广播文本或 None)；空内容 → (格式提示, None)。"""
    db = host.db
    if not raw:
        return _T.static("gm.usage_broadcast"), None
    return _T.text("gm.broadcast_ok", n=len(db.get_player_groups())), _T.text("gm.bc_head", text=raw)


# ============ 玩家查询 ============

def players_text(host, group_id, raw: str) -> str:
    """gm_玩家 [关键词] [页码]：玩家列表（每页 10）。"""
    db = host.db
    kw = ""
    page = 1
    for tok in raw.split():
        if tok.isdigit():
            page = int(tok)
        else:
            kw = tok
    players = db.all_players(group_id)
    if kw:
        players = [p for p in players if kw in (p.get("name") or "") or kw in (p.get("qq_id") or "")]
    page_items_list, pages, page = page_items(players, page, per_page=10)
    lines = [_T.text("gm.players_title", n=len(players)) + (_T.text("gm.players_kw", kw=kw) if kw else "") + _T.text("gm.players_page", page=page, pages=pages)]
    for p in page_items_list:
        lines.append(
            _T.text("gm.players_row", lv=p.get('level', 1), name=p.get('name') or '?',
                gold=p.get('gold', 0),
                cls=host.C.display('classes', p.get('class_name')) if p.get('class_name') else '',
                qq=p.get('qq_id'))
        )
    return "\n".join(lines)


def query_text(host, raw: str) -> str:
    """gm_查询 <QQ/名字>：玩家详情。"""
    db, C = host.db, host.C
    tgt, terr = resolve_target(host, raw)
    if not tgt:
        return terr
    p = db.get_player("", tgt)
    if not p:
        return _T.static("gm.query_missing")
    cls = C.display("classes", p.get("class_name") or "") if p.get("class_name") else ""
    sub = p.get("cur_subarea") or ""
    loc = (MAP_BY_ID.get(p.get("cur_map") or "", {}) or {}).get("name") or p.get("cur_map") or "?"
    if sub:
        cm = MAP_BY_ID.get(p.get("cur_map") or "", {})
        for sa in (cm.get("subareas") or []):
            if sa.get("id") == sub:
                loc += f"·{sa.get('name')}"
                break
    lines = [
        _T.text("gm.query_title", name=p.get('name'), qq=p.get('qq_id')),
        _T.text("gm.query_class", cls=cls, race=p.get('race') or 'human', gender=p.get('gender') or '-'),
        _T.text("gm.query_level", level=p.get('level', 1), exp=p.get('exp', 0)),
        _T.text("gm.query_gold", gold=p.get('gold', 0), stamina=p.get('stamina', 0),
            stamina_max=100 + (p.get('level') or 1) * 2),
        _T.text("gm.query_hpmp", hp=p.get('hp'), max_hp=p.get('max_hp'), mp=p.get('mp'),
            max_mp=p.get('max_mp')),
        _T.text("gm.query_loc", loc=loc or '?', tier=p.get('class_tier', 0)),
        _T.text("gm.query_time", created=p.get('created_at'), active=p.get('last_active')),
    ]
    return "\n".join(lines)


# ============ 玩家操作 ============

def give_gold(host, raw: str) -> str:
    """gm_发金币 <QQ/名字> <数量>"""
    db = host.db
    parts = raw.split()
    if len(parts) < 2:
        return _T.static("gm.usage_give_gold")
    tgt, terr = resolve_target(host, parts[0])
    if not tgt:
        return terr
    try:
        n = int(parts[1])
    except ValueError:
        return _T.static("gm.amt_int")
    if n < 0:
        return _T.static("gm.amt_neg")
    p = db.get_player("", tgt)
    db.update_player("", tgt, gold=(p.get("gold") or 0) + n)
    return _T.text("gm.give_gold_ok", name=p.get('name'), n=n, gold=p.get('gold', 0) + n)


def give_item(host, raw: str) -> str:
    """gm_发物品 <QQ/名字> <物品名> [数量]"""
    db = host.db
    parts = raw.split()
    if len(parts) < 2:
        return _T.static("gm.usage_give_item")
    tgt, terr = resolve_target(host, parts[0])
    if not tgt:
        return terr
    item_name = parts[1]
    count = 1
    if len(parts) >= 3:
        try:
            count = max(1, int(parts[2]))
        except ValueError:
            return _T.static("gm.amt_int")
    key, data = find_item(host, item_name)
    if not key:
        return _T.text("gm.item_missing", name=item_name)
    db.add_item("", tgt, key, data, count)
    return _T.text("gm.give_item_ok", name=db.get_player('', tgt)['name'], item=data['name'], n=count)


def give_exp(host, raw: str) -> str:
    """gm_发经验 <QQ/名字> <经验值>"""
    db = host.db
    parts = raw.split()
    if len(parts) < 2:
        return _T.static("gm.usage_give_exp")
    tgt, terr = resolve_target(host, parts[0])
    if not tgt:
        return terr
    try:
        n = int(parts[1])
    except ValueError:
        return _T.static("gm.exp_int")
    if n < 0:
        return _T.static("gm.exp_neg")
    p = db.get_player("", tgt)
    db.update_player("", tgt, exp=(p.get("exp") or 0) + n)
    # 读档惰性升级会在下次 get_player 时结算
    return _T.text("gm.give_exp_ok", name=p.get('name'), n=n)


def set_level(host, raw: str) -> str:
    """gm_设等级 <QQ/名字> <等级>（重算属性回满血；v113.2 QA 修复：补属性点/技能点）"""
    db = host.db
    parts = raw.split()
    if len(parts) < 2:
        return _T.static("gm.usage_set_level")
    tgt, terr = resolve_target(host, parts[0])
    if not tgt:
        return terr
    try:
        n = int(parts[1])
    except ValueError:
        return _T.static("gm.lv_int")
    if not 1 <= n <= 99:
        return _T.static("gm.lv_range")
    p = db.get_player("", tgt)
    try:
        st = host.player_final_stats(
            p["class_name"], n, p.get("equipment", {}), p.get("class_tier", 0),
            p.get("attributes"), p.get("evolve_path", 0), host.panel_bonus("", tgt),
            p.get("race"))
    except Exception:
        return _T.static("gm.lv_recalc_fail")
    # v113.2 QA 修复：GM 造号补属性点/技能点（对齐升级链 每级+3属性点/每级+1技能点），
    # 取 max 保留玩家已用/已有点数，避免"等级到了但没点数"的测试污染
    db.update_player("", tgt, level=n, exp=0, max_hp=st["max_hp"], max_mp=st["max_mp"],
                     hp=st["max_hp"], mp=st["max_mp"],
                     attr_pts=max(p.get("attr_pts", 0), (n - 1) * 3),
                     skill_points=max(p.get("skill_points", 0), n - 1))
    return _T.text("gm.set_level_ok", name=p.get('name'), n=n)


def teleport(host, raw: str) -> str:
    """gm_传送 <QQ/名字> <地图名>（v101.28p：落点设默认子区域）"""
    db = host.db
    parts = raw.split()
    if len(parts) < 2:
        return _T.static("gm.usage_teleport")
    tgt, terr = resolve_target(host, parts[0])
    if not tgt:
        return terr
    map_name = " ".join(parts[1:])
    mid = find_map(host, map_name)
    if not mid:
        return _T.text("gm.map_missing", name=map_name)
    # v101.28p：传送落点设默认子区域（优先广场），否则 cur_subarea 空=卡城镇总览无法进子区域
    db.update_player("", tgt, cur_map=mid, cur_subarea=default_subarea(host, mid))
    p = db.get_player("", tgt)
    return _T.text("gm.teleport_ok", name=p.get('name'), map=MAP_BY_ID[mid]['name'])


def stamina(host, raw: str) -> str:
    """gm_体力 <QQ/名字> [数值]（不填=回满）"""
    db = host.db
    parts = raw.split()
    if not parts:
        return _T.static("gm.usage_stamina")
    tgt, terr = resolve_target(host, parts[0])
    if not tgt:
        return terr
    p = db.get_player("", tgt)
    mx = 100 + (p.get("level") or 1) * 2
    if len(parts) >= 2:
        try:
            n = int(parts[1])
        except ValueError:
            return _T.static("gm.st_int")
        n = max(0, min(n, mx))
    else:
        n = mx
    db.update_player("", tgt, stamina=n, stamina_ts=int(time.time()))
    return _T.text("gm.stamina_ok", name=p.get('name'), n=n, mx=mx)


def rename(host, raw: str) -> str:
    """gm_改名 <QQ/名字> <新名字>"""
    db = host.db
    parts = raw.split()
    if len(parts) < 2:
        return _T.static("gm.usage_rename")
    tgt, terr = resolve_target(host, parts[0])
    if not tgt:
        return terr
    new_name = " ".join(parts[1:]).strip()
    if not new_name or len(new_name) > 12:
        return _T.static("gm.rename_len")
    p = db.get_player("", tgt)
    db.update_player("", tgt, name=new_name)
    return _T.text("gm.rename_ok", name=p.get('name'), new_name=new_name)


# ============ GM 白名单管理 ============

def load_whitelist(host) -> list:
    """读库内白名单（真源 `_load_wl`）。"""
    try:
        raw = host.db.get_event_state("gm_whitelist")
        return [str(x) for x in json.loads(raw)] if raw else []
    except Exception:
        return []


def save_whitelist(host, wl: list) -> None:
    """写库内白名单（真源 `_save_wl`）。"""
    host.db.set_event_state("gm_whitelist", json.dumps(wl, ensure_ascii=False))


def add_gm(host, raw: str) -> str:
    """gm_加GM <QQ号>"""
    if not raw or not raw.isdigit():
        return _T.static("gm.usage_add_gm")
    wl = load_whitelist(host)
    if raw not in wl:
        wl.append(raw)
        save_whitelist(host, wl)
    return _T.text("gm.add_gm_ok", qq=raw, n=len(wl))


def del_gm(host, raw: str) -> str:
    """gm_删GM <QQ号>"""
    if not raw or not raw.isdigit():
        return _T.static("gm.usage_del_gm")
    wl = load_whitelist(host)
    if raw in wl:
        wl.remove(raw)
        save_whitelist(host, wl)
    return _T.text("gm.del_gm_ok", qq=raw, n=len(wl))


# ============ 世界 Boss 伤害倍率 / 帮助 ============

def boss_dmg(host, qq_id, raw: str) -> str:
    """gm_伤害 [倍率]：世界 Boss 伤害倍率（0.1－100）。"""
    db = host.db
    cur = db.get_boss_dmg_mult(qq_id)
    if not raw:
        return _T.text("gm.boss_cur", cur=cur)
    try:
        m = float(raw)
    except ValueError:
        return _T.static("gm.usage_boss_dmg")
    if not 0.1 <= m <= 100:
        return _T.static("gm.boss_range")
    m = round(m, 2)
    db.set_event_state(f"boss_dmg_{qq_id}", m)
    return _T.text("gm.boss_set", m=m, cur=cur)


# ============================================================
# 资料表热重载（引擎注册表重载 + 包内派生缓存重建）
# ============================================================
# 引擎侧只重载 `Records` 表；包内从域表**派生**出来的模块级缓存不会自己跟着变 —— 命令层读到的
# 会是旧值。这些派生物的重建由**引擎通用视图注册表**（`saintess_engine.records.views`）负责：
# 每个派生模块在 import 期 `register_view(<自己的重建函数>, order=<依赖序>)`，
# `rebuild_views(module_prefix=__package__)` 按 `(order, 登记序)` 依次调用它们。
#
# 消费方看到新值的两条口径（模块序台账见下）：
#   ① 可变容器（dict / list / set）**就地更新** —— `from X import Y` 的消费方持有的是同一对象；
#   ② 非容器（tuple / frozenset / 数字 / 字符串）由引擎按**旧对象身份**回填到本包各模块的同名
#      全局上（视图函数把 `(旧对象, 新对象)` 交出来，引擎做通用别名回填）。
#
# 模块序（`order`）—— 被别的视图读到的模块先跑：
#     tables 10 · catalog_b143 20 · catalog_items 30 · catalog_life 40 · catalog_core 50 ·
#     catalog_quests 60 · collection 70 · catalog_rules 80 · catalog_legacy 90 ·
#     fishing 100 · pois 110 · maps 120 · index_build 150 · index 200
#     （`content/index.py` 的 `_INDEXES`/`_BUILT` 重建在 index 那个视图里，排在最后）


def _rebuild_derived_caches() -> int:
    """按已登记的视图函数重建包内模块级派生缓存，返回重建的视图个数。"""
    return rebuild_views(module_prefix=__package__)


def reload_tables(reload_all_sets, reload_error) -> list:
    """重载资料表（引擎注册表跨集合全有或全无 + 包内派生缓存重建）→ 中文回报。

    失败时把 `RecordsReloadError` 的点名信息**原样**回给 GM（fail-closed，不吞成「成功」）。
    """
    try:
        change = reload_all_sets()
    except reload_error as exc:
        return [_T.static("gm.reload_fail") % exc]
    try:
        rebuilt = _rebuild_derived_caches()
    except Exception as exc:                                  # noqa: BLE001
        return [_T.static("gm.reload_rebuild_fail") % (type(exc).__name__, exc)]
    total = sum(len(per) for per in change.values())
    rows = sorted({(domain, row["before"], row["after"])
                   for per in change.values() for domain, row in per.items()
                   if row["before"] != row["after"]})
    lines = [_T.static("gm.reload_ok")
             % (total, len(change), rebuilt)]
    if not rows:
        lines.append(_T.static("gm.reload_none"))
        return lines
    lines.append(_T.static("gm.reload_head"))
    lines.extend("  %s：%d → %d" % row for row in rows)
    return lines


def help_text() -> str:
    """gm_帮助：GM 指令一览（逐字真源整段）。"""
    return (
        _T.static("gm.help")
    )
