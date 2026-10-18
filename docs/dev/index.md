---
title: 开发指南
---

## 说明

这个目录主要用于存放开发记录，帮助其他开发者理解我要做什么，以及是怎么做的。如果后期有人愿意加入进来一起开发的话，可以以该部分作为指导手册。

* **核心受众**：未来的你（在写代码时）、开源贡献者

* **解决的痛点**：接手项目时，不知道从何下手。

* **建议内容**：

    * **环境搭建**：需要 Python 3.12+、PDM、Node.js、pnpm，以及怎么一步到位启动开发环境。

    * **项目结构**：核心目录（`backend/app/domains/<域>/{views,schemas,models}.py`、`backend/app/services/`、`backend/app/core/`）的职责说明。

    * **开发流程**：我们的 API-First 工作流 (Spec -> Schema -> Model -> API -> Test)。

    * **代码风格与工具**：提交前必须运行 `ruff` 和 `pre-commit`。

    * **关键规范**：RESTful 接口风格、Pydantic Schema 定义、对外 API 响应结构约定。

    * **清单指引**：直接链接到我们现有的文档，如 `docs/spec/index.md`（需求与开发规范体系）、`CHECKLIST.md`。

    * **特点**：像一张藏宝图，告诉开发者代码在哪里、怎么改、有什么规矩。

让开发者可以部署起来。

## 文档

多多贝文档站使用 [VitePress](https://vitepress.dev/) + `@duxweb/vitepress-theme` 生成（由早期 VuePress v1 迁移而来，见提交 `291000a`）。包管理统一为 **pnpm**，请勿混用 npm / yarn。

* 本地预览

```bash
pnpm docs:dev
```

* 构建产物

```bash
pnpm docs:build   # 输出到 docs/.vitepress/dist，部署时发布该目录
```

* lint 文档

```bash
pnpm docs:lint-md
```

### 访问管控（哪些文档对外可见）

文档按敏感程度分为三层，由 `docs/.vitepress/config.mjs` 控制：

| 层级 | 目录 | 对外表现 |
|---|---|---|
| 公开 | `guide/` `features/` `api/` 及根目录站点页 (`about` `faq` 等) | 顶栏导航 + 侧边栏均收录，普通用户可见 |
| 内部可见 | `dev/` `pytest/` `ops/` `spec/` `design/` | 仅侧边栏收录（不在顶栏），协作者可见；无敏感信息 |
| 彻底屏蔽 | `working-notes/` + 根目录备忘 `.md` | 由 `config.mjs` 的 `srcExclude` 排除出构建，不进产物，远端访问即 404，仅仓库源码可见 |

屏蔽文件清单与说明见 [内部资产/备忘索引](/spec/internal-index.html)。
新增需屏蔽的备忘时，在 `config.mjs` 的 `srcExclude` 列表登记，并同步在该索引页登记。

## 预览

### 前端

```bash
cd frontend
pnpm install
pnpm serve # 也可以使用 pnpm dev
```

:::info
提示 *There is an issue with `node-fibers`*

参阅：[node 16.X 或更高版本 fibers 出错 is missing._fibers.node-CSDN 博客](https://blog.csdn.net/weixin_44149645/article/details/121362208)
:::

### 后端

* 安装开发环境

依赖统一由 [PDM](https://pdm-project.org/) 管理，声明在 `backend/pyproject.toml`、锁文件为 `backend/pdm.lock`。**仓库没有 `requirements/*.txt`，也不再使用 pip-compile-multi**（历史方案，已随依赖迁移到 PDM 而废除）。

```bash
cd backend
pdm install -G dev      # 含测试 / invoke 等开发依赖
```

:::tip
如果默认 PyPI 源不够快可以换源（PDM 机器级配置，不改仓库文件）：

```shell
pdm config pypi.url https://mirrors.aliyun.com/pypi/simple/
# 一键切回官方源（镜像滞后时用）
pdm config pypi.url https://pypi.org/simple/
```

:::

* 修改环境变量 `.env`（模板见 `backend/.env.example`），启动 API：

```bash
pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000
```

* 安装生产依赖（不含 dev 组）：

```bash
# fundmate/backend
pdm install --prod
```

* 更新依赖（重解并更新 `pdm.lock`）：

```bash
pdm update
```

如果执行 Python 工具时遇到 `UnicodeDecodeError: 'gbk' codec can't decode byte ...`，是 Windows 控制台编码问题，先设置 `PYTHONUTF8=1` 再重新执行。

### 启动数据库

* 初始化数据库

建表由应用启动时的 `init_db()` 完成（`backend/app/main.py` 的 `create_app()` 内调用），实现为 `Base.metadata.create_all()` + 增量列/索引迁移（`backend/app/core/database.py::init_db`），**没有 flask-migrate / Alembic 迁移链**，因此不存在 `flask db migrate / upgrade` 一类命令：

```bash
pdm run flask --app app.main:app run   # 启动即自动建表 / 补列
```

## 数据来源

1. `http://fund.eastmoney.com/js/fundcode_search.js` 数据 13420 条
2. `https://api.doctorxiong.club/v1/fund/all` 数据 11736 条
3. `http://fund.eastmoney.com/fund.html` 数据 11493 条

* 更新基金相关数据

```bash
# 全市场基金名录（默认只更新基金信息）
pdm run sync --job fund_list
# 或经 invoke 入口
pdm run invoke grab.job fund_list
```
