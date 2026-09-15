# -*- coding: utf-8 -*-
"""v95.24 性别系统：注册可选性别（男/女），角色面板显示

验证：
  1. 新格式『注册 <名字> [种族] [性别]』→ 见习 + 性别落库 + 文案显示
  2. 旧格式『注册 <职业> <名字> [种族] [性别]』兼容
  3. 性别/种族顺序可换（『注册 格温 女 精灵』）
  4. 只给性别（『注册 格温 男』）→ 种族默认人类
  5. 未知性别/种族报错
  6. 存量档（无性别）角色面板不显示性别、不崩
  7. 角色面板显示性别
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)

    print("【1. 新格式带性别：注册 格温 女】")
    out = await cmd(m, "register", "g1", "w1", "注册 格温 女")
    check("注册成功", "欢迎来到奥兰迪亚大陆" in out, out[:200])
    check("文案显示性别", "♀ 女" in out, out[:300])
    p = db.get_player("g1", "w1")
    check("gender=female", p.get("gender") == "female", str(p.get("gender")))
    check("见习职业", p["class_name"] == "cls_novice", p.get("class_name", ""))
    check("种族默认人类", p.get("race") == "human", str(p.get("race")))

    print("【2. 新格式种族+性别：注册 小芽 精灵 男】")
    out = await cmd(m, "register", "g1", "w2", "注册 小芽 精灵 男")
    check("注册成功", "欢迎来到奥兰迪亚大陆" in out, out[:200])
    p = db.get_player("g1", "w2")
    check("gender=male", p.get("gender") == "male", str(p.get("gender")))
    check("race=elf", p.get("race") == "elf", str(p.get("race")))
    check("文案显示种族", "银月精灵" in out, out[:300])
    check("文案显示性别", "♂ 男" in out, out[:300])

    print("【3. 性别/种族顺序互换：注册 小丽 女 精灵】")
    out = await cmd(m, "register", "g1", "w3", "注册 小丽 女 精灵")
    p = db.get_player("g1", "w3")
    check("gender=female", p.get("gender") == "female", str(p.get("gender")))
    check("race=elf", p.get("race") == "elf", str(p.get("race")))

    print("【4. 旧格式带性别：注册 战士 勇者 人类 男】")
    out = await cmd(m, "register", "g1", "w4", "注册 战士 勇者 人类 男")
    check("注册成功", "职业：🛡️ 战士" in out or "战士" in out, out[:200])
    p = db.get_player("g1", "w4")
    check("职业=战士", p["class_name"] == "cls_zhan_shi", p.get("class_name", ""))
    check("race=human", p.get("race") == "human", str(p.get("race")))
    check("gender=male", p.get("gender") == "male", str(p.get("gender")))

    print("【5. 旧格式无种族带性别：注册 法师 小红 女】")
    out = await cmd(m, "register", "g1", "w5", "注册 法师 小红 女")
    p = db.get_player("g1", "w5")
    check("职业=法师", p["class_name"] == "cls_fa_shi", p.get("class_name", ""))
    check("gender=female", p.get("gender") == "female", str(p.get("gender")))
    check("race 默认人类", p.get("race") == "human", str(p.get("race")))

    print("【6. 无性别注册被拒（v95.26 性别强制）】")
    out = await cmd(m, "register", "g1", "w6", "注册 路人甲")
    check("报错含性别提示", "请选择性别" in out, out[:200])
    p = db.get_player("g1", "w6")
    check("未建角色", p is None, "should be None")

    print("【7. 未知性别报错】")
    out = await cmd(m, "register", "g1", "w7", "注册 阿猫 猫")
    check("报未知提示", "未知种族或性别" in out, out[:200])
    p = db.get_player("g1", "w7")
    check("未建角色", p is None, "should be None")

    print("【8. 角色面板显示性别】")
    out = await cmd(m, "profile", "g1", "w2", "角色")
    check("面板显示男", "♂ 男" in out, out[:300])
    out = await cmd(m, "profile", "g1", "w1", "角色")
    check("面板显示女", "♀ 女" in out, out[:300])

    print("【9. 存量档无性别：面板不崩不显示】")
    # 直接建一个无 gender 的旧档（绕过注册）
    db.create_player("g1", "w8", "旧人", "cls_zhan_shi", {}, 150, 50)
    p = db.get_player("g1", "w8")
    check("旧档 gender 默认空", not p.get("gender"), str(p.get("gender")))
    out = await cmd(m, "profile", "g1", "w8", "角色")
    check("面板正常", "Lv.1" in out, out[:200])
    check("无性别行", "性别：" not in out, out[:300])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    import asyncio
    asyncio.new_event_loop().run_until_complete(main())
