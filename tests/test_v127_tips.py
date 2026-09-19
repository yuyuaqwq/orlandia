# -*- coding: utf-8 -*-
"""v127 提示库数据驱动测试：TIPS 结构合规 + _tip 随机抽取行为。

覆盖：
1. TIPS 表结构：58 分类全部非空、每条 ≤20 字、无重复条目
2. common 兜底存在
3. _tip(cat) 返回带 💡 前缀且是池内条目；未知 key 回退 common 不崩
4. 所有命令层 _tip("key") 调用点使用的 key 都在 TIPS 中（防传错 key 静默回退）
"""
import os
import re
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ["GWEN_GAME_DB"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_tips.db")

from _engine_harness import C
from _engine_harness import Main as CommandBase  # 原 game.commands.base.CommandBase 壳 → 测试侧驱动口
# `_tip` 的提示池经 `HostShell._tip_pool_map()` → 包内 `cmds_base_rules.TIP_POOL`
# 取件，必须有已装配的包对象（`HostShell.__new__` 的裸实例没有 `_pkg` ⇒ AttributeError）。
from _engine_harness import harness as _harness  # noqa: E402
from _check import bind_check

_h = _harness()
# 终态扫描根：命令实现体在包内 `content/**`（旧 `game/commands/**` 已薄壳化）
PKG_ROOT = os.path.dirname(os.path.abspath(_h.facade.__file__))

FAILS = []


# ★ 审计 P0-1 单源化：断言助手唯一实现 = tests/_check.py
#   （原先本文件手抄一份 def check；差异项已作为 bind_check 参数写出）
check = bind_check(globals(), failures="FAILS")


def _scan_multi_tip():
    """v127.1 防回归：同函数内相同 key 的 _tip 调用 >1 = 面板堆叠多条提示。
    互斥分支白名单：craft/quest_branch 三分支/camp_task/camp_shop。
    """
    import ast as _ast
    root = PKG_ROOT
    allowed = {
        # v127.1 实测互斥分支：每次只走其一，允许同 key 多调用点（终态 = 包内文件名）
        ("economy_cmds.py", "craft"),
        ("world_cmds.py", "_complete_side_quest"),
        ("world_cmds.py", "camp_task"),
        ("world_cmds.py", "camp_shop"),
        ("instance_cmds.py", "_instance_map_view"),   # 通关分支 vs 正常视图
        ("player_cmds.py", "leaderboard"),            # 战力榜 vs 等级榜
    }
    bad = []
    for dirpath, dirnames, filenames in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            tree = _ast.parse(open(os.path.join(dirpath, fn), encoding="utf-8").read())
            for node in _ast.walk(tree):
                if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    continue
                if (fn, node.name) in allowed:
                    continue
                calls = {}
                for sub in _ast.walk(node):
                    if isinstance(sub, _ast.Call) and isinstance(sub.func, _ast.Attribute) \
                            and sub.func.attr in ("_tip", "_rand_tip") and sub.args \
                            and isinstance(sub.args[0], _ast.Constant):
                        calls.setdefault(sub.args[0].value, []).append(sub.lineno)
                for key, lines in calls.items():
                    if len(lines) > 1:
                        bad.append(f"{rel}:{node.name} {key!r} x{len(lines)} @{lines}")
    return bad

def _check_one_tip_per_panel():
    bad = _scan_multi_tip()
    check("每面板同一分类最多 1 条提示", not bad, f"{bad}")


def main():
    tips = C.TIPS
    # 1. 结构
    check("TIPS 分类数≥50", isinstance(tips, dict) and len(tips) >= 50, f"actual={len(tips)}")
    check("common 存在", "common" in tips)
    total = 0
    for k, items in tips.items():
        check(f"分类 {k} 非空", isinstance(items, list) and len(items) >= 3, f"len={len(items) if isinstance(items,list) else 'NA'}")
        if not isinstance(items, list):
            continue
        total += len(items)
        for it in items:
            check(f"{k} 条目≤20字", len(it) <= 20, f"{len(it)}字: {it}")
        check(f"{k} 无重复", len(set(items)) == len(items), f"dup={[x for x in set(items) if items.count(x)>1]}")
    print(f"  总条数: {total}")

    # 2. _tip 行为
    cb = CommandBase(None)
    for k in ("bag", "shop", "common"):
        t = cb._tip(k)
        pool = tips.get(k) or tips["common"]
        check(f"_tip({k}) 带回💡前缀", t.startswith("💡 "))
        check(f"_tip({k}) 是池内条目", t[2:] in pool, f"got={t}")
    t = cb._tip("no_such_key_xyz")
    check("_tip(未知key) 回退common", t[2:] in tips["common"], f"got={t}")
    # 随机性：同 key 抽 20 次至少出现 2 种
    seen = {cb._tip("bag") for _ in range(30)}
    check("_tip 随机抽取", len(seen) >= 2, f"seen={len(seen)}")

    # 3. 命令层调用点 key 全部存在于 TIPS（防传错 key 静默回退）
    root = PKG_ROOT
    used_keys = set()
    for dirpath, dirnames, filenames in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            src = open(p, encoding="utf-8").read()
            for m in re.finditer(r'(?:self\._tip|world\._tip|_rand_tip)\(\s*["\']([a-z_]+)["\']', src):
                used_keys.add(m.group(1))
    missing = used_keys - set(tips.keys())
    check(f"命令层 key 全部在 TIPS（used={len(used_keys)}）", not missing, f"missing={missing}")

    # 4. item_templates 用 _rand_tip 的 key 同样覆盖
    _check_one_tip_per_panel()
    print(f"\n总计: {sum(1 for _ in FAILS)} 失败 / 全部检查完成")
    if FAILS:
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
