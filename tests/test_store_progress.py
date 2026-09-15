# -*- coding: utf-8 -*-
"""store 层 · 进度族：quests 任务 + battle_state 战斗状态

验证任务存档（主线/每日/侧线）与战斗状态存取。
"""
import sys, os
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

    print("【store·进度族：quests】")
    db.save_quests("g1", "q1", {"main_quest": "q1", "main_status": "进行中", "main_progress": 1,
                               "daily": {}, "completed_main": [], "side": []})
    q = db.get_quests("g1", "q1")
    check("quests 主线程存取", q.get("main_quest") == "q1" and q.get("main_progress") == 1, str(q)[:120])
    db.save_quests("g1", "q1", {"main_quest": "q1", "main_status": "进行中", "main_progress": 2,
                               "daily": {"d1": {"id": "d1", "progress": 1}}, "completed_main": [], "side": []})
    q2 = db.get_quests("g1", "q1")
    check("quests 进度更新", q2.get("main_progress") == 2, str(q2)[:120])
    check("quests 每日任务存取", q2.get("daily", {}).get("d1", {}).get("progress") == 1, str(q2.get("daily"))[:80])

    print("【store·进度族：battle_state】")
    # v181 P3：save_battle 裸怪调用自动包装 enemies 阵列（存档结构 = 完整 battle state）
    db.save_battle("g1", "q1", {"enemy": "野狗", "hp": 50})
    bs = db.get_battle("g1", "q1")
    st = bs.get("state", bs) if isinstance(bs, dict) else {}
    enem0 = ((st.get("enemies") or [{}])[0]) if isinstance(st.get("enemies"), list) else {}
    check("battle_state 存取", enem0.get("enemy") == "野狗" and enem0.get("hp") == 50, str(bs)[:160])
    db.clear_battle("g1", "q1")
    bs2 = db.get_battle("g1", "q1")
    check("clear_battle 生效", not bs2 or (isinstance(bs2, dict) and not bs2.get("state")), str(bs2)[:80])

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
