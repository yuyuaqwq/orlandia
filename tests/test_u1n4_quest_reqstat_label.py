# -*- coding: utf-8 -*-
"""审计 L4781：`require_stats` 的内部 stats 计数键**直上屏**的判据。

原实现（`content/world_cmds.py::quest_accept`）：

    _rs = sq.get("require_stats") or {}
    _need = ", ".join(f"{k} {v}次" for k, v in _rs.items())
    yield event.plain_result(_T.text("quest.secret", cond=_need))

`require_stats` 的键是 **stats 表列名**（`content/persistence/stats.py::STAT_FIELDS`），
不是玩家词汇 ⇒ 玩家实见「需要 fish_count 10次 后才会出现」。

本判据钉住的是**这一类**（不是单条文案）：

  ① **域侧穷举**： quests.json / weekly_quests.json 里 `require_stats` 出现的**每一个**键
     都必须在 `_STAT_COUNT_CN` 有登记 —— 域里新增键而读口没跟上，本判据当场报红
     （这是「玩家可见文本里不得出现机器键」这条**全仓没有门禁**的补门，审计 §④ 结论）。
  ② **登记的键必须是真源键**： 文案表里的 `stat_count_name.*` 不得凭空多出没被用到的键。
  ③ **真渲染**： 真调文案表 + 真实 `require_stats` 值 ⇒ 断言渲染结果里**不含**机器键形状
     （`xxx_count` 之类的下划线机器名），且含登记的中文名。

**不改判据迁就实现**： ②③ 都由数据真源驱动，改数据就得同批改读口（并被本判据逮到）。
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配（引擎根 + extends）

import content.world_cmds as W  # noqa: E402
from content import texts as _T  # noqa: E402

passed = failed = 0
from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")

_PD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content", "data")


def _require_stats_keys():
    """扫真源域：require_stats 用到的全部键（不写死是哪几条 —— 域里加了本判据要跟上）。"""
    out = {}
    for fn in ("quests.json", "weekly_quests.json"):
        p = os.path.join(_PD, fn)
        if not os.path.isfile(p):
            continue
        raw = json.load(open(p, encoding="utf-8"))
        for qid, q in (raw.items() if isinstance(raw, dict) else []):
            if not isinstance(q, dict):
                continue
            for k, v in (q.get("require_stats") or {}).items():
                out.setdefault(k, []).append((fn, qid, v))
    return out


#: stats 表真源列名（读口不许登记不存在的键）
sys.path.insert(0, os.path.join(_paths.PKG_ROOT, "content"))
from content.persistence import stats as _stats  # noqa: E402

_MACHINE_KEY = __import__("re").compile(r"\b[a-z]+_[a-z_]+\b")


def main():
    used = _require_stats_keys()
    check("真源域里确有 require_stats（本判据不至于空跑）", bool(used), str(used))

    # ---- ① 域侧穷举：域里每个键都必须登记 ----
    for k, hits in sorted(used.items()):
        check("require_stats 键已登记中文名：%s（%d 处）" % (k, len(hits)), k in W._STAT_COUNT_CN, k)

    # ---- ② 登记的键不得凭空多出（不得有不存在的键，也不得有域里没用到的键）----
    for k in sorted(W._STAT_COUNT_CN._keys):
        check("登记键是真实 stats 列名：%s" % k, k in _stats.STAT_FIELDS, k)
        check("登记键被 require_stats 真正用到：%s" % k, k in used, k)

    # ---- ③ 真渲染：真实数据 → 玩家实见文本里不得有机器键 ----
    for k, hits in sorted(used.items()):
        for fn, qid, v in hits:
            need = W._req_stats_label({k: v})     # ★ 真调生产读口（不在测试里重写一遍拼装）
            line = _T.text("quest.secret", cond=need)
            check(
                "渲染无机器键：%s（%s/%s）" % (qid, fn, k),
                not _MACHINE_KEY.search(line),
                line,
            )
            check(
                "渲染含登记的中文名：%s（%s）" % (qid, k),
                W._STAT_COUNT_CN.get(k, k) in line,
                line,
            )

    # ---- 反证：钉住「机器键形状」这条判据保护的东西 ----
    #   原始写法渲染出来确实含机器键 ⇒ 判据不是永真的同义反复。
    _raw = ", ".join(
        "%s %s次" % (k, hits[0][2]) for k, hits in sorted(used.items())
    )
    check(
        "反证：旧写法（直接插键名）确实会被本判据逮到",
        bool(_MACHINE_KEY.search(_raw)),
        _raw,
    )

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
