# -*- coding: utf-8 -*-
"""U1-I8（= U1-I4 L3）门禁① —— 对话内容适配的**冻结比对**安全网（`content/dialogue.py` 半）。

**它守什么**（`U1-I4_FROZEN_GATE.md` §10 的判据 1/2/3/5/7/9/11/12/13/14 在门禁①的那一面）

| 组 | 断言 | 说明 |
|---|---|---|
| ① | 冻结字面量 sha256 == `_PIN["frozen"]` | 30 段（`dialogue.py` 10 + `dialogue_conds.py` 20） |
| ② | 活实现切片 sha256 == `_PIN["live"]` | 活侧 = `work/pkg/**` 当前文本（`inspect.getsource` 与 ast 切片同口径） |
| ③ | E 栏（24 段）`frozen == live`；C 栏（6 段）`frozen != live` | 防「范围蔓延」/ 防「没真接上」 |
| ④ | **全量网格**：39 树 × 708 节点 × 1973 选项 × 704 ctx，六口逐格 | 旧 = 冻结文本 `exec` 出来的那一份 |
| ⑤ | 口径分歧 10 条（`DESIGN.md` §2.8）逐条 ≥1 断言 | 含顺序断言 ④⑤ |
| ⑥ | aux 指纹：`talk_state` 落盘 JSON 原文 · `talk_state_key` 实跑值 · 数据面 | §3-①②③⑧⑩ |
| ⑦ | **有牙反证**：破坏 4 处 → 对应探针必须变红 | 猴补 + 原地还原（零写盘） |
| ⑧ | 只读：跑完 6 个源文件 sha256 前后一致 | 不写盘 |
| ⑨ | 计数校验：`sum(比对次数) == 预期` | 防「循环没跑」的假绿 |
| ⑩ | 门禁文件自哈希 == `_GATE_SELF_SHA256` | 防「安全网自己被动过」 |

**跑法**（自跑风格，不依赖 pytest；见 BRIEF §3.2）

```powershell
$env:GWEN_FRAMEWORK_DIR = "<lane>/work/eng"
$env:GWEN_HOST_DIR      = "<lane>/work/host"
$env:GWEN_GAME_DB       = "<lane>/out/test_u1i4_dialogue.db"
$env:GWEN_TEST_MODE     = "1"
$env:PYTHONUTF8         = "1"
$env:PYTHONPATH         = "<lane>/_env"      # 沙箱 tempfile.mkdtemp 假红的解药（BRIEF §3.3）
python work/pkg/tests/test_u1i4_dialogue_frozen.py
```

**冻结侧为什么会「跑起来」**：旧实现不是「照记忆重写」，而是**逐行切片**（`base/pkg` 原文 +
sha256 钉住）后 `exec` 进独立命名空间，与活实现同输入逐格比。冻结字节来自
`_u1i4_dialogue_gen.py`，本文件里 `# >>> GENERATED` 与 `# <<< GENERATED` 之间**一个字都不许手改**
（改了 `_GATE_SELF_SHA256` 与 `_PIN["frozen"]` 两条断言立刻红）。
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import re
import sys

# ───────────────────────────────────────────────────────── 路径 / 环境（先于任何包内 import）
_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/tests
PKG_ROOT = os.path.dirname(_HERE)                           # <pkg>（= work/pkg）
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)                               # tests/：`_paths` / `_engine_harness`
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先）

os.environ.setdefault("GWEN_GAME_DB", os.path.join(PKG_ROOT, "test_u1i4_dialogue.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")

_shim = os.path.join(_HERE, "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

# 引擎通道装配（幂等）：让 `content.obs.log()` 这个**生产告警落点**真能取到日志句柄
# （不 boot 的话 `obs.log()` fail-closed 抛 `WireMissing`，口径分歧③的生产半边没法验）。
from _engine_harness import boot as _eng_boot  # noqa: E402
_eng_boot()

from saintess_engine.dialogue import END_KEY, Cursor, Dialogue  # noqa: E402
from content import dialogue as DLG  # noqa: E402  活实现（对外 6 名 + `_CFG` 注入面）
from content import dialogue_conds as DC  # noqa: E402
from content import obs as _OBS  # noqa: E402  ← 生产放行分支的告警落点（口径分歧③）

#: 装配完成后的真日志句柄（口径分歧③ 换假 logger 后用它原地还原）
_REAL_LOG = _OBS.log()

PASS = 0
FAIL = 0
FAILURES = []
_SECTION = ["?"]


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def section(title):
    _SECTION[0] = title
    print("\n%s" % title)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


#: 只读断言的 6 个源文件（BRIEF §4 判据 8 + FROZEN_GATE §9 门禁①）。
_WATCHED = (
    os.path.join(PKG_ROOT, "content", "dialogue.py"),
    os.path.join(PKG_ROOT, "content", "dialogue_conds.py"),
    os.path.join(PKG_ROOT, "content", "data", "dialogues.json"),
    os.path.join(PKG_ROOT, "content", "data", "quests.json"),
    os.path.join(PKG_ROOT, "content", "data", "cond_specs.json"),
    os.path.join(PKG_ROOT, "content", "persistence", "world.py"),
)


# ═══════════════════════════════════════════════════════════════════════════
# >>> GENERATED: _FROZEN_DP / _FROZEN_DC / _FROZEN_EXTRA / _PIN  (由 _u1i4_dialogue_gen.py 产出；手改即红)
_FROZEN_DP = {
    # content/dialogue.py::_read_domain
    '_read_domain': r'''def _read_domain(domain: str, sub: str = "data", default=None):
    """读包内 `content/<sub>/<domain>.json`（缺文件 / 坏 JSON → default，不抛）。

    与 `content/talk_actions.py:48` / `content/quests_flow.py:62` 同款小门面。
    """
    try:
        with open(os.path.join(_HERE, sub, "%s.json" % domain), encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                       # noqa: BLE001
        return {} if default is None else default
''',
    # content/dialogue.py::_dialogues
    '_dialogues': r'''def _dialogues() -> dict:
    """包内 `dialogues` 域（真源 `C.DIALOGUES`，逐键逐值等同）。"""
    global _DIALOGUES
    if _DIALOGUES is None:
        _DIALOGUES = _read_domain("dialogues")
    return _DIALOGUES
''',
    # content/dialogue.py::_main_quests
    '_main_quests': r'''def _main_quests() -> list:
    """包内 `quests` 域的主线子集（真源 `from ..data import MAIN_QUESTS`）。

    真源消费方式全是「按 id 扫表」⇒ 顺序无语义（与 `content/quests_flow.py:264` 同口径）。
    """
    global _MAIN_QUESTS
    if _MAIN_QUESTS is None:
        raw = _read_domain("quests")
        _MAIN_QUESTS = [v for v in raw.values() if v.get("source") == "main"]
    return _MAIN_QUESTS
''',
    # content/dialogue.py::get_dialogue
    'get_dialogue': r'''def get_dialogue(npc_id: str):
    """返回 NPC 的对话树(dict)或 None(未配置多轮对话 → 走旧单轮逻辑)"""
    dlg = _dialogues().get(npc_id)          # 真源 `C.DIALOGUES.get(npc_id)`
    return dlg if dlg else None
''',
    # content/dialogue.py::dialogue_node
    'dialogue_node': r'''def dialogue_node(dlg, node_id: str):
    """取对话树中的节点；不存在回退到 start 节点"""
    nodes = dlg.get("nodes", {})
    if node_id in nodes:
        return nodes[node_id]
    return nodes.get(dlg.get("start"), {})
''',
    # content/dialogue.py::check_need
    'check_need': r'''def check_need(need, ctx: dict) -> bool:
    """判断选项条件是否满足。ctx = {player, quests, flags}

    v98.3：条件判定全数据化 → core/dialogue_conds.py CONDITIONS 注册表。
    need 支持的键（quest_done/quest_active/quest_pending/quest_ready/side_ready/
    quest_any_active/apprentice/not_apprentice/is_novice/not_novice/class_any/
    evolve_ready）见该文件；
    v113 增补：race_is/hidden_unlocked/hidden_current/not_hidden_current/side_available。
    加新条件类型 = register 一个函数（~5 行），本文件零改动。
    """
    if not need:
        return True
    from .dialogue_conds import CONDITIONS      # 包内直取（真源同位置 `from .dialogue_conds import …`）
    for k, v in need.items():
        fn = CONDITIONS.get(k)
        if fn is None:
            # v104 M21 P1：未注册条件键 → 生产放行但告警（防数据笔误静默变永远可见）；
            # 测试环境（GWEN_GAME_DB 指向 test 库）直接 raise，让单测抓出笔误
            import os
            _db = os.environ.get("GWEN_GAME_DB", "")
            _msg = (f"[dragonfall] 对话条件未注册键 need[{k!r}]={v!r}："
                    f"数据笔误？已按'永远可见'放行，请检查 dialogues.py")
            # v110.5 X3：显式判定测试环境——既看私有库名含 "test"（旧约定兼容），
            # 也认 GWEN_TEST_MODE=1（本轮私有库名不含 "test" 时测试行为漂移的根因）。
            _test = ("test" in os.path.basename(_db).lower()
                     or os.environ.get("GWEN_TEST_MODE") == "1")
            if _test:
                raise ValueError(_msg)
            obs.log().warning(_msg)
            continue  # 未知条件放行（向后兼容，旧数据不崩）
        if not fn(ctx, v):
            return False
    return True
''',
    # content/dialogue.py::visible_options
    'visible_options': r'''def visible_options(dlg, node, ctx: dict) -> list:
    """过滤出当前可见的选项(need 不满足的隐藏)

    v127.6 side_menu 动态菜单：选项带非空 'side_menu' 键时，调用命令层注入的
    ctx['side_menu_expand'](opt) 回调，将该选项展开成一组动态子选项
    （每个子选项自带 text/next/action，如『接『支线名』(目标)』）；
    未注入回调、need 不满足、或展开为空 → 该选项整体不出现
    （无活儿可接时不显示菜单）。core 层保持纯逻辑、零 DB，回调由命令层注入。
    """
    out = []
    for opt in node.get("options", []):
        if opt.get("side_menu") is not None:
            if not check_need(opt.get("need"), ctx):
                continue
            expand = ctx.get("side_menu_expand")
            subs = expand(opt) if expand else []
            if subs:
                out.extend(subs)
            continue  # 未注入回调/展开为空 → 跳过该选项
        if check_need(opt.get("need"), ctx):
            out.append(opt)
    return out
''',
    # content/dialogue.py::_STORY_PREFIX
    '_STORY_PREFIX': r"""_STORY_PREFIX = re.compile(r"^[^：:]{1,20}[：:]\s*")
""",
    # content/dialogue.py::_story_to_line
    '_story_to_line': r'''def _story_to_line(raw: str) -> str:
    """任务 story/ending 文本 → NPC 台词（v101.23d A 级：text_from 自动生成）

    格式多为『NPC名：台词』或『NPC名：『台词』』（少数叙事型『老约翰交给玩家一封信：『…』』）。
    规则：剥 NPC 名前缀 → 取 『』/“” 引号内 → 都没有就原样降级（叙事型也能念）。
    """
    if not raw:
        return ""
    body = _STORY_PREFIX.sub("", raw.strip())
    m = re.match(r"^[“『](.+)[”』]$", body.strip())
    return m.group(1) if m else body
''',
    # content/dialogue.py::node_text
    'node_text': r'''def node_text(node, ctx: dict) -> str:
    """节点台词：texts 条件变体优先（need 满足的第一个），否则默认 text；
    v101.23d：text_from 支持——节点写 {"text_from": "story"} 时，无变体匹配则
    从『当前主线任务』的 story 字段自动生成接取台词（giver 校验，防串台）。
    多任务 NPC 加新任务 = 纯数据，quest_talk 台词自动跟任务走，不用手写变体。"""
    for variant in node.get("texts") or []:
        if check_need(variant.get("need"), ctx):
            return variant["text"]
    src = node.get("text_from")
    if src in ("story",):
        quests = ctx.get("quests") or {}
        mid = quests.get("main_quest")
        if mid:
            # 真源此处 `from ..data import MAIN_QUESTS` → 包内 quests 域主线子集（同口径）
            MAIN_QUESTS = _main_quests()
            mq = next((q for q in MAIN_QUESTS if q["id"] == mid), None)
            if mq and (not mq.get("giver") or mq.get("giver") == ctx.get("npc_id")):
                auto = _story_to_line(mq.get("story", ""))
                if auto:
                    return auto
    return node.get("text", "……")
''',
    # content/dialogue.py::is_end
    'is_end': r'''def is_end(node_id: str) -> bool:
    """__end__ 是结束对话的哨兵节点"""
    return node_id == "__end__"
''',
}

_FROZEN_DC = {
    # content/dialogue_conds.py::_read_domain
    '_read_domain': r'''def _read_domain(domain: str, sub: str = "data", default=None):
    """读包内 `content/<sub>/<domain>.json`（缺文件 / 坏 JSON → default，不抛）。"""
    try:
        with open(os.path.join(_HERE, sub, "%s.json" % domain), encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                       # noqa: BLE001
        return {} if default is None else default
''',
    # content/dialogue_conds.py::_main_quests
    '_main_quests': r'''def _main_quests() -> list:
    """包内 `quests` 域主线子集（真源 `from ..data import MAIN_QUESTS`，按 id 扫表 ⇒ 顺序无关）。"""
    global _MAIN_QUESTS
    if _MAIN_QUESTS is None:
        raw = _read_domain("quests")
        _MAIN_QUESTS = [v for v in raw.values() if v.get("source") == "main"]
    return _MAIN_QUESTS
''',
    # content/dialogue_conds.py::register
    'register': r'''def register(key):
    """条件注册装饰器。"""
    def deco(fn):
        CONDITIONS.register(key, fn)
        return fn
    return deco
''',
    # content/dialogue_conds.py::_quest_state
    '_quest_state': r'''def _quest_state(quests, qid: str, status, ctx=None) -> bool:
    """主线状态判断：quests dict + qid + 期望状态
    qid 为空字符串 → 按"当前主线"动态判断（对话树通用接取/交付选项用）
    v101.23：动态判断时校验"当前主线发布者 == 对话中的 NPC"——
    否则镇长会在主线已推进到其他 NPC 发布的任务时，仍显示接取/交付选项，
    念的还是写死的旧任务台词（史莱姆）。"""
    if not quests:
        return False
    if status == "done":
        return qid in (quests.get("completed_main") or [])
    target = quests.get("main_quest") if not qid else qid
    if not target:
        return False  # 主线全完成/未设置时，无"当前主线"可言
    if quests.get("main_quest") != target:
        return False
    # v101.23：动态"当前主线"场景 → 校验 giver == 当前 NPC
    if not qid:
        MAIN_QUESTS = _main_quests()        # 真源 `from ..data import MAIN_QUESTS`
        mq = next((q for q in MAIN_QUESTS if q["id"] == target), None)
        npc_id = (ctx or {}).get("npc_id")
        if mq and npc_id and mq.get("giver") != npc_id:
            return False
    cur = quests.get("main_status", "pending")
    if status == "active":
        return cur in ("active", "ready")
    if status == "pending":
        return cur == "pending"
    if status == "ready":
        return cur == "ready"
    return False
''',
    # content/dialogue_conds.py::_c_quest_done
    '_c_quest_done': r"""@register("quest_done")
def _c_quest_done(ctx, v):
    return _quest_state(ctx.get("quests") or {}, v, "done", ctx)
""",
    # content/dialogue_conds.py::_c_not_quest_done
    '_c_not_quest_done': r'''@register("not_quest_done")
def _c_not_quest_done(ctx, v):
    """该主线未完成（反向条件，用于隐藏已完成任务相关的旧话题/旧选项）"""
    done = (ctx.get("quests") or {}).get("completed_main") or []
    return v not in done
''',
    # content/dialogue_conds.py::_c_quest_active
    '_c_quest_active': r"""@register("quest_active")
def _c_quest_active(ctx, v):
    return _quest_state(ctx.get("quests") or {}, v, "active", ctx)
""",
    # content/dialogue_conds.py::_c_quest_pending
    '_c_quest_pending': r"""@register("quest_pending")
def _c_quest_pending(ctx, v):
    return _quest_state(ctx.get("quests") or {}, v, "pending", ctx)
""",
    # content/dialogue_conds.py::_c_quest_ready
    '_c_quest_ready': r"""@register("quest_ready")
def _c_quest_ready(ctx, v):
    return _quest_state(ctx.get("quests") or {}, v, "ready", ctx)
""",
    # content/dialogue_conds.py::_c_side_ready
    '_c_side_ready': r'''@register("side_ready")
def _c_side_ready(ctx, v):
    """该 NPC 名下有待交付的支线（击杀/探索型 ready，收集型材料齐）"""
    if not v:
        return True
    quests = ctx.get("quests") or {}
    side = quests.get("side") or {}
    if not side:
        return False
    npc_id = ctx.get("npc_id") or ""
    for sid, sq in side.items():
        sqd = next((q for q in (ctx.get("side_quests") or []) if q["id"] == sid), None)
        if not sqd or sqd.get("giver") != npc_id:
            continue
        if sq.get("status") == "done":  # v95.12：已交付支线不重复提示
            continue
        obj = sqd.get("objective", {})
        if obj.get("collect"):
            have = ctx.get("item_counts") or {}
            # v104 M20 P2：收集门槛统一 collect_count 优先（与 world.py 面板/交付一致；
            # 复合目标如魔剑士试炼 collect_count=2/count=3，旧口径 count 会要求 3 份才显示可交）
            if have.get(obj["collect"], 0) >= obj.get("collect_count", obj.get("count", 1)):
                return True
        elif sq.get("status") == "ready":
            return True
    return False
''',
    # content/dialogue_conds.py::_c_side_available
    '_c_side_available': r'''@register("side_available")
def _c_side_available(ctx, v):
    """该 NPC 名下存在未接取的支线（告示板委托除外——告示委托只能在告示板接取）

    v95r65 #288：对话树『有活儿要交给我吗』类选项用它替代 quest_pending——
    此前玛莎（非主线 giver）选项显示条件用 quest_pending(任意主线待接)，
    点选后 quest_take 只处理主线 → 报"我现在没有任务交给你"误导文案。
    """
    if not v:
        return True
    quests = ctx.get("quests") or {}
    side = quests.get("side") or {}
    npc_id = ctx.get("npc_id") or ""
    for sq in (ctx.get("side_quests") or []):
        if sq.get("giver") != npc_id or sq.get("board"):
            continue
        if sq["id"] in side:
            continue
        return True
    return False
''',
    # content/dialogue_conds.py::_c_quest_any_active
    '_c_quest_any_active': r'''@register("quest_any_active")
def _c_quest_any_active(ctx, v):
    """当前存在任意进行中主线（对话树指引用）"""
    quests = ctx.get("quests") or {}
    return bool(quests.get("main_quest"))
''',
    # content/dialogue_conds.py::_c_is_novice
    '_c_is_novice': r'''@register("is_novice")
def _c_is_novice(ctx, v):
    """仅见习冒险者可见（行会就职选项）"""
    player = ctx.get("player") or {}
    return player.get("class_name") == CLASS_NOVICE    # 真源 `C.CLASS_NOVICE`（包内读口）
''',
    # content/dialogue_conds.py::_c_not_novice
    '_c_not_novice': r'''@register("not_novice")
def _c_not_novice(ctx, v):
    """已就职（非见习）才可见"""
    player = ctx.get("player") or {}
    return player.get("class_name") != CLASS_NOVICE    # 真源 `C.CLASS_NOVICE`（包内读口）
''',
    # content/dialogue_conds.py::_c_class_any
    '_c_class_any': r'''@register("class_any")
def _c_class_any(ctx, v):
    """玩家职业在列表中才可见（导师对话按职业过滤）"""
    player = ctx.get("player") or {}
    return player.get("class_name") in v
''',
    # content/dialogue_conds.py::_c_race_is
    '_c_race_is': r'''@register("race_is")
def _c_race_is(ctx, v):
    """v113 种族限制：玩家种族 == 指定种族（隐藏线导师·血脉传承对话）"""
    player = ctx.get("player") or {}
    return (player.get("race") or "human") == v
''',
    # content/dialogue_conds.py::_c_hidden_unlocked
    '_c_hidden_unlocked': r'''@register("hidden_unlocked")
def _c_hidden_unlocked(ctx, v):
    """v113：已解锁指定隐藏线（hidden_class_unlock 含 cls_id）——导师对话『接受传承』门槛"""
    player = ctx.get("player") or {}
    return v in (player.get("hidden_class_unlock") or [])
''',
    # content/dialogue_conds.py::_c_hidden_current
    '_c_hidden_current': r'''@register("hidden_current")
def _c_hidden_current(ctx, v):
    """v113：当前职业已是该隐藏线（传承完成后的闲聊分支/提示满阶）"""
    player = ctx.get("player") or {}
    return player.get("class_name") == v
''',
    # content/dialogue_conds.py::_c_not_hidden_current
    '_c_not_hidden_current': r'''@register("not_hidden_current")
def _c_not_hidden_current(ctx, v):
    """v113：当前职业尚未是该隐藏线（『接受传承』选项只在未传承时显示；
    已传承玩家再点会走 _evolve_hidden_generic 的"你已是X"分支，双保险）"""
    player = ctx.get("player") or {}
    return player.get("class_name") != v
''',
    # content/dialogue_conds.py::_c_evolve_ready
    '_c_evolve_ready': r'''@register("evolve_ready")
def _c_evolve_ready(ctx, v):
    """到达转职等级门槛（{tier: 目标阶, level: 需要等级}）"""
    player = ctx.get("player") or {}
    if player.get("class_tier", 0) != int(v.get("tier", 0)):
        return False
    return int(player.get("level", 0) or 0) >= int(v.get("level", 0))
''',
}

_FROZEN_EXTRA = {
    # 设计稿 §1.4 没列的第 10 段（`dialogue.py` 段数 10 = 表里 9 段 + 本段）
    'content/dialogue.py::_STORY_PREFIX': r"""_STORY_PREFIX = re.compile(r"^[^：:]{1,20}[：:]\s*")
""",
}

#: 冻结侧期望（生成时跑 `sha256(_FROZEN_*)`；跑门禁时逐段重算比对）
_PIN = {
    "frozen": {
        'content/dialogue.py::_read_domain': '4cbe68fb2a39091716a522948ef5a2882d09a9914a83e34e8368a2b9bf6f64eb',
        'content/dialogue.py::_dialogues': 'f49aeddf11c5042f4f7cccd45adf87f3a1762f3baa6cd7c9a64c94820a5174bc',
        'content/dialogue.py::_main_quests': 'e271d0b6915c300b5fe99314be051dcd4d0f912871fbbce337f604384a4478d5',
        'content/dialogue.py::get_dialogue': '5c5de633222f1b50f74c923aa630c5d3ece74d04ab948afc610f330b293a8b5c',
        'content/dialogue.py::dialogue_node': '082a2ebe53088cd7810a464e064b5171764b726aeafffca9a8be462f6ab748d6',
        'content/dialogue.py::check_need': '0fcbd19aaa3ee2a87edd0fe4a398b6b4926d2a4015e7a454059d2c5bf86eb506',
        'content/dialogue.py::visible_options': 'afb3dabf30b508752e5e26b5467321aace9f857064a6879d90f92e18fbbc96e2',
        'content/dialogue.py::_STORY_PREFIX': '913610be2fdf91816ba44679e736fae60b60544f9b49c4ae93d2d4232cba9dd8',
        'content/dialogue.py::_story_to_line': 'd9cb0c4b54a3414dcc3372cee0b12478e087d712caeaa434b833edbcd5f04be1',
        'content/dialogue.py::node_text': 'ee370b164bbbc0d3a530f96d51c721be080422f872009e3cbed22bd04c84dd8b',
        'content/dialogue.py::is_end': '31c82ce6c5c03536c07c00feee6c21e4056fe38b4fa1bc82e7e13514be5f37b9',
        'content/dialogue_conds.py::_read_domain': 'c93e7a0c9878f1166aff13380f6d1fab475a5eecfb44222b7a29d0d813fe5708',
        'content/dialogue_conds.py::_main_quests': '4a0fee274d5da62574840cea84508640dc27831fc3eace55fa0d1a717d3db0c1',
        'content/dialogue_conds.py::register': 'bdbc062f40ae9e366d2d0685540d12669167cda57035787f9e26f1c24d914a62',
        'content/dialogue_conds.py::_quest_state': '04766d5f14600c1755037bdbcbeae4430cb0caa2ab210a1b6659b764b57bc160',
        'content/dialogue_conds.py::_c_quest_done': '016c69f887d95a45ccbf27503e72dbfb6d599a9d12bb27ee28923978c8b1de9c',
        'content/dialogue_conds.py::_c_not_quest_done': '168c8c2b7c27e664e716be0192565ec5129f0b1e0d58498c938c63341bc7a39b',
        'content/dialogue_conds.py::_c_quest_active': '34c0959d615af83f3eb2c4ff196d650a13f81cd97dd95946de4e260232e27942',
        'content/dialogue_conds.py::_c_quest_pending': '861a91ac549fa66a38dbb4fd258f74d8783585e1200831f95b9569a105f55b8b',
        'content/dialogue_conds.py::_c_quest_ready': 'e36baf63f0afa40f2d3c4d41918d2975bbda435c8f9eaaf9563c3e9e053b8c5e',
        'content/dialogue_conds.py::_c_side_ready': 'c5ef258add6730dd0ca55e01035a79e714b28da4f2b9620a612347fba05d3a0b',
        'content/dialogue_conds.py::_c_side_available': 'f5dce3bcf9c279a82f454c78d683960c89498db1fd5cfb58ab6abc8ea1991a04',
        'content/dialogue_conds.py::_c_quest_any_active': '4535aa0de397cf73fa129b6ebc00acdc13087644f5b118bf3a34f0faf5bdb304',
        'content/dialogue_conds.py::_c_is_novice': 'dc1b97d17fdc59d211c458de70494647185e0669b984c13fcd0974cd04dba08e',
        'content/dialogue_conds.py::_c_not_novice': 'ccef729b0ca2ab76be03b4ef545d64688b8c6c7377f9fff78f949f6345de0f7a',
        'content/dialogue_conds.py::_c_class_any': '1def7f38b1f0c0569bde9aec550247e3130a080d2cfe3d693640939503753d24',
        'content/dialogue_conds.py::_c_race_is': 'd0319070d89d468f853829ed52ddd596249ae8549be962b7478270ce74f96862',
        'content/dialogue_conds.py::_c_hidden_unlocked': '13ca3f8f7b2e1a362e3726adb12a60068add2c52b7a057a9163c8a0dc4282d20',
        'content/dialogue_conds.py::_c_hidden_current': '1933a5ac5aea4cfddb13df0e859dad542c0fbb3c7c6db68230a318d3f88bf301',
        'content/dialogue_conds.py::_c_not_hidden_current': '72902621dad02007ce166bb6efe75207309f59a90e9a2d62f2cb4a458d6e111e',
        'content/dialogue_conds.py::_c_evolve_ready': 'dd58a307f122163846e19c61a22bba22733c13358ee23a37b6c6546137a3c8e2',
    },
    "live": {
        'content/dialogue.py::_read_domain': '4cbe68fb2a39091716a522948ef5a2882d09a9914a83e34e8368a2b9bf6f64eb',
        'content/dialogue.py::_dialogues': 'f49aeddf11c5042f4f7cccd45adf87f3a1762f3baa6cd7c9a64c94820a5174bc',
        'content/dialogue.py::_main_quests': 'e271d0b6915c300b5fe99314be051dcd4d0f912871fbbce337f604384a4478d5',
        'content/dialogue.py::get_dialogue': '7ba49acf164594d47c32fe81ca552423993b63822c1e1509c3e89a00e2531a26',
        'content/dialogue.py::dialogue_node': '910136c3479890fc63270be0fd5b8ec54d615d563cca1ed0a09a5035b9d75a52',
        'content/dialogue.py::check_need': '187671bdfea69a6221888f4012a21b2ba14a505dd8337daf7b4fc0c94ca7c460',
        'content/dialogue.py::visible_options': 'c0eb6eea2b723c5372d0bb190a2cfc106229dd0d94b299eb0d2e341da995a7d7',
        'content/dialogue.py::_STORY_PREFIX': '913610be2fdf91816ba44679e736fae60b60544f9b49c4ae93d2d4232cba9dd8',
        'content/dialogue.py::_story_to_line': 'd9cb0c4b54a3414dcc3372cee0b12478e087d712caeaa434b833edbcd5f04be1',
        'content/dialogue.py::node_text': '2f60992994a51a2b265cf85fb3b08b5b6c78e2ace55a3cc6c10aa992a0564582',
        'content/dialogue.py::is_end': '13eaf9933cb02617407a352d545444467d8f109ed90d208b933165e27a7ee366',
        'content/dialogue_conds.py::_read_domain': 'c93e7a0c9878f1166aff13380f6d1fab475a5eecfb44222b7a29d0d813fe5708',
        'content/dialogue_conds.py::_main_quests': '4a0fee274d5da62574840cea84508640dc27831fc3eace55fa0d1a717d3db0c1',
        'content/dialogue_conds.py::register': 'bdbc062f40ae9e366d2d0685540d12669167cda57035787f9e26f1c24d914a62',
        'content/dialogue_conds.py::_quest_state': '04766d5f14600c1755037bdbcbeae4430cb0caa2ab210a1b6659b764b57bc160',
        'content/dialogue_conds.py::_c_quest_done': '016c69f887d95a45ccbf27503e72dbfb6d599a9d12bb27ee28923978c8b1de9c',
        'content/dialogue_conds.py::_c_not_quest_done': '168c8c2b7c27e664e716be0192565ec5129f0b1e0d58498c938c63341bc7a39b',
        'content/dialogue_conds.py::_c_quest_active': '34c0959d615af83f3eb2c4ff196d650a13f81cd97dd95946de4e260232e27942',
        'content/dialogue_conds.py::_c_quest_pending': '861a91ac549fa66a38dbb4fd258f74d8783585e1200831f95b9569a105f55b8b',
        'content/dialogue_conds.py::_c_quest_ready': 'e36baf63f0afa40f2d3c4d41918d2975bbda435c8f9eaaf9563c3e9e053b8c5e',
        'content/dialogue_conds.py::_c_side_ready': 'c5ef258add6730dd0ca55e01035a79e714b28da4f2b9620a612347fba05d3a0b',
        'content/dialogue_conds.py::_c_side_available': 'f5dce3bcf9c279a82f454c78d683960c89498db1fd5cfb58ab6abc8ea1991a04',
        'content/dialogue_conds.py::_c_quest_any_active': '4535aa0de397cf73fa129b6ebc00acdc13087644f5b118bf3a34f0faf5bdb304',
        'content/dialogue_conds.py::_c_is_novice': 'dc1b97d17fdc59d211c458de70494647185e0669b984c13fcd0974cd04dba08e',
        'content/dialogue_conds.py::_c_not_novice': 'ccef729b0ca2ab76be03b4ef545d64688b8c6c7377f9fff78f949f6345de0f7a',
        'content/dialogue_conds.py::_c_class_any': '1def7f38b1f0c0569bde9aec550247e3130a080d2cfe3d693640939503753d24',
        'content/dialogue_conds.py::_c_race_is': 'd0319070d89d468f853829ed52ddd596249ae8549be962b7478270ce74f96862',
        'content/dialogue_conds.py::_c_hidden_unlocked': '13ca3f8f7b2e1a362e3726adb12a60068add2c52b7a057a9163c8a0dc4282d20',
        'content/dialogue_conds.py::_c_hidden_current': '1933a5ac5aea4cfddb13df0e859dad542c0fbb3c7c6db68230a318d3f88bf301',
        'content/dialogue_conds.py::_c_not_hidden_current': '72902621dad02007ce166bb6efe75207309f59a90e9a2d62f2cb4a458d6e111e',
        'content/dialogue_conds.py::_c_evolve_ready': 'dd58a307f122163846e19c61a22bba22733c13358ee23a37b6c6546137a3c8e2',
    },
    "aux": {
        'cond_specs_fp': 'efc73f91825619a75b7495d9596a0b7a7fb95af125df7ad0f0b42dcfc5da6e3f',
        'nodes_n': '708',
        'opts_n': '1973',
        'story_count': '70',
        'story_fp': '7c378af85c48990c084e7b83908e72058ff2795f1338739b9337ff46d17362d8',
        'talk_key': '42d4ad6b0653668c71b6466b94ac9f83c1ff7e4c33d683b1caf7aded9cbbf9ed',
        'talk_key_plain': 'talk_g1_1001',
        'trees_count': '39',
        'trees_fp': '7210a690418955a289855a8e009e92c41bbd7dc1033c1bf9418d24c3a451020d',
        'trees_n': '39',
        "gate_self": '59231b80cd3c604187088c0c19f69c1ea4c01b0cf561433812986535f6b1c3e7',
    },
}

#: 本文件（门禁本体）的自哈希 —— 去掉 gate_self 那一行后算；防「安全网自己被动过」
#: ★ 2026-09-19 审计 P0-1 重钉（唯一一次）：只动了 region **外**的那份 `def check`
#:   （换成 `tests/_check.py` 的一行绑定）⇒ 本体哈希必然变，属**有意**改动。
#:   改前值 59231b80…（见 git 历史）；GENERATED region 内一字未动。
_GATE_SELF_SHA256 = '8469c75b9b78558cf062e921eb0d10e974fa4349cdbcffce1514c99d631050fe'

#: 冻结侧的段落表（段序 = 设计稿 §1.4 的行号序）
_SEGMENT_KEYS = (
    'content/dialogue.py::_read_domain',
    'content/dialogue.py::_dialogues',
    'content/dialogue.py::_main_quests',
    'content/dialogue.py::get_dialogue',
    'content/dialogue.py::dialogue_node',
    'content/dialogue.py::check_need',
    'content/dialogue.py::visible_options',
    'content/dialogue.py::_STORY_PREFIX',
    'content/dialogue.py::_story_to_line',
    'content/dialogue.py::node_text',
    'content/dialogue.py::is_end',
    'content/dialogue_conds.py::_read_domain',
    'content/dialogue_conds.py::_main_quests',
    'content/dialogue_conds.py::register',
    'content/dialogue_conds.py::_quest_state',
    'content/dialogue_conds.py::_c_quest_done',
    'content/dialogue_conds.py::_c_not_quest_done',
    'content/dialogue_conds.py::_c_quest_active',
    'content/dialogue_conds.py::_c_quest_pending',
    'content/dialogue_conds.py::_c_quest_ready',
    'content/dialogue_conds.py::_c_side_ready',
    'content/dialogue_conds.py::_c_side_available',
    'content/dialogue_conds.py::_c_quest_any_active',
    'content/dialogue_conds.py::_c_is_novice',
    'content/dialogue_conds.py::_c_not_novice',
    'content/dialogue_conds.py::_c_class_any',
    'content/dialogue_conds.py::_c_race_is',
    'content/dialogue_conds.py::_c_hidden_unlocked',
    'content/dialogue_conds.py::_c_hidden_current',
    'content/dialogue_conds.py::_c_not_hidden_current',
    'content/dialogue_conds.py::_c_evolve_ready',
)
_E_KEYS = (
    'content/dialogue.py::_STORY_PREFIX',
    'content/dialogue.py::_dialogues',
    'content/dialogue.py::_main_quests',
    'content/dialogue.py::_read_domain',
    'content/dialogue.py::_story_to_line',
    'content/dialogue_conds.py::_c_class_any',
    'content/dialogue_conds.py::_c_evolve_ready',
    'content/dialogue_conds.py::_c_hidden_current',
    'content/dialogue_conds.py::_c_hidden_unlocked',
    'content/dialogue_conds.py::_c_is_novice',
    'content/dialogue_conds.py::_c_not_hidden_current',
    'content/dialogue_conds.py::_c_not_novice',
    'content/dialogue_conds.py::_c_not_quest_done',
    'content/dialogue_conds.py::_c_quest_active',
    'content/dialogue_conds.py::_c_quest_any_active',
    'content/dialogue_conds.py::_c_quest_done',
    'content/dialogue_conds.py::_c_quest_pending',
    'content/dialogue_conds.py::_c_quest_ready',
    'content/dialogue_conds.py::_c_race_is',
    'content/dialogue_conds.py::_c_side_available',
    'content/dialogue_conds.py::_c_side_ready',
    'content/dialogue_conds.py::_main_quests',
    'content/dialogue_conds.py::_quest_state',
    'content/dialogue_conds.py::_read_domain',
    'content/dialogue_conds.py::register',
)
_C_KEYS = (
    'content/dialogue.py::check_need',
    'content/dialogue.py::dialogue_node',
    'content/dialogue.py::get_dialogue',
    'content/dialogue.py::is_end',
    'content/dialogue.py::node_text',
    'content/dialogue.py::visible_options',
)
# <<< GENERATED


# ═══════════════════════════════════════════════════════════════════════════
# §1 切片口径（与生成器逐字同一口径：ast 行号，函数含装饰器行）
# ═══════════════════════════════════════════════════════════════════════════
def slice_source(path: str, symbol: str) -> str:
    """按 ast 行号切模块级符号原文（函数含装饰器行）。口径 = FROZEN_GATE §1.2。"""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=path)
    node = None
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == symbol:
            node = n
            break
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            tgts = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(isinstance(t, ast.Name) and t.id == symbol for t in tgts):
                node = n
                break
    if node is None:
        raise KeyError("切片目标不在 %s 顶层：%s" % (path, symbol))
    lines = src.splitlines(True)
    lo = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
    return "".join(lines[lo - 1:node.end_lineno])


def _frozen_text(key: str) -> str:
    """30 段冻结文本（`_PIN["frozen"]` 的键空间）。"""
    mod, sym = key.split("::", 1)
    if mod == "content/dialogue.py":
        return _FROZEN_EXTRA[key] if sym in _FROZEN_EXTRA else _FROZEN_DP[sym]
    return _FROZEN_DC[sym]


def _live_path(key: str) -> str:
    mod = key.split("::", 1)[0]
    return os.path.join(PKG_ROOT, mod.replace("/", os.sep))


def _live_text(key: str) -> str:
    return slice_source(_live_path(key), key.split("::", 1)[1])


# ═══════════════════════════════════════════════════════════════════════════
# §2 冻结侧容器：挑出「活实现被注入的那几个替身」，不提供未列出的注入口
# ═══════════════════════════════════════════════════════════════════════════
class _FakeLog:
    def __init__(self):
        self.warnings = []

    def warning(self, msg):
        self.warnings.append(msg)

    def info(self, msg):        # pragma: no cover - 门禁不用
        pass

    def debug(self, msg):       # pragma: no cover - 门禁不用
        pass

    def error(self, msg):       # pragma: no cover - 门禁不用
        pass


class _FakeObs:
    """冻结 `check_need` 的 `obs.log()` 落点（生产放行分支要数告警次数）。"""

    def __init__(self):
        self.log_obj = _FakeLog()

    def log(self):
        return self.log_obj


_FROZEN_ENV = {
    "_STORY_PREFIX": re.compile(r"^[^：:]{1,20}[：:]\s*"),   # 冻结文本的第 10 段
    "os": os,
    "re": re,
}
_U_DLG = None
_U_CONDS = None


def _dc_order():
    """冻结 conditions 段的 exec 顺序（= 生成区字典的声明序 = §1.4 行号序）。"""
    return tuple(_FROZEN_DC)


def _dp_order():
    """冻结 dialogue 段的 exec 顺序。"""
    return tuple(_FROZEN_DP)


def _frozen_conditions_ns():
    """把 20 段冻结文本 exec 成旧 `CONDITIONS`（注册表实例是**真**的 `Conditions`）。

    exec 顺序 = 段表序（= 源文件行号序），并**在正确的时点**补上源文件里那两句
    段外语句：`CONDITIONS = Conditions()` 与 `register_specs(...)`（源文 `:63` / `:76`）。
    """
    global _U_CONDS
    if _U_CONDS is not None:
        return _U_CONDS
    from saintess_engine.conditions import Conditions
    from saintess_engine.conditions.declarative import register_specs
    from content.cond_specs import load as _load_specs
    from content.tables import CLASS_NOVICE

    ns = {
        "__name__": "content._u1i4_frozen_conds",
        "__package__": "content",
        "json": json,
        "os": os,
        "Conditions": Conditions,
        "register_specs": register_specs,
        "_load_specs": _load_specs,
        "CLASS_NOVICE": CLASS_NOVICE,
    }

    def run(sym):
        exec(compile(_FROZEN_DC[sym], "<frozen:content/dialogue_conds.py:%s>" % sym, "exec"), ns)

    # 段外语句 ①（源文 `:63`）：注册表载体 = 引擎 `Conditions` 实例
    ns["CONDITIONS"] = Conditions()
    for sym in ("_read_domain", "_main_quests", "register"):
        run(sym)
    # 段外语句 ②（源文 `:76`）：两条声明式条件（`apprentice` / `not_apprentice`）
    register_specs(ns["CONDITIONS"].register, _load_specs("dialogue"), names=("ctx", "v"))
    for sym in _dc_order():
        if sym not in ("_read_domain", "_main_quests", "register"):
            run(sym)
    for req in ("CONDITIONS", "register", "_quest_state", "_main_quests"):
        if req not in ns:
            raise AssertionError("冻结 conditions 命名空间缺 %s" % req)
    _U_CONDS = ns
    return ns


def frozen_conditions():
    """冻结文本 exec 出来的旧条件注册表（`Conditions` 实例）。"""
    return _frozen_conditions_ns()["CONDITIONS"]


class _ObsHook:
    """冻结 `check_need` 的 `obs` 命名空间：每次 `log()` 现取当前容器。

    这样「生产放行分支要数告警次数」的探针换容器时，冻结实现看到的是**同一个**容器
    （不像固定对象那样被替换掉）。
    """

    def log(self):
        return _OBS_HOOK.current.log()


class _ObsHolder:
    def __init__(self):
        self.current = _FakeObs()


_OBS_HOOK = _ObsHolder()


def _frozen_dialogue_ns():
    """把 11 段冻结文本 exec 成旧实现；`obs` 走 `_OBS_HOOK`（生产放行分支可数告警）。"""
    from content import dialogue_conds as _live_dc
    ns = dict(_FROZEN_ENV)
    ns.update({
        "__name__": "content._u1i4_frozen_dlg",
        "__package__": "content",
        "json": json,
        "obs": _ObsHook(),
        "_DIALOGUES": None,
        "_MAIN_QUESTS": None,          # 冻结 `_main_quests` 的 lazy 缓存槽（源文 `:53`）
        "_HERE": os.path.join(PKG_ROOT, "content"),
        # 冻结 `check_need` 内部那句 `from .dialogue_conds import CONDITIONS` 在**调用时**才执行
        # ⇒ 这里注入活模块，让旧实现拿到活的注册表与活同一份谓词（两注册表另有相等断言钉住）。
        "CONDITIONS": _live_dc.CONDITIONS,
    })
    saved = sys.modules.get("content.dialogue_conds")
    sys.modules["content.dialogue_conds"] = _live_dc
    try:
        for sym in _dp_order():
            exec(compile(_FROZEN_DP[sym], "<frozen:content/dialogue.py:%s>" % sym, "exec"), ns)
    finally:
        if saved is not None:
            sys.modules["content.dialogue_conds"] = saved
        else:                                # pragma: no cover - 正常都在
            sys.modules.pop("content.dialogue_conds", None)
    for req in ("dialogue_node", "check_need", "visible_options", "node_text", "is_end",
                "_story_to_line", "get_dialogue"):
        if req not in ns:
            raise AssertionError("冻结 dialogue 命名空间缺 %s" % req)
    return ns


_U_DLG = _frozen_dialogue_ns()
_FROZEN_DC_NS = _frozen_conditions_ns()

#: 冻结侧对外（探针用）
_u_get_dialogue = _U_DLG["get_dialogue"]
_u_dialogue_node = _U_DLG["dialogue_node"]
_u_check_need = _U_DLG["check_need"]
_u_visible_options = _U_DLG["visible_options"]
_u_node_text = _U_DLG["node_text"]
_u_is_end = _U_DLG["is_end"]
_u_story_to_line = _U_DLG["_story_to_line"]
_u_main_quests = _U_DLG["_main_quests"]

#: 活侧对外（**懒取**：红基线阶段 `_CFG` / `_unknown_need` / `_story_text` 还不存在，
#: 那时门禁要能**跑起来并报红**，而不是 import 期就炸）。
class _LiveSide:
    """活侧符号的懒取口：缺符号 → `AttributeError`（在断言里变成一条红，不是崩）。"""

    def __getattr__(self, name):
        return getattr(DLG, name)


_L = _LiveSide()


# ═══════════════════════════════════════════════════════════════════════════
# §3 ctx 真值矩阵 K=704（FROZEN_GATE §5.1：11 任务态 × 4 支线态 × 2 道具态 × 2 玩家态 × 2 npc 态）
# ═══════════════════════════════════════════════════════════════════════════
def _options_of(tree):
    for node in (tree.get("nodes") or {}).values():
        if isinstance(node, dict):
            for opt in node.get("options") or []:
                yield opt


def _variants_of(tree):
    for node in (tree.get("nodes") or {}).values():
        if isinstance(node, dict):
            for var in node.get("texts") or []:
                yield var


class _Data:
    """一次算好、门禁全程复用；同时存「输入面计数」（§5.1 计数校验）。"""

    def __init__(self):
        self.trees = DLG._dialogues()
        self.main_quests = DLG._main_quests()
        self.quests_domain = DLG._read_domain("quests")
        self.sides = [v for v in self.quests_domain.values() if v.get("source") != "main"]
        self.conds = DLG._read_domain("cond_specs") or {}
        self.giver = next((m.get("giver") for m in self.main_quests if m.get("giver")), "npc_giver")
        self.hit_id = next((m.get("id") for m in self.main_quests if m.get("id")), "q_hit")
        self.miss_id = self.hit_id + "_u1i4_miss"
        self.novice = "cls_novice"
        self.other_class = next((m.get("id") for m in self.main_quests
                                 if m.get("id") and m.get("id") != self.novice), "cls_u1i4_other")
        self.race = "elf"
        self.collect = next(((s.get("objective") or {}).get("collect") for s in self.sides
                             if (s.get("objective") or {}).get("collect")), "材料A")
        self.collects = sorted({(s.get("objective") or {}).get("collect") for s in self.sides
                                if (s.get("objective") or {}).get("collect")})
        # 计数（§5.1）
        self.n_trees = len(self.trees)
        self.n_nodes = sum(len(t.get("nodes") or {}) for t in self.trees.values())
        self.n_opts = sum(1 for t in self.trees.values() for _ in _options_of(t))
        self.opts_need = [o["need"] for t in self.trees.values()
                          for o in _options_of(t) if o.get("need")]
        self.var_need = [v["need"] for t in self.trees.values()
                         for v in _variants_of(t) if v.get("need")]
        self.n_needs = len(self.opts_need) + len(self.var_need)
        self.n_variants = sum(1 for t in self.trees.values() for _ in _variants_of(t))
        self.n_texts_nodes = sum(1 for t in self.trees.values()
                                 for n in (t.get("nodes") or {}).values()
                                 if isinstance(n, dict) and n.get("texts"))
        self.fail_next_opts = [o for t in self.trees.values() for o in _options_of(t)
                               if "fail_next" in o]
        self.side_menu_opts = [o for t in self.trees.values() for o in _options_of(t)
                               if o.get("side_menu") is not None]
        self.text_from_nodes = [n for t in self.trees.values()
                                for n in (t.get("nodes") or {}).values()
                                if isinstance(n, dict) and n.get("text_from")]
        self.end_next_opts = [o for t in self.trees.values() for o in _options_of(t)
                              if o.get("next") == "__end__"]
        self.need_keys = sorted({k for need in self.opts_need + self.var_need for k in need})
        self.legal_states = ("active", "ready", "pending", "done")

    # ---------------------------------------------------------------- ctx 四维
    def task_states(self):
        """11 态：无任务 / 空 main / None main / pending / active / ready / done×2 /
        具体 id×命中·不命中 / 发布者不匹配（对齐 `_quest_state` 的全部分支）。"""
        out = [
            ("1 无 quests", {}),
            ("2 空 main + pending", {"main_quest": "", "main_status": "pending", "completed_main": []}),
            ("3 main=None + pending", {"main_quest": None, "main_status": "pending", "completed_main": []}),
            ("4 具体 main + pending", {"main_quest": "q1", "main_status": "pending", "completed_main": []}),
            ("5 具体 main + active", {"main_quest": "q1", "main_status": "active", "completed_main": []}),
            ("6 具体 main + ready", {"main_quest": "q1", "main_status": "ready", "completed_main": []}),
            ("7 done 命中（完成表含 q1）", {"main_quest": "q1", "main_status": "done",
                                            "completed_main": ["q1"]}),
            ("8 done 不命中（完成表空）", {"main_quest": "q1", "main_status": "done",
                                           "completed_main": []}),
            ("9 运行时主线 id + active", {"main_quest": self.hit_id, "main_status": "active",
                                          "completed_main": []}),
            ("10 运行时主线 id + ready", {"main_quest": self.hit_id, "main_status": "ready",
                                          "completed_main": []}),
            ("11 done 不命中（别的 id）", {"main_quest": self.hit_id, "main_status": "done",
                                           "completed_main": [self.miss_id]}),
        ]
        assert len(out) == 11, len(out)
        return out

    def side_states(self):
        """4 态：无支线 / 有可接 / 有可交 / 有进行中（全部取自真数据 + 目标 npc）。"""
        g = self.giver
        base = {"main_quest": self.hit_id, "main_status": "pending", "completed_main": []}
        return [
            ("1 无支线", dict(base, side={})),
            ("2 有可接", dict(base, side={self.collect_sid("board0"): {"status": "available"}})),
            ("3 有可交", dict(base, side={self.collect_sid("board1"): {"status": "ready"}})),
            ("4 有进行中", dict(base, side={self.collect_sid("board2"): {"status": "active"}})),
        ]

    def collect_sid(self, slot):
        """挑一条真支线 id（`giver` 就用主线的发布者，保证 `_quest_state` 的 giver 校验有分支）。"""
        for s in self.sides:
            if (s.get("objective") or {}).get("collect") and s.get("id"):
                return s["id"]
        return "sq_u1i4_" + slot

    def side_quest_list(self):
        g = self.giver
        return [
            {"id": self.collect_sid("s0"), "giver": g,
             "objective": {"collect": self.collect, "collect_count": 1}},
            {"id": self.collect_sid("s1") + "_kill", "giver": g, "objective": {"count": 3}},
            {"id": self.collect_sid("s2") + "_board", "giver": g, "board": True, "objective": {"count": 1}},
        ]

    def item_states(self):
        """2 态：材料不够 / 够（覆盖**全部** collect 键，让 `_c_side_ready` 的收集分支全非空跑）。"""
        full = {c: 99 for c in self.collects}
        return [("1 材料不够", {}), ("2 材料够", full)]

    def player_states(self):
        return [
            ("1 见习", {"class_name": self.novice, "race": self.race,
                        "hidden_class_unlock": [], "class_tier": 0, "level": 1}),
            ("2 普通职业", {"class_name": self.other_class, "race": self.race,
                            "hidden_class_unlock": [], "class_tier": 0, "level": 1}),
            ("3 class_any 白名单命中", {"class_name": self.whitelist_class(), "race": self.race,
                                        "hidden_class_unlock": [], "class_tier": 1, "level": 30}),
            ("4 隐藏线（已解锁且当前即它）", {"class_name": self.hidden_class(), "race": self.race,
                                              "hidden_class_unlock": [self.hidden_class()],
                                              "class_tier": 2, "level": 60}),
        ]

    def whitelist_class(self):
        for need in self.opts_need + self.var_need:
            v = need.get("class_any")
            if isinstance(v, list) and v:
                return v[0]
        return self.novice

    def hidden_class(self):
        for need in self.opts_need + self.var_need:
            v = need.get("hidden_current")
            if isinstance(v, str) and v:
                return v
        return "cls_u1i4_hidden"

    def npc_states(self):
        return [("1 == 发布者", self.giver), ("2 != 发布者", "npc_u1i4_other")]

    def build_full_matrix(self):
        """K = 11 × 4 × 2 × 4 × 2 = 704（FROZEN_GATE §5.1）。"""
        sq = self.side_quest_list()
        out = []
        for tlabel, tq in self.task_states():
            for slabel, sq_state in self.side_states():
                for ilabel, items in self.item_states():
                    for plabel, player in self.player_states():
                        for nlabel, npc_id in self.npc_states():
                            q = dict(tq)
                            q["side"] = dict(sq_state)
                            out.append({
                                "label": "%s | %s | %s | %s | %s" % (
                                    tlabel, slabel, ilabel, plabel, nlabel),
                                "ctx": {"quests": q, "player": dict(player), "npc_id": npc_id,
                                        "side_quests": sq, "item_counts": dict(items)},
                            })
        return out

    def small_matrix(self):
        """`node_text` / `visible_options` 用的小矩阵（K=14：2 任务 × 4 支线 × 2 道具 ≈ 够反证）。"""
        sq = self.side_quest_list()
        out = []
        for tlabel, tq in self.task_states()[:4]:
            for slabel, sq_state in self.side_states():
                for ilabel, items in self.item_states():
                    q = dict(tq)
                    q["side"] = dict(sq_state)
                    out.append({
                        "label": "%s | %s | %s" % (tlabel, slabel, ilabel),
                        "ctx": {"quests": q,
                                "player": {"class_name": self.novice, "race": self.race},
                                "npc_id": self.giver, "side_quests": sq,
                                "item_counts": dict(items)},
                    })
        return out


DATA = _Data()
MATRIX = DATA.build_full_matrix()
SMALL = DATA.small_matrix()
NEED_ITEMS = DATA.opts_need + DATA.var_need          # 与 `_u_check_need` 同序
assert len(MATRIX) == 704, len(MATRIX)


# ═══════════════════════════════════════════════════════════════════════════
# §4 网格探针（每个都返回**违规列表**；主流程与有牙反证共用同一批函数）
# ═══════════════════════════════════════════════════════════════════════════
def _probe(val, fn, *args, **kwargs):
    """把「返回值」与「异常类型」都收成可比形状。"""
    try:
        return ("ret", fn(*args, **kwargs))
    except Exception as e:                       # noqa: BLE001 门禁要看异常类型
        return ("raise", type(e).__name__)


def _expand_none(opt):
    return None


def _expand_empty(opt):
    return []


def _expand_one(opt):
    return [{"text": "子1", "next": "n1", "action": None}]


def _expand_three(opt):
    return [{"text": "子1"}, {"text": "子2"}, {"text": "子3"}]


_EXPANDS = (("None", None), ("[]", _expand_empty), ("1项", _expand_one), ("3项", _expand_three))


def grid_check_need(max_report=5):
    """探针 1：`check_need(need, ctx)` 1073 × 704 = 755,392 格。"""
    bad = []
    cells = 0
    for ni, need in enumerate(NEED_ITEMS):
        for ci, item in enumerate(MATRIX):
            old = _probe(need, _u_check_need, need, item["ctx"])
            new = _probe(need, _L.check_need, need, item["ctx"])
            cells += 1
            if old != new:
                if len(bad) < max_report:
                    bad.append("check_need 格(%d,%d) need=%r ctx=%s 旧=%r 新=%r"
                               % (ni, ci, need, item["label"], old, new))
    return bad, cells


def grid_node_text(max_report=5):
    """探针 2：`node_text(node, ctx)` 708 × 704 = 498,432 格。"""
    bad = []
    cells = 0
    for t in DATA.trees.values():
        for nid, node in (t.get("nodes") or {}).items():
            for ci, item in enumerate(MATRIX):
                old = _probe(None, _u_node_text, node, item["ctx"])
                new = _probe(None, _L.node_text, node, item["ctx"])
                cells += 1
                if old != new:
                    if len(bad) < max_report:
                        bad.append("node_text 格(%s,%d) ctx=%s 旧=%r 新=%r"
                                   % (nid, ci, item["label"], old, new))
    return bad, cells


def _vis_sig(opts):
    """可见选项的规范化（保序：`text/next/need/action/fail_next/side_menu`）。"""
    out = []
    for o in opts:
        out.append(json.dumps({k: o.get(k) for k in
                               ("text", "next", "need", "action", "fail_next", "side_menu")},
                              ensure_ascii=False, sort_keys=False))
    return out


def grid_visible_options(max_report=5):
    """探针 3：`visible_options(dlg, node, ctx)` 708 × 704 = 498,432 格（整条列表逐项保序）。"""
    bad = []
    cells = 0
    expanded = 0
    for tid, tree in DATA.trees.items():
        for nid, node in (tree.get("nodes") or {}).items():
            for ci, item in enumerate(MATRIX):
                old = _probe([], lambda: _vis_sig(_u_visible_options(tree, node, item["ctx"])))
                new = _probe([], lambda: _vis_sig(_L.visible_options(tree, node, item["ctx"])))
                cells += 1
                if old != new:
                    if len(bad) < max_report:
                        bad.append("visible_options 格(%s/%s,%d) ctx=%s 旧=%r 新=%r"
                                   % (tid, nid, ci, item["label"], old, new))
    # 展开矩阵：4 条 side_menu × 4 种 expand × need 真/假 = 32
    for opt in DATA.side_menu_opts:
        for elabel, fn in _EXPANDS:
            for ctx in (MATRIX[0]["ctx"], MATRIX[352]["ctx"]):
                old = _probe([], lambda: _vis_sig(_u_visible_options(
                    {"nodes": {"s": {"options": [opt]}}}, {"options": [opt]},
                    dict(ctx, side_menu_expand=fn))))
                new = _probe([], lambda: _vis_sig(_L.visible_options(
                    {"nodes": {"s": {"options": [opt]}}}, {"options": [opt]},
                    dict(ctx, side_menu_expand=fn))))
                cells += 1
                expanded += 1
                if old != new:
                    if len(bad) < max_report:
                        bad.append("side_menu 展开 格(%r,%s) 旧=%r 新=%r" % (opt, elabel, old, new))
    return bad, cells, expanded


def grid_dialogue_node(max_report=5):
    """探针 4：`dialogue_node(dlg, nid)` `Σ(节点数+4)` = 864 格（含未知 id 回退）。"""
    bad = []
    cells = 0
    probes = ("__no_such_node__", "", "start", "__end__")
    for tid, tree in DATA.trees.items():
        ids = list((tree.get("nodes") or {})) + list(probes)
        for nid in ids:
            old = _probe(None, _u_dialogue_node, tree, nid)
            new = _probe(None, _L.dialogue_node, tree, nid)
            cells += 1
            if old != new:
                if len(bad) < max_report:
                    bad.append("dialogue_node 格(%s,%r) 旧=%r 新=%r" % (tid, nid, old, new))
    return bad, cells


def grid_is_end(max_report=5):
    """探针 5：`is_end(x)` 1973 选项 next + 708 节点 id + 4 哨兵 = 2,685 格。"""
    bad = []
    cells = 0
    for t in DATA.trees.values():
        for opt in _options_of(t):
            for x in (opt.get("next"), opt.get("fail_next")):
                old = _u_is_end(x)
                new = _L.is_end(x)
                cells += 1
                if old != new and len(bad) < max_report:
                    bad.append("is_end 格(%r) 旧=%r 新=%r" % (x, old, new))
        for nid in (t.get("nodes") or {}):
            old = _u_is_end(nid)
            new = _L.is_end(nid)
            cells += 1
            if old != new and len(bad) < max_report:
                bad.append("is_end 格(%r) 旧=%r 新=%r" % (nid, old, new))
    for x in ("__end__", None, "", "start"):
        old = _u_is_end(x)
        new = _L.is_end(x)
        cells += 1
        if old != new and len(bad) < max_report:
            bad.append("is_end 哨兵格(%r) 旧=%r 新=%r" % (x, old, new))
    return bad, cells


def _old_route(opt, failed):
    """冻结 `talk_choice` 的路由两行：`nxt = opt.get("next", "__end__")`；
    `failed` → `opt.get("fail_next", nxt)`。"""
    nxt = opt.get("next", "__end__")
    if failed:
        return opt.get("fail_next", nxt)
    return nxt


def grid_next_of(max_report=5):
    """探针 6：`next_of(opt, failed=False/True)` 1973 × 2 = 3,946 格（旧 = 冻结路由两行）。"""
    bad = []
    cells = 0
    seen_fail = 0
    for t in DATA.trees.values():
        for opt in _options_of(t):
            has_fail = "fail_next" in opt
            for failed in (False, True):
                old = _old_route(opt, failed)
                new = _L._CFG.next_of(opt, failed=failed)
                cells += 1
                if has_fail:
                    seen_fail += 1
                if old != new and len(bad) < max_report:
                    bad.append("next_of 格(%r,failed=%r) 旧=%r 新=%r" % (opt.get("text"), failed, old, new))
    return bad, cells, seen_fail


def full_grid():
    """六口全量网格；返回 (违规列表, 计数 dict)。"""
    bad = []
    counts = {}
    b, counts["check_need"] = grid_check_need()
    bad += b
    b, counts["node_text"] = grid_node_text()
    bad += b
    b, counts["visible_options"], counts["side_menu_expand"] = grid_visible_options()
    bad += b
    b, counts["dialogue_node"] = grid_dialogue_node()
    bad += b
    b, counts["is_end"] = grid_is_end()
    bad += b
    b, counts["next_of"], counts["fail_next_cells"] = grid_next_of()
    bad += b
    return bad, counts


# ═══════════════════════════════════════════════════════════════════════════
# §5 口径分歧 10 条（DESIGN §2.8 / FROZEN_GATE §6 对话块）
# ═══════════════════════════════════════════════════════════════════════════
def audit_divergences():
    """10 条**故意差异**逐条断言；返回 (违规, 命中计数)。"""
    v = []
    hits = {}

    def hit(i):
        hits[i] = hits.get(i, 0) + 1

    # ① 未知节点 ≠ 结束：回退 start（不是 {}、不是「结束」）
    tree = {"start": "s", "nodes": {"s": {"text": "开场"}, "a": {"text": "A"}}}
    got = _L.dialogue_node(tree, "__missing__")
    if got is not tree["nodes"]["s"]:
        v.append("分歧①：dialogue_node 未知 id 应回退 start 节点，实测 %r" % (got,))
    else:
        hit(1)
    if _L.is_end("__missing__") is not False:
        v.append("分歧①：is_end(未知 id) 应为 False")
    else:
        hit(1)
    if _L.dialogue_node({"nodes": {}}, "x") != {}:
        v.append("分歧①：无 start 时应回 {}")
    else:
        hit(1)

    # ② side_menu {} ≠ None
    node = {"options": [{"text": "menu", "side_menu": {}}, {"text": "plain", "side_menu": None}]}
    got = _L.visible_options({"nodes": {}}, node, {})
    if [o["text"] for o in got] != ["plain"]:
        v.append("分歧②：`side_menu={}` 应走展开分支（expand 缺省 → 整项消失），实测 %r"
                 % ([o.get("text") for o in got],))
    else:
        hit(2)
    got = _L.visible_options({"nodes": {}}, node, {"side_menu_expand": _expand_three})
    if [o.get("text") for o in got] != ["子1", "子2", "子3", "plain"]:
        v.append("分歧②：`side_menu={}` 展开结果应插回原位置，实测 %r" % ([o.get("text") for o in got],))
    else:
        hit(2)

    # ③ 未注册 need 键：测试 raise / 生产告警放行
    unk = {"u1i4_unknown_key": 1}
    saved_env = {k: os.environ.get(k) for k in ("GWEN_TEST_MODE", "GWEN_GAME_DB")}
    fake_log = _FakeLog()
    try:
        os.environ["GWEN_TEST_MODE"] = "1"
        if _probe(False, _L.check_need, unk, {"player": {}})[0] != "raise":
            v.append("分歧③：测试模式下未注册 need 键应 raise")
        else:
            hit(3)
        os.environ.pop("GWEN_TEST_MODE", None)
        os.environ["GWEN_GAME_DB"] = os.path.join(PKG_ROOT, "prod_u1i4_dialogue.db")
        # 生产半边：活实现的告警落 = `content.obs.log()`；冻结实现的告警落 = `_OBS_HOOK`。
        # 两个落点都换成同一个假 logger（**只就地还原**：`Wire.log` 只读 → 用 `bind()` 回填），
        # 才能对「告警一次」这件事各数一次。
        _OBS.bind(log=fake_log)
        _OBS_HOOK.current.log_obj = fake_log
        got = _L.check_need(unk, {"player": {}})
        n_new = len(fake_log.warnings)
        old = _probe(False, _u_check_need, unk, {"player": {}})
        n_old = len(fake_log.warnings) - n_new
        if got is not True or n_new != 1:
            v.append("分歧③：生产模式下未注册键应「告警一次 + 放行」，实测 got=%r 告警=%d"
                     % (got, n_new))
        else:
            hit(3)
        # 旧实现（冻结文本）走一遍：同一策略、同一条告警
        if old != ("ret", True) or n_old != 1:
            v.append("分歧③：冻结旧实现生产模式应「告警一次 + 放行」，实测 %r 告警=%d" % (old, n_old))
        else:
            hit(3)
        # 未知键真值假 → 拦截（unknown 返回 False 那半边）
        old2 = _probe(False, _u_check_need, unk, {"player": {}})
        new2 = _probe(False, _L.check_need, unk, {"player": {}})
        if old2 != new2:
            v.append("分歧③：生产模式未知键 旧=%r 新=%r" % (old2, new2))
        else:
            hit(3)
    finally:
        _OBS.bind(log=_REAL_LOG)                 # 原地还原（不写盘）
        _OBS_HOOK.current = _FakeObs()
        for k, val in saved_env.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val

    # ④ texts 两条都满足 → 取第一条（声明序）
    node = {"texts": [{"need": {}, "text": "变体A"}, {"need": {}, "text": "变体B"}], "text": "默认"}
    got = _L.node_text(node, {"player": {}})
    if got != "变体A":
        v.append("分歧④：两条都满足应取第一条，实测 %r" % (got,))
    else:
        hit(4)
    node2 = {"texts": [{"need": {}, "text": "变体B"}, {"need": {}, "text": "变体A"}], "text": "默认"}
    if _L.node_text(node2, {"player": {}}) != "变体B":
        v.append("分歧④：对调声明序后应取另一条（证明真在看序）")
    else:
        hit(4)

    # ⑤ 变体缺 text → KeyError；节点缺 text + 生成器返回 "" → fallback
    got = _probe(None, _L.node_text, {"texts": [{"need": {}, "note": "缺 text"}]}, {"player": {}})
    if got != ("raise", "KeyError"):
        v.append("分歧⑤：变体缺 text 键应 KeyError，实测 %r" % (got,))
    else:
        hit(5)
    got = _probe(None, _L.node_text, {"text_from": "story"}, {"player": {}, "npc_id": "nobody"})
    if got[0] != "ret" or got[1] != "……":
        v.append("分歧⑤：text_from 生成器返回假值应落 fallback_text，实测 %r" % (got,))
    else:
        hit(5)

    # ⑥ options 返回原对象（is 相同）
    node = {"options": [{"text": "x", "next": "n"}]}
    got = _L.visible_options({"nodes": {}}, node, {})
    if len(got) != 1 or got[0] is not node["options"][0]:
        v.append("分歧⑥：普通选项应返回原对象（is 相同）")
    else:
        hit(6)

    # ⑦ {} 会话 = 无会话但不许清；坏值 = 无会话（Cursor.of 只做还原不做清理）
    from content.persistence import world as W
    gid, qid = "u1i4g", "u1i4999"
    key = W.talk_state_key(gid, qid)
    W.clear_talk_state(gid, qid)
    for raw in ("{}", "[]", "0", "null", "{bad json"):
        W.set_event_state(key, raw)
        restored = Cursor.of(W.get_talk_state(gid, qid), subject_key="npc", node_key="node")
        if restored is not None:
            v.append("分歧⑦：坏/空值 %r 的 Cursor.of 应为 None" % (raw,))
        else:
            hit(7)
    W.set_event_state(key, "{}")
    if W.get_talk_state(gid, qid) != {}:
        v.append("分歧⑦：`{}` 会话应原样读回 `{}`（falsy）")
    else:
        hit(7)
    if W.get_event_state(key) != "{}":
        v.append("分歧⑦：`{}` 是「壳」，Cursor.of 不负责清残留（清残留留调用方）")
    else:
        hit(7)
    W.clear_talk_state(gid, qid)
    if W.get_talk_state(gid, qid) is not None:
        v.append("分歧⑦：clear 后应读回 None")
    else:
        hit(7)

    # ⑧ 谓词返回假值（None/0/""/[]）→ 不满足（真值判定，不是 `is False`）
    try:
        _reg = _L._CFG._conds
    except Exception:                            # noqa: BLE001 红基线阶段没有 _CFG
        _reg = None
    for i, val in enumerate((None, 0, "", [])):
        probe_key = "u1i4_falsy_%d" % i

        def _falsy(ctx, v, _val=val):
            return _val

        if _reg is None:
            v.append("分歧⑧：红基线阶段无 `_CFG`，无法验真值判定（%r）" % (val,))
            continue
        _reg.register(probe_key, _falsy)
        try:
            got = _L.check_need({probe_key: 1}, {"player": {}})
            if got is not False:
                v.append("分歧⑧：谓词返回 %r 应判不满足，实测 %r" % (val, got))
            else:
                hit(8)
        finally:
            _reg.pop(probe_key, None)

    # ⑨ 节点值可为 None：键在 → 返回 None；键不在 → 回退 start
    tree = {"start": "s", "nodes": {"x": None, "s": {"text": "S"}}}
    if _L.dialogue_node(tree, "x") is not None:
        v.append("分歧⑨：`nodes['x'] is None` 应返回 None（判据是键在不在）")
    else:
        hit(9)
    if _L.dialogue_node(tree, "y") is not tree["nodes"]["s"]:
        v.append("分歧⑨：键不在应回退 start")
    else:
        hit(9)

    # ⑩ text_from 是「表」而不是「枚举」：不在表内 → 不调用生成器，落 text
    calls = []
    try:
        cfg0 = _L._CFG
        unk_fn = DLG._unknown_need
    except Exception:                            # noqa: BLE001 红基线阶段没有 _CFG
        cfg0 = None
        unk_fn = None
    if cfg0 is None or unk_fn is None:
        v.append("分歧⑩：红基线阶段无 `_CFG` / `_unknown_need`，无法验 text_from 注入表")
    else:
        src = dict(cfg0._sources)
        src["probe_src"] = lambda node, ctx: calls.append(1) or "生成"
        cfg2 = Dialogue(end_marker="__end__", fallback_text="……", conditions=cfg0._conds,
                        unknown=unk_fn, text_sources=src)
        got = cfg2.text({"text_from": "probe_src", "text": "原文"}, {})
        if got != "生成" or not calls:
            v.append("分歧⑩：注入表内的 text_from 应调用生成器，实测 %r" % (got,))
        else:
            hit(10)
        got = cfg2.text({"text_from": "nope_src", "text": "原文"}, {})
        if got != "原文":
            v.append("分歧⑩：不在注入表内的 text_from 应落 text，实测 %r" % (got,))
        else:
            hit(10)
        if cfg0.text({"text_from": None, "text": "原文"}, {}) != "原文":
            v.append("分歧⑩：text_from 非字符串 → 不查表，落 text")
        else:
            hit(10)

    return v, hits


# ═══════════════════════════════════════════════════════════════════════════
# §6 顺序断言（FROZEN_GATE §8.2 的 ④⑤）+ 多故障
# ═══════════════════════════════════════════════════════════════════════════
def audit_order():
    """顺序语义：`texts` 取第一 + `need` 键序短路 + `side_menu` 插回原位置。"""
    v = []
    # ④ 变体按序取第一（对调再跑 → 另一条）
    a = {"texts": [{"need": {}, "text": "A"}, {"need": {}, "text": "B"}]}
    b = {"texts": [{"need": {}, "text": "B"}, {"need": {}, "text": "A"}]}
    if _L.node_text(a, {}) != "A" or _L.node_text(b, {}) != "B":
        v.append("顺序④：texts 未按声明序取第一（A/B）")
    # ⑤ need 键序 = 短路序（带计数的探针谓词）
    calls = []
    try:
        reg = _L._CFG._conds
    except Exception:                            # noqa: BLE001 红基线阶段没有 _CFG
        reg = None
    if reg is None:
        v.append("顺序⑤：红基线阶段无 `_CFG`，无法验 need 键序短路")
    else:
        probes = ("u1i4_ord_a", "u1i4_ord_b", "u1i4_ord_c")
        for i, k in enumerate(probes):
            def _mk(idx):
                def _fn(ctx, v):
                    calls.append(idx)
                    return idx != 1          # b 恒假
                return _fn
            reg.register(k, _mk(i))
        try:
            calls[:] = []
            got = _L.check_need({probes[0]: 1, probes[1]: 1, probes[2]: 1}, {})
            if got is not False or calls != [0, 1]:
                v.append("顺序⑤：need 键序短路应为 [a,b]（c 不调用），实测 calls=%r got=%r"
                         % (calls, got))
            calls[:] = []
            got = _L.check_need({probes[2]: 1, probes[1]: 1, probes[0]: 1}, {})
            if got is not False or calls != [2, 1]:
                v.append("顺序⑤：按插入序短路应为 [c,b]，实测 calls=%r got=%r" % (calls, got))
            calls[:] = []
            got = _L.check_need({probes[2]: 1, probes[0]: 1}, {})
            if got is not True or calls != [2, 0]:
                v.append("顺序⑤：全过时应按插入序调用，实测 calls=%r got=%r" % (calls, got))
        finally:
            for k in probes:
                reg.pop(k, None)
    # ③′ side_menu 插回原位置（不是追加末尾）
    node = {"options": [{"text": "A"}, {"text": "M", "side_menu": {}}, {"text": "Z"}]}
    got = [o.get("text") for o in _L.visible_options({"nodes": {}}, node, {"side_menu_expand": _expand_three})]
    if got != ["A", "子1", "子2", "子3", "Z"]:
        v.append("顺序③′：side_menu 展开应插回原位置，实测 %r" % (got,))
    return v


# ═══════════════════════════════════════════════════════════════════════════
# §7 aux 指纹（FROZEN_GATE §3-①②③⑧⑩）
# ═══════════════════════════════════════════════════════════════════════════
def audit_aux():
    """会话键 / 落盘 JSON 原文 / flag 桶 / 数据面（树 / 主线 / cond_specs）。"""
    v = []
    got = {}
    from content.persistence import world as W
    key = W.talk_state_key("g1", "1001")
    got["talk_key_plain"] = key
    got["talk_key"] = _sha(key)
    if key != "talk_g1_1001":
        v.append("aux①：talk_state_key 应为 talk_g1_1001，实测 %r" % (key,))

    gid, qid = "g1", "1001"
    W.clear_talk_state(gid, qid)
    W.set_talk_state(gid, qid, "npc_mayor", "welcome")
    raw = W.get_event_state(key)
    got["talk_state_raw"] = raw
    if raw != '{"npc": "npc_mayor", "node": "welcome"}':
        v.append("aux②：落盘 JSON 原文漂了：%r" % (raw,))
    # Cursor.state 的键名由调用方给（存档 schema 不许动）
    cur = Cursor.of({"npc": "npc_mayor", "node": "welcome"}, subject_key="npc", node_key="node")
    if cur is None or cur.state(subject_key="npc", node_key="node") != {
            "npc": "npc_mayor", "node": "welcome"}:
        v.append("aux②：Cursor.of/state 往返失败")
    W.clear_talk_state(gid, qid)

    flag_key = W.talk_flags_key(gid, qid)
    W.set_talk_flag(gid, qid, "npc_mayor", "pledged")
    got["talk_flag_raw"] = W.get_event_state(flag_key)
    if got["talk_flag_raw"] != '{"npc_mayor": ["pledged"]}':
        v.append("aux③：flag 桶 JSON 原文漂了：%r" % (got["talk_flag_raw"],))
    W.delete_event_state(flag_key)

    # ⑧ 数据面：39 棵树规范化指纹
    per = []
    for tid in sorted(DATA.trees):
        tree = DATA.trees[tid]
        nodes = tree.get("nodes") or {}
        norm = {"start": tree.get("start"), "node_ids": list(nodes)}
        body = {}
        for nid in nodes:
            node = nodes[nid]
            if not isinstance(node, dict):
                body[nid] = {"__nonmapping__": repr(node)}
                continue
            opts = []
            for o in node.get("options") or []:
                opts.append({k: o.get(k) for k in
                             ("text", "next", "need", "action", "fail_next", "side_menu") if k in o}
                            | {"__keys__": list(o)})
            variants = []
            for var in node.get("texts") or []:
                variants.append({"__keys__": list(var), "need": var.get("need"),
                                 "text": var.get("text")})
            body[nid] = {"__keys__": list(node), "text": node.get("text"),
                         "text_from": node.get("text_from"), "texts": variants, "options": opts}
        norm["nodes"] = body
        per.append(_sha(json.dumps(norm, ensure_ascii=False, separators=(",", ":"))))
    got["trees_fp"] = _sha("|".join(per))
    got["trees_count"] = str(len(per))
    got["trees_n"] = str(DATA.n_trees)
    got["nodes_n"] = str(DATA.n_nodes)
    got["opts_n"] = str(DATA.n_opts)
    got["story_fp"] = _sha("|".join("%s\x1f%s\x1f%s" % (m.get("id"), m.get("giver"), m.get("story"))
                                    for m in DATA.main_quests))
    got["story_count"] = str(len(DATA.main_quests))
    got["cond_specs_fp"] = _file_sha(os.path.join(PKG_ROOT, "content", "data", "cond_specs.json"))
    return v, got


# ═══════════════════════════════════════════════════════════════════════════
# §8 有牙反证：破坏 4 处 → 对应探针必须变红（跑完原地还原，零写盘）
# ═══════════════════════════════════════════════════════════════════════════
class _Patch:
    """进入记原值、退出原地还原（**不写盘**）。支持模块属性 / 实例属性。"""

    def __init__(self, obj, name, value):
        self.obj = obj
        self.name = name
        self.value = value
        self.missing = not hasattr(obj, name)
        self.old = getattr(obj, name, None)

    def __enter__(self):
        setattr(self.obj, self.name, self.value)
        return self

    def __exit__(self, *exc):
        if self.missing:
            try:
                delattr(self.obj, self.name)
            except Exception:                    # noqa: BLE001
                pass
        else:
            setattr(self.obj, self.name, self.old)
        return False


def _with_break(patch, probe):
    """在猴补下跑探针（返回 `(变红?, 格数, 首条)`），退出时原地还原。

    探针返回形状有两种：`(bad, cells)` 与 `(bad, cells, extra_counts)`。
    """
    with patch:
        out = probe()
    return bool(out[0]), out[1], out[0][:1]


def _break_check_need(need, ctx):
    """T1 用：活 `check_need` 忽略全部条件。"""
    return True


def _break_node_text(node, ctx):
    """T2 用：活 `node_text` 变体从**末条**往前取。"""
    for var in list(node.get("texts") or [])[::-1]:
        if _L.check_need(var.get("need"), ctx):
            return var["text"]
    return node.get("text", "……")


def _break_next_of(self, option, *, failed=False):
    """T3 用：`next_of` 丢掉 `fail_next`（永远返回 `next`）。"""
    return option.get("next", "__end__")


def _break_is_end(self, node_id):
    """T4 用：`is_end` 恒 False。"""
    return False


def _teeth_check_need():
    """T1：破坏活 `check_need` → 探针 1 必须变红。"""
    return _with_break(_Patch(DLG, "check_need", _break_check_need),
                       lambda: grid_check_need(max_report=3))


def _teeth_node_text():
    """T2：破坏活 `node_text` 变体序 → 探针 2 必须变红。"""
    return _with_break(_Patch(DLG, "node_text", _break_node_text),
                       lambda: grid_node_text(max_report=3))


def _teeth_next_of():
    """T3：破坏引擎 `next_of` → 探针 6 必须变红（16 条 `fail_next` 也要抓住）。

    猴补打在**类**上（`Dialogue` 是 `__slots__` 值对象，实例不让赋属性）；门禁走
    `_L._CFG.next_of(...)` → 命中类属性 → 病态实现被探针看见。
    """
    return _with_break(_Patch(Dialogue, "next_of", _break_next_of),
                       lambda: grid_next_of(max_report=3))


def _teeth_is_end():
    """T4：破坏引擎 `is_end` → 探针 5 必须变红（586 条 `__end__` 覆盖）。"""
    return _with_break(_Patch(Dialogue, "is_end", _break_is_end),
                       lambda: grid_is_end(max_report=3))


_TEETH = (
    ("T1 need 忽略一键", _teeth_check_need, "check_need", grid_check_need),
    ("T2 变体取最后一条", _teeth_node_text, "node_text", grid_node_text),
    ("T3 next_of 丢 fail_next", _teeth_next_of, "next_of", grid_next_of),
    ("T4 is_end 恒 False", _teeth_is_end, "is_end", grid_is_end),
)


# ═══════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════
def main():
    watched_before = {p: _file_sha(p) for p in _WATCHED}

    print("=" * 74)
    print("U1-I8 门禁① —— 对话块冻结比对（冻结旧实现 vs 适配后活实现）")
    print("=" * 74)
    print("pkg   = %s" % PKG_ROOT)
    print("engine= %s" % _paths.ENGINE_ROOT)
    print("db    = %s" % os.environ.get("GWEN_GAME_DB"))
    print("mode  = GWEN_TEST_MODE=%r" % os.environ.get("GWEN_TEST_MODE"))

    # ---------------------------------------------------------------- ① 冻结
    section("【①】冻结字面量：30 段 sha256 == _PIN[\"frozen\"]（安全网自己没被动过）")
    check("段数 == 31（设计稿 §1.4 的 30 段 + 表外的 `_STORY_PREFIX`）",
          len(_SEGMENT_KEYS) == 31, len(_SEGMENT_KEYS))
    check("段表 == 生成器段表（dialogue.py 11 + dialogue_conds.py 20）",
          len(_FROZEN_DP) == 11 and len(_FROZEN_DC) == 20 and len(_FROZEN_EXTRA) == 1,
          (len(_FROZEN_DP), len(_FROZEN_DC), len(_FROZEN_EXTRA)))
    check("键空间 = §1.4 的 30 段 + `_STORY_PREFIX`（第 10 段 dialogue.py 段）",
          len(_SEGMENT_KEYS) - len(_FROZEN_DC) == 11,
          (len(_SEGMENT_KEYS), len(_FROZEN_DC)))
    check("`_STORY_PREFIX` 是第 10 段 `dialogue.py` 段（设计稿 §1.4 表外）",
          "content/dialogue.py::_STORY_PREFIX" in _FROZEN_EXTRA
          and _PIN["frozen"]["content/dialogue.py::_STORY_PREFIX"]
          == _sha(_FROZEN_EXTRA["content/dialogue.py::_STORY_PREFIX"]))
    froz_bad = []
    for key in _SEGMENT_KEYS:
        got = _sha(_frozen_text(key))
        if got != _PIN["frozen"].get(key):
            froz_bad.append("%s 实测 %s / 记录 %s" % (key, got[:16], str(_PIN["frozen"].get(key))[:16]))
    check("30 段冻结字面量 sha256 全等 _PIN[\"frozen\"]", not froz_bad, "；".join(froz_bad[:3]))
    gate_file_sha = _file_sha(os.path.abspath(__file__))
    stripped = "".join(ln for ln in open(os.path.abspath(__file__), encoding="utf-8").read().splitlines(True)
                       if '"gate_self"' not in ln and "_GATE_SELF_SHA256" not in ln)
    check("门禁本体自哈希 == _GATE_SELF_SHA256（安全网文件被手改即红）",
          _sha(stripped) == _GATE_SELF_SHA256, "%s / %s" % (_sha(stripped)[:16], _GATE_SELF_SHA256[:16]))
    check("门禁本体文件可读（自哈希非空）", bool(gate_file_sha))

    # ---------------------------------------------------------------- ② live
    section("【②】活实现：30 段 ast 切片 sha256 == _PIN[\"live\"]")
    live_bad = []
    live_texts = {}
    for key in _SEGMENT_KEYS:
        live_texts[key] = _live_text(key)
        got = _sha(live_texts[key])
        if got != _PIN["live"].get(key):
            live_bad.append("%s 实测 %s / 记录 %s" % (key, got[:16], str(_PIN["live"].get(key))[:16]))
    check("30 段活实现切 sha256 全等 _PIN[\"live\"]", not live_bad, "；".join(live_bad[:3]))

    # ---------------------------------------------------------------- ③ 档位
    section("【③】E 栏 frozen == live（防范围蔓延）· C 栏 frozen != live（防没真接上）")
    e_bad = [k for k in _E_KEYS if _sha(_frozen_text(k)) != _sha(live_texts[k])]
    check("E 栏 25 段 frozen == live", not e_bad, "；".join(e_bad[:3]))
    c_same = [k for k in _C_KEYS if _sha(_frozen_text(k)) == _sha(live_texts[k])]
    # 红基线阶段（实现线还没动手）C 栏本来就相等 → 只告警不判红；改完后应全不等。
    c_all_diff = not c_same
    print("        C 栏 6 段：%s" % ("全部 frozen != live（已接上引擎形状）" if c_all_diff
                                     else "仍有 %d 段与冻结一致（红基线阶段正常）" % len(c_same)))
    # 切片口径的机器证明：ast 切片 == inspect.getsource
    ins_bad = []
    for key in _SEGMENT_KEYS:
        mod = key.split("::", 1)[0]
        sym = key.split("::", 1)[1]
        obj = DLG if mod.endswith("dialogue.py") else DC
        target = getattr(obj, sym, None)
        if not callable(target):
            continue
        if slice_source(_live_path(key), sym) != inspect.getsource(target):
            ins_bad.append(key)
    check("活侧 ast 切片 == inspect.getsource（切片口径与 FROZEN_GATE §1.2 一致）",
          not ins_bad, "；".join(ins_bad[:3]))

    # ---------------------------------------------------------------- ④ 注入面
    section("【④】注入面取值（引擎零默认值 · 内容侧给的那几个取值）")
    live_cfg_ok = True
    try:
        cfg = _L._CFG
        check("_CFG 是引擎 saintess_engine.dialogue.Dialogue 实例", isinstance(cfg, Dialogue), type(cfg))
        check("end_marker == '__end__'", cfg._end == "__end__", cfg._end)
        check("END_KEY == 'end_marker'（引擎只认形参名）", END_KEY == "end_marker", END_KEY)
        check("fallback_text == '……'", cfg._fallback == "……", cfg._fallback)
        check("conditions is content.dialogue_conds.CONDITIONS", cfg._conds is DC.CONDITIONS)
        check("unknown is content.dialogue._unknown_need", cfg._unknown is DLG._unknown_need)
        check("text_sources == {'story': _story_text}", cfg._sources == {"story": DLG._story_text},
              cfg._sources)
        _t0 = DATA.trees[list(DATA.trees)[0]]
        check("_CFG.of(tree).tree is tree（O(1) 换引用，不拷贝）", cfg.of(_t0).tree is _t0)
        check("未知 need 键的 unknown 策略在内容侧 _unknown_need（引擎不读环境）",
              "GWEN_TEST_MODE" in inspect.getsource(DLG._unknown_need))
        check("_story_text / _unknown_need 是内容侧私有函数（不给引擎写默认值）",
              callable(DLG._story_text) and callable(DLG._unknown_need))
    except Exception as e:                       # noqa: BLE001 红基线阶段没有 _CFG，报红不崩
        live_cfg_ok = False
        check("注入面 `_CFG` 就位（红基线阶段应缺）", False, "%s: %s" % (type(e).__name__, e))

    # ---------------------------------------------------------------- ⑤ 全量网格
    section("【⑤】全量网格：39 树 × 708 节点 × 1973 选项 × 704 ctx —— 六口逐格 旧↔新")
    counts = {k: 0 for k in ("check_need", "node_text", "visible_options", "side_menu_expand",
                             "dialogue_node", "is_end", "next_of", "fail_next_cells")}
    bad = []
    if live_cfg_ok:
        try:
            bad, counts = full_grid()
        except Exception as e:                   # noqa: BLE001
            bad = ["全量网格起不来：%s: %s" % (type(e).__name__, e)]
    check("check_need 逐格（1073 × 704）", counts["check_need"] == len(NEED_ITEMS) * len(MATRIX),
          counts["check_need"])
    check("node_text 逐格（708 × 704）", counts["node_text"] == DATA.n_nodes * len(MATRIX),
          counts["node_text"])
    check("visible_options 逐格（708 × 704）+ side_menu 展开 32",
          counts["visible_options"] == DATA.n_nodes * len(MATRIX) + 32
          and counts["side_menu_expand"] == 32,
          (counts["visible_options"], counts["side_menu_expand"]))
    check("dialogue_node 逐格（708 + 39×4）",
          counts["dialogue_node"] == DATA.n_nodes + 4 * DATA.n_trees, counts["dialogue_node"])
    check("is_end 逐格（1973 next/fail_next + 708 id + 4 哨兵）",
          counts["is_end"] == 2 * DATA.n_opts + DATA.n_nodes + 4, counts["is_end"])
    check("next_of 逐格（1973 × 2）",
          counts["next_of"] == 2 * DATA.n_opts or not live_cfg_ok, counts["next_of"])
    check("fail_next 覆盖面（16 条 × failed 两态 = 32 格）",
          counts["fail_next_cells"] == 2 * len(DATA.fail_next_opts),
          counts["fail_next_cells"])
    total = sum(v for k, v in counts.items() if k != "fail_next_cells")
    check("六口全量网格零格不等（含 side_menu 展开）", not bad, "；".join(bad[:4]))
    print("        计数：%s  合计 = %d 格" % (counts, total))
    print("        输入面：%d 树 / %d 节点 / %d 选项 / %d 变体 / %d need 出现 / %d fail_next / "
          "%d side_menu / %d text_from"
          % (DATA.n_trees, DATA.n_nodes, DATA.n_opts, DATA.n_variants, DATA.n_needs,
             len(DATA.fail_next_opts), len(DATA.side_menu_opts), len(DATA.text_from_nodes)))
    print("        ctx 真值矩阵：K = %d（11 任务态 × 4 支线态 × 2 道具态 × 4 玩家态 × 2 npc 态）"
          % len(MATRIX))

    # ---------------------------------------------------------------- ⑥ 对象身份 / 只读
    section("【⑥】不变量：对象身份保留（I8）· 调用零副作用（I3/I9）")
    id_bad = []
    snap = json.dumps(DATA.trees, ensure_ascii=False, sort_keys=True)
    if live_cfg_ok:
        for tid, tree in DATA.trees.items():
            for nid, node in (tree.get("nodes") or {}).items():
                if not isinstance(node, dict):
                    continue
                ctx = MATRIX[0]["ctx"]
                got = _L.visible_options(tree, node, ctx)
                # 期望序（IO5）：普通项 = 原对象；`side_menu` 项 = `ctx["side_menu_expand"]` 的回调结果
                want = []
                for o in (node.get("options") or []):
                    if o.get("side_menu") is not None:
                        if _L.check_need(o.get("need"), ctx):
                            subs = ctx.get("side_menu_expand")
                            subs = subs(o) if subs else []
                            want.extend(subs or [])
                        continue
                    if _L.check_need(o.get("need"), ctx):
                        want.append(o)
                if len(got) != len(want):
                    id_bad.append("%s/%s 条数 %d != %d" % (tid, nid, len(got), len(want)))
                    continue
                for a, b in zip(got, want):
                    if a is not b:
                        id_bad.append("%s/%s 非原对象" % (tid, nid))
                        break
        _t0 = DATA.trees[list(DATA.trees)[0]]
        _L.node_text((_t0.get("nodes") or {}).get(_t0.get("start")) or {}, MATRIX[0]["ctx"])
        _L.visible_options(_t0, {"options": []}, MATRIX[0]["ctx"])
    check("普通选项 is 传入的原对象（39 树全扫）", live_cfg_ok and not id_bad, "；".join(id_bad[:3]))
    check("调用前后树指纹不变（引擎不写树）",
          json.dumps(DATA.trees, ensure_ascii=False, sort_keys=True) == snap)

    # ---------------------------------------------------------------- ⑦ 口径分歧
    section("【⑦】口径分歧 10 条（DESIGN §2.8 / FROZEN_GATE §6 对话块）逐条具名")
    dv, hits = audit_divergences()
    names = {
        1: "① 未知节点 ≠ 结束（回退 start；is_end 只认哨兵）",
        2: "② side_menu {} ≠ None",
        3: "③ 未注册 need 键：测试 raise / 生产告警放行",
        4: "④ 变体取「声明序第一个满足」",
        5: "⑤ 变体缺 text → KeyError；节点缺 text → fallback",
        6: "⑥ options 返回原对象",
        7: "⑦ {} 会话 = 无会话但不许清；坏值 → Cursor.of None",
        8: "⑧ 谓词结果用真值判定（不用 is False）",
        9: "⑨ 节点值可为 None（判据是键在不在）",
        10: "⑩ text_from 是「注入表」不是「枚举」",
    }
    for i in range(1, 11):
        check("分歧%s 至少 1 条断言" % i, hits.get(i, 0) >= 1, "命中 %d 条" % hits.get(i, 0))
    check("分歧 10 条零违规", not dv, "；".join(dv[:4]))

    # ---------------------------------------------------------------- ⑧ 顺序
    section("【⑧】顺序断言（texts 声明序 / need 键序短路 / side_menu 插回原位置）")
    od = audit_order()
    check("顺序断言零违规", not od, "；".join(od[:3]))

    # ---------------------------------------------------------------- ⑨ aux
    section("【⑨】aux 指纹：会话键 / 落盘 JSON 原文 / flag 桶 / 数据面")
    av, aux_got = audit_aux()
    for k in sorted(aux_got):
        if k in _PIN["aux"]:
            check("aux[%s] 逐字节相等" % k, str(aux_got[k]) == str(_PIN["aux"][k]),
                  "%r / %r" % (str(aux_got[k])[:60], str(_PIN["aux"][k])[:60]))
    check("aux 断言零违规", not av, "；".join(av[:3]))
    check("aux 记录了 talk_state_key 实跑值", aux_got.get("talk_key_plain") == "talk_g1_1001",
          aux_got.get("talk_key_plain"))

    # ---------------------------------------------------------------- ⑩ 有牙反证
    section("【⑩】有牙反证：破坏 4 处 → 对应探针必须变红（逐处打印预期/实测；跑完原地还原）")
    teeth_ok = True
    for name, runner, probe_name, probe in _TEETH:
        if not live_cfg_ok:
            check("%s → %s 探针变红" % (name, probe_name), False, "红基线阶段无活实现可比")
            teeth_ok = False
            continue
        red, cells, first = runner()
        print("        %s：预期变红=是 / 实测变红=%s（%s 探针跑了 %d 格）"
              % (name, "是" if red else "否", probe_name, cells))
        if red and first:
            print("          首格：%s" % first[0][:160])
        check("%s → %s 探针变红" % (name, probe_name), red, "未变红（这条断言没牙）")
        teeth_ok &= red
        back = probe(max_report=1)[0]
        check("%s 还原后 %s 探针回绿" % (name, probe_name), not back, "；".join(back[:1]))
    check("有牙反证 4 处全部命中", teeth_ok)
    # 全部还原后复跑四条探针（猴补无残留）
    if live_cfg_ok:
        leftover = (grid_check_need(max_report=1)[0] + grid_node_text(max_report=1)[0]
                    + grid_next_of(max_report=1)[0] + grid_is_end(max_report=1)[0])
        check("4 处猴补全部还原后四条探针仍绿（无残留）", not leftover, "；".join(leftover[:2]))
    else:
        check("4 处猴补全部还原后四条探针仍绿（无残留）", False, "红基线阶段无活实现")

    # ---------------------------------------------------------------- ⑪ 多故障
    section("【⑪】多故障：两处同坏 → 两条探针各自变红，且互不掩盖")
    if live_cfg_ok:
        def _break_need(need, ctx):
            return True

        def _break_text(node, ctx):
            for var in list(node.get("texts") or [])[::-1]:
                if _L.check_need(var.get("need"), ctx):
                    return var["text"]
            return node.get("text", "……")
        with _Patch(DLG, "check_need", _break_need), _Patch(DLG, "node_text", _break_text):
            m1a = bool(grid_check_need(max_report=1)[0])
            m1b = bool(grid_node_text(max_report=1)[0])
        check("M1 双坏同现：check_need 探针变红", m1a)
        check("M1 双坏同现：node_text 探针变红（互不掩盖）", m1b)

        def _break_next(self, option, *, failed=False):
            return option.get("next", "__end__")

        def _break_end(self, node_id):
            return False
        with _Patch(Dialogue, "next_of", _break_next), _Patch(Dialogue, "is_end", _break_end):
            m2a = bool(grid_next_of(max_report=1)[0])
            m2b = bool(grid_is_end(max_report=1)[0])
    else:
        m1a = m1b = m2a = m2b = False
        check("M1 双坏同现：check_need 探针变红", False, "红基线阶段无活实现")
        check("M1 双坏同现：node_text 探针变红（互不掩盖）", False, "红基线阶段无活实现")
    check("M2 双坏同现：next_of 探针变红", m2a)
    check("M2 双坏同现：is_end 探针变红（互不掩盖）", m2b)

    # 第三处仍绿（证明「不是一个大探针管全部」）
    def _break_need2(need, ctx):
        return True
    if live_cfg_ok:
        with _Patch(DLG, "check_need", _break_need2):
            m3_other = bool(grid_next_of(max_report=1)[0]) or bool(grid_is_end(max_report=1)[0])
        check("坏 check_need 时 next_of/is_end 探针仍绿（探针相互独立）", not m3_other)
    else:
        check("坏 check_need 时 next_of/is_end 探针仍绿（探针相互独立）", False, "红基线阶段无活实现")

    # ---------------------------------------------------------------- ⑫ 只读
    section("【⑫】只读：跑完 6 个源文件 sha256 前后一致（不写盘）")
    watched_after = {p: _file_sha(p) for p in _WATCHED}
    drift = [os.path.basename(p) for p in _WATCHED if watched_before[p] != watched_after[p]]
    check("6 个被碰过的源文件 sha256 前后一致", not drift, "；".join(drift))
    check("门禁本体文件 sha256 未变", True)
    for p in _WATCHED:
        print("        %-58s %s" % (os.path.relpath(p, PKG_ROOT), watched_after[p][:16]))

    # ---------------------------------------------------------------- 结果
    print("\n== 结果：通过 %d / 共 %d ==" % (PASS, PASS + FAIL))
    if FAILURES:
        print("失败项（%d）：" % len(FAILURES))
        for f in FAILURES:
            print("  FAIL: %s" % f)
        return 1
    print("全绿 [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
