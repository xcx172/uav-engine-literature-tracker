# 航空二冲程活塞发动机转速控制文献追踪看板

本地运行的文献追踪工具：设定时间窗口 X（天），从 OpenAlex 检索航空二冲程活塞发动机转速控制方向的论文，经 DeepSeek 抽取「一句话贡献 / 方法与数据集 / 代码是否开源」，落库 SQLite，用 Streamlit 展示、搜索与筛选。

## 1. 功能概览

- **演示模式**：内置合成数据，无需 Key、不发网络请求，页面显著标注「合成演示数据」。
- **在线模式**：三组 OpenAlex 查询（航空二冲程 / 航空活塞 / 二冲程），每组取前 20 条，按发表日期倒序；判定后提取最多 20 篇。
- **分类**：直接相关、近邻·航空活塞、近邻·二冲程；排除项只计数、不出卡片。
- **筛选**：关键词（标题、摘要、方法与数据集、证据）与代码状态（Yes / No / 未确认）取交集。
- **异常**：区分「直接相关 0 但有近邻」「三组成功且零命中」「查询失败」；失败时单独展示历史缓存。

## 2. 环境与安装

要求：Windows + Python 3.13（`py -3.13` 可用）、Git（提交用）。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. 无 Key 启动演示

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

浏览器打开终端显示的本地地址。默认进入演示模式，可试用关键词与开源状态筛选；不会发起任何网络请求。

## 4. 在线模式（使用你自己的 Key）

1. 确认项目根目录已有 `.gitignore`。
2. 复制模板并编辑：

```powershell
Copy-Item .env.example .env
notepad .env
```

3. 在 `.env` 中填入你自己的 `OPENALEX_API_KEY`、`DEEPSEEK_API_KEY`；`DEEPSEEK_MODEL` 默认 `deepseek-flash`。
4. 重启看板，左栏切到「在线模式」，设置 X 后点击「在线更新」。

真实 Key 只保存在本机 `.env`，不会写入仓库、日志或页面。模板与文档只使用占位符。

## 5. 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试全部使用模拟接口，离线运行，不读取真实 `.env`。当前基线：**53 passed**（Python 3.13.1 / Windows）。

## 6. 命令行更新

```powershell
.\.venv\Scripts\python.exe -m src.refresh --days 365 --max-summaries 20
```

与页面共用 `run_refresh()`；单次提取上限 20 篇，每组查询上限 20 条。

## 7. 目录结构

```text
uav-engine-literature-tracker/
├── app.py
├── src/
│   ├── config.py / errors.py / http.py
│   ├── openalex.py / classify.py / extract.py
│   ├── prompts.py / store.py / refresh.py
├── tests/
├── data/demo_papers.json
├── requirements.txt
├── .env.example
├── .gitignore
├── AGENTS.md / 研究说明.md / 技术设计文档.md / progress.md
└── README.md
```

## 8. 判定与窗口（摘要）

- 窗口 `[D−(X−1), D]`，默认 365，范围 1–3650；未来日期排除；日期未知入库、单列计数、不入窗口与提取队列。
- 直接相关须同时有：航空/无人机用途、**明示**的活塞结构、二冲程、发动机轴转速控制，且证据指向同一台受控发动机。
- 仅把 `6000 rpm` 当试验工况、拿二冲程做油耗对照、或受控对象其实是电机/涡轮的，不归直接相关。
- 摘要缺失保留标题与链接，标「摘要缺失，未提取」；短而有内容的摘要仍按证据判定。
- 同一篇只保留一条；后来补到摘要或 Prompt 版本变化时更新同条并重新提取；DOI 迟到冲突按事务合并。

## 9. 已知覆盖范围与限制

- 判定是标题 + 摘要的句级启发式，不做全文语义理解。
- 只接 OpenAlex 一个来源，不下载 PDF，不做引用网络分析。
- 未实现定时调度；命令行入口便于后续自行挂计划任务。
- 在线模式的真实字段与额度需在本机联调确认；查询 400 时该组标记失败，其余组继续。

## 10. 密钥与提交

- `.env`、`.venv/`、SQLite、日志、缓存均已加入 `.gitignore`。
- 提交前按 `AGENTS.md` §8 检查：忽略规则、`git ls-files`/`git log` 受限路径、`.env.example` 仅占位符、演示数据标注 synthetic。
- 真实 API 联调与 Git 提交由使用者本人执行。

## 11. 当前状态

- 第 1–3 轮：需求、技术设计、后端与测试已完成。
- 第 4 轮：本页面、演示数据与 README。
- 第 5 轮：全量验收与本机脱敏联调。
