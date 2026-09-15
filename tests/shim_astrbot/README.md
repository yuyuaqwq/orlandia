# tests/shim_astrbot —— AstrBot 平台适配层替身（测试专用，v117.5）

## 定位
游戏命令层（`game/commands/*.py`、`main.py`）import 的 astrbot 符号，经审计全部是：
**注册副作用装饰器（返回原函数）+ 类型标注 + 简单数据类**。本目录提供行为等价的
轻量替身，让测试进程跳过真实 astrbot SDK import（约 3s/进程，链：`astrbot.api →
core.star/provider → google.genai + openai`）。

效果：全量回归 149 文件 ~105s → **~27s**（并行 8 路）；单文件 5s → 0.6s。

## 注入方式（自动，无需手动配置）
1. **runner**：`scripts/run_all_tests.py` 子进程 env 自动把本目录加入 PYTHONPATH
   （覆盖全部测试文件，含不 import conftest 的）；`--real-astrbot` 可退回真实 astrbot 对照。
2. **conftest**：`tests/conftest.py` 顶部在 import main 之前把本目录插入 sys.path，
   手动单跑 `python tests/test_xxx.py` 同样提速；设 `GWEN_NO_SHIMMED_ASTRBOT=1` 退回真实。

## 行为等价原则（必须遵守）
替身语义照抄 astrbot 真实现（site-packages 同路径文件）：
- `@filter.regex / @filter.custom_filter`：注册到 `star_handlers_registry`，**返回原函数**；
  直接调用 handler 不经 filter 检查（与真实一致）。
- `star_handlers_registry`：`_handlers` 列表 + `get_handler_by_full_name` 去重。
- `MessageChain`：`chain` 列表 + `.message()` 返回 self；`Plain/Node/Nodes` 字段类。
- `CustomFilter`：`__init__(raise_error=True)` + `filter(event, cfg)`。
- `star.Star / star.Context`：空基类（`Main.__init__` 不调 super，仅标注）。

## 对照验证（改 shim 后必做）
任选代表文件，两种模式结果必须一致：
```bash
# 真实模式
GWEN_NO_SHIMMED_ASTRBOT=1 python tests/test_commands_battle.py
# shim 模式
python tests/test_commands_battle.py
```
全量对照：`python scripts/run_all_tests.py --serial --real-astrbot`（~9 分钟，仅大改后抽查）。

## 已知边界
- 真实 astrbot 的「插件加载时 handler 被 partial 包装」在本替身下不存在——`base.py
  _find_handler` 已兼容（isinstance 判断 + 静态表回退）。
- 测试不直接 import astrbot（审计确认），运行时接触点仅 registry 遍历 / MessageChain
  构造 / stop_event，均已覆盖验证。
- 生产环境（真实 AstrBot 进程）绝不加载本替身——只有测试进程的 PYTHONPATH 会命中它。
