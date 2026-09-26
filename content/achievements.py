# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 成就系统（B13-L4，2026-09-14；B2-S4 劈形状，2026-09-24）。

★ 2026-09-24 B2-S4（抽包工程 B2 批第四步）：**账本形状**（解锁遍历 / 领取 / 标签名 / 点数）
已抽进扩展包 —— `ext_achieve.ledger`（二十个句柄 `bind(...)` 注入）。本模块只剩**这款游戏
自己的那一半**：

  ① 注入面     `_ledger_bind(...)` 把二十个句柄逐个落到本包域名上（存档读写口 / 条件判据 /
               文案槽位 / 奖励发放 / 升级结算 / 三态机 / 点数权重 / 通关记录键前缀 / 显示名）
  ② 条件注册   `cond_met` + `COND_CHECKS` 三条 v140 条件（本模块**仍是**条件注册表的注册点）
  ③ 统计读口   `_bestiary_kills` / `_monster_total`（`achievement_conds` 的延迟引用点）
  ④ 四个对外函数 `check_achievements` / `claim_achievement_rewards` / `achievement_titles` /
               `achievement_points` —— 对外签名一字未改，函数体只剩「转给形状 + 降级兜底」

真源：游戏仓 `game/core/achievements.py`（305 行 / 阶段九 14 章）。

★ 顺序不变式（逐字节等价的关键，与 `content/talk_actions.py` 的 ACTIONS 同款）
  · `from .achievement_conds import COND_CHECKS as _COND_CHECKS` + 3 个 `@_register_cond`
    （blueprints_learned / quests_done / chests_opened）在**本模块 import 期**执行 —— 与真源
    「import achievements 即注册」逐字等价（宿主薄壳 import 包内本模块，注册随之发生）；
  · `ACHIEVEMENTS`（包内门面 `content/catalog_quests.py`）的**源列表序**决定
    `check_achievements` 的解锁顺序与 `achievement_titles` 的称号序 —— 源列表序的遍历现在在
    形状里（`ext_achieve.ledger`），表本身仍由本模块注入。

★ 真源遗留缺陷**逐字保留**：`claim_achievement_rewards` 的 `except` 分支里 `LOG` 是**未定义
  的全局名**（真源模块级没有 `LOG`，只有 `check_achievements` 里那处函数内 import）→ 该分支
  实际抛 `NameError: name 'LOG' is not defined`。本模块**故意不在模块级定义 `LOG`**（快照
  `失败分支 EXC: NameError name 'LOG' is not defined` 与改前逐字节相同）。
  修它 = 行为变更，留给后续单独一批。

  ⇒ B2-S4 之后这段兜底从「形状内部」挪到了**本模块的外层**（形状不吞异常）：可观测行为不变
  （异常仍在本模块的 `try` 里被接住，`LOG` 仍未定义），但引擎侧的形状里不再躺一个故意的
  undefined name。

真源原文头注（逐字保留）
------------------------
    奥兰迪亚·余烬纪年核心层 - achievements.py（阶段九：成就系统，14 章）
    
    - cond_met(player, stats, profs, extra, cond)：单条条件判定
    - check_achievements(group_id, qq_id)：遍历 97 成就，满足且未解锁 → 解锁 + 发奖励
    - achievement_titles(qq_id)：已解锁成就的称号名列表（与 titles.py TITLES 合并成称号总表）
    - achievement_points(qq_id)：成就点计算（普通 1 / 隐藏 2）
    
    ⚠️ 本模块在 core 聚合链内，禁止顶层 import content/engine（循环导入），一律函数内延迟导入。
    数据源：players（level/evolve_path/learned_skills/apprentices/gold/learned_blueprints）、
    stats 表（kills/elite/boss/visited_areas/inst_clears/party_count/副业次数/world_events/chests_opened）、
    professions 表（副业等级）、quests（completed_main/side）、bestiary（击杀/图鉴）、
    achievements 表（已解锁 + inst_clear_* 记录）。
    
    v140 波2（成就/称号/收藏资源化 3.9）：
    - reward.items 物品奖励发放（claim_achievement_rewards）
    - 3 个新条件类型注册（blueprints_learned/quests_done/chests_opened）——直接 extend
      COND_CHECKS 注册表（achievement_conds.py 的 dict 是模块级单例，注册后 cond_met 立即可用）"""

from __future__ import annotations

from ._domainio import read_domain as _read_domain


# ============================================================
# 包内域读口（I1）：`items` 域（真源 `C.ITEMS`）
# 实测（探针 `overnight/w1213_b13l4_probe.py`）：900 键 / 键集合与 `name` 字段**全等** →
# 正文里物品显示名读本读口；B14-2 起材料 / 成就 / 地图索引三名数据名也切门面。
# ============================================================


ITEMS = _read_domain("items")                   # ← 真源 `C.ITEMS`

# B14-2（L7 线）：数据名读点切包内门面 —— 原 `C.<名>` 直取换成包内门面同名绑定
from .catalog_items import MATERIALS            # 真源 `C.MATERIALS`
from .catalog_quests import ACHIEVEMENTS        # 真源 `C.ACHIEVEMENTS`（源列表序）
from .catalog_space import MAP_BY_ID            # 真源 `C.MAP_BY_ID`


# ============================================================
# 存储/日志取口（B2-C4 收口）
#   `db` = 包内 `content/_pkgref.DB`（B1 口径）；LOG = `content/obs.py::log()`（包内唯一日志取用口）
# ============================================================
from . import obs                          # noqa: E402  包内唯一 LOG/tlog 取用口（fail-closed）
from . import texts as _T                    # noqa: E402  文案真源取件口（C 档 34c：成就面板/领取）
from .index import display as _index_display   # noqa: E402  `C.display` → 包内直取（同一对象）
from ._pkgref import DB as db              # noqa: E402  `from .. import db` 的包内等价物
from saintess_engine.conditions.declarative import bind_spec   # S4：声明式条目装配
from ext_life.collect import TierBoard     # noqa: E402  收集三态机（引擎侧形状，B2-S4 注入给账本形状）
from .cond_specs import load as _load_specs

# B2-S4：账本形状（解锁 / 领取 / 标签名 / 点数）—— 实现已进扩展包 `ext_achieve.ledger`
from ext_achieve.ledger import bind as _ledger_bind             # noqa: E402
from ext_achieve.ledger import check as _ledger_check           # noqa: E402
from ext_achieve.ledger import claim as _ledger_claim           # noqa: E402
from ext_achieve.ledger import labels as _ledger_labels         # noqa: E402
from ext_achieve.ledger import points as _ledger_points         # noqa: E402
# v140 波2：3 个新条件类型注册（数据已有零消费点或最小接线）
# 与 achievement_conds.py 共用 COND_CHECKS 单例：本模块 import 它再注册，cond_met 同 dict 生效。
try:
    from .achievement_conds import COND_CHECKS as _COND_CHECKS
except Exception:
    _COND_CHECKS = None


def _register_cond(key):
    """向 COND_CHECKS 注册条件判定（v140 波2 新增类型）。"""
    def deco(fn):
        if _COND_CHECKS is not None:
            _COND_CHECKS.register(key, fn)
        return fn
    return deco


# ★ S4 数据化：`blueprints_learned` / `chests_opened` 两条形状固定，判定搬进
#   `content/data/cond_specs.json`（此处只保留登记动作，注册表与签名不变）。
_S4_DECL = _load_specs("achievement")
for _k in ("blueprints_learned", "chests_opened"):
    if _COND_CHECKS is not None:
        _COND_CHECKS.register(_k, bind_spec(
            _S4_DECL[_k], ("player", "stats", "profs", "extra", "cond")))


@_register_cond("quests_done")
def _c_quests_done(player, stats, profs, extra, cond):
    """累计完成任务数（v140 波2：读 quests.completed_main + side done 计数，数据已有零消费点）"""
    gid = extra.get("_group_id")
    if not gid:
        return False
    try:
        q = db.get_quests(gid, player["qq_id"])
    except Exception:
        return False
    if not q:
        return False
    done = len(q.get("completed_main") or [])
    for _s in (q.get("side") or {}).values():
        if isinstance(_s, dict) and _s.get("status") == "done":
            done += 1
    return done >= cond.get("value", 0)


def _bestiary_kills(qq_id, keyword) -> int:
    """bestiary 按怪物名关键词统计击杀数"""
    try:
        rows = db.get_bestiary("", qq_id)
    except Exception:
        return 0
    total = 0
    for r in rows:
        name = _index_display("monsters", r["monster"])
        if keyword in (name or ""):
            total += int(r.get("kills", 0) or 0)
    return total


def _monster_total() -> int:
    """地图怪物去重总数(图鉴全解锁判定)"""
    try:
        ids = set()
        for mid, m in MAP_BY_ID.items():
            for mon in (m.get("monsters") or []):
                if isinstance(mon, dict):
                    ids.add(mon.get("id") or mon.get("name"))
                else:
                    ids.add(mon)
        return max(len(ids), 100)
    except Exception:
        return 150


def cond_met(player: dict, stats: dict, profs: dict, extra: dict, cond: dict, group_id: str = None) -> bool:
    """成就条件判定。extra 携带事件上下文(inst_id/flawless/worldboss/flags 等)
    v99.5：判定逻辑数据化 → core/achievement_conds.py COND_CHECKS 注册表
    （41 种条件类型；未知 type / 异常 → False，与旧 if 链兜底一致）
    v100.3b：新增可选 group_id —— 非 None 时注入 extra['_group_id'] 副本，
    供 quest_done/item_has 查询任务/背包（原代码引用未定义 group_id → 恒 False 的历史 bug）"""
    try:
        from .achievement_conds import COND_CHECKS
        fn = COND_CHECKS.get(cond.get("type"))
        if fn is None:
            return False
        if group_id is not None and extra.get("_group_id") is None:
            extra = dict(extra)
            extra["_group_id"] = group_id
        return fn(player, stats, profs, extra, cond)
    except Exception:
        return False


# ============================================================
# ★ B2-S4 注入面：账本形状（`ext_achieve.ledger`）的二十个句柄
#   形状里零内容词表、零数据包 import；这一节就是「这款游戏那一半」——
#   存档 schema、文案键、点数权重、通关记录键名、物品显示名全落在这里。
# ============================================================

#: 文案槽位 → (文案键, 取法)：`text` = 带槽位格式化 · `static` = 原样取
#: （键名只在本模块出现；形状只传**槽位名**与实参 —— 文案真源 `content/data/text_specs.json`）
_ACH_COPY = {
    "reward_exp": ("ach.exp_part", "text"),
    "reward_currency": ("ach.gold_part", "text"),
    "claim_head": ("ach.claim_head", "text"),
    "claim_currency": ("ach.claim_gold", "text"),
    "claim_hint": ("ach.claim_hint", "static"),
    "items_head": ("ach.items_head", "static"),
    "items_partial_fail": ("ach.items_partial_fail", "static"),
    "none": ("ach.none", "static"),
    "need_register": ("ach.need_register", "static"),
}

#: 通关记录的键前缀（`inst_clear_<副本 id>`）—— 键名约定属本包，形状只问 `clear_of`
_CLEAR_PREFIX = "inst_clear_"

#: 隐藏类分类名（点数权重 2 的那一类）
_HIDDEN_CAT = "隐藏"


def _phrase(slot, **slots):
    """文案槽位 → 文案（未知槽位 ⇒ KeyError，fail-loud）。"""
    key, how = _ACH_COPY[slot]
    return _T.text(key, **slots) if how == "text" else _T.static(key)


def _ledger_rows(_group_id, qq_id):
    """账本行 → 形状契约三字段（存储 schema `ach_key/claimed/progress` 只在本模块出现）。

    组号只是透传槽（本游戏的账本按 `qq_id` 全局，真源 `achievement_titles` 那两处传的是
    空串）；读口异常**不吞**：由形状各调用点按真源口径分别处理（标题/点数 ⇒ 空集，
    解锁遍历 ⇒ 空集，领取 ⇒ 交给降级兜底）。
    """
    return [{"id": r["ach_key"],
             "claimed": r.get("claimed"),
             "progress": r.get("progress", 1)}
            for r in (db.get_achievements(_group_id or "", qq_id) or [])]


def _clear_of(key):
    """账本键 → 已通关副本 id（本包键名约定）；不是通关记录 ⇒ None。"""
    s = str(key)
    return s[len(_CLEAR_PREFIX):] if s.startswith(_CLEAR_PREFIX) else None


def _weight_of(entry) -> int:
    """成就点权重：隐藏类 2 分，其余 1 分（真源 `achievement_points` 的唯一内容判据）。"""
    return 2 if entry.get("cat") == _HIDDEN_CAT else 1


def _reward_of(entry):
    """奖励 dict → `(经验, 金币, 物品表)` 三支路（键名是**本包 schema**，形状不认）。"""
    rw = entry.get("reward") or {}
    return rw.get("exp", 0), rw.get("gold", 0), rw.get("items")


def _has_claimable_reward(a) -> bool:
    """该成就是否带可发奖励（经验 / 金币 / 物品）—— 三态机的 `claimable` 判据。"""
    rw = a.get("reward") or {}
    return bool(rw.get("exp", 0) or rw.get("gold", 0) or rw.get("items"))


def _claim_machine(unlocked, claimed):
    """待领档位三态机（引擎收集形状 `ext_life.collect.TierBoard`）：达成 = 该 id 已解锁；
    可领 = 带奖励。`claim(a)` 幂等（`READY` 才记入，已领/未达成/无物可领一律 `False`）。"""
    return TierBoard(ACHIEVEMENTS,
                     claimed=set(claimed),
                     key=lambda a: a["id"],
                     reached=lambda a: a["id"] in unlocked,
                     claimable=_has_claimable_reward)


def _item_name(key) -> str:
    """物品 key → 显示名（域读口 → 门面；取不到回落 key 本身，与真源同口径）。"""
    try:
        return (ITEMS.get(key) or MATERIALS.get(key) or {}).get("name", key)
    except Exception:
        return key


def _enrich(group_id, qq_id, player):
    """领奖前把加成字段挂到玩家副本上（真源 `player["_panel_bonus"] = stat_bonus(...)`）。

    K0-A1：复用统一单点 `stat_bonus()`（含 M18 同名去重 + TITLES 侧 bonus），不再用轻量
    `_title_bonus_plain` —— 避免 Lv.10 副业大师称号被当作第二份双算。
    """
    from .stat_bonus import stat_bonus
    player["_panel_bonus"] = stat_bonus(group_id, qq_id, player)
    return player


def _payout(group_id, qq_id, player, exp, currency):
    """把两类奖励记进玩家记录（字段名是存储 schema）。"""
    player["exp"] = player.get("exp", 0) + exp
    player["gold"] = player.get("gold", 0) + currency
    return player


def _save_player(group_id, qq_id, player):
    """领奖后的玩家落库（字段清单 = 真源 `db.update_player` 的那 11 个）。"""
    db.update_player(group_id, qq_id,
                     exp=player["exp"], gold=player["gold"], level=player["level"],
                     hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"],
                     skills=player["skills"], attr_pts=player.get("attr_pts", 0),
                     skill_points=player.get("skill_points", 0),
                     learned_skills=player.get("learned_skills", []))


def _grant(group_id, qq_id, items, lines):
    """物品发放（v174 统一抽象：与任务/对话/收藏同一实现）。"""
    from .reward import grant_items_batch
    return grant_items_batch(group_id, qq_id, items, lines=lines)


def _levelup(group_id, qq_id, player):
    """升级结算（真源 `check_player_level_up`）。"""
    from .gameplay_rules import check_player_level_up
    return check_player_level_up(group_id, qq_id, player)


_ledger_bind(
    entries=lambda: ACHIEVEMENTS,
    ledger_of=_ledger_rows,
    # ★ 惰性转发：`db` 是 wire 代理，属性解析要留到**调用时**——
    #   真源那两处也是运行时才取件（import 期取会让 content.persistence 的半初始化态撞上）
    mark=lambda group_id, qq_id, key, progress, claimed:
        db.set_achievement(group_id, qq_id, key, progress, claimed),
    player_of=lambda group_id, qq_id: db.get_player(group_id, qq_id),
    stats_of=lambda group_id, qq_id: db.get_stats(group_id, qq_id) or {},
    profs_of=lambda group_id, qq_id: db.get_professions(group_id, qq_id) or {},
    save_player=_save_player,
    cond_of=cond_met,
    clear_of=_clear_of,
    weight_of=_weight_of,
    label_of=lambda a: a.get("title"),
    name_of=_item_name,
    line_of=lambda a: "🏅 %s" % a["name"],
    reward_of=_reward_of,
    phrase=_phrase,
    machine=_claim_machine,
    enrich=_enrich,
    grant=_grant,
    levelup=_levelup,
    payout=_payout,
)


# ============================================================
# 对外四函数（签名一字未改）—— 函数体只剩「转给形状 + 降级兜底」
# ============================================================

def achievement_titles(qq_id) -> list:
    """已解锁成就的称号名列表(14 章：达成成就自动获得称号)。形状：`ext_achieve.ledger.labels`。"""
    return _ledger_labels(qq_id)


def achievement_points(qq_id) -> int:
    """成就点(普通 1 / 隐藏 2)。形状：`ext_achieve.ledger.points`（权重由本包注入）。

    ⚠️ 14 章四「成就等级体系（青铜→传奇）」待后续版本，未实装：当前只算点数，
    无等级划分/等级称号/等级加成。（v105 M18 P2 标注）
    """
    return _ledger_points(qq_id)


def check_achievements(group_id, qq_id, player=None, extra=None) -> list:
    """通用成就判定：事件后调用。返回本次新解锁的成就(dict)列表。

    v101.22（鱼鱼拍板）：解锁不再自动发奖励——改为待领取(claimed=0)，
    玩家用『成就 领取』手动领。奖励数值同步下调(新手期 500→100)。
    返回的成就 dict 带 _reward_txt 供调用方提示。

    形状：`ext_achieve.ledger.check`；本层只留**降级兜底**（真源口径：任何异常 ⇒ 记一条
    警告 + 返回空列表，不打断事件链）。
    """
    try:
        return _ledger_check(group_id, qq_id, player, extra)
    except Exception:
        obs.log().warning("[dragonfall] check_achievements 异常，成就列表降级为空", exc_info=True)
        return []


def claim_achievement_rewards(group_id, qq_id) -> tuple:
    """领取全部待领取的成就奖励(经验/金币/物品)。返回 (lines, err) 供命令输出。

    v101.22：成就解锁后奖励待领取，玩家手动『成就 领取』时统一发放，
    发放走 check_player_level_up 正常结算升级。未解锁/无奖励成就忽略。
    v140 波2（成就/称号/收藏资源化 3.9）：reward 新增 items 物品奖励
    （{item_key: count}），与经验/金币一同发放——db.add_item 入包，
    物品 key 走 _key_to_id 兼容中文名；发放失败静默跳过（物品缺失不影响其他奖励）。
    ★ U1-I3：筛选「可领档位」改走引擎收集形状 `collect.TierBoard.claim()`（幂等 + 不可重领）。

    形状：`ext_achieve.ledger.claim`；本层只留**降级兜底**（见模块头注「真源遗留缺陷逐字
    保留」——`LOG` 仍是未定义的全局名 ⇒ 这一路实际抛 NameError，与改前逐字节相同）。
    """
    try:
        return _ledger_claim(group_id, qq_id)
    except Exception as e:
        LOG.warning(f"[dragonfall] 成就领取失败: {e}")
        return [], _T.static("ach.fail")
