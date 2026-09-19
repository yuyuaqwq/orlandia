# -*- coding: utf-8 -*-
"""v166 商店价格分阶段门禁（economy_lib.shop_scan 模型驱动）

验证：
  1. shop_scan 可跑，6 阶段桶齐全，总行数 > 300
  2. 每阶段有行（配货覆盖 E1-E5；E6 无配货是已知缺口，记 warning 不红）
  3. **anchor_issues 必须为 0**（锚点阶段价格偏离 = 必须修：新手城宰人/出生点过便宜）
  4. stage_issues 仅作 warning 输出（死价格便利品延伸），打印前 20 供人审
  5. 任一改动跑本门禁 = 全绿才能提交（价格/配货改动后回归）

独立运行：python tests/test_numeric_shop_pricing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/（economy_lib 随迁落点）

try:
    import conftest  # noqa: F401  隔离测试库环境
except Exception:
    pass

from economy_lib import shop_scan, ECON_STAGES

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


print("== 商店价格分阶段门禁（economy_lib.shop_scan）==")

scan = shop_scan()

# 1. 基本结构
check("shop_scan 可跑", isinstance(scan, dict), "")
check("总配货行 > 300", scan["total"] > 300, f"got {scan['total']}")
check("6 阶段桶齐全", all(sid in scan["stages"] for sid, *_ in ECON_STAGES),
      str(list(scan["stages"].keys())))

# 2. 每阶段行分布（E1-E5 必须有货；E6 允许空但提示）
for sid, _name, *_rest in ECON_STAGES:
    n = len(scan["stages"].get(sid, {}).get("rows", []))
    if sid == "E6":
        if n == 0:
            print("  ⚠️ E6(毕业期)无商店配货——毕业城缺补给锚点，记观察项（不红）")
            PASS += 1
        else:
            check(f"{sid} 有配货", n > 0, str(n))
    else:
        check(f"{sid} 有配货", n > 0, f"{sid} rows={n}")

# 3. anchor_issues == 0（必须修干净才能提交）
anchors = scan.get("anchor_issues", [])
if anchors:
    print("  ❌ anchor_issues 非空（锚点阶段价格偏离，必须调价）：")
    for x in anchors:
        print(f"    [{x['verdict']}] {x['name']} @ {x['sa']} Lv{x['town_lv']}城 {x['stage']} "
              f"price={x['price']} kills={x['kills']} band={x['band']}")
    FAIL += 1
else:
    PASS += 1
    print("  ✅ anchor_issues == 0（锚点阶段价格全部健康）")

# 4. HIGH（任何阶段卖太贵 = 玩家被宰）都不允许
highs = [x for x in anchors if x.get("verdict") == "HIGH"]
check("无 HIGH（玩家被宰）", len(highs) == 0, str(len(highs)))

# 5. stage_issues 打印供审（warning 不红）
stage_issues = scan.get("stage_issues", [])
print(f"\n== stage_issues（死价格便利品延伸 warning，{len(stage_issues)} 条，不阻塞）==")
for x in stage_issues[:20]:
    print(f"  [{x['verdict']}] {x['name']} @ {x['sa']} Lv{x['town_lv']}城 {x['stage']} "
          f"price={x['price']} kills={x['kills']}")

# 阶段 summary
print("\n== 各阶段偏离汇总 ==")
for sid, _name, *_rest in ECON_STAGES:
    st = scan["stages"].get(sid, {})
    print(f"  {sid}: rows={len(st.get('rows', []))} low={len(st.get('low', []))} high={len(st.get('high', []))}")

print(f"\n结果: PASS {PASS} / FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
