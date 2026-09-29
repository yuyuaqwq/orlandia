# -*- coding: utf-8 -*-
"""审计 B2 自开口（族：玩家可见说明按**字符数**截断）· 百科三处（词条 / 符文 / 收藏）。

原实现（`content/economy_cmds.py` 三处各写一份）：

    _desc = _av2.get("desc", "")
    if len(_desc) > 24:
        _desc = _desc[:24] + "…"          # 词条
    ...
    if len(_d) > 30:
        _d = _d[:30] + "…"                # 符文
    ...
    _hint = _T.text("adv.col_hint", desc=_d[:30]) if _d else ""   # 收藏

`desc` 是**中文正文**（一个全角字占 2 个显示列），而切点按**字符数**算 ⇒ 切点可以落在一个
数字的中间 ⇒ 上屏的是一个**读起来成立、但数值是错的**句子。实跑数据：

    swift_tailwind 「…下刻 精力回复 +10」   ⇒ 上屏「…精力回复 +1…」   ← 玩家照 +1 练级
    break_magic    「…＋25% 伤害」          ⇒ 上屏「…＋2…」         ← 伤害砍成十分之一
    combo_ward     「(史诗 30%；攻线限定)」  ⇒ 上屏「(史诗 3…」       ← 品质线读成 3%

本判据钉住的是**这一类**（数据驱动，不写死是哪几条）：

  ① **前缀不变式（核心）**：任一被截断的描述，去掉尾省略号后**必须是原文的前缀**
     —— 于是屏幕上不可能出现「原文里根本没有的数值」。改数据 / 加新条目都被自动覆盖。
  ② **宽度不变式**：截断后显示列宽 ≤ 统一列宽 + 1（省略号那一格）。
  ③ **不得在窄列下吐半截数字**：把列宽压到很窄，输出仍须满足 ①（这条直接钉住
     「+10 → +1」那个形态在**任何**列宽下都不可能发生）。
  ④ **三处共用一个出口**：词条 / 符文 / 收藏三处的宽度必须**逐字相同**（原 24 / 30 / 30）。
  ⑤ **短描述零改动**：宽度足够的描述**一个字符都不动**（防止「统一出口」退化成统一截断）。

**不改判据迁就实现**：①③ 由真实域数据驱动 —— 域里加一条长描述，本判据立刻重新验。
"""
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401  导入即完成 sys.path 装配

from _check import bind_check  # noqa: E402  断言助手单源：tests/_check.py

passed = failed = 0
check = bind_check(globals(), "passed", "failed")

_PD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content", "data")
_ECON = os.path.join(os.path.dirname(_PD), "economy_cmds.py")

# ── 读生产出口（真模块，不在判据里重写一遍实现）────────────────────────────────
_src = open(_ECON, encoding="utf-8").read()
_i = _src.index("_NUM_TAIL =")
_j = _src.index("# ★ D5：部位中文别名")
_ns = {"_ud": unicodedata}
exec(compile(_src[_i:_j], "economy_cmds-clamp", "exec"), _ns)
_clamp_desc = _ns["_clamp_desc"]
COLS = _ns["_ENCY_DESC_COLS"]

#: 三处调用点各自的**当前**写法（本轮收口后应全部是 `_clamp_desc(..., COLS)`）
SITE_AFFIX = '_clamp_desc(_av2.get("desc", ""), _ENCY_DESC_COLS)'
SITE_RUNE = '_clamp_desc(_ri.get("desc") or _rs.get("desc", ""), _ENCY_DESC_COLS)'
SITE_COLL = '_clamp_desc(_d, _ENCY_DESC_COLS)'


#: 三处调用点：各自在 `economy_cmds.py` 源码里**当前**的那一行（判据按行形状取，不写死实现）。
import re as _re

def _site_window(anchor_re):
    """取该调用点**及其后两行**的源码窗口（旧写法把切片写在下一行的 if 里）。"""
    m = _re.search(anchor_re, _src, _re.M)
    if m is None:
        return ""
    return _src[m.start():m.start() + 240]


_SEG_AFFIX = _site_window(r"^\s*_desc\s*=\s*_av2.*$")
_SEG_RUNE = _site_window(r"^\s*_d\s*=\s*_ri.*$")
_SEG_COLL = _site_window(r"^.*adv\.col_hint.*$")
_SITES = {"affix": (_SEG_AFFIX, 24), "rune": (_SEG_RUNE, 30), "coll": (_SEG_COLL, 30)}


def site_render(desc, which):
    """照该调用点**源码里现在那一句**渲染 desc —— 撤回修正时这里立刻走旧写法。

    ★ 本轮自纠：判据原先只打 `_clamp_desc()` 这个**助手**，于是「撤回调用点、保留助手」
      仍全绿 = 假门禁。现在由源码行形状决定走哪条路，撤调用点必然报红。
    """
    frag, old_n = _SITES[which]
    if not frag:
        return desc
    if "_clamp_desc" in frag:
        return _clamp_desc(desc, COLS)
    # ★ 旧写法是 `if len(x) > 24:` + `x[:24] + "…"`（**逗号后有空格**）⇒ 按正则认，别按子串。
    if _re.search(r"\[:\s*%d\s*\]" % old_n, frag) or _re.search(r">\s*%d" % old_n, frag):
        return desc[:old_n] + ("…" if len(desc) > old_n else "")
    return desc


def _w(s):
    """显示列宽：全角/宽字符 2 列，半角 1 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


#: 数词字符（数字 · 百分号 · 小数点 · 千分位 · 正负号 · 乘号 · 半/全角减号 · 波浪）
_NUMCH = "0123456789.,%％+－-×~"


def _ends_mid_number(shown: str, full: str) -> bool:
    """截断后的尾巴是不是一个**被切了一半的数词**。

    `+1…`（原文 `+10`）/ `＋2…`（原文 `＋25%`）/ `史诗 3…`（原文 `史诗 30%`）都命中。
    ★ 注意：**前缀不变式抓不到这三种**（它们都是真前缀）—— 这正是本轮判据第一版的盲区。
    """
    body = shown[:-1] if shown.endswith("…") else shown
    if not body:
        return False
    i = len(body)
    while i > 0 and body[i - 1] in _NUMCH:
        i -= 1
    if i == len(body):
        return False                      # 尾巴不是数词 ⇒ 没问题
    tail = body[i:]
    rest = full[len(body):] if full.startswith(body) else ""
    # 原文在同一个数词的**中间**还有延续（下一位仍是数词字符）⇒ 被切断
    return bool(rest) and rest[0] in _NUMCH


def _is_prefix(shown, full):
    if shown == full:
        return True
    return shown.endswith("…") and full.startswith(shown[:-1])


def _descs():
    """三处上屏描述的真源全集（affixes / runes / type=收藏）。"""
    out = []
    aff = json.load(open(os.path.join(_PD, "affixes.json"), encoding="utf-8"))
    for k, v in aff.items():
        if isinstance(v, dict) and isinstance(v.get("desc"), str):
            out.append(("affix:" + k, v["desc"]))
    rn = json.load(open(os.path.join(_PD, "runes.json"), encoding="utf-8"))
    for k, v in rn.items():
        if isinstance(v, dict) and isinstance(v.get("desc"), str):
            out.append(("rune:" + k, v["desc"]))
    for fn in os.listdir(_PD):
        if not fn.endswith(".json"):
            continue
        d = json.load(open(os.path.join(_PD, fn), encoding="utf-8"))
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if isinstance(v, dict) and v.get("type") == "收藏" and isinstance(v.get("desc"), str):
                out.append(("coll:" + k, v["desc"]))
    return out


_ALL = _descs()
_LONG = [(k, d) for k, d in _ALL if _w(d) > COLS]
_SHORT = [(k, d) for k, d in _ALL if _w(d) <= COLS]

# ── ④ 三处共用一个出口 ───────────────────────────────────────────────────────
for _name, _frag in (("词条", SITE_AFFIX), ("符文", SITE_RUNE), ("收藏", SITE_COLL)):
    check("④ %s 走上 _clamp_desc 单一出口" % _name, _frag in _src,
          "找不到这一处调用点：%s" % _frag)
check("④ 三处不再各写各的 desc[:N] 字符截断",
      "if len(_desc) > 24" not in _src and "if len(_d) > 30" not in _src,
      "仍有裸的 desc[:N] 字符截断残留")

# ── ① 前缀不变式 + ② 宽度不变式（数据驱动全量）───────────────────────────────
_bad_prefix = [(k, d, _clamp_desc(d, COLS)) for k, d in _LONG
               if not _is_prefix(_clamp_desc(d, COLS), d)]
check("① 全部 %d 条长描述截断后仍是原文前缀（不吐原文没有的数值）" % len(_LONG),
      not _bad_prefix,
      "违反前缀不变式：%s" % [(k, s) for k, _, s in _bad_prefix][:5])

_bad_width = [(k, _w(_clamp_desc(d, COLS))) for k, d in _LONG
              if _w(_clamp_desc(d, COLS)) > COLS + 1]
check("② 全部截断结果显示列宽 ≤ %d+1" % COLS, not _bad_width, "超宽：%s" % _bad_width[:5])

# ── ③ 窄列下也不得吐半截数字（本条直接钉住「+10 → +1」那个形态）──────────────
_hard = []
for _k, _d in _LONG:
    for _c in (12, 16, 20, 24, 28, 32, COLS):
        _sh = _clamp_desc(_d, _c)
        if not _is_prefix(_sh, _d):
            _hard.append((_k, _c, _sh))
check("③ %d 条长描述 × 7 个列宽下均满足前缀不变式（半截数字不可能上屏）" % len(_LONG),
      not _hard, "窄列下吐了非前缀：%s" % _hard[:5])

_hard_num = [(_k, _c, _clamp_desc(_d, _c)) for _k, _d in _LONG for _c in (12, 16, 20, 24, 28, 32, COLS)
             if _ends_mid_number(_clamp_desc(_d, _c), _d)]
check("③″ %d 条长描述 × 7 个列宽下均不吐半截数词（★ 本 bug 的真正判据）" % len(_LONG),
      not _hard_num, "窄列下吐了半截数词：%s" % _hard_num[:5])

# ── ①′ 前缀不变式打在**真实调用点**上（撤回修正即报红）──────────────────────
for _which, _label in (("affix", "词条"), ("rune", "符文"), ("coll", "收藏")):
    _srcs = [(k, d) for k, d in _ALL if k.split(":", 1)[0] in
             ("affix", "rune", "coll") and _which in ("affix", "rune", "coll")]
    if _which == "rune":
        _srcs = [(k, d) for k, d in _ALL if k.startswith("rune:")]
    elif _which == "coll":
        _srcs = [(k, d) for k, d in _ALL if k.startswith("coll:")]
    else:
        _srcs = [(k, d) for k, d in _ALL if k.startswith("affix:")]
    _bad_site = [(k, site_render(d, _which)) for k, d in _srcs
                 if not _is_prefix(site_render(d, _which), d)]
    check("①′ %s 调用点：%d 条描述截断后仍是原文前缀" % (_label, len(_srcs)),
          not _bad_site, "调用点吐出非前缀：%s" % _bad_site[:5])
    _bad_num = [(k, site_render(d, _which)) for k, d in _srcs
                if _ends_mid_number(site_render(d, _which), d)]
    check("①″ %s 调用点：%d 条描述不吐半截数词（+1 / ＋2 / 史诗 3 那三种形态）" % (_label, len(_srcs)),
          not _bad_num, "调用点吐了半截数词：%s" % _bad_num[:5])


# ── ⑤ 短描述零改动 ──────────────────────────────────────────────────────────
_dirt = [k for k, d in _SHORT if _clamp_desc(d, COLS) != d]
check("⑤ %d 条短描述逐字未动（统一出口不退回统一截断）" % len(_SHORT), not _dirt, "被改了：%s" % _dirt[:5])

# ── 附：点名钉住本轮那三个实跑证据（防「数据改了判据也跟着失效」）────────────
_AFF = json.load(open(os.path.join(_PD, "affixes.json"), encoding="utf-8"))
for _k, _forbidden in (("swift_tailwind", "…+1…"), ("break_magic", "＋2…"), ("combo_ward", "史诗 3…")):
    _sh = _clamp_desc(_AFF[_k]["desc"], COLS)
    check("★ %s 不再上屏半截数值（%s）" % (_k, _forbidden), _forbidden not in _sh, "上屏 = %s" % _sh)

print("PASS=%d FAIL=%d" % (passed, failed))
sys.exit(1 if failed else 0)
