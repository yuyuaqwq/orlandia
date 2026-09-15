# -*- coding: utf-8 -*-
"""v59 换行指令修复：『意见』等 13 个 (?:.*)$ 收尾正则不匹配换行，
   消息带 \n 就触发不了 → 统一改 (?:[\s\S]*)$ 支持多行内容。"""
import sys, os, re, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 装饰器扫描：统一走 tests/_cmd_registry.py（@filter.regex 字面量 + @declared 声明都认）
from _cmd_registry import pattern_map  # noqa: E402

handlers = [(pat, name) for name, pat in pattern_map().items()]

passed = 0
def check(name, cond, detail=""):
    global passed
    assert cond, f"{name}: {detail}"
    passed += 1
    print(f"  ✓ {name}")

def test_no_dotstar():
    print("【正则库无 .* 收尾（换行杀手）】")
    bad = []
    for pat, name in handlers:
        if re.search(r"\(\?:\.\*\)\$", pat):
            bad.append((name, pat))
    check("无 (?:.*)$ 收尾正则", len(bad) == 0, str(bad))

def test_newline_trigger():
    print("【带换行消息可触发】")
    # 意见：核心修复
    pat_fb = next(p for p, n in handlers if n == "feedback_cmd")
    check("意见+换行触发", re.match(pat_fb, "意见 第一行\n第二行") is not None, pat_fb)
    check("意见+换行开头触发", re.match(pat_fb, "意见\n换行开头") is not None)
    # 其余改过正则的指令（抽查）
    pat_map = {n: p for p, n in handlers}
    for name, word in [("craft", "锻造 铁剑\n备注"), ("item_detail", "物品详情 铁剑\n看属性"),
                       ("skill", "技能 1\n继续"), ("instance_cmd", "副本\n组队")]:
        if name in pat_map:
            r = re.match(pat_map[name], word)
            check(f"{name} 换行触发", r is not None, f"{name}: {pat_map[name]}")

def test_no_conflict():
    print("【多行内容不产生双触发】")
    # 意见带换行只命中 feedback_cmd，不误伤其他
    pat_fb = next(p for p, n in handlers if n == "feedback_cmd")
    msg = "意见 测试\n内容"
    # `_maint_gate`（停服全局 gate）匹配所有消息，不参与指令互斥 → 显式剔除
    # （与 test_v87_command_matrix / test_v104 同口径）
    hits = [n for p, n in handlers if n != "_maint_gate" and re.match(p, msg)]
    check("意见换行只命中 feedback_cmd", hits == ["feedback_cmd"], str(hits))

if __name__ == "__main__":
    test_no_dotstar()
    test_newline_trigger()
    test_no_conflict()
    print(f"\n结果: {passed} 通过, 0 失败")
