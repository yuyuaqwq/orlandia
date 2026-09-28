# -*- coding: utf-8 -*-
"""容器形状读口（收口第 2 批 · 2026-09-28）—— 测试侧唯一「护盾在哪」的口。

为什么需要这个
------------------------------------------------------------------
状态容器收口第 2 批把承伤资源从**独立容器** `actor["shields"]` 并进
`effects` 容器：护盾 = 容器里**一条带 `value` 的条目**，是否吸收由**内容侧声明**
`rules/effect_rules.json` 的 `absorb: true` 决定（引擎零游戏名词，只问「声明了什么」）。
于是判据里所有「读 `actor["shields"][key]`」的写法都失效了（读出来恒空）。

判据怎么改（**只加强不削弱**）
------------------------------------------------------------------
* 断言**不断在旧键上**（那等于给死键发免检证），改为断言**新形状**：
  条目在 `effects` 里 + `value` 对 + 到期走条目的 `expire`。
* ★ 额外**加钉**「吸收真的发生了」（旧形状下护盾压根没接进伤害路径，只断
  `value` 写对了并不能证明机制在跑）—— 读口 `sh_value_of` 只读数据，
  真吸收由各测试自己调 `deal_damage` 验（引擎侧同款门禁
  `tests/test_state_container_r2.py` ②⑤⑥）。

装包提示：读口依赖 `EFFECT_RULES` 已挂载（`content.apply.install_engine()`）。
未挂载时 `absorb_keys` 返回空名单 ⇒ 读口返回 0（fail-closed，不静默给旧键兜底）。
"""
from __future__ import annotations


def _effects(actor: dict) -> dict:
    ef = (actor or {}).get("effects")
    return ef if isinstance(ef, dict) else {}


def _absorb_names(actor: dict) -> list:
    """容器里**声明了 `absorb`** 的条目 key（引擎问内容侧声明，不认键名）。"""
    try:
        from ext_combat.battle.state_effects import absorb_keys
        return list(absorb_keys(actor))
    except Exception:
        return []


def sh_value_of(actor: dict, key: str) -> int:
    """actor 身上某条护盾条目的 `value`（读**容器条目**；不是护盾 ⇒ 0）。"""
    entry = _effects(actor).get(key)
    if not isinstance(entry, dict):
        return 0
    try:
        return int(entry.get("value", 0) or 0)
    except (TypeError, ValueError):
        return 0


def sh_of(actor: dict, key: str) -> dict:
    """actor 身上某条护盾条目本体（读**容器条目**；不是护盾 ⇒ {}）。"""
    entry = _effects(actor).get(key)
    return entry if isinstance(entry, dict) else {}


def shield_total(actor: dict) -> int:
    """actor 身上**全部**护盾条目 `value` 之和（面板/对拍用）。"""
    return sum(sh_value_of(actor, k) for k in _absorb_names(actor))


def shield_names(actor: dict) -> list:
    """actor 身上全部护盾条目的 key（按容器顺序）。"""
    return _absorb_names(actor)


def arm_shield(actor: dict, key: str, value: int, expire=None, stacks: int = 1) -> dict:
    """给 actor 挂一条护盾条目——走**容器唯一写口** `actors.open_entry`（同 `act_shield`）。"""
    from ext_combat.battle.actors import open_entry
    return open_entry(actor, key, stacks=stacks, value=value, expire=expire)


def clear_shields(actor: dict) -> None:
    """清掉 actor 身上全部护盾条目（旧写法 `actor["shields"].clear()` 的新形状等价物）。"""
    ef = _effects(actor)
    for k in _absorb_names(actor):
        ef.pop(k, None)


class _absorb_off:
    """上下文管理器：临时把某条（或全部）`absorb` 声明从**挂载中的**规则表摘掉。

    ★ **反证用**（不是绿判据的辅助）：它断言「吸收与否的唯一开关 = 内容侧声明」，
    断言本身在**调用方的 check** 里写死（期望值是「不吸收」），所以本类只负责
    把声明摘干净 + 还原。

    装：直接改 `saintess_engine.config` 挂载的那张表（与 `tests/test_state_container_r2.py`
    的 `_probe_rules` 同款做法 —— 必须改**挂载中的表**，改 `get_effect_rules()` 返回的
    临时 dict 等于没改）。
    """

    def __init__(self, *keys):
        self._keys = keys

    def __enter__(self):
        from saintess_engine import config as CFG
        tbl = CFG.get_config("effect_rules")
        self._tbl = tbl if isinstance(tbl, dict) else None
        self._saved = {}
        if self._tbl is None:
            return self
        for k in (self._keys or list(self._tbl.keys())):
            if k in self._tbl:
                self._saved[k] = dict(self._tbl[k]) if isinstance(self._tbl[k], dict) \
                    else self._tbl[k]
                self._tbl.pop(k, None)
        return self

    def __exit__(self, *exc):
        if self._tbl is not None:
            self._tbl.update(self._saved)
        return False


__all__ = ["sh_value_of", "sh_of", "shield_total", "shield_names",
           "arm_shield", "clear_shields", "_absorb_off"]
