# progress.md — 第 5 轮进度、验收与本机执行指引

> 项目：航空二冲程活塞发动机转速控制文献追踪看板（`uav-engine-literature-tracker`）
> 「当前轮次」以本文件为准；与对话冲突时，以你最近一次明确指示为准（`AGENTS.md` §2）。
> 最后更新：2026-11-07

---

## 当前状态

| 项目 | 内容 |
|---|---|
| **当前轮次** | **第 5 轮（验收准备）**——离线部分完成；T-03 / T-04 待你本机执行 |
| 需求 / 设计基线 | `研究说明.md` v1.5；`技术设计文档.md` v1.1 |
| 交付 | `src/`、`tests/`、`app.py`、`data/demo_papers.json`、`README.md`、配置模板 |
| 测试 | Harness：53 passed / exit 0；**你本机：53 passed in 1.23s / exit 0** |
| 演示 | `http://localhost:8501` 可访问；无 Key 演示与组合筛选用 AppTest 复核 |
| T-01 | **本机验证通过**（你已验收演示页面与组合筛选） |
| T-02 | **本机验证通过**（53 passed in 1.23s，退出码 0） |
| T-03 | **待验证**（真实 API 联调，你本机执行） |
| T-04 | **待验证**（Git 检查与提交，你本机执行） |
| 密钥 | 未创建 `.env`，未使用真实 Key |

### 验收状态概览

| AC 范围 | 状态 | 依据 |
|---|---|---|
| AC-01~AC-09 | 已由单元测试覆盖 | `test_classify` / `test_dates` / `test_openalex` |
| AC-10~AC-12 | 页面部分由 AppTest 验证；无 Key 拦截已测 | 真实浏览器验收（T-01 已通过） |
| AC-13~AC-18 | 已由单元测试覆盖 | `test_http` / `test_extract` |
| AC-19、AC-20 | **待你本机执行** | T-03 / T-04 |
| AC-21~AC-23 | 已由测试覆盖 | `test_refresh` / `test_store` |
| AC-24~AC-26 | 演示区分、数据覆盖已测；页面视觉待你确认 | AppTest / `test_demo` |
| AC-27 | 已覆盖（全部 mock、无网络） | pytest 运行记录 |
| AC-28 | 卡片三类标签与计数已实现；视觉待确认 | AppTest |

---

## 1. 本机验收记录

### T-01 演示页面与组合筛选（本机通过）

Harness 自检计数（Streamlit AppTest，无 Key）如下；每步条件已注明：

| 步骤 | 关键词 | 开源状态 | 卡片数 | 命中说明 |
|---|---|---|---|---|
| 1 | 空 | 全部 | **8** | 全部合成演示 |
| 2 | `two-stroke` | 全部 | **7** | 标题/摘要/字段命中 |
| 3 | `two-stroke` | Yes | **3** | W001、W003、W005（交集） |
| 4 | 空 | No | **3** | W002、W006、W008 |
| 5 | `no-such-term` | 全部 | **0** | 空状态提示 |

- 8 条数据逐条复跑判定：8/8 与标签一致；直接相关 3 条证据同指一台发动机；Yes/No 证据均在摘要；`null` 显示「未确认」。
- 你在本机已验收演示页面与组合筛选，T-01 记为本机通过。

### T-02 本机测试（本机通过）

- 命令：`.\.venv\Scripts\python.exe -m pytest -q`
- 结果：**53 passed in 1.23s**，退出码 **0**（你本机）。
- Harness 复核：`53 passed`，exit 0。

---

## 2. T-03 真实 API 联调（待你执行）

### 2.1 前提

1. 若项目还不是 Git 仓库，先初始化（由你执行；只需一次）：

```powershell
git init
```

2. 然后确认 `.env` 会被忽略（在创建 `.env` 之前执行）：

```powershell
git check-ignore -- .env .env.local .streamlit/secrets.toml
```

三个路径都应被列出；若 `.env` 未被列出，先停下，不要填 Key。

3. 复制模板并在本机编辑器中填写真实 Key（不要粘贴到聊天、命令行参数或截图）：

```powershell
Copy-Item .env.example .env
notepad .env
```

4. 重启看板：

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### 2.2 步骤

1. 左栏切到「在线模式」，X 设为 **365**（或 180），点击「在线更新」。
2. 等待完成，记录：状态、`N/3` 组成功、三类命中数、队列/提取/失败数。
3. 打开 1–2 张卡片：核对题目、发表日期、贡献、方法/数据集、代码状态与证据、原文链接可点击。
4. 再次点击更新（同 X）：观察是否复用缓存、提取数是否下降。
5. 若出现 400：记录为 `PARAM_INVALID`（该组失败、其余组继续）；**不要擅自改参数**，把脱敏结果反馈给我。
6. 若出现 401/402：确认停止后续同服务调用，页面只显示配置提示。

### 2.3 通过标准

- 三组查询均成功（`3/3`）；若任一组 400/失败，本次联调记为**未通过/待定位**，不按通过计。
- 页面显示真实记录（非演示数据），卡片五类字段齐全，链接可打开。
- 零命中时显示「本次检索无命中」；直接相关 0 但有近邻时显示「直接相关 0 篇」并展示近邻。
- 页面、日志、错误提示中**不出现** Key、`Authorization`、含 `api_key=` 的 URL、原始响应。
- 第二次更新不重复提取已成功且输入未变的记录；上次 `deferred` 仍可从库续提取。

### 2.4 脱敏结果记录模板（贴回给我即可，不含 Key）

```text
日期：
X：
模式：在线
查询：N/3 成功
命中：直接相关 __ / 近邻·航空 __ / 近邻·二冲程 __
队列：__ 篇；提取：__ 篇；失败：__ 篇；deferred：__ 篇
状态：ok / partial / failed
错误（只用固定类型 + 状态码）：
页面观察：卡片字段 / 链接 / 零命中文案 / 历史缓存标注
结论：通过 / 不通过（原因）
```

---

## 3. T-04 Git 提交前检查（待你执行）

### 3.1 忽略规则与历史

若尚未初始化仓库，先 `git init`（由你执行）。然后：

```powershell
git check-ignore -- .env .env.local .streamlit/secrets.toml
git ls-files -- ':(glob)**/.env' ':(glob)**/.env.*' ':(glob,exclude)**/.env.example' ':(glob)**/.streamlit/secrets.toml'
git log --all --format=%h -- ':(glob)**/.env' ':(glob)**/.env.*' ':(glob,exclude)**/.env.example' ':(glob)**/.streamlit/secrets.toml'
```

- 第一条必须列出三个路径。
- 第二条、第三条必须**无输出**。

### 3.2 逐项暂存

```powershell
git add -- .gitignore .env.example AGENTS.md "研究说明.md" "技术设计文档.md" progress.md README.md requirements.txt app.py
git add -- src/ tests/ data/demo_papers.json
git diff --cached --name-only
git diff --cached --check
```

- 名单里不应出现 `.env`、`.venv/`、`__pycache__/`、`.pytest_cache/`、`*.log`、`*.sqlite*`、截图。
- `data/demo_papers.json` 每条均应含 `"synthetic": true`。

### 3.3 密钥扫描（本机）

按手册 6.3 的脚本运行（读取你本机 `.env`，只输出 `PASS`/`BLOCKED`/`INCOMPLETE`）：

```powershell
@'
import os
import subprocess
from dotenv import dotenv_values

names = ("OPENALEX_API_KEY", "DEEPSEEK_API_KEY")
placeholders = {"your_openalex_key_here", "your_deepseek_key_here"}
local = dotenv_values(".env", encoding="utf-8-sig", interpolate=False)
keys = set()
for name in names:
    values = {v.strip() for v in (os.getenv(name), local.get(name)) if v}
    values -= placeholders | {""}
    if not values or any("\n" in v or "\r" in v for v in values):
        raise SystemExit("INCOMPLETE: check local API key configuration.")
    keys.update(values)
patterns = ("\n".join(sorted(keys)) + "\n").encode("utf-8")
commits = subprocess.run(["git", "rev-list", "--all"], capture_output=True)
messages = subprocess.run(["git", "log", "--all", "--format=%B"], capture_output=True)
if commits.returncode or messages.returncode:
    raise SystemExit("INCOMPLETE: run this check from the project repository root.")
if any(k.encode("utf-8") in messages.stdout for k in keys):
    raise SystemExit("BLOCKED: a configured API key is in a commit message.")
for scope in ["--cached", *commits.stdout.decode("ascii").splitlines()]:
    result = subprocess.run(
        ["git", "grep", "-a", "-F", "-q", "-f", "-", scope, "--"],
        input=patterns, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        raise SystemExit("BLOCKED: a configured API key is in the index or history.")
    if result.returncode != 1:
        raise SystemExit("INCOMPLETE: Git could not scan the index or history.")
print("PASS: configured API key values were not found in the index or history.")
'@ | .\.venv\Scripts\python.exe -
```

### 3.4 通过标准

- `git check-ignore` 三个路径全部列出。
- `git ls-files` / `git log --all` 受限路径无输出。
- 扫描脚本输出 `PASS`。
- 暂存清单逐条可解释，无日志、缓存、截图、`.env`。
- `.env.example` 仅 3 行占位符；演示数据全部 `synthetic`。

提交与推送由你执行；提交后按 README 在新目录克隆，验证「无 Key 演示 + 安装依赖 + pytest」可复现。

---

## 4. 变更记录

| 轮次 / 事件 | 日期 | 变更 |
|---|---|---|
| 第 1–4 轮 | 2026-11-07 | 需求、TDD、后端测试、页面与演示 |
| 第 5 轮（本次） | 2026-11-07 | T-01 / T-02 记为本机通过；记录 8→7→3、No=3、空=0 的筛选条件；补 T-03 联调步骤/通过标准/记录模板；补 T-04 提交前检查步骤；T-03 / T-04 保持待验证 |
