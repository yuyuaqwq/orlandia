# -*- coding: utf-8 -*-
"""包内测试共享脚手架（conftest）—— 包仓自包含版。

所有新测试从这里 import 公共设施，禁止再手抄 FakeEvent/run 模板：
    from conftest import FakeEvent, run, clean_db, make_player, TEST_DB, PLUGIN_DIR

- 自动设置 GWEN_GAME_DB → 独立测试库（绝不触碰生产 game_data.db）
- 路径装配交给 `tests/_paths.py`（**唯一**发现点）：
    包根      = 本文件所在目录（tests/）的上一级
    引擎根    = GWEN_FRAMEWORK_DIR 优先 → 否则 ../framework · ../framework-engine · ./framework
                → 都找不到 → ★ 醒目报错（打印缺什么、试过哪些候选），不许静默 SKIP 装绿
    宿主壳根  = 引擎根所在部署树的 `host/`（平台驱动面，见 tests/_engine_harness.py）
    再装 shim_astrbot（平台适配层替身；GWEN_NO_SHIMMED_ASTRBOT=1 退回真实 astrbot）
- 取件口 = 包内真源 + 引擎通道（`tests/_engine_harness.py`）：
    `C`  = 包内聚合门面 `content/facade.py::C`
    `db` = 包内存档半边 `content/persistence`
    `Main` = 测试侧驱动口（终态宿主壳 + 引擎通道派发）
"""
import os
import sys
import asyncio
import sqlite3

# ---- 路径（装配本体在 tests/_paths.py；此处只给包内测试的默认库与测试模式）----
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(TESTS_DIR)                     # 包仓根
TEST_DB = os.path.join(PLUGIN_DIR, "test_game_data.db")

# 必须在 import 包/引擎前设置（存档层模块级读句柄）
# R3 P3-4：setdefault 尊重测试脚本预置的独立私有库（test_v95_76/77 等用
# 各自 test_<名>.db），不再强制覆盖——消除共享 test_game_data.db 顺序执行
# 残留导致的偶发红（v95_77 曾在 line 48 因残留 battle 为 None 崩）
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
# v110.5 X3：显式测试模式标记——dialogue.check_need 据 GWEN_TEST_MODE=1 在测试环境
# 对未知条件键直接 raise（与库名含 "test" 的旧约定双保险，消除私有库名不含 "test"
# 时测试行为漂移导致的假失败）。
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, TESTS_DIR)                               # tests/（_paths / _engine_harness）

# v117.5 测试提速：shim astrbot（平台适配层替身，行为等价，省 ~3s/进程 import）。
# 游戏命令层用到的 astrbot 符号都是注册副作用装饰器+类型标注+简单数据类，
# 见 tests/shim_astrbot/README.md。设 GWEN_NO_SHIMMED_ASTRBOT=1 退回真实 astrbot（对照验证用）。
if os.environ.get("GWEN_NO_SHIMMED_ASTRBOT") != "1":
    _SHIM_DIR = os.path.join(TESTS_DIR, "shim_astrbot")
    if os.path.isdir(_SHIM_DIR) and _SHIM_DIR not in sys.path:
        sys.path.insert(0, _SHIM_DIR)

# ★ 取件口：包内真源 + 引擎通道（`tests/_engine_harness.py`）。
#   路径装配（包根 / 引擎根 / 宿主壳根）已由 `tests/_paths.py` 在 import 本模块时完成；
#   引擎根缺失时 `_paths` **醒目报错**（不静默 SKIP）。
from _engine_harness import C, db, Main                       # noqa: E402,F401
from _engine_harness import QQBOT_DIR                         # noqa: E402,F401  宿主壳根（部署树根）
_CONFTEST_FACE = "pkg-engine-harness"


# v94 体力：测试环境走 register 命令建号（不走 make_player）时，注册后体力拉满，
# 防动作类命令（探索/战斗/锻造/开本等）被体力拦截导致测试误挂。
# （`_engine_harness.Main.register` 已内建同一副作用；此处保留同名包装，语义/时机逐字不变。）
_orig_register = Main.register
async def _register_with_stamina(self, event):
    gid = event.get_group_id() or "private"
    qid = event.get_sender_id() or "unknown"
    async for r in _orig_register(self, event):
        yield r
    try:
        db.update_player(gid, qid, stamina=999999)
    except Exception:
        pass
Main.register = _register_with_stamina


class FakeEvent:
    """模拟 AstrBot 消息事件。"""

    def __init__(self, group_id, qq_id, msg=""):
        self._g = group_id
        self._q = qq_id
        self.message_str = msg
        self._stopped = False

    def get_group_id(self):
        return self._g

    def get_sender_id(self):
        return self._q

    def get_message_str(self):
        return self.message_str

    def plain_result(self, text):
        return text

    def stop_event(self):
        """v101.16：npc_quick_dialog 测试需要（拦截后续 handler 的标记）。"""
        self._stopped = True


async def run(handler, ev):
    """调用 async handler，收集全部 yield 结果。

    v139 兼容：普通 async def（无 yield，如 _maint_gate v134.7 后静默 stop）直接 await，
    返回 []；async generator（有 yield，有 asend 方法）逐个收集。"""
    gen = handler(ev)
    results = []
    try:
        # async generator 有 asend 方法；普通 coroutine 没有
        if hasattr(gen, "asend"):
            while True:
                results.append(await gen.__anext__())
        else:
            await gen
    except StopAsyncIteration:
        pass
    return results


def _db_path():
    """库路径：包内存档半边（`content.persistence`）给 `db_path()`。"""
    getter = getattr(db, "db_path", None)
    return getter() if callable(getter) else db.DB_PATH


def clean_db(*tables):
    """清空指定表（默认清核心业务表）。"""
    db.init_db()
    conn = sqlite3.connect(_db_path())
    try:
        targets = tables or (
            "players", "player_groups", "inventory", "quests", "battle_state",
            "achievements", "stats", "feedback", "market", "bestiary",
            "guilds", "guild_members", "party", "pets", "pet_dex", "reputation", "signin", "fishing",
            "visited", "world_event", "event_state", "professions", "props_use",
            "visited_subareas", "possessed",
        )
        for t in targets:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.close()


def make_player(gid="g1", qid="q1", name="测试", cls="战士", level=1):
    """落库一个玩家，返回 player dict。"""
    # v87.17 与真实注册一致：中文职业名 → 内部 cls_id（如 战士 → cls_zhan_shi）
    cls_id = C.resolve("classes", cls) if hasattr(C, "resolve") else cls
    db.create_player(gid, qid, name, cls_id, {}, 100, 100)
    p = db.get_player(gid, qid)
    if level > 1:
        db.update_player(gid, qid, level=level)
    # v94 体力：测试环境体力拉满（999999），防动作类命令被体力拦截
    db.update_player(gid, qid, stamina=999999)
    return db.get_player(gid, qid)


def new_main():
    """干净实例（带独立清理后的测试库）。"""
    clean_db()
    return Main(None)


# 让测试脚本直接 `python tests/test_xxx.py` 也能跑（无 pytest 环境）
if __name__ == "__main__":
    print(f"conftest OK: TEST_DB={TEST_DB}")
    print(f"  content 表数量: {len([k for k in dir(C) if k.isupper() and isinstance(getattr(C, k), dict)])}")
    print(f"  Main Mixin: {[c.__name__ for c in Main.__mro__ if c.__name__ != 'object']}")
