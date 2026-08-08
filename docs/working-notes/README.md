# 工作记录索引（2026-07-31 ~ 2026-08-01）

本目录归集了本轮会话中产生的工作文档，避免散落于仓库根目录 `docs/`。

| 文件 | 内容 |
|---|---|
| `code-audit-and-remediation-2026-08-01.md` | 合并的 6 份代码审计与架构整改记录：① 代码问题审查（初版 2026-07-31）② 代码问题审查（深化版 2026-08-01）③ V1（`backend/fundmate/`）退役清除分析 ④ `data/` 接口可用性评估 ⑤ `libs/cal` 与测试目录瘦身 ⑥ FastAPI 解耦规划（`@bp.input` 自动范式冲突） |
| `erniao-fetcher-redesign-2026-08-01.md` | 二鸟说手抄报 fetcher 重构设计（独立功能文档，与代码审计无直接关联） |
| `supabase-jwks-es256-verification-2026-08-08.md` | Supabase JWT 验签改造为 JWKS+ES256（HS256 已失效）；含 3 条踩坑教训（Key ID≠密钥 / jwks_uri 以 OpenID 为准 / 端点要 apikey 头） |
| `brandsub-beta-pending-2026-08-08.md` | **悬挂问题**：SidebarLogo/NavHorizontal 的 brand-sub/beta 改动被误删，待另一会话处理或本会话重建（有完整 diff 可恢复） |

## 关联 SPEC 条目
- §1.3 技术栈规范（不依赖自动范式、预留 FastAPI 迁移空间）
- §10 技术债务表（V1 退役、错误信封、13 处 `@bp.input` 冲突等）
- §12 决策记录（V1 退役闭环、错误信封闭环、二鸟说拆分 WeChatRSS）
