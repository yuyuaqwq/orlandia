# 奥兰迪亚·余烬纪年 —— 数据包（**独立仓**，2026-09-15 B16 拆仓）

这是《奥兰迪亚·余烬纪年》（QQ 机器人文字 RPG）的**引擎数据包**，也是**包内容的唯一真源**。
自 2026-09-15（B16）起，它从引擎仓的 `games/orlandia` 迁出为独立仓：

```text
包仓（本仓）  git@github.com:yuyuaqwq/orlandia.git        ← 改包在这里改（main 分支）
引擎仓        git@github.com:yuyuaqwq/SaintessEngine.git  ← games/orlandia = 本仓的 submodule
宿主仓        git@github.com:yuyuaqwq/dragonfall.git      ← framework/games/orlandia = 同一 submodule（nested）
```

三处**各是一份独立检出**，一致性由 **git 提交**保证。门禁 = 宿主仓 `scripts/check_package_landings.py`：
三个落点必须 **同包 id / 同内容 sha256 / 同提交**，且都必须是**独立检出**（内嵌副本 = 拆仓没拆干净）。

---

## 一、改包流程

```bash
# ① 在本仓改（+ 跑门禁）→ 提交 → 推
cd C:/Users/yuyu/orlandia
git add -A && git commit -m "…" && git push origin main

# ② 引擎仓 bump 包指针 → 推
cd C:/Users/yuyu/framework-engine
git -C games/orlandia fetch origin && git -C games/orlandia checkout -q <本仓 sha>
git add games/orlandia && git commit -m "bump 包指针 → <sha>" && git push

# ③ 宿主仓 bump 引擎指针 → 推（nested submodule ⇒ 需要 --recursive init）
cd C:/Users/yuyu/qqbot/data/plugins/dragonfall
git -C framework fetch origin && git -C framework checkout -q <引擎 sha>
git -C framework submodule update --init --recursive games/orlandia
git add framework && git commit -m "bump 引擎指针 → <sha>" && git push

# ④ 核验三落点一致
python scripts/check_package_landings.py
```

**只让本地两处检出看到最新包（开发期，不提交指针）**：

```bash
NEW=$(git -C C:/Users/yuyu/orlandia rev-parse HEAD)
for R in C:/Users/yuyu/framework-engine/games/orlandia \
         C:/Users/yuyu/qqbot/data/plugins/dragonfall/framework/games/orlandia; do
  git -C "$R" fetch -q origin && git -C "$R" checkout -q "$NEW"
done
```

### ⚠️ 两条踩过的坑（B16 实测）

* **`git submodule update` 忠于索引** —— 要让子模块换到新提交，必须**先 `git add <submodule>`（stage gitlink）再 update**，
  否则 update 会把它拉回索引里记录的旧提交（B16 第一遍就白做了一次）。
* **Windows 常见 system 级 `core.autocrlf=true`** 会把包内 LF 文件在新 clone 时转成 CRLF ⇒ 当场撞三条格式门禁
  （`commands.json` CRLF / `test_command_priority_sync` / `test_texts_specs_sync`）。
  本仓已放 **`.gitattributes`（`* -text`）** 根治；本地 clone 建议同时 `git config core.autocrlf false`。

> 旧时代的镜像脚本 `sync_pkg.py` / `sync_engine_host.py` **已退役**（拆仓后没有「两份要抄」的问题了），
> 归档在宿主工作区 `_retired/20260915_b16/`。

---

## 二、包里有什么

```text
content/data/*.json     68 个域表（当前合计 9361 条）
content/rules/*.json     5 个规则表
content/*.py           115 个包内实现
editor/domains.json     域声明（含 owner / tier）—— **域清单的真源在这里**
editor/glossary/*.json  70 个域的词表（字段中文名 / 分组 / 控件随包走，第 3 层）
schemas/*.json          70 个域 schema
game.json               包清单（id / engine 版本 / domains / entry / bind 声明）
```

★ **域清单以 `editor/domains.json` 为真源**（本文不重复列表，避免过期）；条数随开发变化，用门禁核：
`python scripts/verify_package_coverage.py --check` →
最近一次 **域 73 个 / 条目合计 9361 / 失败 0**。

**包内实现的分层**（与引擎的契约）：

```text
content/cmds_*.py        命令实现（194 条声明的 handler 落点）
content/flow/            流程（副本战斗/结算/周常进度…）
content/persistence/     存档层的表结构与 CRUD（只吃宿主注入的句柄：db_path / clock / log / tlog / grant_reward）
content/facade.py        聚合门面 `C`（惰性聚合句柄）+ `bind_host(**inject)`（应答 game.json 的 bind 声明）
content/obs.py           日志/流水取用口（唯一入口，fail-closed）
```

---

## 三、落盘规范（手改必须照此，否则门禁红）

```text
UTF-8 无 BOM · LF 行尾 · json.dump(indent=2) · 文件末尾换行 · 外层键**升序**（插入序用条目内 seq 字段）
```

文案唯一真源 = 包内 `texts` 域（`content/data/text_specs.json`）；代码只传槽位，禁写 default。

---

## 四、门禁

```bash
cd C:/Users/yuyu/qqbot/data/plugins/dragonfall          # 宿主仓里有全套门禁（读包内真源）
python scripts/verify_package_coverage.py --check       # 域清单四方一致 / 落点 / 条数>0 / 逐条过 schema / 无孤儿文件
python tests/test_export_package_sync.py                # 冻结门禁（items 900 等冻结规模账 + 落盘规范 + 清单一致）
python tests/test_monster_roster_closure.py             # 名册闭合（读包内三域）
python scripts/check_terminal_state.py --check          # 终态六条判据（含「包内覆盖 0 失败」）
python scripts/check_package_landings.py                # 三落点一致（本仓 / 引擎仓检出 / 宿主检出）
```

引擎侧：`cd C:/Users/yuyu/framework-engine && python tests/run_all.py`（54 文件，当前 54/54）。
