# -*- coding: utf-8 -*-
"""data 层 · 生物族：怪物 / 地区怪物 / 怪物技能 / 坐骑 / 宠物 / 世界Boss

验证 ENCY_MONSTER_MAP / ENCY_MAP_MONSTERS / MONSTER_SKILLS / MOUNT / PET / WORLD_BOSS_POOL。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C
# ★ P5E-DELETE（2026-09-15，删壳批）：`_INDEXES` 在包侧是**惰性**的
#   （`content/index.py:92-103`，`_indexes()` 首次访问建一次；`C._INDEXES` 是同一只 dict）。
#   旧宿主门面是装配期渴求态（`game/data/_assembly.py` 建好）⇒ 本文件过去不需要显式建。
#   终态按包侧口径**显式取一次**（`C.resolve` 内部就走 `_indexes()`）。判据与阈值一条未变。
C.resolve("monsters", "野狗")

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
    print("【data·生物族：怪物】")
    check("ENCY_MONSTER_MAP 130 怪物", len(C.ENCY_MONSTER_MAP) >= 100, str(len(C.ENCY_MONSTER_MAP)))
    check("ENCY_MAP_MONSTERS 72 地区", len(C.ENCY_MAP_MONSTERS) >= 50, str(len(C.ENCY_MAP_MONSTERS)))
    check("MONSTER_SKILLS 60 技能", len(C.MONSTER_SKILLS) >= 40, str(len(C.MONSTER_SKILLS)))

    print("【data·生物族：索引双向】")
    mi = C._INDEXES["monsters"]
    check("怪物索引 130 个", len(mi["name_to_id"]) >= 100, str(len(mi["name_to_id"])))
    check("野狗 → m_wild_dog", mi["name_to_id"]["野狗"] == "m_wild_dog")
    check("m_wild_dog → 野狗", mi["id_to_name"]["m_wild_dog"] == "野狗")

    print("【data·生物族：坐骑/宠物】")
    check("MOUNT_BY_KEY 非空", len(C.MOUNT_BY_KEY) > 0, str(len(C.MOUNT_BY_KEY)))
    check("MOUNT_POOL 非空", hasattr(C, "MOUNT_POOL") and len(getattr(C, "MOUNT_POOL", [])) > 0, "MOUNT_POOL")
    check("PET_POOL 非空", hasattr(C, "PET_POOL") and len(getattr(C, "PET_POOL", [])) > 0, "PET_POOL")

    print("【data·生物族：世界Boss】")
    check("WORLD_BOSS_POOL 非空", hasattr(C, "WORLD_BOSS_POOL") and len(getattr(C, "WORLD_BOSS_POOL", [])) > 0,
          "WORLD_BOSS_POOL")

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
