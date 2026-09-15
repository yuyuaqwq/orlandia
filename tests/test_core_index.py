# -*- coding: utf-8 -*-
"""core 层 · 索引族：v46 ID 体系

验证 index.py 的 resolve / display / pinyin_id 双向一致与稳定性。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C
from content import index as core_index

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
    print("【core·索引族：resolve/display】")
    check("resolve 双向一致", C.resolve("monsters", "野狗") == "m_wild_dog")
    check("display 双向一致", C.display("monsters", "m_wild_dog") == "野狗")
    check("resolve 未知名字返回原值", C.resolve("monsters", "不存在的怪物") == "不存在的怪物")

    print("【core·索引族：pinyin_id】")
    pid = getattr(core_index, "pinyin_id", None) or getattr(C, "pinyin_id", None)
    if pid:
        check("pinyin_id(狼皮)=lang_pi", pid("狼皮") == "lang_pi", pid("狼皮"))
        check("pinyin_id 稳定幂等", pid("猛击") == pid("猛击"))
    else:
        check("pinyin_id 可访问", False, "未暴露")

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
