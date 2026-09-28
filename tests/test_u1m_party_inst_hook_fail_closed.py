# -*- coding: utf-8 -*-
"""审计 L891：`content/party.py::target_in_battle` 的副本判定钩子 fail-closed 判据。

原实现：
    if inst_battle_hook is not None:
        try:
            if inst_battle_hook(group_id, target_qq):
                return "instance"
        except Exception:
            pass
    return None

**真实代价**（不是「少显示一行提示」）：钩子读不到时塌成 `None`，而 `None` 的含义是
「目标不在战斗中」⇒ **正在副本里的人照样能被拉进队伍** —— 调用方
`content/cmds_social.py:348` 拿 `_tb_state` 当放行闸，塌成 None 就等于放行。
副本战斗行存在队长名下，被拉走 ⇒ 原队伍解散 ⇒ **副本僵尸化**
（`cmds_social.py:343-347` 的注释自陈：防的正是「把副本队长/队员拉走」）。

本判据只钉 fail-closed 语义（**不改判据迁就实现**）：
  ① hook 抛 ⇒ 抛（不得静默当成「不在战斗中」）
  ② 异常原因为 `__cause__` 保住（诊断链不丢）
  ③ 正常路逐字不变：无战斗 → None · 副本中 → "instance" · 不传 hook → None
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 路径装配**走仓内单源** tests/_paths.py（不自己拼 sys.path —— 那会造第二份路径真源）
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配（引擎根 + extends）

import content.party as _P  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


class _NoBattleDB(object):
    """战斗行读不到（正常「不在战斗中」）。"""

    def get_battle(self, gid, qq):
        return None


def main():
    _P.db = _NoBattleDB()
    tib = _P.target_in_battle

    def _hook_none(gid, qq):
        return None

    def _hook_hit(gid, qq):
        return {"state": {"type": "instance"}, "name": "", "updated_at": 0}

    def _hook_raise(gid, qq):
        raise KeyError("存档行读不到")

    # ---- 正常路（逐字不变，回归保护）----
    check("正常·hook 判无战斗 → None", tib("g1", "u1", inst_battle_hook=_hook_none) is None, "")
    check("正常·hook 判副本中 → 'instance'",
          tib("g1", "u1", inst_battle_hook=_hook_hit) == "instance", "")
    check("正常·不传 hook（缺省兜底）→ None", tib("g1", "u1") is None, "")

    # ---- 核心判据：hook 抛必须响亮失败，不得静默当成「不在战斗中」----
    try:
        got = tib("g1", "u1", inst_battle_hook=_hook_raise)
    except Exception as e:
        check("hook 抛 → 抛（不静默放行拉人）", True, "")
        check("异常类型可辨（RuntimeError 而非裸吞）",
              type(e).__name__ == "RuntimeError", type(e).__name__)
        check("异常信息点名 hook 读不到",
              "inst_battle_hook" in str(e), str(e)[:80])
        check("原异常留在 __cause__（诊断链不丢）",
              isinstance(getattr(e, "__cause__", None), KeyError),
              repr(getattr(e, "__cause__", None)))
    else:
        check("hook 抛 → 抛（不静默放行拉人）", False, f"却返回了 {got!r}（= 静默当成不在战斗中）")
        check("异常类型可辨（RuntimeError 而非裸吞）", False, "未抛")
        check("异常信息点名 hook 读不到", False, "未抛")
        check("原异常留在 __cause__（诊断链不丢）", False, "未抛")

    # ---- 反证：塌成 None 会被调用方当放行闸（钉住本判据保护的东西）----
    # 调用方 cmds_social.py:348：`if _tb_state:` 才拦；None ⇒ 不拦 ⇒ 放行。
    _blocked = {"None": True, "instance": True, "battle": True}
    check("调用方闸口径：None 不拦、instance/battle 拦",
          (None not in _blocked) and _blocked.get("instance") and _blocked.get("battle"), "")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
