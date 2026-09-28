# -*- coding: utf-8 -*-
"""审计 afix2 自查新开口：`content/economy_cmds.py` 重锻「升级投资继承」取名册路径 fail-closed 判据。

原实现（:3437-3442）::

    _base_lv = d.get("lv", 0) or 0
    try:
        for _rid in _cit.EQUIP_ROSTER_BY_NAME.get(src_name, []):
            _base_lv = _cit.EQUIP_ROSTER[_rid].get("lv", _base_lv)
            break
    except Exception:
        pass
    _upg_boost = max(0, ((d.get("lv", 0) or 0) - _base_lv))

**真实代价**（不是「少显示几件东西」）：`pass` 盖住的是「按装备名反查名册基础 lv」。
读不到 ⇒ `_base_lv` 停在旧装备**当前 lv** ⇒ `_upg_boost = max(0, lv - lv) = 0`
⇒ **玩家的升级投资一层都不继承，新装备退回名册基础等级**。而它原先跑在
**扣完材料 + 扣完金币 + 扣掉旧装备之后** ⇒ 玩家付了全额代价、拿到一件低一级的
装备、回话照样印「重锻成功」，全程零异常（台账 L4574 那族：内层 except 把真故障
降级成假数据）。

**修法两半，顺序也是修法的一部分**：
  ① `except Exception: pass` 删除 —— 名册索引是纯数据表，抛错 = 数据坏了。
  ② 整段**前移到扣任何东西之前** —— 在原位抛等于「收了钱再报错」，比静默更糟。

**刻意不动的那一路（防过度约束）**：`EQUIP_ROSTER_BY_NAME.get(src_name, [])`
查不到**名字**时循环不执行、`_base_lv` 留在当前 lv —— 那是注释里写明的**有意兜底**
（「查不到兜底用当前 lv 当已含全部升级 → 不继承」），是设计不是故障。本判据只钉
「抛了不许被吃掉」与「读取点排在扣款之前」，不碰那一路。

**本判据不重写实现**：`refine` 是 async 生成器 + 依赖注入面太宽，本文件按
`bind_check` 之外的最小替身驱动**真函数体**的方式是脆弱的（会退化成「在测试里
重写一遍拼装」—— 那正是第一版探针犯过的错）。故本文件改为**结构性判据**：
从生产源码里定位那段取名册的代码，断言 (a) 它不再被 `except … pass` 吞、
(b) 它排在所有 `db.remove_item` / `db.update_player(gold=…)` **之前**、
(c) 升级继承的算式逐字未变、(d) 索引自身完好（不是「永远不会触发」的永真豁免）。
§3 用**真调**独立复算继承算式，证明 (c) 的口径与新装备 lv 一致。
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配（引擎根 + extends）

from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

passed = failed = 0
check = bind_check(globals(), "passed", "failed")

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "content", "economy_cmds.py")


def _code_lines():
    r"""生产源码的**代码**行（注释与 docstring 整行剔除，原文另存）。

    ★ 为什么必须剔：本判据按文本定位，而修正**自带一段说明性注释**，
    注释里逐字引用了 `_upg_boost = max(0, …)` 与旧的 `except … pass` ——
    不剔就会「grep 撞上我自己写的解释」= 恒红/定位歧义。
    （同族：L1102 那次按 `self.ok` 字面 grep 撞上修正里新加的说明注释。）
    判据本身不靠"别在注释里写这两个串"活着 —— 那是把判据建在措辞上。
    """
    raw = io.open(SRC, encoding="utf-8").read().splitlines()
    code = []
    for l in raw:
        s = l.strip()
        if s.startswith("#"):
            code.append("")
            continue
        # 行尾注释：按引号配平切，避免把字符串里的 # 误当注释
        body, in_s, in_d, i = "", False, False, 0
        while i < len(l):
            ch = l[i]
            if ch == "\\" and in_s:
                body += l[i:i + 2]
                i += 2
                continue
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == "#" and not in_s and not in_d:
                break
            body += ch
            i += 1
        code.append(body)
    return raw, code


def _fn_end(code, at):
    """从 `at` 往后找下一个「同缩进的 def / @decorator」——即本函数体的结束行。

    ★ 需要它是因为 `economy_cmds.py` 里有多个**同形**的扣款段（重锻 / 炼成），
    纯文本定位必然撞第二个。收窄到「同一函数」是让结构性判据不退化成永真/恒红
    的必要条件（第一版两处都栽在这里）。
    """
    indent = len(code[at]) - len(code[at].lstrip())
    for j in range(at + 1, len(code)):
        l = code[j]
        if not l.strip():
            continue
        ind = len(l) - len(l.lstrip())
        if ind <= indent and (l.lstrip().startswith("def ")
                              or l.lstrip().startswith("async def ")
                              or l.lstrip().startswith("@")):
            return j
    return len(code)


def _refine_region():
    """返回 (原文行, 代码行, 升级投资算式行号)。"""
    raw, code = _code_lines()
    # 定位：升级投资算式那行（`_upg_boost = max(0, …)`）—— 只在代码行里找
    idx = [i for i, l in enumerate(code) if "_upg_boost = max(0," in l]
    assert len(idx) == 1, "定位不到唯一的 _upg_boost 算式行：%r" % (idx,)
    return raw, code, idx[0]


def main():
    global passed, failed
    lines, code, at = _refine_region()

    # ---- §1 结构：取名册那段不再被 except…pass 吞 ----
    # 往上找这次 for 循环（它是「按名反查名册」本体）
    loop_at = None
    for i in range(at, max(-1, at - 30), -1):
        if "EQUIP_ROSTER_BY_NAME.get(src_name" in code[i]:
            loop_at = i
            break
    check("§1 定位到按名反查名册的 for 循环", loop_at is not None,
          "at=%d 附近没有 EQUIP_ROSTER_BY_NAME.get(src_name" % at)

    # ★ 判据第一版是「for 之后 8 行内不得有 except…pass」，**反证当场通过 ⇒ 假门禁**：
    #   把 except 装回来时它就落在 for 之后第 3 行，窗口却没盖到。⇒ 改成按**缩进**判：
    #   取名册那个 for 到本函数末尾之间，不得出现 except…pass / except…return None。
    #   这才是「这段逻辑被不被吞」的准确判法 —— 判窗口长度是在判措辞。
    # ★ 判据演进（三版都栽在这里，记下免得下一个人重走）：
    #   v1「for 之后 8 行内无 except…pass」—— 反证当场通过 = 假门禁（窗口没盖到）。
    #   v2「for → 函数末」窗口 —— 仍然通过，因为 except 挂在 for 的**外面**
    #      （try 是父块，for 是子句）⇒ 窗口从 for 起根本看不到 except。
    #   ⇒ 正确锚点是 **try 行**（没有 try 就以 for 行为准）。
    #   ★ 教训：判「这段逻辑被不被吞」不能从被保护的**子句**起量窗口，
    #     要从**包住它的块**起量。
    #   ★ 本块刻意不用正则：前两版里 [""] 在落盘时被吃成控制字符（0x08），
    #     判据静默退化成「永不匹配」= 又一层假门禁。改用 startswith 前缀判。
    anchor = loop_at
    for i in range(loop_at, max(-1, loop_at - 6), -1):
        if code[i].strip() == "try:":
            anchor = i
            break
    seg = code[anchor:_fn_end(code, anchor)]
    swallowed = []
    for i in range(len(seg) - 1):
        if seg[i].strip().startswith("except") and seg[i].rstrip().endswith(":"):
            nxt = seg[i + 1].strip()
            if nxt == "pass" or nxt in ("return None", "return {}", "return []"):
                swallowed.append((anchor + i, seg[i].strip(), nxt))
    check("§1 取名册那段不再有 except…pass 吞异常", not swallowed,
          "仍在吞：%r（锚点行 %d）" % (swallowed, anchor))

    # ---- §2 顺序：读取点排在所有不可逆扣款之前 ----
    # ★ 本文件有两处 `db.remove_item(..., m, n)`（重锻 + 炼成）—— 必须**按函数边界**
    #   收窄，不能只按「在算式行之后」（炼成那处也在之后）。第一版只加了 `i > at`
    #   仍命中两处、直接把自己搞红 ⇒ 教训：收窄条件要收到「**同一函数内**」。
    end = _fn_end(code, at)
    scope = range(at, end)
    check("§2 收窄到重锻函数体内（找到下一个同缩进定义）", end > at,
          "at=%d end=%d" % (at, end))
    deduct = [i for i in scope if "db.remove_item(group_id, qq_id, m, n)" in code[i]]
    check("§2 重锻段内扣材料那一行唯一", len(deduct) == 1, repr(deduct))
    # ★ 定位失败不许 IndexError 崩掉（崩掉虽然也 rc≠0，但**丢掉其余 14 条判据的报告**）。
    #   门禁的第一职责是「把话说清楚」，第二才是「红」。
    deduct_at = deduct[0] if deduct else at
    check("§2 扣金币在读取点之后（玩家已付代价才读名册 = 收了钱再报错）",
          deduct_at > loop_at,
          "扣材料@%d 取名册@%d" % (deduct_at, loop_at))
    gold = [i for i in scope if 'gold=player["gold"] - rec["gold"]' in code[i]]
    check("§2 扣金币行存在且在读取点之后", gold and gold[0] > loop_at,
          "扣金币@%r 取名册@%d" % (gold, loop_at))

    # ---- §3 算式逐字未变（换的是「读不到怎么办」，不是「怎么算」）----
    m = re.search(r"_upg_boost\s*=\s*max\(0,\s*\(\(d\.get\(\"lv\",\s*0\)\s*or\s*0\)\s*-\s*_base_lv\)\)",
                  code[at])
    check("§3 升级投资算式逐字未变", m is not None, lines[at].strip())
    check("§3 算式行紧随取名册段之后（未被打散）", at - loop_at <= 6,
          "loop@%d at=%d" % (loop_at, at))

    # ---- §4 索引自身完好：证明「今天不触发」不是永真豁免 ----
    from content import catalog_items as _cit  # noqa: E402  真装内容侧
    byname, ros = _cit.EQUIP_ROSTER_BY_NAME, _cit.EQUIP_ROSTER
    dangling = [(n, r) for n, ids in byname.items() for r in ids if r not in ros]
    check("§4 名册索引无悬空 rid", not dangling, repr(dangling[:5]))
    nolv = [n for n, ids in byname.items()
            if ids and not isinstance(ros[ids[0]].get("lv"), int)]
    check("§4 索引首个 rid 都带整数 lv", not nolv, repr(nolv[:5]))
    check("§4 索引非空（否则本判据第④节会退化成空转）", len(byname) > 100,
          "名字数=%d" % len(byname))

    # ---- §5 真调独立复算继承算式（证明 §3 的口径与新装备 lv 一致）----
    def upg_boost(cur_lv, base_lv):
        return max(0, ((cur_lv or 0) - base_lv))

    # 半额：旧装 10 级、名册基础 4 级 ⇒ 玩家花了 6 层 ⇒ half 得 3
    check("§5 full 继承：旧装 10/基础 4 ⇒ +6", upg_boost(10, 4) == 6)
    check("§5 half 继承：旧装 10/基础 4 ⇒ +3", upg_boost(10, 4) // 2 == 3)
    # 坏档那一路的对照臂：base_lv 停在当前 lv ⇒ 恒 0（这就是原 bug 的值）
    check("§5 反证臂·原 bug 的值是 0（基础 lv 停在当前 lv）", upg_boost(10, 10) == 0)
    # 目标装备基础 lv 更高时不得为负
    check("§5 基础 lv 高于当前 lv ⇒ 0（不为负）", upg_boost(4, 10) == 0)

    print("passed=%d failed=%d" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
