# -*- coding: utf-8 -*-
"""P2 并发/重入补强：store 层线程并发读取 + RLock 重入不死锁 + 物品增删边界

基于现有代码行为（不依赖未落地的原子性修复）：

1) RLock 重入不死锁 —— connection.py:18-20 注释记录 v105 M01#11 死锁修复：
   get_player 读档惰性升级会在锁内再调 title_bonus / check_player_level_up，
   它们又各自调用 get_stats/get_quests/get_inventory/get_achievements 等 store
   函数（再次获取 _lock）。本测试构造 exp 足够触发惰性升级的玩家，验证该锁内嵌套
   store 调用路径不抛异常、不死锁、正确升级。
2) 线程并发读：多线程同时 get_player/add_item/remove_item 同一玩家——单进程 RLock
   串行化是设计如此，测试目标是"不崩、数据一致"。
3) remove_item 不存在物品 → 返回 False 且不抛异常。
4) add_item 负数/零 count 的当前行为记录（若当前写入负 count 属审计发现的问题，
   由 F1 修复——本测试只记录现状并按"不抛异常"软断言，注明待 F1 修复后翻转）。
"""
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("GWEN_GAME_DB", os.path.join(HERE, "test_store_concurrency.db"))
sys.path.insert(0, HERE)
from conftest import db, clean_db, make_player  # noqa: E402

_passed = _failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print("  ✅ %s" % name)
    else:
        _failed += 1
        print("  ❌ %s %s" % (name, detail))


def main():
    clean_db()

    # ============ 1) RLock 重入不死锁：惰性升级路径 ============
    print("【RLock 重入：get_player 锁内惰性升级 + 嵌套 store 调用】")
    make_player("g1", "q1", "格温", "战士", level=2)
    # exp 远超 exp_to_next(2)（=60*2^1.45+50≈647），触发 get_player 惰性升级多条 store 嵌套
    db.update_player("g1", "q1", exp=5000)
    try:
        p = db.get_player("g1", "q1")  # 内部 title_bonus→get_stats/get_quests/get_reputation/get_achievements，全部重新取 _lock
        check("get_player 惰性升级路径不抛异常、不死锁", p is not None, str(p)[:80])
        check("惰性升级已生效（level>2）", p["level"] > 2, "level=%s" % p["level"])
    except Exception as e:
        check("get_player (嵌套 store 调用) 不抛异常", False, "异常: %r" % e)

    # 显式锁内再进 store（模拟调用方持锁后调 get_player）
    try:
        with db._lock:
            p2 = db.get_player("g1", "q1")
            inv = db.get_inventory("g1", "q1")
            st = db.get_stats("g1", "q1")
        check("锁内再进 get_player/get_inventory/get_stats 不死锁", p2 is not None, str(None))
    except Exception as e:
        check("锁内再进 store 不死锁", False, "异常: %r" % e)

    # ============ 2) 线程并发读：get_player/add_item/remove_item ============
    print("【线程并发：多线程同时读写同一玩家】")
    g, q = "g1", "q2"
    db.create_player(g, q, "并发", "cls_zhan_shi", {}, 100, 100)
    N_THREADS = 4
    ADD_PER = 10  # 每线程每轮向同一堆叠材料 +10
    ITERS = 20    # 每线程重复轮数
    errors = []
    barrier = threading.Barrier(N_THREADS)

    def worker():
        try:
            barrier.wait()  # 尽量同时起跑，放大竞争
            for _ in range(ITERS):
                db.get_player(g, q)                # 并发读
                db.add_item(g, q, "mat_lang_pi", {"name": "狼皮", "type": "材料", "stackable": True}, count=ADD_PER)
                db.remove_item(g, q, "eq_not_exist")  # 不存在物品：应返回 False 不抛
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    expected_total = ADD_PER * N_THREADS * ITERS
    check("并发线程无一抛异常", not errors, "errors: %r" % errors[:3])
    total = db.count_item(g, q, "mat_lang_pi")
    check("并发 add_item 数量一致 (=%d)" % expected_total,
          total == expected_total, "实际 count=%s" % total)
    check("并发后 get_player 仍正常", db.get_player(g, q) is not None)

    # ============ 3) remove_item 不存在物品 → False ============
    print("【remove_item 不存在】")
    try:
        r = db.remove_item("g1", "q3", "mat_bu_cun_zai", 5)
        check("remove_item 不存在返回 False 且不抛", r is False, "返回=%r" % r)
    except Exception as e:
        check("remove_item 不存在不抛", False, "异常: %r" % e)

    # ============ 4) add_item 负数/零 count 现状记录 ============
    # 注：并行 Agent(F1) 已在 inventory.py:45 落地"非法数量拒绝"（count<=0 直接 return False）。
    # 当前代码行为 = 负数/零 count 不写库、返回 False。审计报告原记录"会写入负 count"的
    # 问题已被 F1 修复。本段按当前行为断言（若未来回归成可写负 count，应在此暴露）。
    print("【add_item 负数/零 count：当前行为（F1 已加拒绝守卫）】")
    r0 = db.add_item("g1", "q4", "mat_zero_test", {"name": "零测试", "type": "材料", "stackable": True}, count=0)
    z = db.count_item("g1", "q4", "mat_zero_test")
    check("add_item(count=0) 返回 False", r0 is False, "返回=%r" % r0)
    check("add_item(count=0) 不写入库存(count=0)", z == 0, "count_item=%s" % z)

    rn = db.add_item("g1", "q5", "mat_neg_test", {"name": "负测试", "type": "材料", "stackable": True}, count=-5)
    n = db.count_item("g1", "q5", "mat_neg_test")
    check("add_item(count=-5) 返回 False", rn is False, "返回=%r" % rn)
    check("add_item(count=-5) 不写入负 count(count=0)", n == 0, "count_item=%s" % n)

    # 清理私有库文件
    tmp = db.DB_PATH
    for f in (tmp, tmp + "-journal", tmp + "-wal", tmp + "-shm"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    print("\n结果: %d 通过, %d 失败" % (_passed, _failed))
    return _failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
