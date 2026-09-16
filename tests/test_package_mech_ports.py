#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""门禁：P4「逐字端口」保真 —— 包内 `content/mech/*.py` vs 游戏仓真源（双源漂移哨兵）。

跑法（系统 python 即可）：
    cd dragonfall && python tests/test_package_mech_ports.py
退出码：0 = 全绿；1 = 有红（红行点名族 / 文件 / 差异内容）。

框架仓路径：默认 `C:/Users/yuyu/framework-engine`，可用环境变量 `GWEN_FRAMEWORK_DIR` 覆盖
（与同目录 `test_export_package_sync.py` 同口径）。

为什么要有这道门禁（背景）
--------------------------
P4-D2 把游戏仓的机制代码**逐字**搬进了框架侧游戏包 `games/orlandia/content/mech/*.py`。
搬完之后两边是**双源**：真源改了、包没跟着改，运行时没有任何人会报警。本门禁就是那个哨兵。

本门禁锁什么（四类断言）
------------------------
1. **端口文件必须真存在** —— 缺文件 = 红行点名族 + 期望路径（不是「找不到就跳过」）。
2. **`@register_action("名字")` 集合逐名相等** —— 真源 AST 扫出的名字集合 == 包内端口文件的名字
   集合（两个方向都查：真源有包内无 → 漏搬；包内有真源无 → 私自加动词）。真源里没有
   `register_action` 的**装配器**端口（equip）改断言装配函数名存在（`install_ext_actions` /
   `apply_to_actor`），另 `apply_bar_procs` / `apply_cond_procs` / `apply_element_procs` /
   `apply_class_mech` / `apply_class_passives` 也逐个点名要求两端都在。
3. **参数表 deep-equal** —— `MECH_CASH` / `MECH_CFG` / `BAR_INJECT_FIELDS` / `BAR_STATE_PREFIX`
   / `REACTION_TABLE` / `ELEMENT_REACTIONS` / `WEAPON_EFFECT_DATA` / kinds 常量（`SkillKind`
   成员 + `K_*` + `_KIND_META` + `_DMG_KINDS`）从**两边源码静态读出**后逐值比较。
4. **漂移反证（防「门禁永远绿」）** —— 在 tmp 里复制一份端口目录，造 4 种「装坏」的假想端口
   （改动作名 / 删文件 / 改表值 / 改标量），断言门禁在副本上**必须报红**；随后再断言真仓
   **依然全绿**（证明前面只动了副本，没污染真源/真包）。

实现纪律（为什么不用 import）
------------------------------
真源模块**绝不 import**（会拉起 astrbot / sqlite 一整套宿主副作用，且慢）。表值用
「同文件模块级名字解析 + 静态字面量求值」读出来：`ast` 解析 → 模块级 `Assign/AnnAssign`
建名字表 → 递归折叠 `Constant/List/Tuple/Set/Dict(含 **spread)/UnaryOp/Name`。折不动
（函数调用、属性取值等）的节点退化为**源码文本**（`«expr»…`）参与比较 —— 仍能发现漂移。
本批 12 张表无需任何退化；只有 `K_*` 因真源写法是 `SkillKind.X.value` 先退化为文本，随后
**代入 SkillKind 成员求值**再比真值（求不动才退回文本比较），并另单独逐值比较枚举成员。

只读两仓；唯一写操作 = 在 `tempfile.mkdtemp()` 的副本上装坏（跑完删掉）。禁 git 操作。
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import shutil
import sys
import tempfile
import time

sys.dont_write_bytecode = True
try:                                                            # 中文断言消息
    sys.stdout.reconfigure(encoding="utf-8")                    # type: ignore[attr-defined]
except Exception:                                               # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)                               # dragonfall/
DEFAULT_FRAMEWORK_DIR = "C:/Users/yuyu/framework-engine"
FW_ROOT = os.path.abspath(os.environ.get("GWEN_FRAMEWORK_DIR") or DEFAULT_FRAMEWORK_DIR)
PKG_ID = "orlandia"
PKG_ROOT = os.path.join(FW_ROOT, "games", PKG_ID)               # <pkg_root>/content/mech/*.py
MECH_REL = "content/mech"
EXPR = "«expr»"
MAX_DIFF = 3                                                    # 每条红行最多贴几处差异

# ---------------------------------------------------------------------------
# 端口清单表（真源 → 包内端口；行号 = 2026-09-13 实测）
# ---------------------------------------------------------------------------
# 族            真源文件（游戏仓）                              真源行号                          包内端口
# ------------  --------------------------------------------  --------------------------------  ---------------------------
# class_mech    game/services/class_mech_proc.py               :100-1809（39 动作 / 全 2446 行）  content/mech/class_mech.py
# equip         game/services/battle_equip_proc.py             :1083 install_ext_actions,        content/mech/equip.py
#                                                              :1133 apply_to_actor（0 动作）
# we_procs      ★ 宿主壳已退役（B18-REPOINT；tests 侧零引用）    :99-1436（27 动作 / 全 1484 行）  content/mech/we_procs.py
# team_procs    ★ 宿主壳已退役（B18-REPOINT；tests 侧零引用）    :172-768（20 动作 / 全 788 行）   content/mech/team_procs.py
# bar_procs     ★ 宿主壳已退役（B18-REPOINT；tests 侧零引用）    :94-169（4 动作）:203 apply_bar   content/mech/bar_procs.py
# cond_procs    game/services/battle_cond_procs.py             :120（1 动作）:156 apply_cond       content/mech/cond_procs.py
# element_procs ★ 宿主壳已退役（B18-REPOINT；tests 侧零引用）    :133-272（4 动作）:296 apply_elem   content/mech/element_procs.py
# worldboss     game/services/battle_worldboss_procs.py        :27-48（1 动作；apply 未搬 :51-75） content/mech/worldboss.py
# kinds         game/data/kinds.py                             :1-120（SkillKind/K_*/_KIND_META） content/mech/kinds.py
# class_data    game/data/battle_rules.py + battle_config.py    :624 MECH_CASH / :455 MECH_CFG      content/mech/class_data.py
# element_data  game/data/battle_config.py                     :80-90 ELEMENT_REACTIONS,         content/mech/element_data.py
#                                                              :147-152 REACTION_TABLE, :142/:154
# we_data       game/data/weapon_effect_data.py + core/const   :27 WEAPON_EFFECT_DATA,           content/mech/we_data.py
#                                                              game/core/constants.py:156 ACT_TICK
# params        game/data/battle_rules.py                      :742 BAR_INJECT_FIELDS,           content/mech/params.py
#                                                              :749 BAR_STATE_PREFIX
PORTS = [
    # (族, 真源文件（单文件端口；多文件的数据端口用 None）, 真源行号说明, 包内端口文件, 装配器函数名, 动作集合是否比)
    # ★ B18-REPOINT（2026-09-15）：`we_procs` / `team_procs` / `bar_procs` / `element_procs` 四族的
    #   宿主壳已退役 ⇒ 它们的「真源文件」列 = **None**（见下方 RETIRED_SRC；② 段对这类族只审端口自身）。
    ("class_mech", "game/services/class_mech_proc.py",
     ":100-1809（39 个动作装饰器；全文件 :1-2446）", "content/mech/class_mech.py",
     ("apply_class_mech", "apply_class_passives", "apply_class_channels"), True),
    ("equip", "game/services/battle_equip_proc.py",
     ":1083 install_ext_actions / :1133 apply_to_actor（全文件 :1-1174，0 个动作）", "content/mech/equip.py",
     ("install_ext_actions", "apply_to_actor"), True),
    ("we_procs", None,
     ":99-1436（27 个动作；全文件 :1-1484）", "content/mech/we_procs.py", (), True),
    ("team_procs", None,
     ":172-768（20 个动作；全文件 :1-788）", "content/mech/team_procs.py", (), True),
    ("bar_procs", None,
     ":94-169（4 个动作）；:203 apply_bar_procs（全文件 :1-244）", "content/mech/bar_procs.py",
     ("apply_bar_procs",), True),
    ("cond_procs", "game/services/battle_cond_procs.py",
     ":120（1 个动作）；:156 apply_cond_procs（全文件 :1-180）", "content/mech/cond_procs.py",
     ("apply_cond_procs",), True),
    ("element_procs", None,
     ":133-272（4 个动作）；:296 apply_element_procs（全文件 :1-341）", "content/mech/element_procs.py",
     ("apply_element_procs",), True),
    ("worldboss", "game/services/battle_worldboss_procs.py",
     ":27-48（1 个动作 wb_gm_dmg_mult；apply_gm_dmg_mult :51-75 未搬，见文件头）",
     "content/mech/worldboss.py", (), True),
    ("kinds", "game/data/kinds.py", ":1-120（SkillKind / K_* / _KIND_META）",
     "content/mech/kinds.py", (), False),
    ("class_data", None, ":624 MECH_CASH / :455 MECH_CFG", "content/mech/class_data.py", (), False),
    ("element_data", None, ":80-90 ELEMENT_REACTIONS / :147-152 REACTION_TABLE / :142 / :154",
     "content/mech/element_data.py", (), False),
    ("we_data", None, ":27 WEAPON_EFFECT_DATA / game/core/constants.py:156 ACT_TICK",
     "content/mech/we_data.py", (), False),
    ("params", None, ":742 BAR_INJECT_FIELDS / :749 BAR_STATE_PREFIX", "content/mech/params.py", (), False),
]

# ---------------------------------------------------------------------------
# ★ B18-REPOINT（2026-09-15）**退役族**：这四族的宿主壳已从 tests 侧零引用
# ---------------------------------------------------------------------------
# `we_procs` / `team_procs` / `bar_procs` / `element_procs` 四族的宿主壳已退役（宿主侧另一条线
# 负责物理删除），tests 侧不再 import、不再探路径、不再打桩 ⇒ 本门禁对这四族**不再读宿主**：
#   · PORTS 里它们的「真源文件」= None（② 段按 `RETIRED_SRC` 走退役分支）；
#   · 退役分支的断言语义（**口径变更，不是删断言**）：
#       ⓐ 端口动作 KEY 集 == 冻结清单（原样保留 —— 漏搬 / 私加 / 改名照样红）
#       ⓑ 装配器名仍在**端口模块顶层**（原「宿主壳再导出超集」的宿主无关等价物：
#          没有壳 = 没有宿主调用点要保名，能保名的只剩端口自己）
#     「壳确实 import 了包内族模块」一条**随壳退役**（没有壳可查）。
#   · 其余 4 族（class_mech / equip / cond_procs / worldboss）仍走 B10 薄壳分支，口径一字不变。
RETIRED_SRC = {"we_procs", "team_procs", "bar_procs", "element_procs"}

# ---------------------------------------------------------------------------
# B10（2026-09-13）「双源收口」后的断言语义 —— **本门禁最重要的一次口径变更**
# ---------------------------------------------------------------------------
# B10 把 8 个族的宿主实现改成了**薄壳**（`game/services/*.py` = 包加载口 + 全量再导出 +
# 入口一行委托；唯一实现在包内 `content/mech|content/*.py`）。于是本门禁原来那句
# 「真源 AST ↔ 端口 AST 逐名相等」的**前提消失了**：薄壳里根本没有 `@register_action`，
# 拿它当真源只会得到「真源 0 / 包内 N」的假红（B10 实测 10 条，全是这一句）。
# ⇒ 对**已收口族**（自动判据 `is_shell_file()`：0 个 `@register_action` + 源文本 import 了
#   `content.*` + <400 行），② 段三条断言换成**宿主无关**的等价物：
#     ⓐ 端口动作集 == 冻结清单 `EXPECT_ACTIONS`（漏搬 / 私加 / 端口被掏空都报红）
#     ⓑ 薄壳模块级导出（def/class/赋值名）⊇ 端口动作集 ∪ 装配器名
#        —— 这正是「宿主调用点不会 AttributeError」的静态保证（薄壳少再导出 = 红）
#     ⓒ 薄壳确实 import 了对应包内族模块（防「壳连包都不读」）
#   未收口族（真源仍是旧实现：别仓 / 未搬完）走原逻辑不变。
# ---------------------------------------------------------------------------
# 冻结动作 KEY 集（2026-09-13 B10 收口后实测，源 = 包内端口 `register_action` 的 key）——
# 漏搬 / 私加 / **改名** 都报红（`class_mech` 的动作原是 `install()` 内闭包，宿主侧从未按名暴露，
# 故它的 key 集也必须冻结在这儿，否则「改名」无从发现）。
EXPECT_ACTION_KEYS = {
    "class_mech": (
        "class_faith_load_tier", "class_faith_overload", "class_guard_stance_enter",
        "class_melody_act", "class_melody_dirge_tick", "class_res_channel_gain",
        "class_shadow_dance_enter", "class_stance_counter", "class_stance_guard_enter",
        "mech_cash_clear", "mech_cash_dmg_mult", "mech_cash_finisher_crit", "mech_cash_fury_enter",
        "mech_cash_per_system_mult", "passive_bar_decay_half", "passive_bar_extend",
        "passive_cc_break", "passive_cc_clear", "passive_cond_crit", "passive_counter",
        "passive_ctrl_extend", "passive_dmg_mult", "passive_dot_mult", "passive_element_core_crit",
        "passive_heal_overflow_shield", "passive_kill_gain", "passive_lian_duan_soft",
        "passive_lifesteal_buff", "passive_low_hp_core", "passive_mark_enhance", "passive_melody_duet",
        "passive_overflow_shield", "passive_poison_spread", "passive_poison_weaken",
        "passive_res_gain_turn", "passive_revive_berserk", "passive_revive_guard",
        "passive_shadow_buff", "passive_taken_reduce",
    ),
    "we_procs": (
        "we_abyss", "we_act_done_slow", "we_affix_bonus", "we_affix_counter", "we_affix_defdown",
        "we_affix_dot", "we_affix_element", "we_affix_purify", "we_affix_res_gain",
        "we_affix_tenacity", "we_amp_consume", "we_combo_end", "we_combo_stack", "we_control",
        "we_death_pool_add", "we_death_pool_pay", "we_dmg_mult_cond", "we_dot", "we_extra_dmg",
        "we_guardian_will", "we_hit_slow", "we_mana_once", "we_reflect", "we_shield_cond",
        "we_shield_taken", "we_stack_prod", "we_taken_mult_cond",
    ),
    "team_procs": (
        "arcane_edge_apply", "arcane_field", "block_once", "block_once_apply", "block_reflect_hit",
        "guard_expire", "guard_reflect", "self_cc_immune", "self_shield", "target_lock_mark",
        "team_apply", "team_cc_immune", "team_dmg_aura", "team_dmg_aura_apply", "team_guard",
        "team_shield", "team_ss_reduce_apply", "team_taken_reduce", "timed_vuln", "timed_vuln_apply",
    ),
    "bar_procs": (
        "bar_gain", "bar_phase_preserve", "bar_time_settle", "passive_reflect_bar",
    ),
    "cond_procs": (
        "skill_cond_mult",
    ),
    "element_procs": (
        "class_element_switch", "elem_conv_apply", "elem_counter", "elem_reaction",
    ),
    "worldboss": (
        "wb_gm_dmg_mult",
    ),
    "equip": (),
}
EXPECT_ACTIONS = {k: len(v) for k, v in EXPECT_ACTION_KEYS.items()}
# 这些族的**原宿主**把动作定义在模块级（顶格 `@register_action`）→ 测试按名 `from game.services.X import <函数名>`
# 必须继续可用 ⇒ 薄壳须再导出「动作函数名」。`class_mech` 例外：39 个动作原是 `install()` 内的**闭包**
# （模块级从未暴露过），故只要求装配器名；`equip` 本就 0 动作。
EXPOSE_ACTIONS = {"class_mech": False, "equip": False}
SHELL_MARK = re.compile(r"^\s*from\s+content(?:\.\w+)*\s+import\s", re.M)
# 动态再导出机制（PEP 562 `__getattr__` / `globals()[...] = ...`）：有它 = **任何**名字都能转发到包内
DYN_MARK = re.compile(r"def\s+__getattr__|globals\(\)\s*\.\s*update|globals\(\)\[|\bg\s*=\s*globals\(\)")


def is_shell_file(path: str, view=None) -> bool:
    """薄壳判据（B10 收口族）：0 个 `@register_action` + import 了包内模块 + <400 行。"""
    try:
        v = view if view is not None else ModView(path)
    except SyntaxError:
        return False
    if v.actions:
        return False
    txt = _read(path)
    return len(txt.splitlines()) < 400 and bool(SHELL_MARK.search(txt))


def shell_exports(path: str):
    """薄壳对外名字面：静态名字（def/class/赋值/`import` 进来的）+ 是否有动态再导出机制。"""
    txt = _read(path)
    tree = ast.parse(txt, filename=path)
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            names |= {a.asname or a.name for a in node.names}
        elif isinstance(node, ast.Import):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        else:
            tgts = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else [])
            for t in tgts:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names, bool(DYN_MARK.search(txt))


def port_action_funcs(path: str) -> set:
    """端口里被 `@register_action("k")` 装饰的**函数名**（宿主可见名；与 action key 未必同名，
    如 `bar_gain_act` ↔ key `bar_gain`）。只看模块顶层 —— 与「宿主模块级暴露过谁」对齐。"""
    tree = ast.parse(_read(path), filename=path)
    out = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                f = d.func if isinstance(d, ast.Call) else d
                nm = getattr(f, "id", None) or getattr(f, "attr", None)
                if nm in ("register_action", "register_cond"):
                    out.add(node.name)
    return out


# 参数表 deep-equal：(表名, 真源文件, 真源行号, 包内端口, 包内变量名)
TABLES = [
    ("MECH_CASH", "game/data/battle_rules.py", ":624", "content/mech/class_data.py", "MECH_CASH"),
    ("MECH_CFG", "game/data/battle_config.py", ":455", "content/mech/class_data.py", "MECH_CFG"),
    ("BAR_INJECT_FIELDS", "game/data/battle_rules.py", ":742", "content/mech/params.py", "BAR_INJECT_FIELDS"),
    ("BAR_STATE_PREFIX", "game/data/battle_rules.py", ":749", "content/mech/params.py", "BAR_STATE_PREFIX"),
    ("REACTION_TABLE", "game/data/battle_config.py", ":147", "content/mech/element_data.py", "REACTION_TABLE"),
    ("ELEMENT_REACTIONS", "game/data/battle_config.py", ":80", "content/mech/element_data.py", "ELEMENT_REACTIONS"),
    ("ELEMENT_MARKS_MAX", "game/data/battle_config.py", ":142", "content/mech/element_data.py", "ELEMENT_MARKS_MAX"),
    ("ELEMENT_SAME_CAST_EXTRA_CHARGE", "game/data/battle_config.py", ":154",
     "content/mech/element_data.py", "ELEMENT_SAME_CAST_EXTRA_CHARGE"),
    ("WEAPON_EFFECT_DATA", "game/data/weapon_effect_data.py", ":27", "content/mech/we_data.py", "WEAPON_EFFECT_DATA"),
    ("ACT_TICK", "game/core/constants.py", ":156", "content/mech/we_data.py", "ACT_TICK"),
    ("K_PHYS", "game/data/kinds.py", ":56", "content/mech/kinds.py", "K_PHYS"),
    ("K_MAGI", "game/data/kinds.py", ":57", "content/mech/kinds.py", "K_MAGI"),
    ("K_HEAL", "game/data/kinds.py", ":58", "content/mech/kinds.py", "K_HEAL"),
    ("K_BUFF", "game/data/kinds.py", ":59", "content/mech/kinds.py", "K_BUFF"),
    ("K_PASSIVE", "game/data/kinds.py", ":60", "content/mech/kinds.py", "K_PASSIVE"),
    ("K_SUMMON", "game/data/kinds.py", ":61", "content/mech/kinds.py", "K_SUMMON"),
    ("K_TRUE", "game/data/kinds.py", ":62", "content/mech/kinds.py", "K_TRUE"),
    ("K_TAUNT", "game/data/kinds.py", ":63", "content/mech/kinds.py", "K_TAUNT"),
    ("_KIND_META", "game/data/kinds.py", ":66", "content/mech/kinds.py", "_KIND_META"),
    ("_DMG_KINDS", "game/data/kinds.py", ":78", "content/mech/kinds.py", "_DMG_KINDS"),
]

# 真源里非字面量（`SkillKind.X.value`）→ 先把成员代进去求值再比；求不动才退化为文本比较
EXPR_TABLES = {"K_PHYS", "K_MAGI", "K_HEAL", "K_BUFF", "K_PASSIVE", "K_SUMMON", "K_TRUE", "K_TAUNT"}
# B16 收口（2026-09-14）：宿主 `game/data/kinds.py` 已随数据层删除 → 枚举只剩包内一份，
# 无法再"两边比"。换成与 §3 同款的**冻结基线**（成员值 + 锚点；下表由
# `tests/_ports_freeze_gen.py --write` 生成，改值必须显式重跑并复核）。
SKILL_KIND_REL = "content/mech/kinds.py"

# ---------------------------------------------------------------------------
# 参数表冻结基线（B16 收口实测；来源 = 包内端口源码**静态**求值）
# ---------------------------------------------------------------------------
# 为什么需要它：这些表的宿主真源 `game/data/*.py` 已物理删除（74.7k 行 / 87 文件），
# 旧口径「端口源码 == 宿主真源源码逐值」失去参照物；把参照指回包内同一文件会退化成
# "自己跟自己比"（永远绿 = 没牙）。冻结基线是仍成立、且不比旧口径弱的机器证据：
#   · `n`      —— 键数（漏搬/私加/结构变了 = 红）
#   · `sha`    —— canonical 求值的 sha256（改任何一格 = 红，改值必须显式更新）
#   · anchors  —— 「键路径 → 值」硬编码抽查（sha 更新时不许盲改：锚点会对不上）
FROZEN_TABLE = {
    "MECH_CASH": {
        "n": 9,
        "sha": "a571b3b2fe9853532471972529f0f98d142a25918320d8bc1ac5dcf32513ff17",
        "anchors": [
            (("'finisher'", "'name'"), '终结技'),
            (("'finisher'", "'mode'"), 'dmg_mult_clear'),
            (("'finisher'", "'key'"), 'lian_duan'),
        ],
    },
    "MECH_CFG": {
        "n": 15,
        "sha": "a8308ce16be321eb8bc404c60cda9e8dfc9eace55e976dde8a6b3dd874dcf04f",
        "anchors": [
            (("'dot'", "'poison'", "'atk'"), 0.8),
            (("'dot'", "'poison'", "'matk'"), 0.0),
            (("'dot'", "'poison'", "'hp'"), 0.0),
        ],
    },
    "BAR_INJECT_FIELDS": {
        "n": 1,
        "sha": "7d48d4298c3e40df616e450749bf84eca8a931a5e3677ade155653bd064d4ee0",
        "anchors": [
            (("'shaken_gain'", "'key'"), 'shaken'),
            (("'shaken_gain'", "'per_hit'"), True),
        ],
    },
    "BAR_STATE_PREFIX": {
        "n": 1,
        "sha": "2434973763607aa7d54a3d48c3891e23fc2f6b5b36b3d0093e26b6beff8f0057",
        "anchors": [
            ((), 'bar:'),
        ],
    },
    "REACTION_TABLE": {
        "n": 4,
        "sha": "8b541aff45698425d714de8ace345edf40b4e809e6c683b322fe10a0adae2494",
        "anchors": [
            (("('fire', 'ice')", "'kind'"), 'vaporize'),
            (("('fire', 'ice')", "'name'"), '蒸发'),
            (("('fire', 'ice')", "'mult'"), 1.3),
        ],
    },
    "ELEMENT_REACTIONS": {
        "n": 4,
        "sha": "e746adce411d2cf6fe00ce07e5daa79e93c079c47101e6d834c94885db34bc04",
        "anchors": [
            (("('ice', 'fire_mark')", "'name'"), '蒸发'),
            (("('ice', 'fire_mark')", "'mult'"), 1.3),
            (("('ice', 'fire_mark')", "'clear'"), True),
        ],
    },
    "ELEMENT_MARKS_MAX": {
        "n": 1,
        "sha": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
        "anchors": [
            ((), 3),
        ],
    },
    "ELEMENT_SAME_CAST_EXTRA_CHARGE": {
        "n": 1,
        "sha": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
        "anchors": [
            ((), 1),
        ],
    },
    "WEAPON_EFFECT_DATA": {
        "n": 82,
        "sha": "aa9b344acd202ece8a548d3b6d9846750ad05030fd18143234bf9cf36392a7ef",
        "anchors": [
            (("'starlight_bulwark'", "'family'"), 'proc_shield'),
            (("'starlight_bulwark'", "'shield_hp_pct'"), 0.1),
            (("'starlight_bulwark'", "'turns'"), 3),
        ],
    },
    "ACT_TICK": {
        "n": 1,
        "sha": "d0ff5974b6aa52cf562bea5921840c032a860a91a3512f7fe8f768f6bbe005f6",
        "anchors": [
            ((), 1.0),
        ],
    },
    "K_PHYS": {
        "n": 1,
        "sha": "c9f5e55e325225233349acef54c440f9d617ed02322637f2ebf92a3d5dcd3b73",
        "anchors": [
            ((), '物理'),
        ],
    },
    "K_MAGI": {
        "n": 1,
        "sha": "a07cee41b5a7bc6120243513ae2d865b61e55378e7a092d9774fe09fd4796811",
        "anchors": [
            ((), '魔法'),
        ],
    },
    "K_HEAL": {
        "n": 1,
        "sha": "c58094d8b9cd4efe90a96d08f145a07e6477586c4089a0e3fe5c93fd8c3e7a95",
        "anchors": [
            ((), '治疗'),
        ],
    },
    "K_BUFF": {
        "n": 1,
        "sha": "9f555a96234913ca18fcde2dd837c657fa68a1f1c68f64d2b1ea442315ab44ce",
        "anchors": [
            ((), '增益'),
        ],
    },
    "K_PASSIVE": {
        "n": 1,
        "sha": "edec036a5293aa1ed06248006e200d9523daaca00ec9e6897a8a412848537bf5",
        "anchors": [
            ((), '被动'),
        ],
    },
    "K_SUMMON": {
        "n": 1,
        "sha": "e9c7527229727f9206ae2dd2cb35406de77e8923ba119f06a2a21d87379acf38",
        "anchors": [
            ((), '召唤'),
        ],
    },
    "K_TRUE": {
        "n": 1,
        "sha": "d04ff763c8e28ac17bce743e0a3814c2b97b4ef6f12c90a45c71ac8708971ea4",
        "anchors": [
            ((), '真伤'),
        ],
    },
    "K_TAUNT": {
        "n": 1,
        "sha": "0238d1e3da2c5f44bbf328c15bc628d31d1c23b9902c986ba05130f14ef274a6",
        "anchors": [
            ((), '嘲讽'),
        ],
    },
    "_KIND_META": {
        "n": 8,
        "sha": "104c02355b19c95d57bc3ed230493639a62e9542616740a8d4687794fc968db4",
        "anchors": [
            (("'«expr»SkillKind.PHYS'", "'seg'"), 'phys'),
            (("'«expr»SkillKind.PHYS'", "'damage'"), True),
            (("'«expr»SkillKind.PHYS'", "'lifesteal'"), 'phys'),
        ],
    },
    "_DMG_KINDS": {
        "n": 3,
        "sha": "dde4b0a87a3a6f15b02c9f2b2d0635a4c158e03a4eca1607c56cb5d6e0f7a2c4",
        "anchors": [],
    },
}

FROZEN_SKILLKIND = {
    "BUFF": '增益',
    "HEAL": '治疗',
    "MAGI": '魔法',
    "PASSIVE": '被动',
    "PHYS": '物理',
    "SUMMON": '召唤',
    "TAUNT": '嘲讽',
    "TRUE": '真伤',
}

# 双源收敛后的「再导出」接线：这些名字必须仍从单源（params.py）再导出（防第二个副本长回来）
REEXPORTS = [
    ("content/mech/class_data.py", "BAR_INJECT_FIELDS", "params"),
    ("content/mech/class_data.py", "BAR_STATE_PREFIX", "params"),
    ("content/mech/element_data.py", "BAR_INJECT_FIELDS", "params"),
]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _p(*parts: str) -> str:
    return os.path.join(*[p.replace("/", os.sep) for p in parts])


def _is_reg(fn) -> bool:
    return ((isinstance(fn, ast.Name) and fn.id == "register_action")
            or (isinstance(fn, ast.Attribute) and fn.attr == "register_action"))


class ModView:
    """一个 .py 的静态视图：模块级赋值 + 顶层 def/class + @register_action 名字。永不 import。"""

    def __init__(self, path: str):
        self.path = path
        self.tree = ast.parse(_read(path), filename=path)
        self.assigns: dict = {}
        self.defs: set = set()
        self.actions: list = []
        self.nonliteral: list = []
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs.add(node.name)
            tgts = []
            if isinstance(node, ast.Assign):
                tgts = node.targets
            elif isinstance(node, ast.AnnAssign):
                tgts = [node.target]
            for t in tgts:
                if isinstance(t, ast.Name):
                    self.assigns[t.id] = node.value
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and _is_reg(node.func):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    self.actions.append(node.args[0].value)
                else:
                    self.nonliteral.append(node.lineno)
        self.actions = sorted(set(self.actions))

    # ---- 静态求值 ----
    def value(self, name: str):
        if name not in self.assigns:
            return "«missing»"
        return self._conv(self.assigns[name], 0)

    def _conv(self, node, depth: int):
        if depth > 12:
            return EXPR + "<深>"
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            items = [self._conv(e, depth) for e in node.elts]
            return items if isinstance(node, ast.List) else tuple(items)
        if isinstance(node, ast.Set):
            return frozenset(self._conv(e, depth) for e in node.elts)
        if isinstance(node, ast.Dict):
            out = {}
            for k, v in zip(node.keys, node.values):
                if k is None:                                   # **spread（同文件名字表能折就折）
                    spread = self._conv(v, depth + 1)
                    if isinstance(spread, dict):
                        out.update(spread)
                        continue
                    out[EXPR + "spread:" + ast.unparse(v)] = EXPR
                    continue
                out[self._conv(k, depth + 1)] = self._conv(v, depth + 1)
            return out
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = self._conv(node.operand, depth + 1)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return -v if isinstance(node.op, ast.USub) else v
            return EXPR + ast.unparse(node)
        if isinstance(node, ast.Name) and node.id in self.assigns:
            return self._conv(self.assigns[node.id], depth + 1)
        return EXPR + ast.unparse(node)                          # 退化：源码文本比较

    def enum_members(self, cls: str) -> dict:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == cls:
                out = {}
                for st in node.body:
                    if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                        out[st.targets[0].id] = self._conv(st.value, 0)
                return out
        return {}

    def imports_from(self, module_tail: str) -> list:
        out = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == module_tail:
                out.extend(a.name for a in node.names)
        return out


_ENUM_REF = re.compile(r"^SkillKind\.(\w+)(?:\.value)?$")


def _canon(v):
    """canonical 编码（与 tests/_ports_freeze_gen.py **逐行同一实现**；tuple/frozenset/expr 各带标记）。"""
    if isinstance(v, dict):
        return {"§dict": [[_canon(k), _canon(x)]
                          for k, x in sorted(v.items(), key=lambda kv: repr(kv[0]))]}
    if isinstance(v, tuple):
        return {"§tuple": [_canon(x) for x in v]}
    if isinstance(v, list):
        return [_canon(x) for x in v]
    if isinstance(v, frozenset):
        return {"§frozenset": sorted(repr(x) for x in v)}
    if isinstance(v, str) and v.startswith(EXPR):
        return {"§expr": v}
    return v


def _canon_sha(v) -> str:
    """冻结基线的值指纹：canonical JSON → sha256。"""
    import hashlib
    import json as _json
    return hashlib.sha256(_json.dumps(_canon(v), ensure_ascii=False,
                                      sort_keys=True).encode("utf-8")).hexdigest()


def _anchor_get(val, segs):
    """按锚点路径取值：段 = `repr(键)`（dict）或索引字符串（list/tuple）。"""
    for seg in segs:
        if isinstance(val, dict):
            hit = [k for k in val if repr(k) == seg]
            if not hit:
                return "«缺键 %s»" % seg
            val = val[hit[0]]
        else:
            try:
                val = val[int(seg)]
            except (IndexError, ValueError, TypeError):
                return "«取不到 %s»" % seg
    return val


def _resolve(view: ModView, val):
    """把退化成文本的值再救一次：`«expr»SkillKind.PHYS.value` → 枚举成员的真值。"""
    if isinstance(val, str) and val.startswith(EXPR):
        m = _ENUM_REF.match(val[len(EXPR):].strip())
        if m:
            mem = view.enum_members("SkillKind")
            if m.group(1) in mem:
                return mem[m.group(1)]
    return val


def _diff(a, b, path: str = "¥", out=None, limit: int = MAX_DIFF) -> list:
    """浅层结构化差异文案（最多 limit 条），用于红行定位。"""
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) - set(b), key=repr):
            out.append("%s 真源有键 %r 而包内无" % (path, k))
            if len(out) >= limit:
                return out
        for k in sorted(set(b) - set(a), key=repr):
            out.append("%s 包内多出键 %r（真源没有）" % (path, k))
            if len(out) >= limit:
                return out
        for k in sorted(set(a) & set(b), key=repr):
            if a[k] != b[k]:
                _diff(a[k], b[k], "%s%r." % (path, k), out, limit)
        return out
    if a != b:
        out.append("%s 真源=%r 包内=%r" % (path, a if not hasattr(a, "__len__") else str(a)[:120],
                                          b if not hasattr(b, "__len__") else str(b)[:120]))
    return out


class Rep:
    def __init__(self, quiet: bool = False):
        self.passed = 0
        self.failed = 0
        self.violations: list = []
        self.quiet = quiet

    def check(self, name: str, cond: bool, detail: str = "") -> bool:
        if cond:
            self.passed += 1
            if not self.quiet:
                print("  ✅ %s" % name)
        else:
            self.failed += 1
            msg = "%s %s" % (name, detail)
            self.violations.append(msg.strip())
            if not self.quiet:
                print("  ❌ %s" % msg.strip())
        return bool(cond)


# ---------------------------------------------------------------------------
# 四类断言
# ---------------------------------------------------------------------------
# 参数表单源审计（2026-09-13 新增 —— 对应当天修的一个真 bug）
# ---------------------------------------------------------------------------
# 实测踩过：`MECH_CFG` 在包内**三份**（class_data 全量 = 等于真源 / element_data 只 element 一档 /
#   params 只 enemy_bar 一档**且截断**：真源 ENEMY_BAR_CFG 是 {curse, shaken}，它只抄了 shaken）。
#   而 params 那份挂在引擎 hook `mech_cfg_fn` 上 → `config.mech_cfg("enemy_bar")` 拿到的配置**缺 curse**
#   （静默少一档），走 class_data 的装配层却拿到完整的 —— 同一机制名、两条入口、两套值。
# `MECH_CASH` 同理：class_data 9 条 / params 空 `{}`。
# ⇒ 判据：每张参数表在包内**最多一处"字面量定义"**（赋值右侧直接是 dict/list/常量）。
#   再导出（`from x import Y`）与派生值（`Y = f(...)`）**不算**第二份定义 —— 那正是我们要的形状。
SINGLE_SOURCE_TABLES = ("MECH_CFG", "MECH_CASH", "BAR_INJECT_FIELDS", "BAR_STATE_PREFIX",
                        "WEAPON_EFFECT_DATA", "REACTION_TABLE", "ELEMENT_REACTIONS",
                        "ELEMENT_MARKS_MAX", "FORMULA_SKELETON", "SKILL_FLAT", "ACT_TICK")


def single_source_audit(pkg_root: str, rep: Rep) -> None:
    """每张参数表在包内最多一处字面量定义（同表多份 = 值碰巧一致 → 改一处就漂）。"""
    mech = _p(pkg_root, MECH_REL)
    hits: dict = {t: [] for t in SINGLE_SOURCE_TABLES}
    for fn in sorted(os.listdir(mech)):
        if not fn.endswith(".py"):
            continue
        try:
            tree = ast.parse(_read(os.path.join(mech, fn)))
        except SyntaxError:
            continue
        for node in tree.body:                       # 只看**模块顶层**赋值（函数内的临时量不算）
            tgt = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
            elif isinstance(node, ast.AnnAssign):    # `X: dict = {...}` 也算定义（实测 params 用过这写法）
                tgt = node.target
            if not isinstance(tgt, ast.Name) or tgt.id not in hits:
                continue
            if isinstance(node.value, (ast.Dict, ast.List, ast.Tuple, ast.Constant)):
                hits[tgt.id].append("%s:%d" % (fn, node.lineno))
    dup = {t: v for t, v in hits.items() if len(v) > 1}
    rep.check("每张参数表在包内最多一处字面量定义（共查 %d 张）" % len(SINGLE_SOURCE_TABLES),
              not dup, "同表多份定义（值碰巧一致也会漂）：%s" % dup)
    rep.check("单源检查不是空转（至少定位到 1 张表的定义处）",
              any(hits.values()), {t: v for t, v in hits.items() if v})


def audit(pkg_root: str, game_root: str, rep: Rep) -> None:
    """把 <pkg_root>/content/mech 当端口，对 game_root 真源跑四类断言（只读）。"""
    def head(msg: str) -> None:
        if not rep.quiet:
            print(msg)

    # ---- ① 端口文件存在 ----
    head("\n【1】端口文件存在（缺文件 = 点名红，绝不静默跳过）")
    for fam, _src, span, prel, _asm, _cmp in PORTS:
        path = _p(pkg_root, prel)
        rep.check("族 %-13s 端口存在 %s（真源 %s）" % (fam, prel, span),
                  os.path.isfile(path), "缺文件：%s" % path)

    # ---- ② @register_action 集合逐名相等 + 装配器名 ----
    # B10 起分两支：已收口族（宿主 = 薄壳）走「冻结动作数 + 薄壳导出超集 + 壳确实读包」，
    # 未收口族走原来的「真源 ↔ 端口 逐名相等」。（口径见文件中部 B10 说明块）
    head("\n【2】@register_action 集合逐名相等（装配器名）—— 已收口族（薄壳）走等价断言")
    for fam, src, span, prel, asm, cmp_actions in PORTS:
        ppath = _p(pkg_root, prel)
        if not os.path.isfile(ppath):
            continue                                            # ① 已红，不重复报
        try:
            pv = ModView(ppath)
        except SyntaxError as e:
            rep.check("族 %s 端口可解析" % fam, False, "语法错：%r" % (e,))
            continue
        rep.check("族 %-13s 端口内 register_action 全是字面量（门禁看得全）" % fam,
                  not pv.nonliteral, "非字面量调用在行 %s" % pv.nonliteral)
        if not cmp_actions:
            continue
        gpath = _p(game_root, src) if src else None
        # ★ P5C-REPOINT（2026-09-15）：宿主壳随 `game/**` 整棵树删除 —— PORTS 里指向
        #   `game/services/*.py` 的真源届时**不再存在**。口径与下面 `RETIRED_SRC` 分支
        #   （B18-REPOINT 已立的先例）逐条相同：不再读宿主 ⇒ 换成**宿主无关的等价物**
        #   （端口动作 KEY 集 == 冻结清单 + 装配器名仍在端口模块顶层），并打印一行去向。
        #   真源仍在时（本仓未删游戏的对照跑）原 B10 口径**一字不变** —— 不是放宽阈值，
        #   真源缺失也不再是「红/静默跳过」：仍跑端口自证断言（与 §3「真源已删 → 冻结基线」同策）。
        host_src_gone = bool(src) and not os.path.isfile(gpath)
        if src is None or fam in RETIRED_SRC or host_src_gone:
            if host_src_gone:
                head("  · 族 %-13s 真源已随 game/** 删除（%s）→ 退到端口自证口径"
                     % (fam, src))
            # ---- ★ B18-REPOINT：宿主壳已退役族 → 只审端口自身（不读宿主，零宿主路径引用）----
            exp_keys = EXPECT_ACTION_KEYS.get(fam)
            pset0 = set(pv.actions)
            only_pkg = sorted(pset0 - set(exp_keys)) if exp_keys is not None else []
            only_exp = sorted(set(exp_keys) - pset0) if exp_keys is not None else []
            rep.check("族 %-13s 宿主壳已退役：端口动作 KEY 集 == 冻结清单（%d 个；私加 %s / 缺 %s）"
                      % (fam, len(exp_keys or ()), only_pkg[:3], only_exp[:3]),
                      exp_keys is None or (not only_pkg and not only_exp),
                      "端口动作集变了（漏搬/私加/**改名**？）：私加=%s 缺=%s" % (only_pkg, only_exp))
            miss_asm = sorted(n for n in asm if n not in pv.defs)
            rep.check("族 %-13s 退役族装配器名仍在端口模块顶层（%s；缺 %s）"
                      % (fam, "/".join(asm) or "(无)", miss_asm), not miss_asm,
                      "装配器名不在端口顶层 → 宿主无关的唯一调用面消失：%s" % miss_asm)
            continue

        gpath = _p(game_root, src)
        if not os.path.isfile(gpath):
            rep.check("族 %s 真源存在 %s" % (fam, src), False, "真源文件缺失：%s" % gpath)
            continue

        if is_shell_file(gpath):
            # ---- B10 收口族：真源侧已是薄壳 → 换成宿主无关的断言 ----
            exported, dyn = shell_exports(gpath)
            funcs = port_action_funcs(ppath) if EXPOSE_ACTIONS.get(fam, True) else set()
            need = set(asm) | funcs
            miss_static = sorted(need - exported)
            missing = [] if dyn else miss_static
            exp_keys = EXPECT_ACTION_KEYS.get(fam)
            pset0 = set(pv.actions)
            only_pkg = sorted(pset0 - set(exp_keys)) if exp_keys is not None else []
            only_exp = sorted(set(exp_keys) - pset0) if exp_keys is not None else []
            rep.check("族 %-13s 已收口（宿主薄壳）：端口动作 KEY 集 == 冻结清单（%d 个；私加 %s / 缺 %s）"
                      % (fam, len(exp_keys or ()), only_pkg[:3], only_exp[:3]),
                      exp_keys is None or (not only_pkg and not only_exp),
                      "端口动作集变了（漏搬/私加/**改名**？）：私加=%s 缺=%s" % (only_pkg, only_exp))
            rep.check("族 %-13s 薄壳对外名字面 ⊇ %d 装配器 + %d 动作函数名（缺：%s；机制 = %s）"
                      % (fam, len(asm), len(funcs), missing, "动态再导出" if dyn else "静态再导出"),
                      not missing,
                      "薄壳少再导出 → 宿主调用点会 AttributeError：%s（静态缺 %d 个）"
                      % (miss_static[:6], len(miss_static)))
            rep.check("族 %-13s 薄壳确实 import 了包内族模块（%s）"
                      % (fam, prel.split("/")[-1]), bool(SHELL_MARK.search(_read(gpath))),
                      "薄壳里没有 `from content... import ...` —— 壳没读包？")
            continue

        gset, pset = set(ModView(gpath).actions), set(pv.actions)
        only_g, only_p = sorted(gset - pset), sorted(pset - gset)
        rep.check("族 %-13s @register_action 集合逐名相等（真源 %d / 包内 %d）" % (fam, len(gset), len(pset)),
                  gset == pset,
                  "真源有包内无(漏搬)：%s；包内有真源无(私加)：%s" % (only_g, only_p))
        if asm:
            gdefs = ModView(gpath).defs
            miss_g = [n for n in asm if n not in gdefs]
            miss_p = [n for n in asm if n not in pv.defs]
            rep.check("族 %-13s 装配器 %s 两端都在" % (fam, "/".join(asm)),
                      not miss_g and not miss_p,
                      "真源缺：%s；包内缺：%s" % (miss_g, miss_p))

    # ---- ③ 参数表：真源仍在 → 逐值 deep-equal；真源已删（B16）→ 冻结基线（sha + 键数 + 锚点）----
    head("\n【3】参数表（宿主真源已删的表走**冻结基线**；真源仍在的表仍走逐值 deep-equal）")
    for name, src, sline, prel, var in TABLES:
        gpath, ppath = _p(game_root, src), _p(pkg_root, prel)
        if not os.path.isfile(ppath):
            rep.check("表 %-30s 端口存在 %s" % (name, prel), False, "端口文件缺失：%s" % ppath)
            continue
        try:
            pv = ModView(ppath)
            b = _resolve(pv, pv.value(var))
        except SyntaxError as e:
            rep.check("表 %s 可静态读出" % name, False, "语法错：%r" % (e,))
            continue
        if b == "«missing»":
            rep.check("表 %-30s 端口 %s 里取得到 %s" % (name, prel, var), False, "取不到 %s" % var)
            continue

        if os.path.isfile(gpath):
            # 宿主真源**仍在**（如 ACT_TICK 来自仍在的 game/core/constants.py）→ 原口径不动
            try:
                gv = ModView(gpath)
                a = _resolve(gv, gv.value(var))
            except SyntaxError as e:
                rep.check("表 %s 真源可静态读出" % name, False, "语法错：%r" % (e,))
                continue
            extra = "（真源写法非字面量 → 代入 SkillKind 成员求值后比较）" if name in EXPR_TABLES else ""
            if a == "«missing»":
                rep.check("表 %-30s 两边都取到 %s%s%s" % (name, var, sline, extra), False,
                          "取不到：真源=%r 包内=%r" % (a, b))
                continue
            diffs = _diff(a, b)
            rep.check("表 %-30s == 真源 %s%s（真源 %s 项 / 包内 %s 项）"
                      % (name, src.split("/")[-1] + sline, extra,
                         len(a) if hasattr(a, "__len__") else 1,
                         len(b) if hasattr(b, "__len__") else 1),
                      not diffs, "；".join(diffs))
            continue

        # ---- 宿主真源已随 B16 删除 → 冻结基线（原出处 %s%s 仅作追溯）----
        fro = FROZEN_TABLE.get(name)
        if fro is None:
            rep.check("表 %-30s 已登记冻结基线" % name, False,
                      "TABLES 新增了表但没登记冻结值 —— 跑 tests/_ports_freeze_gen.py --write")
            continue
        n = len(b) if isinstance(b, (dict, list, tuple, set, frozenset)) else 1
        sha = _canon_sha(b)
        rep.check("表 %-30s 键数 == 冻结 %d（实测 %d；原出处 %s%s）"
                  % (name, fro["n"], n, src, sline), n == fro["n"],
                  "键数变了（漏搬 / 私加 / 结构改了？）")
        rep.check("表 %-30s 值 sha256 == 冻结值（%s…）" % (name, fro["sha"][:12]),
                  sha == fro["sha"],
                  "值漂了（实测 %s）；确认是有意改值再重跑 _ports_freeze_gen.py --write" % sha)
        for segs, want in fro["anchors"]:
            got = _anchor_get(b, segs)
            rep.check("表 %-30s 锚点 %s == %r" % (name, " > ".join(segs) if segs else "(根)", want),
                      repr(got) == repr(want), "实际 %r" % (got,))

    # ---- ③b SkillKind 枚举成员（包内单源 + 冻结基线；K_* 的「两边比较」随真源删除退役）----
    try:
        pm = ModView(_p(pkg_root, SKILL_KIND_REL)).enum_members("SkillKind")
    except (OSError, SyntaxError) as e:
        rep.check("SkillKind 枚举可读", False, "%r" % (e,))
        pm = {}
    if pm:
        rep.check("SkillKind 枚举成员 == 冻结基线（%d 个 / 冻结 %d 个）：%s"
                  % (len(pm), len(FROZEN_SKILLKIND), ",".join(sorted(pm))),
                  pm == FROZEN_SKILLKIND, "；".join(_diff(FROZEN_SKILLKIND, pm)))
        for _m in sorted(FROZEN_SKILLKIND):
            rep.check("SkillKind.%s 锚点 == %r" % (_m, FROZEN_SKILLKIND[_m]),
                      pm.get(_m) == FROZEN_SKILLKIND[_m], "实际 %r" % (pm.get(_m),))

    # ---- ③c 再导出接线（双源收敛不许长回第二个副本）----
    head("\n【4】单源再导出接线（BAR_* 唯一真源在 params.py）")
    for prel, nm, srcmod in REEXPORTS:
        ppath = _p(pkg_root, prel)
        ok = os.path.isfile(ppath) and nm in ModView(ppath).imports_from(srcmod)
        rep.check("%s 里 %s 仍从 .%s 再导出" % (prel, nm, srcmod), ok,
                  "未见 `from .%s import %s`（双源长回来了？）" % (srcmod, nm))
    pparams = _p(pkg_root, "content/mech/params.py")
    if os.path.isfile(pparams):
        pv = ModView(pparams)
        rep.check("params.py 是 BAR_* 的字面量单源（本文件自带定义，非再导出）",
                  "BAR_INJECT_FIELDS" in pv.assigns and "BAR_STATE_PREFIX" in pv.assigns,
                  "params.py 里没有 BAR_* 的模块级赋值")

    # ---- ⑤ 参数表单源（同表多份 = 值碰巧一致也会漂；2026-09-13 新增）----
    head("\n【5】参数表单源（每张表最多一处字面量定义；MECH_CFG 曾散成三份且一份截断）")
    single_source_audit(pkg_root, rep)


# ---------------------------------------------------------------------------
# ④ 漂移反证：在 tmp 副本上「装坏」，门禁必须报红
# ---------------------------------------------------------------------------
def _copy_pkg(pkg_root: str, tmp_root: str) -> None:
    shutil.copytree(_p(pkg_root, MECH_REL), _p(tmp_root, MECH_REL),
                    ignore=shutil.ignore_patterns("__pycache__"))


def _mutate(path: str, old: str, new: str) -> bool:
    txt = _read(path)
    if old not in txt:
        return False
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(txt.replace(old, new, 1))
    return True


def drift_reversal(pkg_root: str, game_root: str, rep: Rep, tmp_root: str) -> None:
    """造 7 份「装坏后」的副本 → 每份都必须在门禁下报红（防门禁永远绿）。"""
    print("\n【6】漂移反证（tmp 副本上装坏 → 门禁必须红；真仓不受影响）")
    cases = [
        ("M1 改动作名", "class_mech.py", '@register_action("passive_counter")',
         '@register_action("passive_counter_renamed")', "passive_counter"),
        ("M2 删端口文件", None, None, None, "worldboss.py"),
        ("M3 改参数表值", "class_data.py", "'crit_at': 4,", "'crit_at': 5,", "MECH_CASH"),
        ("M4 改标量表", "params.py", 'BAR_STATE_PREFIX = "bar:"', 'BAR_STATE_PREFIX = "barX:"',
         "BAR_STATE_PREFIX"),
        # M5：把"同表多份"长回来（在另一个文件里再写一份 MECH_CFG 字面量）→ 单源审计必须报红
        ("M5 双源长回来", "element_data.py", "ELEMENT_SAME_CAST_EXTRA_CHARGE = 1",
         'ELEMENT_SAME_CAST_EXTRA_CHARGE = 1\nMECH_CFG = {"element": {}}', "MECH_CFG"),
        # ★ B18-REPOINT 新增：退役族分支（src=None）也必须**有牙** —— 退役 = 只审端口自身，
        #   故在端口副本上改动作 KEY / 改装配器名，必须分别被 ①动作集 ②装配器名 两条断言抓住。
        ("M7 退役族改动作名", "we_procs.py", '@register_action("we_dot")',
         '@register_action("we_dot_renamed")', "we_dot"),
        ("M8 退役族删装配器名", "bar_procs.py", "def apply_bar_procs(",
         "def apply_bar_procs_renamed(", "apply_bar_procs"),
    ]
    for tag, fname, old, new, must_mention in cases:
        sub = os.path.join(tmp_root, tag.split()[0])
        os.makedirs(sub, exist_ok=True)
        _copy_pkg(pkg_root, sub)
        mech = _p(sub, MECH_REL)
        if fname is None:
            os.remove(os.path.join(mech, must_mention))
            mutated = True
        else:
            mutated = _mutate(os.path.join(mech, fname), old, new)
        if not mutated:
            rep.check("反证 %s：装坏生效（哨兵字串命中）" % tag, False,
                      "副本里没找到 %r —— 真源/包内写法变了，请更新本门禁的哨兵串" % (old or fname))
            continue
        quiet = Rep(quiet=True)
        audit(sub, game_root, quiet)
        hit = [v for v in quiet.violations if must_mention in v]
        rep.check("反证 %s：门禁在副本上报红且点名 %r（共 %d 条红）"
                  % (tag, must_mention, len(quiet.violations)), bool(hit),
                  "未报红 = 门禁是死的！" if not quiet.violations
                  else "红了 %d 条但没点名 %r：%s" % (len(quiet.violations), must_mention, quiet.violations[:2]))

    # ---- M6（B10 新增）：薄壳再导出缺失 / 端口动作集漂移，必须被「已收口族」断言抓住 ----
    # 用**合成薄壳文本**自证（不动真仓）。
    # ★ B18-REPOINT（2026-09-15）：we_procs 的宿主壳已退役 ⇒ 原「真仓薄壳再导出一个都不缺」这条
    #   对照**换位**：改成「端口自身对外名字面 ⊇ 全部动作函数名」（宿主无关的同类自证，
    #   机制仍是同一套 `shell_exports` / `ModView`，只是被测对象从壳换成唯一的真源 = 端口）。
    psh = _p(pkg_root, "content/mech/we_procs.py")
    if os.path.isfile(psh):
        pv6 = ModView(psh)
        fake = os.path.join(tmp_root, "fake_shell_we_procs.py")
        with open(fake, "w", encoding="utf-8", newline="") as f:
            f.write("from content.mech import we_procs as _E\n\n"
                    "we_dot = _E.we_dot\nensure_registered = _E.ensure_registered\n")
        fv6 = ModView(fake)
        f_missing = sorted(set(pv6.actions) - (set(fv6.defs) | set(fv6.assigns)))
        rep.check("反证 M6 合成薄壳（只再导出 we_dot）→ 必须判定缺 %d 个动作、且不缺 we_dot"
                  % (len(pv6.actions) - 1),
                  len(f_missing) == len(pv6.actions) - 1 and "we_dot" not in f_missing,
                  "缺 %d 个：%s" % (len(f_missing), f_missing[:3]))
        p_exported, p_dyn = shell_exports(psh)
        p_funcs = port_action_funcs(psh)
        p_missing = [] if p_dyn else sorted(p_funcs - p_exported)
        rep.check("反证 M6 对照：端口自身对外名字面 ⊇ 全部 %d 个动作函数名（缺 %s）"
                  % (len(p_funcs), p_missing), not p_missing, p_missing)
        rep.check("反证 M6 冻结清单：we_procs 端口动作数 == EXPECT_ACTIONS[we_procs]=27",
                  len(pv6.actions) == EXPECT_ACTIONS["we_procs"], len(pv6.actions))
    else:
        rep.check("反证 M6 前置：we_procs 端口在位", False, "缺 %s" % psh)

    recheck = Rep(quiet=True)
    audit(pkg_root, game_root, recheck)
    rep.check("反证收尾：前面 7 次装坏只动了 tmp 副本/合成文本，真仓/真包依然全绿",
              recheck.failed == 0, "真仓被污染了！%s" % recheck.violations[:2])


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 第三类：事件名反静默失效（2026-09-13 新增）
# ---------------------------------------------------------------------------
# 为什么：引擎 `fire()` 对**不在 EVENTS 全集**的事件名**静默 return**（effect_triggers.py 的
#   `if not event or event not in EVENTS: return`）→ "翻译器/数据写了个死名" = 触发器装上了
#   却永不触发、且**没有任何痕迹**（2026-09-13 缺口定性查出的第 4 条，属最难查的一类）。
#   端口侧已补运行时告警（`equip._UNKNOWN_EVENTS` + `map_event` 未知名 logging.warning）——
#   本类守那套机制**在位**（被删/被绕开都会红）+ 数据侧的名字**必须可解析**。
KNOWN_NON_EVENT_MARKERS = ("passive",)   # 常驻型标记：不是引擎事件，也不该被 fire 到（设计如此）


def dead_event_audit(pkg_root: str, game_root: str, rep: Rep) -> None:
    """事件名反静默失效（源码/数据口径，不 import —— 与前两类一致）。"""
    if not rep.quiet:
        print("\n【7】事件名反静默失效（死名 = 触发器装了却永不生效）")

    eng = _p(FW_ROOT, "saintess_engine", "battle", "effect_triggers.py")
    events: set = set()
    try:
        for n in ast.walk(ast.parse(_read(eng))):
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "EVENTS":
                events = set(ast.literal_eval(n.value))
    except Exception as e:                                       # noqa: BLE001
        rep.check("读得到引擎 EVENTS 全集（%s）" % eng, False, repr(e))
        return
    rep.check("引擎事件全集非空（%d 个事件）" % len(events), len(events) >= 20, sorted(events))

    # ---- 机制在位 ----
    eq = _p(pkg_root, "content", "mech", "equip.py")
    src = _read(eq)
    rep.check("端口 equip.py 保留未知名告警机制（_UNKNOWN_EVENTS + _known_engine_events）",
              "_UNKNOWN_EVENTS" in src and "def _known_engine_events" in src,
              "机制被删/被绕过 —— fire() 会静默吞掉死名")
    ev_map: dict = {}
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_EVENT_MAP":
            ev_map = ast.literal_eval(n.value)
    rep.check("_EVENT_MAP 有 dot_taken → dot_tick（对齐 N9 迁移表）",
              tuple(ev_map.get("dot_taken") or ()) == ("dot_tick",), ev_map.get("dot_taken"))
    bad_map = {k: [v for v in vs if v not in events] for k, vs in ev_map.items()
               if any(v not in events for v in vs)}
    rep.check("_EVENT_MAP 每个展开目标都在引擎事件全集里", not bad_map, bad_map)

    # ---- 数据侧：包内武器特效表的事件名必须可解析 ----
    we = _p(pkg_root, "content", "mech", "we_data.py")
    data_events: set = set()
    for n in ast.walk(ast.parse(_read(we))):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "WEAPON_EFFECT_DATA":
            for _k, v in ast.literal_eval(n.value).items():
                e = v.get("event") if isinstance(v, dict) else None
                for x in (e if isinstance(e, (list, tuple)) else [e]):
                    if x:
                        data_events.add(str(x))
    dead = sorted(x for x in data_events
                  if x not in events and x not in ev_map and x not in KNOWN_NON_EVENT_MARKERS)
    rep.check("武器特效数据的 %d 个 event 名全部可解析（引擎全集 ∪ _EVENT_MAP ∪ 非事件标记）"
              % len(data_events), not dead, "死名（会被 fire 静默吞掉）：%s" % dead)
    rep.check("武器特效数据里确实有走 _EVENT_MAP 的旧名（别把断层测成空转）",
              any(x in ev_map for x in data_events), sorted(data_events))


def main() -> int:
    t0 = time.time()
    print("=== P4「逐字端口」保真门禁（包内 mech vs 游戏仓真源）===")
    print("    真源 = %s（退役族不读宿主：%s）" % (REPO_ROOT, sorted(RETIRED_SRC)))
    print("    框架 = %s" % FW_ROOT)
    print("    端口 = %s" % _p(PKG_ROOT, MECH_REL))
    if not os.path.isdir(_p(PKG_ROOT, MECH_REL)):
        print("❌ 端口目录不存在：%s（可用 GWEN_FRAMEWORK_DIR 覆盖框架仓路径）" % _p(PKG_ROOT, MECH_REL))
        return 1

    rep = Rep()
    audit(PKG_ROOT, REPO_ROOT, rep)
    dead_event_audit(PKG_ROOT, REPO_ROOT, rep)
    tmp_root = tempfile.mkdtemp(prefix="mech_port_drift_")
    try:
        drift_reversal(PKG_ROOT, REPO_ROOT, rep, tmp_root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    print("\n=== 汇总：%d 通过 / %d 失败（%.1fs）===" % (rep.passed, rep.failed, time.time() - t0))
    if rep.failed:
        print("修法：① 已收口族红了 → 分两支：\n"
              "        · 退役族（RETIRED_SRC：宿主壳已删）→ 只可能红在**端口动作集**或**装配器名不在端口顶层**：\n"
              "          端口 key 改了 = 改 EXPECT_ACTION_KEYS（并同步包内使用点）；装配器名没了 = 端口被掏空。\n"
              "        · 仍带壳族（class_mech / equip / cond_procs / worldboss）→ 端口动作集或**薄壳再导出**漂了：\n"
              "          薄壳少了再导出 = 补回 `X = _pkg.X`。\n"
              "      ② 【3】参数表红了 → 分两支：宿主真源**仍在**的表（ACT_TICK）走逐值比对，改真源就得\n"
              "       同步包内；宿主真源**已删**的表（B16 其余全部）走**冻结基线**：确认是有意改值后\n"
              "       跑 `python tests/_ports_freeze_gen.py --write` 重生成 sha/键数/锚点（锚点对不上\n"
              "       = 你改的不止你以为的那一格）。\n"
              "      ③ 别为了让门禁变绿而删断言 —— 除非端口清单表本身写错了（文件/行号以本文件头部表为准）。")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
