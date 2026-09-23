# -*- coding: utf-8 -*-
"""《奥兰迪亚·余烬纪年》CTB 时间模型（V3：行动耗时公式下沉到内容侧）。

背景（鱼鱼原话）
----------------
「我要的是公式支持配置，不同的游戏数值可能又不一样，开方这个是属于写死了吧，
可以下沉到奥兰迪亚」。

v3 前：`extends/ext_combat/battle/schedule.py` 里写死

    CAST_ATK=1.0 / CAST_SKILL=1.6 / CAST_DEFEND=0.6 / SPD_REF=50.0
    action_time(spd, base) = base × sqrt(SPD_REF / spd)

v3 后：**引擎只留机制**（谁 ct 小谁先动、行动后 `ct = now + 本次耗时`），
「一次行动耗时多少」= 本模块从 `content/rules/game_config.json` 读形状与参数、
构造出 `fn(spd, base) -> float`，再由 `content/apply.py::install_engine()` 挂到引擎注入面

    time_model_fn     fn(spd, base) -> float   第一段耗时（游戏秒）
    action_base_fn    fn(action) -> float      行动类别（通用键）→ 第一段基准耗时
    recover_model_fn  fn(spd, base) -> float   第二段（收招）耗时（游戏秒）
    recover_base_fn   fn(action) -> float      行动类别 → 第二段基准耗时

★ 两段（T14 · 2026-09-20）：引擎只做「两段相加」，不认识「出招/收招」业务词；
「没有第二段」由本包**显式声明 0** 表达（`recover` 段全 0 ⇒ 行为与单段逐字节相同）。

**未装配 → fail-closed**：引擎 `schedule.action_time()` 抛 `EngineNotConfigured`
（引擎侧没有、也不许有"默认公式"）。

数据单源
--------
形状与参数只此一份：`content/rules/game_config.json` →
`formula_skeleton` 组 → `FORMULA_SKELETON.TIME_MODEL` 子键
（读口 `content/catalog_rules.py::time_model()`）。
本模块**不自带第二份数值**；表缺了/坏了 → 抛 `TimeModelConfigError` 点名（不静默降级）。

    {
      "shape": "sqrt",                    # sqrt | linear | flat（两段默认形状）
      "spd_ref": 50.0,
      "cast": {"attack": 1.0, "skill": 1.6, "defend": 0.6, "item": 1.0},
      "recover": {"attack": 0.0, "skill": 0.0, "defend": 0.0, "item": 0.0},
      "recover_shape": null,              # null = 复用 shape；给值 = 第二段独立形状（如 "flat" = 收招不吃速度）
      "spd_cap": null                     # null = 不截断（min(spd, cap) 仅在给了正数时生效）
    }

两段都是「同形状分发、各自基准查表」：`action_time` 走 `cast` + `shape`，
`recover_time` 走 `recover` + `recover_shape`（缺省回落 `shape`）。

三种 shape 的公式（`s = max(spd, 1)`；给了正 `spd_cap` 时 `s = min(s, spd_cap)`）
-------------------------------------------------------------------------------
| shape    | 公式                        | 语义 |
|---|---|---|
| `sqrt`   | `base × sqrt(spd_ref / s)`  | 速度收益递减（奥兰迪亚现值）；spd=200 是 spd=50 的 1/2 |
| `linear` | `base × (spd_ref / s)`      | 速度线性缩放；spd=200 是 spd=50 的 1/4 |
| `flat`   | `base`                      | 不随速度变（行动耗时恒定） |

数值验证（base=1.0 / spd_ref=50 / spd_cap=null，手算 vs 实跑，V3 探针 `out/raw/`）：
`sqrt`: spd=1 → 7.0710678118654755 · spd=50 → 1.0 · spd=200 → 0.5
`linear`: spd=1 → 50.0 · spd=50 → 1.0 · spd=200 → 0.25
`flat`: 任意 spd → 1.0

未知 shape / 缺字段 / 非正 spd_ref → `TimeModelConfigError`（点名缺哪个键）。
"""
from __future__ import annotations

import math

#: 引擎动作类别通用键的**默认项**（未知类别回落它；与引擎 `schedule.DEFAULT_ACTION` 同口径）
DEFAULT_ACTION = "attack"


class TimeModelConfigError(ValueError):
    """时间模型配置缺失/非法（fail-closed：不猜、不用默认值兜）。"""


def time_model() -> dict:
    """读包内时间模型参数表（单源 = `content/rules/game_config.json`）。

    缺表/坏 JSON → `{}`（域读口不抛）→ 本函数随即抛 `TimeModelConfigError` 点名，
    不让引擎拿到一个编出来的公式。
    """
    from ..catalog_rules import time_model as _read    # 域读口（延迟导入避开装配期环）
    cfg = _read()
    if not isinstance(cfg, dict) or not cfg:
        raise TimeModelConfigError(
            "时间模型未配置：content/rules/game_config.json 的 "
            "formula_skeleton.FORMULA_SKELETON.TIME_MODEL 缺失或为空"
            "（需要 shape / spd_ref / cast 三个键）"
        )
    return cfg


def action_base(action: str) -> float:
    """行动类别 → 基准耗时（`action_base_fn` 供体）。

    类别名集合与数值都在数据表 `cast` 段（通用键：attack/skill/defend/item…）。
    未声明的类别 → 回落 `DEFAULT_ACTION` 项；`cast` 里连默认项都没有 → 点名报错。
    """
    cfg = time_model()
    cast = cfg.get("cast")
    if not isinstance(cast, dict) or not cast:
        raise TimeModelConfigError(
            "时间模型缺少 cast 段（行动类别 → 基准耗时）：formula_skeleton.TIME_MODEL.cast"
        )
    key = action or DEFAULT_ACTION
    val = cast.get(key)
    if val is None:
        val = cast.get(DEFAULT_ACTION)
    if val is None:
        raise TimeModelConfigError(
            "时间模型 cast 段缺少默认项 %r：formula_skeleton.TIME_MODEL.cast" % DEFAULT_ACTION
        )
    return float(val)


def recover_base(action: str) -> float:
    """行动类别 → **第二段**基准耗时（`recover_base_fn` 供体）。

    与 `action_base` 同口径，只是读 `recover` 段：「没有第二段」= 该段显式写 0.0。
    """
    cfg = time_model()
    rec = cfg.get("recover")
    if not isinstance(rec, dict) or not rec:
        raise TimeModelConfigError(
            "时间模型缺少 recover 段（行动类别 → 第二段基准耗时）："
            "formula_skeleton.TIME_MODEL.recover（「无第二段」= 显式写 0.0）"
        )
    key = action or DEFAULT_ACTION
    val = rec.get(key)
    if val is None:
        val = rec.get(DEFAULT_ACTION)
    if val is None:
        raise TimeModelConfigError(
            "时间模型 recover 段缺少默认项 %r：formula_skeleton.TIME_MODEL.recover" % DEFAULT_ACTION
        )
    return float(val)


def _seg_shape(cfg: dict, seg: str) -> str:
    """取某一段的形状：`<seg>_shape` 有值则用它（该段独立形状），否则回落全局 `shape`。"""
    if seg:
        v = cfg.get(seg + "_shape")
        if v:
            return str(v).strip().lower()
    return str(cfg.get("shape") or "").strip().lower()


def recover_time(spd: int, base: float) -> float:
    """一次行动的**第二段**耗时（游戏秒，`recover_model_fn` 供体）。

    形状 = `recover_shape`（缺省回落 `shape`）—— 给 `"flat"` 即「收招不吃速度」。
    """
    cfg = time_model()
    return _scaled(spd, base, cfg, _seg_shape(cfg, "recover"))


def action_time(spd: int, base: float) -> float:
    """**第一段**行动耗时（游戏秒，`time_model_fn` 供体）。

    `shape` 的**通用能力**（下面是三种形状的分发器）归内容侧构造点；
    引擎只调 `fn(spd, base)`，不认识 sqrt/linear/flat 任何一个词。
    """
    cfg = time_model()
    return _scaled(spd, base, cfg, _seg_shape(cfg, ""))


def _scaled(spd, base: float, cfg: dict, shape: str) -> float:
    """按形状折算 base（三种 shape 的**唯一**分发点；第一段 / 第二段共用）。"""
    if shape not in ("sqrt", "linear", "flat"):
        raise TimeModelConfigError(
            "时间模型 shape 未支持：%r（支持 sqrt / linear / flat）" % (shape,)
        )
    _ref = cfg.get("spd_ref")
    if shape != "flat":
        if _ref is None:
            raise TimeModelConfigError("时间模型 shape=%s 缺少 spd_ref" % shape)
        _ref = float(_ref)
        if _ref <= 0:
            raise TimeModelConfigError("时间模型 spd_ref 必须为正数（实得 %r）" % (_ref,))
    try:
        s = max(float(spd or 0), 1.0)
    except (TypeError, ValueError):
        s = 1.0
    cap = cfg.get("spd_cap")
    if cap:
        s = min(s, float(cap))
    if shape == "flat":
        return float(base)
    if shape == "linear":
        return float(base) * (_ref / s)
    return float(base) * math.sqrt(_ref / s)
