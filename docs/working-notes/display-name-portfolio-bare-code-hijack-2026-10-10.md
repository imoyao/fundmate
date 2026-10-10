# 展示名反查把投顾组合错标成同裸码基金（2026-10-10，#2029）

> 触发：用户反馈自选 / 详情页里投顾组合「远足」显示成「民生加银中证500指数增强A」。
> 结论先行：**数据没坏，错在读取端反查**；修读取端即自愈，无需回填数据。
> 配套硬约束已写进 `AGENTS.md`「依赖复用与 Worktree 规范 → 临时改共享配置的还原纪律」。

## 一、取证（本机 `backend/invest.db`，2026-10-10）

| 表 | 实际内容 | 判定 |
|---|---|---|
| `advisor_portfolios` | `ZH012926 / QIEMAN / name='远足'` | ✅ 一直是对的 |
| `watchlist` id=27 | `symbol='ZH012926'`、`name=NULL`、`asset_type='portfolio'` | 快照为空 → 只能走反查链 |
| `funds` | `fund_code='012926' = 民生加银中证500指数增强A` | ← 被撞上的就是它 |

详情页副标题仍是「投顾组合 / QIEMAN · 基民柠檬」，标题却是基金名 —— 说明
`resolve_product_identity` 与自选列表走的是**同一条** `resolve_display_name`。

## 二、根因（`backend/app/services/watchlist_service.py::resolve_display_name`）

`bare_code_of` 抹掉命名空间：`ZH012926` → `''.join(数字)` → `012926` → 等值查 `funds` 命中 → **提前 return**，
`AdvisorPortfolio` 分支排在它后面，沦为死代码。两个缺陷叠加：

1. **裸码回退没有形态闸门**——#1497 引入回退时只特判了 `asset_type == 'index'`（那是「指数不许回退 funds」，
   不是「不许跨形态抽数字」），投顾 / 基金经理两种码空间完全没管；
2. **`asset_type` 只有 `index` 被消费**，`portfolio` 落进 `else` 的基金分支，且基金分支排在组合分支**之前**。

**讽刺点**：同一个坑隔壁已经修过 —— `product_identity._looks_like_exchange_code` 的注释原话是
「若不限定形态，前者会撞上上证指数、后者会撞上任意同号基金 —— 投顾组合与基金经理就被错标成别的东西了」。
但那是**另一处实现**，#1497 加回退时没接同一个闸门。即本仓反复强调的
**「同一判据两处实现必然漂移」**，这次漂移的方向是「一边有闸门、一边没有」。

## 三、影响面

- **114 个投顾组合中 18 个**裸码撞真实基金：远足 / 我要稳稳的幸福 / 货币三佳 / U定投 / 盈米稳健八心八箭 /
  Earl二八轮动 / 新锐债券组合 / 天颐五剑 / 守望者组合 / 交银赢定投 / 二八轮动 / 盈米股基精选组合 /
  静静聊吧 / 新锐突击组合 / 银河之力 / 李时珍医药基金组合 / 低估定投计划 / 周周有鱼。
- 自选里 3 条 `asset_type='portfolio'` 行：`ZH012926`（`name IS NULL`，**本次可见**）、
  `ZH013136`（有快照名，被 #1508 盖住看不出）、`ZH030684`（裸码未撞）。
- `manager` 码（`MGR_xxx`）同样暴露：`lookup_manager` 未命中时会落到裸码回退，
  `MGR_012926` 会取出 `012926` 那只基金。**本次一并堵上**。
- 未被自选的组合在「投顾组合详情页」入口同样中招（走 `resolve_product_identity`）。

## 四、修复（PR 见 issue #2029 关联）

1. `looks_like_exchange_code` 与 `bare_code_of` **成对收口**到 `watchlist_service`
   （两个前缀常量一并搬走），`product_identity` 改为 `from ... import`，**判据只剩一处定义**；
2. 裸码回退套上 `if looks_like_exchange_code(symbol):` —— 只对「指数 / 场内」形态开放；
3. `AdvisorPortfolio` 分支**上提**到基金分支之前（与 `product_identity` 的「按形态独特性排序」一致）；
4. 回归测试两条：单元（必然撞码的最小构造：`fund 012926` + `AdvisorPortfolio ZH012926`，含不传
   `asset_type` / `MGR_` / 目录未收录 / 闸门不削弱 #1497 六个断言）+ 端到端（POST 不带 `name` 模拟
   `name IS NULL` 存量行 → GET 列表断言 `display_name == '远足'`）。

**回退探针（关键步骤，别省）**：`git checkout --` 两个 service 文件 → 2 条新用例**变红**、
失败值正是 `民生加银中证500指数增强A` → 还原 → 全绿（`CAUGHT / GREEN`）。
判据没做过回退验证等于没有判据（同 `AGENTS.md`「前端交互修复」§三）。

## 五、同场教训：依赖源「索引新、文件旧」（→ #2031）

为给新 worktree 装依赖时踩到，与本 bug 无关但同属本次会话产出：

| 包 | 阿里云索引页 | 阿里云文件 URL（HEAD 实测） |
|---|---|---|
| `python-dotenv` | 列出 `1.2.3`、`1.2.4` | `python_dotenv-1.2.3-py3-none-any.whl.metadata` → **404** |
| `mcp` | 列出 `2.0.1`… | `mcp-2.0.0-py3-none-any.whl.metadata` → **404** |

`pdm.lock` 锁的正是这两个版本 → `pdm sync` 解析直接失败。**这不是配置回归**：
仓库的「本机阿里云 / CI PyPI」分工仍在 `ci.yml` L106-121（#1628），且注释已实测
`[[tool.pdm.source]]` 优先级高于 `PDM_PYPI_URL`，故 env 覆盖无效、只能改文件 —— 这也正是
**本地没有干净的临时换源通道**的原因。处置：

- 临时改源必须 `try/finally` 还原（本次先改后还原、顺序反了，用户看见 `git status` 误判为回归）；
- 根治：源下沉到机器级 `pdm config pypi.url`，pyproject 不声明源 → 本机天然阿里云、CI 天然 PyPI，
  `ci.yml` 那段 sed 改写可整体删除 → **#2031**（里程碑 M6、象阵 Q2）。

## 六、相关

- 修复卡：#2029（里程碑「自选增强」、象阵 Q2）
- 根治卡：#2031（依赖源下沉机器级配置）
- 历史：#1497（引入裸码回退）、#1508（`watchlist.name` 快照）、#1499（可转债）、#1392/#1468（投顾组合）、#1628（CI 切源）
