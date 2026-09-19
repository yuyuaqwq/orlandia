# -*- coding: utf-8 -*-
"""包内杂项命令门面（`content/misc_cmds.py`）—— 帮助面板 / 新手指引 / 签到 / 成就面板 / 意见箱。

★ B9 L9（2026-09-13）命令层薄壳化：宿主 `game/commands/misc.py`（468 行）只留「注册 + 取玩家 +
调包 + 渲染」，**真实实现正文搬进本模块**。逐命令落点判定（详见 `overnight/B9-L9-misc.md`）：

    帮助 help_cmd      面板 11 份 + 主题表 + 兜底回执 → 本模块（`HELP_PANELS` / `HELP_MAP` / `help_reply`）
                       参数解析（`[At:…]` 前缀剥离 +「帮助/help」前缀）留宿主 = QQ 消息形态适配
    新手指引 game_tip   整段文案 → 本模块常量 `GAME_TIP`
    签到 signin         认领 / 运势 / 幸运符 / 金币 / 节日口径 → `signin_start()`；周奖励档位抽取留宿主
                        （源码级绑定门禁要求 `QUALITY_TIERS.pick_weights(_wq, rng=random)` 字面留在
                        命令层，见报告缺口 ④）；`signin.*` 十条文案留宿主（文案表按命令层 AST 对账）
    成就 achievements   分类 / 进度 / 奖励文案拼装 → `achievement_panel()`；「领取」回执 → `claim_reply()`
                        表与成就点仍由宿主取（源列表序 + `core/achievements.py:achievement_points`，
                        见报告缺口 ②③）
    意见 feedback_cmd   校验 / 频控（30s、≤200 字）/ 入库 → `feedback_precheck()` + `feedback_submit()`
                        Hermes webhook 通知留宿主（宿主集成，非游戏内容）

宿主替身（`bind_host`，与 `content/talk_actions.py` 同款）
--------------------------------------------------------
    `db` = 宿主存储层模块（真源 `from .. import db`）：正文 `db.xxx(...)` 一行未改；
    未注入时按 `sys.modules` 找**已加载**的宿主模块（绝不 import 宿主模块树）。

数据面（读包内域，不 import 宿主内容层）
----------------------------------------
    `content/data/items.json` ← 真源 `game/data/items.py ITEMS`（900 条；MATERIALS 598 条 ⊆ 它）
        · 成就奖励物品名解析（真源 `(C.ITEMS.get(k) or C.MATERIALS.get(k) or {}).get("name", k)`）

    ⚠️ 幸运符的**材料键由宿主给**（`signin_start(..., luck_mat=…)`）：包内没有 materials 域，而材料
    键集**无法从 items 域反推**（实测 598 个材料键里 7 个没有 `mat_` 前缀：`item_edmund_tag` /
    `item_thank_letter` / `i_stone_refine` / `i_stone_upgrade` / `item_dried_flower` /
    `i_stone_blessed` / `item_late_letter`；且 `type='任务道具'` 在材料 73 条与非材料 1 条之间**交叉**）
    —— 两套启发式都**不成立**，故不猜：宿主按 `C.resolve("materials", LUCK_MATERIAL_NAME)` +
    `key in C.MATERIALS` 求值后传入（全仓唯一一次该查表）。见报告 §缺口⑤。

签名里的三个宿主入参（`cfg` / `table` / `points`）分别是：签到数值配置（`game/data/signin_config.py`
SIGNIN_CONFIG，属 L7 域批次）、成就表（`C.ACHIEVEMENTS`，源列表序）、成就点（宿主 core 计算）——
三者的「该进包但还没有域」的理由逐条写在报告 §缺口里，本模块**不复制**任何一份数据。
第四个入参 `luck_mat` = 幸运符的材料键（见上「宿主给」那条）。

不改语义：命中 / 分支 / 阈值 / 文案一字未动；随机流与真源逐位一致（整条签到只 `random.random()` 一次）。

★ U1-I3：本模块里的两处「手写形状」改走引擎 —— 意见箱频控 = `periodic.Cooldown`
（末次触达时刻 + 窗口；键与存档口径不变），成就面板的三态 = `collect.TierBoard` +
N/M 进度 = `collect.Tally`（达成/可领判据由本模块给）。文案与行序逐字节不变。
"""
from __future__ import annotations

import json
import os
import random
_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_DATA_DIR = os.path.join(_HERE, "data")

# 宿主模块名（运行时 `main.py` 的模块路径 = `data.plugins.dragonfall`；测试同样）—— 与
# `content/talk_actions.py` 同口径（B8.2 线1 立的规矩）
from ._hostref import make_bound_host  # 取件工厂单源（P0-3；常量本身不再被本文件引用）
from ._domainio import read_json as _read_json            # P0-4b 读口单源


# ============================================================
# 宿主替身口（存储层）—— 引擎 wire 形状
# ============================================================
from saintess_engine.wire import Wire
from saintess_engine.collect import CLAIMED, LOCKED, READY, Tally, TierBoard
from saintess_engine.periodic import Cooldown
from . import texts as _T                       # 文案表（B 批 B-1 B 档：帮助面板）

#: 注入句柄面（`bind_host()` 写；`None` = 没给）——槽名 = `bind_host` 形参名
_WIRE = Wire()


def bind_host(db=None) -> None:
    """宿主替身注入（幂等；宿主薄壳在 import 期调用）——写进引擎 wire 句柄面（`None` = 没给）。"""
    _WIRE.bind(db=db)


_bound_host = make_bound_host(_WIRE, "misc_cmds")


class _HostDB:
    """惰性宿主存储层代理（真源 `from .. import db`）——`db.xxx` 正文不动，属性访问时解析。"""

    def __getattr__(self, name):
        return getattr(_bound_host("db"), name)


db = _HostDB()


# ============================================================
# ① 帮助面板（11 份，内容侧文本）
#   ★ B 批 B-1 B 档（2026-09-17）：**句壳已搬进文案真源** `content/data/text_specs.json`
#   的 `help_panel.*`（11 条，逐字节照搬原类属性）。11 个常量仍以 str 形式存在于模块上
#   （模块内裸名引用 / 测试的 `from … import CMD_HELP_X` 语义逐字不变），值取自文案表
#   ⇒ 改文案只动表；热更新需 `content.texts.reload()` + 重入取值点（import 期已取值）。
# ============================================================
CMD_HELP = _T.static("help_panel.CMD_HELP")
CMD_HELP_CHAR = _T.static("help_panel.CMD_HELP_CHAR")
CMD_HELP_ADV = _T.static("help_panel.CMD_HELP_ADV")
CMD_HELP_BATTLE = _T.static("help_panel.CMD_HELP_BATTLE")
CMD_HELP_SKILL = _T.static("help_panel.CMD_HELP_SKILL")
CMD_HELP_PROF = _T.static("help_panel.CMD_HELP_PROF")
CMD_HELP_ITEM = _T.static("help_panel.CMD_HELP_ITEM")
CMD_HELP_INSTANCE = _T.static("help_panel.CMD_HELP_INSTANCE")
CMD_HELP_SOCIAL = _T.static("help_panel.CMD_HELP_SOCIAL")
CMD_HELP_WORLD = _T.static("help_panel.CMD_HELP_WORLD")
CMD_HELP_OTHER = _T.static("help_panel.CMD_HELP_OTHER")
# 面板登记（**注册顺序 = 渲染顺序**）—— ★ B-1 B 档起 = 映射读口（值实时取自文案表；
#   搬前「宿主薄壳类属性逐个 re-export」的形已随删壳批消失，此处只留名 → 键）
_HELP_PANEL_KEYS = {   # 面板名 → 文案键（字面量！文案门禁靠它判「非死文案」）
    "CMD_HELP": "help_panel.CMD_HELP",
    "CMD_HELP_CHAR": "help_panel.CMD_HELP_CHAR",
    "CMD_HELP_ADV": "help_panel.CMD_HELP_ADV",
    "CMD_HELP_BATTLE": "help_panel.CMD_HELP_BATTLE",
    "CMD_HELP_SKILL": "help_panel.CMD_HELP_SKILL",
    "CMD_HELP_PROF": "help_panel.CMD_HELP_PROF",
    "CMD_HELP_ITEM": "help_panel.CMD_HELP_ITEM",
    "CMD_HELP_INSTANCE": "help_panel.CMD_HELP_INSTANCE",
    "CMD_HELP_SOCIAL": "help_panel.CMD_HELP_SOCIAL",
    "CMD_HELP_WORLD": "help_panel.CMD_HELP_WORLD",
    "CMD_HELP_OTHER": "help_panel.CMD_HELP_OTHER",
}
# ★ B 批 B-1 B 档：面板名 → 面板文本（映射读口；`[k]`/`in`/`.get(k,d)`/`.items()` 语义不变）
HELP_PANELS = _T.names(_HELP_PANEL_KEYS, prefix="help_panel")

# 主题 → 面板（真源 `commands/misc.py:_HELP_MAP`，18 键逐条照搬；值 = 上面的面板名）
_HELP_TOPIC_2_PANEL = {
    "角色": "CMD_HELP_CHAR",
    "人物": "CMD_HELP_CHAR",
    "冒险": "CMD_HELP_ADV",
    "世界": "CMD_HELP_WORLD",
    "地图": "CMD_HELP_ADV",
    "战斗": "CMD_HELP_BATTLE",
    "pvp": "CMD_HELP_BATTLE",
    "技能": "CMD_HELP_SKILL",
    "技能系统": "CMD_HELP_SKILL",
    "副业": "CMD_HELP_PROF",
    "生活": "CMD_HELP_PROF",
    "物品": "CMD_HELP_ITEM",
    "背包": "CMD_HELP_ITEM",
    "副本": "CMD_HELP_INSTANCE",
    "组队": "CMD_HELP_INSTANCE",
    "社交": "CMD_HELP_SOCIAL",
    "公会": "CMD_HELP_SOCIAL",
    "其他": "CMD_HELP_OTHER"
}

HELP_MAP = {k: HELP_PANELS[v] for k, v in _HELP_TOPIC_2_PANEL.items()}

# 兜底回执里那句「可用主题」——**逐字**取自真源（顺序即真源字符串的顺序）
HELP_TOPICS = "角色 冒险 战斗 技能 副业 物品 社交 世界 其他"


def help_reply(arg: str) -> str:
    """`帮助 <主题>` 的一整条回执（空主题 → 总览；未收录主题 → 兜底 + 总览）。

    真源 `commands/misc.py:help_cmd` 的 :213-222 逐行等价（宿主只做参数解析后调本函数）。
    """
    if not arg:
        return CMD_HELP
    panel = HELP_MAP.get(arg)
    if panel:
        return panel
    return _T.static("help_panel.no_topic") % (arg, HELP_TOPICS, CMD_HELP)


# ============================================================
# ② 新手指引（`游戏提示` 命令整段文案；真源 = 原 `commands/misc.py:game_tip` 的字符串）
# ============================================================
GAME_TIP = """📖 【新手指引】刚来到奥兰迪亚的你，可以这样开始：
━━━━━━━━━━━━
① 开局流程：『注册 <名字> <性别>』创建角色 → 在城镇找 NPC 接任务（『任务』看主线）
　 · 打怪练级：『探索』遇敌 → 战斗中用『技能 <名称/序号>』输出
　 · 30 级可『转职』选择职业分支，技能/属性更专精
② 体力规则：探索/战斗/采集等消耗体力，体力为 0 会困在野外
　 · 恢复：城镇『休息』/『住宿』、吃食物（『背包』里的烤肉串等）
③ 常用指令：『背包』看物品 ｜ 『技能列表』看技能 ｜ 『地图』看周围
　 · 『商店』买补给 ｜ 『锻造』做装备 ｜ 『副本』组队闯关
④ 快捷操作：『设置技能 <槽位> <技能名>』放技能栏，战斗中『技能 <槽位>』秒放
　 · 列表类指令（背包/技能/任务）可发『+/-』翻页，发序号可快捷查看
⑤ 副本钥匙：高难副本需要钥匙/信物才能进（如『王陵钥匙』）
　 · 『副本』看每本需求 ｜ 『百科 <钥匙名>』查获取途径 ｜ 已通关可免钥匙
━━━━━━━━━━━━
💡 更多指令见『帮助』；卡住时试试『百科 <材料/怪物/地图/钥匙>』查询～"""


# ============================================================
# ③ 签到（`签到` 命令：认领 + 运势 + 幸运符 + 金币 + 节日口径）
# ============================================================
# 幸运符（内容侧物品名；材料键由宿主求值传入 —— 见文件头「宿主给」那条）
LUCK_MATERIAL_NAME = "幸运符"


def signin_start(group_id, qq_id, today: str, yesterday: str, cfg: dict, luck_mat=None):
    """签到第 1 段：原子认领 → 运势 → 幸运符消解 → 记运势 → 金币（真源 :259-290 逐行等价）。

    返回 `None` = 今日已签（调用方回 `signin.already` 并结束）；
    否则 `{"streak", "total", "fortune", "gold", "festival"}`（周奖励的档位抽取与文案全留宿主）。

    `luck_mat` = 幸运符的材料键（宿主 `C.resolve("materials", LUCK_MATERIAL_NAME)` +
    `key in C.MATERIALS` 求值；包内不猜材料归属，见文件头）。`None` = 真源里「不在 MATERIALS」那支。

    异常**不吞**：`signin_claim`/运势/幸运符/金币这几段在真源里就不在 try 内，异常照原样上抛。
    随机流与真源逐位一致：本函数只抽 1 次 `random.random()`（运势），且用的就是 `random` 模块本身
    （测试对 `random.random` 打桩、对 `random.seed` 定种都照旧生效）。
    """
    _claimed, streak, total = db.signin_claim(group_id, qq_id, today, yesterday)
    if not _claimed:
        return None
    # v87 02 章 7.6：每日运势（签到随机三档：大吉/平/小凶；幸运符可+1 档）
    # v125：阈值数据下沉 signin_config.SIGNIN_CONFIG
    fortune_roll = random.random()
    if fortune_roll < cfg["fortune_bad_th"]:
        fortune = "小凶"   # 15%：当日金币 -10%
    elif fortune_roll < cfg["fortune_good_th"]:
        fortune = "平"     # 40%：无效果
    else:
        fortune = "大吉"   # 45%：当日经验 +10%
    # 幸运符：使用后当日运势+1 档（小凶→平→大吉→大吉）
    if fortune == "小凶":
        if luck_mat is not None and db.count_item(group_id, qq_id, luck_mat) > 0:
            db.remove_item(group_id, qq_id, luck_mat)
            fortune = "平"
    elif fortune == "平":
        if luck_mat is not None and db.count_item(group_id, qq_id, luck_mat) > 0:
            db.remove_item(group_id, qq_id, luck_mat)
            fortune = "大吉"
    db.set_event_state("daily_fortune_%s_%s" % (group_id, qq_id),
                       json.dumps({"date": today, "fortune": fortune}))
    # 连续签到（streak/total 已由 signin_claim 原子算好）
    # v125：奖励数值数据下沉 signin_config.SIGNIN_CONFIG
    gold = cfg["base_gold"] + streak * cfg["streak_gold_step"]
    # 节日庆典：签到奖励翻倍
    cur_evt = db.get_world_event()
    festival = bool(cur_evt and cur_evt["etype"] == "festival")
    if festival:
        gold *= cfg["festival_mult"]
    return {"streak": streak, "total": total, "fortune": fortune, "gold": gold,
            "festival": festival}


# ============================================================
# ④ 成就面板（`成就 [分类|领取]`：总览 / 分类明细 / 领取回执）
# ============================================================
# 成就分类（**顺序 = 面板渲染顺序**，真源 `commands/misc.py:achievements` 的 `cats`）
ACH_CATS = ["战斗", "成长", "探索", "副业", "社交", "隐藏"]
# 奖励 key → 中文（真源 `_RW_CN`）
_RW_CN = {"exp": "经验", "gold": "金币"}
# 档位三态（引擎 `collect` 形状的通用标识）→ 面板标记（措辞是本内容侧的口径）
_TIER_MARK = {LOCKED: "⬜", READY: "🎁", CLAIMED: "✅"}


def _ach_tally(rows, unlocked) -> Tally:
    """N/M 进度（引擎 `collect.Tally`）：一条算数当且仅当它的 id 已解锁。"""
    return Tally(rows, hit=lambda a: a["id"] in unlocked)


def _ach_board(table, unlocked, claimed) -> TierBoard:
    """成就档位状态机（引擎 `collect.TierBoard`）：达成 = 已解锁；可领 = 该项配了奖励。

    `claimed` 由调用方给（面板路径只读；领取路径同一形状的 `claim()` 会就地记入）。
    """
    return TierBoard(table,
                     claimed=claimed,
                     key=lambda a: a["id"],
                     reached=lambda a: a["id"] in unlocked,
                     claimable=lambda a: bool(a.get("reward")))


def achievement_panel(raw: str, table, unlocked, claimed, points: int) -> list:
    """成就面板行（真源 `commands/misc.py:achievements` 的 :340-390 逐行等价）。

    `table` = 成就表（`[{id,cat,name,desc,cond,points,reward,…}]`，**源列表序** —— 分类明细的
    渲染顺序即它）；`unlocked`/`claimed` = 已解锁 / 已领取的成就 id 集合（宿主从 DB 取）；
    `points` = 成就点（宿主 core 算）。返回行列表（宿主还要补 "" + 底部随机提示行）。

    档位三态（未达成 / 可领 / 已领）走引擎收集形状 `collect.TierBoard`：
    达成判据 = 已解锁，可领判据 = 该项配了奖励；三态 → 面板标记的映射见 `_TIER_MARK`。
    """
    cat = raw if raw in ACH_CATS else ""
    achs = [a for a in table if (not cat or a["cat"] == cat)]
    if cat:
        title = _T.static("achp.title_cat") % cat
    else:
        title = _T.static("achp.title")
    total_all = len(table)
    got_all = len(unlocked)
    board = _ach_board(table, unlocked, claimed)
    pending_cnt = board.pending()
    lines = [title, "━━━━━━━━━━━━"]
    if pending_cnt:
        lines.append(_T.static("achp.pending") % pending_cnt)
    if cat:
        got_c, total_c = _ach_tally(achs, unlocked).progress()
        lines.append(_T.static("achp.cat_progress") % (got_c, total_c))
        for a in achs:
            mark = _TIER_MARK[board.state(a)]
            rw = a.get("reward") or {}
            # v105 M18 P3：奖励 key 显示中文（经验/金币），对齐解锁提示 _reward_txt
            # v140 波2：items 物品奖励也显示（《物品名》×N）
            rw_parts = []
            for k, v in rw.items():
                if k == "items":
                    for _ik, _ic in (v or {}).items():
                        rw_parts.append("%s×%s" % (item_name(_ik), _ic))
                else:
                    rw_parts.append("%s+%s" % (_RW_CN.get(k, k), v))
            rw_txt = "（%s）" % "、".join(rw_parts) if rw_parts else ""
            lines.append("%s %s：%s%s" % (mark, a["name"], a["desc"], rw_txt))
    else:
        lines.append(_T.static("achp.total") % (got_all, total_all, points))
        for c in ACH_CATS:
            sub = [a for a in table if a["cat"] == c]
            got_c, total_c = _ach_tally(sub, unlocked).progress()
            lines.append(_T.static("achp.cat_row")
                         % ("✅" if got_c == total_c else "⬜", c, got_c, total_c, c))
    return lines


def claim_reply(lines, err) -> str:
    """『成就 领取』的一整条回执（真源 :334-338 逐行等价）。"""
    return ("🎁 %s" % err) if err else "\n".join(lines)


# ============================================================
# ⑤ 意见箱（`意见 <内容>`：校验 / 频控 / 入库）
# ============================================================
FEEDBACK_CD_SECONDS = 30           # 同 qq 30 秒内限 1 条（真源 :407 的注释口径）
FEEDBACK_MAX_LEN = 200             # 单条上限（真源 :404）
MSG_EMPTY = """📮 想给格温提建议？发『意见 <你的想法>』就行～
例：『意见 希望能出个坐骑系统』"""
MSG_TOO_LONG = """❌ 意见太长啦(≤200 字)，精简一下再说～"""
MSG_TOO_FAST = """意见发送太频繁，请稍后再试～"""
MSG_SAVE_FAIL = """❌ 意见保存失败，稍后再试试～"""


def _fb_cd_key(qq_id) -> str:
    return "fb_cd_%s" % qq_id


def _fb_cd(qq_id) -> Cooldown:
    """意见箱频控（引擎周期形状 `periodic.Cooldown`：末次触达时刻 + 窗口）。

    存储面 = 包内 event_state 读写口；**键由本模块拼**（存档口径，逐字节不变）；
    `now` 由调用方给（引擎不读钟）。
    """
    return Cooldown(db.get_event_state, db.set_event_state, _fb_cd_key(qq_id),
                    window=FEEDBACK_CD_SECONDS)


def feedback_precheck(args: str, qq_id, now_ts: float):
    """意见箱前置校验（真源 :401-416 逐行等价）：返回拒绝文案；放行 → `None`。

    频控读 `event_state`（`fb_cd_<qq>`）；读失败/值坏 → 视为「没提过」（真源同款宽容口径，
    由引擎 `Cooldown.last()` 的坏值兜底承担）。
    """
    if not args:
        return MSG_EMPTY
    if len(args) > FEEDBACK_MAX_LEN:
        return MSG_TOO_LONG
    # q11 低风险项：同 qq 30 秒内限 1 条（意见箱防刷屏），沿用 event_state 存末次提交时间戳
    if not _fb_cd(qq_id).ready(now_ts):
        return MSG_TOO_FAST
    return None


def feedback_submit(group_id, qq_id, args: str, now_ts: float) -> dict:
    """入库 + 记频控时间戳 + 回执文案（真源 :417-425 逐行等价；异常**不吞**，调用方记日志 + 回执）。"""
    fid = db.add_feedback(qq_id, group_id, args)
    # 持续成功的频控：仅成功后更新时间戳，避免失败的尝试锁住玩家再次提交
    _fb_cd(qq_id).touch(now_ts)
    text = (_T.static("fb.receipt") % (fid, args))
    return {"fid": fid, "text": text}


# ============================================================
# ⑥ 物品域读口（items.json；惰性加载）
# ============================================================
_ITEMS = None


def _items() -> dict:
    """包内 items 域（`content/data/items.json`，900 条）—— 惰性加载（没用到就不读）。"""
    global _ITEMS
    if _ITEMS is None:
        _ITEMS = _read_json(os.path.join(_DATA_DIR, "items.json"), {}) or {}
    return _ITEMS


def item_name(key: str) -> str:
    """物品 key → 显示名；查不到 / 非对象 → **原样返回 key**。

    真源 `(C.ITEMS.get(k) or C.MATERIALS.get(k) or {}).get("name", k)` 的等价口：items 域 =
    `ITEMS` 全量且 `MATERIALS ⊆ ITEMS`（导出器已证），故一次查表与真源两次查表逐条等价。
    """
    ent = _items().get(key)
    if isinstance(ent, dict):
        return ent.get("name", key)
    return key
