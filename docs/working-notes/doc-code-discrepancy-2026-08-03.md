# 文档与代码误差追踪（会议纪要）（2026-08-03）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 建立：2026-08-03。用途：记录 `docs/` 与实际代码的偏差，便于后续修正与追踪。
> 维护方式：发现一条加一条；修正后在「状态」列标注已解决。

## 一、已发现偏差

| # | 偏差点 | 文档说法 | 代码实际 | 状态 |
|---|--------|----------|----------|------|
| 1 | 鉴权实现 | `docs/dev/flask-auth.md` 称已实现 Flask-praetorian 登录/找回/重置 | `main.py` 未注册任何 auth 蓝图；`ledgers/views.py` 等用硬编码常量 `CURRENT_USER_ID` | 待确认 |
| 2 | 鉴权方案命名 | 文档只提 praetorian/JWT | 用户口述 login「借助 Subversion」实为 **Supabase**（`frontend/package.json` 含 `@supabase/supabase-js`） | 待确认 |
| 3 | 目录结构 | `docs/features/overview.md` 引用 `backend/app/models/transaction.py`、`account.py`、`fund.py` | 实际已重构到 `backend/app/domains/*/models.py` | 待修正 |
| 4 | 启动/建表方式 | README 用 `flask db migrate/upgrade`（flask-migrate） | `main.py` 用 `Base.metadata.create_all`（无迁移） | 待统一 |
| 5 | 依赖管理 | `docs/dev/index.md` 用 `requirements/dev.txt` + pip-compile-multi | 仓库实际为 `pyproject.toml` + pdm（`pdm.lock`） | 待更新 |
| 6 | 多币种建模 | SPEC(overview) 称 `positions` 含 `currency` | `transactions/models.py` 未见 currency 列（positions 模型未读，待核对） | 待核对 |
| 7 | 启动依赖风险 | 文档未列为 blocker | `main.py` 顶部 `import xalpha`（gitee 源），依赖 akshare/playwright；本地无网或安装失败会直接起不来 | 待记录 |
| 8 | 命名 | 内部名「叽咕」、产品名「多倍贝」、前端包名 `duobeibei`、README 称 "FMP/showbuy" | 对外命名不统一 | 待统一 |
| 9 | 前端模板基线 | docs 未说明 | 实际基于 **pure-admin-thin**（非完整 pure-admin） | 已澄清 |

## 二、决策记录（本会话）

- **鉴权方向**：用户要求单用户→家庭成员多用户，且拒绝写死变量。建议继续用 **Supabase Auth** + Flask 侧薄 JWT 校验中间件（替换 `CURRENT_USER_ID`），不在后端自造 JWT。
- **裁剪范围收窄**：保留 error/404 与「付费拦截」所需能力；仅删除 RBAC 用户/角色**管理后台页**与权限演示页（Supabase 控制台已管）。
- **优先总纲**：先定 landing 配置 + 品牌故事 + 产品设计故事 三份文档，作为 UI/规划的唯一真相源，避免返工。

## 三、待办（owner / 期限）

- [ ] 统一鉴权方案（Supabase vs praetorian）并修正 `flask-auth.md` — owner: 你 — 接身份前
- [ ] 同步 docs 路径到 `domains/` 结构 — owner: 你
- [ ] 统一依赖/启动方式（pdm vs requirements，create_all vs migrate）— owner: 你
- [ ] 确认多币种建模位置（positions.currency?）— owner: 你
- [ ] 将 xalpha/akshare 启动依赖记录为「可运行性风险」— owner: 你
- [ ] 对外命名统一（叽咕/多倍贝/duobeibao/FMP）— owner: 你
