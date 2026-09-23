# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 隐藏怪环境条件（**内容半边**）。

2026-09-24 B2a（抽包工程 B2 批第一步）：本模块原来把「形状 + 内容」焊在一起，
现在**形状在扩展包** `ext_achieve`、**内容留在这里**：

  形状（`ext_achieve.cond`）：条件注册表 `Registry`（未知名按默认键兜底 · 声明表整表装配）
                            · 环境位图 `EnvCtx` / `envs_of`（这是本模块的进口，见下两行）
  内容（本文件）：`ENV_KEYWORDS`（地图 ID 关键词 → 环境分类）·
              `cond_specs.json` 的 `hidden` 族（6 条环境判定的声明）·
              本包自己的扩展点（注册新环境 / 新条件）

对外面**一字未改**（消费者零改动）：

    content/combat_cmds.py:1213   from .hidden_cond import envs_of, check_cond, HiddenCtx
    tests/test_v98_03_registry.py HC.ENV_KEYWORDS / HC.register / HC.envs_of /
                                  HC.HiddenCtx / HC.check_cond / HC.CONDITIONS

扩展方式（与本模块进扩展包之前完全相同）：
- 加环境类型：`ENV_KEYWORDS` 加一组关键词（形状按**同一份对象**读，立即生效）
- 加判定：`@register("名字")` 注册一个 `fn(ctx) -> bool`（ctx = `HiddenCtx`）
"""
from __future__ import annotations

from ext_achieve.cond import EnvCtx, Registry, bind_envs
from ext_achieve.cond import envs_of as _envs_of

from .cond_specs import load as _load_specs


# 地图 ID 关键词 → 环境分类（**内容侧的活**：地名怎么起名是这款游戏的设定；
# 形状 `envs_of` 只按这张表算位图 —— 表在包内，形状零内容词表）
ENV_KEYWORDS = {
    "forest": ("forest", "wood", "glade"),
    # v110 审计修复：补 "trench"——深海鮟鱇 e_deep_angler 限定图 mist_trench（迷雾海沟）
    # 原无任何 water 关键词命中 → cond="water" 恒 False，该隐藏怪永刷不出（"击败全部
    # 25 种隐藏怪"成就与荧光鳞掉落不可达）；deep_dragon_palace/shipwreck_graveyard 为
    # 深海/沉船语义但 id 无关键词，仍由 mist_trench 命中补全可刷性
    "water": ("river", "lake", "sea", "reef", "dock", "swamp", "brook", "trench"),
    "ruin": ("ruin", "mine", "abyss", "battlefield", "altar", "tunnel", "crypt"),
}

# ── 装配（一次性；形状侧持有的是**同一份对象**，就地改表即刻生效）────────────────
_REG = Registry(default_key="any")
CONDITIONS = _REG.table                 # 旧名保留：普通 dict，外部直接写 / pop 照旧可用
register = _REG.register
bind_envs(ENV_KEYWORDS)                 # 环境词表注入（形状不复制）

# 6 条环境判定（恒真 / 位图取真值 / 位图与夜）走 `cond_specs.json` 的 hidden 族：
# 声明节点由引擎 `saintess_engine.conditions.declarative` 编译，形状只负责登记；
# 未知 cond 按 any 的既有口径一字未改。
_REG.register_specs(_load_specs("hidden"))

HiddenCtx = EnvCtx                      # 旧名保留（判定上下文：mid / cur_map / is_night / envs）
envs_of = _envs_of


def check_cond(cond: str, ctx) -> bool:
    """cond 名 → 判定；未知 cond 按默认键（any）处理（口径同本模块进扩展包之前）。"""
    return _REG.check(cond, ctx)
