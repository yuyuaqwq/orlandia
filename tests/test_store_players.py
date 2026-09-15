# -*- coding: utf-8 -*-
"""store 层 · 玩家族：players 档案 + inventory 背包

验证：
  1. create/get/update（属性、技能、快捷指令）
  2. 物品 ID 存储、材料合并、count_item、装备 uuid、remove_item
  3. v46 核心约定：内存用名字，落库转 ID
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
    print("【store·玩家族：players 档案】")
    p = make_player("g1", "q1", "格温", "战士")
    check("create_player 返回 player", p is not None and p["name"] == "格温", str(p)[:100])
    check("class_name 正确", p["class_name"] == "cls_zhan_shi", str(p.get("class_name")))  # v87.17 make_player 走 resolve
    check("level 默认 1", p["level"] == 1, str(p.get("level")))
    db.update_player("g1", "q1", level=5, gold=999)
    p2 = db.get_player("g1", "q1")
    check("update level=5", p2["level"] == 5, str(p2.get("level")))
    check("update gold=999", p2["gold"] == 999, str(p2.get("gold")))
    # 技能存取（v46：内存名字 / 落库 ID）
    # v151 职业重构：旧技能（火球术/冰箭——冰箭已删）读档时被检测为失效技能 → 自动重置清空
    # （读档一次性技能重置：清 learned_skills/skill_levels，skill_spent 返还 skill_points）。
    # 因此验证 v151 重置语义：旧技能被清空 + _v151_skill_reset 标记置位；
    # 用现存的 v151 技能验证读回名字（如 火球术 仍存在）。
    db.update_player("g1", "q1", learned_skills=["火球术", "冰箭"], skill_spent=2, skill_points=1)
    p3 = db.get_player("g1", "q1")
    check("v151 技能重置清空旧技能", p3["learned_skills"] == [], str(p3.get("learned_skills")))
    check("skill_spent 返还 skill_points", p3.get("skill_points") == 1 + 2, str((p3.get("skill_points"), p3.get("skill_spent"))))
    check("重置标记置位", p3.get("_v151_skill_reset") is True, str(p3.get("_v151_skill_reset")))
    # v151 现存技能（挥砍）读回名字——注意：重置只发生一次（_v151_skill_reset 标记），
    # 且 v151 技能按玩家职业校验（战士 火球术 非本职业技能仍会被清）
    db.update_player("g1", "q1", learned_skills=["挥砍"])
    p3b = db.get_player("g1", "q1")
    check("v151 技能读回是名字", p3b["learned_skills"] == ["挥砍"], str(p3b.get("learned_skills")))
    # 快捷指令
    db.update_player("g1", "q1", shortcuts={"1": "探索"})
    p4 = db.get_player("g1", "q1")
    check("shortcuts 存取", p4.get("shortcuts") == {"1": "探索"}, str(p4.get("shortcuts")))

    print("【store·玩家族：inventory 背包】")
    clean_db("inventory")
    db.add_item("g1", "q1", "mat_lang_pi", {"name": "狼皮", "type": "材料", "stackable": True})
    db.add_item("g1", "q1", "狼皮", {"name": "狼皮", "type": "材料", "stackable": True}, count=3)
    inv = db.get_inventory("g1", "q1")
    mat_items = [it for it in inv if it["data"].get("type") in C.MATERIAL_KIND_TYPES]
    check("材料按 ID 合并", len(mat_items) == 1 and mat_items[0]["count"] == 4,
          str([(it["key"], it["count"]) for it in inv]))
    check("count_item(狼皮)=4", db.count_item("g1", "q1", "狼皮") == 4, str(db.count_item("g1", "q1", "狼皮")))
    check("count_item(mat_lang_pi)=4", db.count_item("g1", "q1", "mat_lang_pi") == 4,
          str(db.count_item("g1", "q1", "mat_lang_pi")))
    db.add_item("g1", "q1", "eq_abc123", {"name": "铁皮长剑", "type": "装备", "stackable": False})
    inv2 = db.get_inventory("g1", "q1")
    eqs = [it for it in inv2 if it["key"].startswith("eq_")]
    check("装备 key 保留 uuid", len(eqs) == 1 and eqs[0]["key"] == "eq_abc123", str([it["key"] for it in inv2]))
    db.remove_item("g1", "q1", "eq_abc123")
    inv3 = db.get_inventory("g1", "q1")
    check("remove_item 生效", all(it["key"] != "eq_abc123" for it in inv3))

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
