# ShowBuy

> 个人投资记账与家庭资产管理平台 · 代码仓库：`fundmate`

基于 **Flask（APIFlask）** 与 **Vue 3（pure-admin）** 的前后端分离 Web 应用，用于记录基金 / 股票等投资交易、追踪资产与收益，并内置「市场温度计」等分析工具。

> ⚠️ 命名说明：本仓库历史文档曾使用「叽咕」等名称，当前 `SPEC.md` 与代码（`backend/app/main.py`）统一为 **ShowBuy**。若品牌名已有最终定论，请同步修改本文件与代码中的 `title`。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12+ · Flask + APIFlask · SQLAlchemy 2.x · PDM 管理依赖 |
| 前端 | Vue 3 · TypeScript · Vite · pure-admin |
| 数据 | 本地 SQLite（默认 `backend/invest.db`） |

## 目录结构（仅列关键目录）

```
fundmate/
├─ backend/      # 后端服务；V2 代码在 backend/app/（backend/fundmate/ 为已退役 V1，勿用）
├─ frontend/     # 前端应用（Vue 3 + Vite）
├─ docs/         # 文档与开发笔记
├─ scripts/      # 工程脚本（含 V1 引用守卫、本地启动脚本）
├─ SPEC.md       # 需求规格说明书
└─ README.md
```

> 完整目录以实际文件系统为准，无需在此穷举。

## 本地开发

### 一键启动（推荐）

```bash
./scripts/dev.sh
```

脚本会同时拉起后端（`:8000`）与前端（`:8848`），按 `Ctrl + C` 一并退出。
首次运行或依赖变更时加 `--install` 重新安装：

```bash
./scripts/dev.sh --install
```

启动后访问：

- 前端页面：<http://localhost:8848>
- 后端 API 文档（Swagger UI）：<http://localhost:8000/docs>

### 手动启动

后端：

```bash
cd backend
pdm install                      # 首次或依赖变更时
pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
pnpm install                     # 首次或依赖变更时
pnpm dev
```

### 环境变量

- 后端读取 `backend/.env`（参考 `backend/.env.example`）。
- 前端开发配置见 `frontend/.env.development`：默认前端端口 `:8848`，并将 `/api` 代理到后端 `:8000`。

## 文档

完整需求与开发规范见 `docs/` 与根目录 `SPEC.md`。

## License

MIT
