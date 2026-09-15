# -*- coding: utf-8 -*-
"""store 层 · 统计族：feedback / stats / world_event / bestiary

验证意见反馈、击杀统计、世界事件、图鉴（ID 存储+名字字段）的落库。
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, make_player

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
    clean_db()
    make_player("g1", "q1", "格温", "战士")

    print("【store·统计族：feedback】")
    db.add_feedback("g1", "q1", "测试意见")
    fb = db.get_feedback()
    row0 = dict(fb[0]) if fb and hasattr(fb[0], "keys") else (fb[0] if fb else {})
    check("feedback 入库且 status=new", len(fb) >= 1 and row0.get("status") == "new", str(row0)[:120])

    print("【store·统计族：world_event】")
    db.save_world_event("test_event", int(time.time()) + 3600, {"event": "test"})
    we = db.get_world_event()
    we_dict = we if isinstance(we, dict) else (we[0] if we else {})
    check("world_event 存取", isinstance(we_dict, dict) and we_dict.get("etype") == "test_event", str(we)[:120])

    print("【store·统计族：stats】")
    db.init_stats("g1", "q1")
    db.bump_stats("g1", "q1", kills=1)
    st = db.get_stats("g1", "q1")
    check("stats 累计", st.get("kills", 0) >= 1, str(st)[:120])

    print("【store·统计族：bestiary 图鉴】")
    db.bump_bestiary("g1", "q1", "野狗")
    db.bump_bestiary("g1", "q1", "野狗")
    be = db.get_bestiary("g1", "q1")
    check("图鉴 kills 累计（ID 存储+名字字段）",
          any(b["monster"] == "m_wild_dog" and b["name"] == "野狗" and b["kills"] == 2 for b in be),
          str(be)[:150])

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
