# -*- coding: utf-8 -*-
"""core 层 · 装备族：装备生成 / 符文强化

验证 affix.generate_equip 与 rune_value / rune_conflict / rune_item（词缀、孔、冲突）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C
from content import affix

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, detail))


def main():
    print("【core·装备族：装备生成】")
    ge = getattr(affix, "generate_equip", None) or getattr(C, "generate_equip", None)
    if ge:
        e = ge("weapon", 10, "blue", "sword")
        check("generate_equip 返回 dict", isinstance(e, dict) and "name" in e, str(e)[:120])
        check("装备有攻击属性", "atk" in e or "stats" in e, str(list(e.keys()))[:80])
        e2 = ge("weapon", 10, "blue", "sword")
        check("同名装备可重复生成", isinstance(e2, dict) and "name" in e2, str(e2)[:80])
    else:
        check("generate_equip 可访问", False, "未暴露")

    print("【core·装备族：符文】")
    rv = getattr(C, "rune_value", None)
    if rv:
        check("rune_value 等级递增", rv("brutal", 3) > rv("brutal", 1), "%s→%s" % (rv("brutal", 1), rv("brutal", 3)))
    else:
        check("rune_value 可访问", False, "未暴露")
    rc = getattr(C, "rune_conflict", None)
    if rc:
        check("rune_conflict 返回 bool", isinstance(rc("burn", "brutal"), bool), str(rc("burn", "brutal")))
    else:
        check("rune_conflict 可访问", False, "未暴露")
    ri = getattr(C, "rune_item", None)
    if ri:
        r = ri("brutal", 2)
        check("rune_item 返回 dict", isinstance(r, dict) and "name" in r, str(r)[:80])
    else:
        check("rune_item 可访问", False, "未暴露")

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
