# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 多轮对话（U1-I8：形状进引擎 `saintess_engine.dialogue`）。

本模块 = **薄包装 + 取值注入**。对话树的形状（取节点 / 条件槽 / 渲染槽 / 路由 / 会话游标）
已进引擎 `saintess_engine/dialogue/__init__.py`；这里只留三件事：

1. **数据读口**：`_dialogues()` / `_main_quests()` / `_read_domain()`（读包内 `content/data/*.json`）。
2. **注入面**：`_CFG = Dialogue(end_marker=…, fallback_text=…, conditions=…, unknown=…, text_sources=…)`
   —— 引擎**零默认值**，结束哨兵 / 兜底台词 / 条件查表口 / 未知键策略 / 自动文本源全在这里给。
3. **对外 6 名**：`get_dialogue` / `dialogue_node` / `check_need` / `visible_options` / `node_text` / `is_end`
   —— **签名与返回一字不改**（`content/facade.py:177-178` 注册了前两名；`talk_actions.py:143`、
   `shop.py:295-298`、`world_cmds.py:2840/2845/3216/3217/3542/3568/3570/3603/3609` 直取；
   `tests/test_v98_03_registry.py:44` 直取 `check_need`）。

两个**取值**私有函数（形状搬走后剩下的「内容判断」）
----------------------------------------------------
| 私有函数 | 是什么取值 |
|---|---|
| `_story_text(node, ctx)` | `text_from == "story"` 的自动台词源：扫主线表 + giver 校验 + `_story_to_line` 的中文冒号/书名号正则 |
| `_unknown_need(key, value)` | 未注册 need 键的策略：生产「告警 + 放行」/ 测试「`raise`」（`os.environ` 判定在内容侧） |

数据面（**本模块零改动**）：`content/data/dialogues.json`（39 树 / 708 节点 / 1973 选项）·
`content/data/quests.json`（主线 70 条）· 条件谓词与条件名全在 `content/dialogue_conds.py`。
存档面（`event_state: talk_{gid}_{qid}` = `{"npc": …, "node": …}`）仍在 `content/persistence/world.py`，
本线一字不动。

口径分歧（**故意保留，后人不得顺手统一**，见 `U1-I4_DESIGN.md` §2.8 + 门禁①逐条断言）
------------------------------------------------------------------------------------
① 未知节点**回退 `start`**（不是 `{}`、不是「结束」）；② `side_menu: {}` 走展开分支（`null` 走普通分支）；
③ 未注册 need 键：测试 `raise` / 生产告警放行；④ `texts` 取**声明序第一个满足者**（不取「最具体」）；
⑤ 变体缺 `text` 键 → `KeyError`，节点缺 `text` → 兜底台词；⑥ `options()` 返回**原对象**（`is` 相同）；
⑦ 空壳会话 `{}` 与坏值都还原不出游标，但「要不要清残留」在调用方；
⑧ 谓词结果用**真值**判定（不是 `is False`）；⑨ 节点值可为 `None`（判据是「键在不在」）；
⑩ `text_from` 是**注入表**而不是枚举。

等价证据：`tests/test_u1i4_dialogue_frozen.py`（门禁①：30 段冻结 + 双 sha256 + 39×708×1973×704
六口逐格比对 + 10 条口径分歧 + 4 处有牙反证 + 只读断言）· `tests/_u1i4_dialogue_gen.py`（切片生成器）。
"""
from __future__ import annotations

import json
import os
import re

from saintess_engine.dialogue import Dialogue

from . import obs                                 # noqa: E402  包内唯一日志取用口（fail-closed）
from .dialogue_conds import CONDITIONS            # 条件名 + 谓词实现全在内容侧

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content


def _read_domain(domain: str, sub: str = "data", default=None):
    """读包内 `content/<sub>/<domain>.json`（缺文件 / 坏 JSON → default，不抛）。

    与 `content/talk_actions.py:48` / `content/quests_flow.py:62` 同款小门面。
    """
    try:
        with open(os.path.join(_HERE, sub, "%s.json" % domain), encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                       # noqa: BLE001
        return {} if default is None else default


_DIALOGUES = None
_MAIN_QUESTS = None


def _dialogues() -> dict:
    """包内 `dialogues` 域（真源 `C.DIALOGUES`，逐键逐值等同）。"""
    global _DIALOGUES
    if _DIALOGUES is None:
        _DIALOGUES = _read_domain("dialogues")
    return _DIALOGUES


def _main_quests() -> list:
    """包内 `quests` 域的主线子集（真源 `from ..data import MAIN_QUESTS`）。

    真源消费方式全是「按 id 扫表」⇒ 顺序无语义（与 `content/quests_flow.py:264` 同口径）。
    """
    global _MAIN_QUESTS
    if _MAIN_QUESTS is None:
        raw = _read_domain("quests")
        _MAIN_QUESTS = [v for v in raw.values() if v.get("source") == "main"]
    return _MAIN_QUESTS


_STORY_PREFIX = re.compile(r"^[^：:]{1,20}[：:]\s*")


def _story_to_line(raw: str) -> str:
    """任务 story/ending 文本 → NPC 台词（v101.23d A 级：text_from 自动生成）

    格式多为『NPC名：台词』或『NPC名：『台词』』（少数叙事型『老约翰交给玩家一封信：『…』』）。
    规则：剥 NPC 名前缀 → 取 『』/“” 引号内 → 都没有就原样降级（叙事型也能念）。
    """
    if not raw:
        return ""
    body = _STORY_PREFIX.sub("", raw.strip())
    m = re.match(r"^[“『](.+)[”』]$", body.strip())
    return m.group(1) if m else body


def _story_text(node, ctx) -> str:
    """`text_from == "story"` 的自动台词源（引擎 `text_sources` 表里那一个取值）。

    从『当前主线任务』的 `story` 字段生成接取台词（**giver 校验，防串台**）：
    多任务 NPC 加新任务 = 纯数据，quest_talk 台词自动跟任务走，不用手写变体。
    取不到 / 校验不过 / 生成空 → 返回假值，引擎落节点 `text` 或兜底台词。
    """
    quests = ctx.get("quests") or {}
    mid = quests.get("main_quest")
    if not mid:
        return ""
    mq = next((q for q in _main_quests() if q["id"] == mid), None)
    if mq and (not mq.get("giver") or mq.get("giver") == ctx.get("npc_id")):
        return _story_to_line(mq.get("story", ""))
    return ""


def _unknown_need(key, value) -> bool:
    """未注册 need 键的策略（**取值**：生产告警放行 / 测试 `raise`）—— 引擎不读环境。

    v104 M21 P1：未注册条件键 → 生产放行但告警（防数据笔误静默变永远可见）；
    v110.5 X3：显式判定测试环境——既看私有库名含 "test"（旧约定兼容），
    也认 `GWEN_TEST_MODE=1`（私有库名不含 "test" 时测试行为漂移的根因）。
    """
    _db = os.environ.get("GWEN_GAME_DB", "")
    _msg = (f"[dragonfall] 对话条件未注册键 need[{key!r}]={value!r}："
            f"数据笔误？已按'永远可见'放行，请检查 dialogues.py")
    _test = ("test" in os.path.basename(_db).lower()
             or os.environ.get("GWEN_TEST_MODE") == "1")
    if _test:
        raise ValueError(_msg)
    obs.log().warning(_msg)
    return True


#: 注入面（引擎零默认值 → 取值全在内容侧）：
#:   end_marker    = 数据里 586 次出现（路由约定的结束哨兵）
#:   fallback_text = 节点无台词时的中文兜底
#:   conditions    = `content/dialogue_conds.py` 的注册表（`Conditions` 实例，引擎鸭子类型用）
#:   unknown       = 未注册 need 键策略（本模块 `_unknown_need`）
#:   text_sources  = `text_from` 取值 → 生成器（本模块 `_story_text`）
_CFG = Dialogue(
    end_marker="__end__",
    fallback_text="……",
    conditions=CONDITIONS,
    unknown=_unknown_need,
    text_sources={"story": _story_text},
)


def get_dialogue(npc_id: str):
    """返回 NPC 的对话树(dict)或 None(未配置多轮对话 → 走旧单轮逻辑)。

    ⚠️ **数据读口留内容侧**（引擎不提供数据读口）：这里仍然是「域 JSON 直读」。
    """
    dlg = _dialogues().get(npc_id)
    return dlg if dlg else None


def dialogue_node(dlg, node_id: str):
    """取对话树中的节点；不存在回退到 start 节点（判据是「键在不在」，键在值为 None 也原样返回）。"""
    return _CFG.of(dlg).node(node_id)


def check_need(need, ctx: dict) -> bool:
    """判断选项条件是否满足。ctx = {player, quests, flags}

    v98.3：条件判定全数据化 → `core/dialogue_conds.py CONDITIONS` 注册表。
    need 支持的键（quest_done/quest_active/quest_pending/quest_ready/side_ready/
    quest_any_active/apprentice/not_apprentice/is_novice/not_novice/class_any/
    evolve_ready）见该文件；
    v113 增补：race_is/hidden_unlocked/hidden_current/not_hidden_current/side_available。
    加新条件类型 = register 一个函数（~5 行），本文件零改动。
    """
    return _CFG.satisfied(need, ctx)


def visible_options(dlg, node, ctx: dict) -> list:
    """过滤出当前可见的选项(need 不满足的隐藏)

    v127.6 side_menu 动态菜单：选项带非空 'side_menu' 键时，调用命令层注入的
    ctx['side_menu_expand'](opt) 回调，将该选项展开成一组动态子选项
    （每个子选项自带 text/next/action，如『接『支线名』(目标)』）；
    未注入回调、need 不满足、或展开为空 → 该选项整体不出现
    （无活儿可接时不显示菜单）。core 层保持纯逻辑、零 DB，回调由命令层注入。
    """
    return _CFG.of(dlg).options(node, ctx, expand=ctx.get("side_menu_expand"))


def node_text(node, ctx: dict) -> str:
    """节点台词：texts 条件变体优先（need 满足的第一个），否则默认 text；
    v101.23d：text_from 支持——节点写 {"text_from": "story"} 时，无变体匹配则
    从『当前主线任务』的 story 字段自动生成接取台词（giver 校验，防串台）。
    多任务 NPC 加新任务 = 纯数据，quest_talk 台词自动跟任务走，不用手写变体。"""
    return _CFG.text(node, ctx)


def is_end(node_id: str) -> bool:
    """__end__ 是结束对话的哨兵节点"""
    return _CFG.is_end(node_id)
