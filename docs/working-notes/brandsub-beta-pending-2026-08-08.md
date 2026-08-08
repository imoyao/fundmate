# 悬挂问题：SidebarLogo / NavHorizontal 的 brand-sub/beta 改动被误删（2026-08-08）

## 状态

**悬挂（PENDING）**。等待另一会话处理；若其后续未自行处理，须由本记录持有者重建恢复。

## 问题描述

2026-08-08 本会话为完成「品牌 logo 组件化」，按「先不提交含他人改动的文件」决策执行 `git restore --staged --worktree`，将 `SidebarLogo.vue` / `NavHorizontal.vue` / `useNav.ts` / `public/logo.svg` 回退到 HEAD。但这两个 `.vue` 文件里混有**另一会话未提交的改动**（「投资账本」副标 `.brand-sub` + 「Beta 预览版」挂件 `.brand-beta`），回退操作将其一并覆盖丢失。

提交 `57da689`（feat(frontend): 侧边栏/顶栏 logo 区加「投资账本」副标与 Beta 挂件）的 message 声称已包含上述改动，但 `git show --stat 57da689` 证实这两个文件**不在该提交中**（回退后与 HEAD 无 diff，无法进入提交）。

## 证据（当前 HEAD 状态）

- `frontend/src/layout/components/lay-sidebar/components/SidebarLogo.vue:7` — `const { title, getLogo } = useNav();`，仍用 `<img :src="getLogo()">`
- `frontend/src/layout/components/lay-sidebar/NavHorizontal.vue` — 同样为旧版 `<img>` + `getLogo`
- `57da689` 未包含上述两文件（`git show --stat 57da689 | Select-String "SidebarLogo|NavHorizontal"` 无命中）

## 期望最终形态

两文件应为「`<BrandLogo>` 组件 + 品牌文字组「多倍贝」+ `.brand-sub`（投资账本，副标 0.6em φ⁻¹ 黄金分割比、`·` 分隔）+ `.brand-beta`（Beta 预览版挂件，`top:-0.35em` 上浮）」；同时 `useNav.ts` 删除 `getLogo()`、删除 `frontend/public/logo.svg`。

## 恢复方案

本会话在回退前的 staged diff 中保留了**完整代码**（BrandLogo 替换 + `.brand-sub`/`.brand-beta` 样式与文案），可无损重建。BrandLogo 组件、`frontend/src/assets/brand/logo.svg`、`MarketHeader`、登录页改动已由 `57da689` 随提交入库，重建时直接复用组件即可。

## 解除悬挂的触发条件

1. 另一会话后续提交了上述两文件的正确版本（含 `.brand-sub`/`.brand-beta`）→ 悬挂解除，无需动作；
2. 若长时间未处理 → 按「恢复方案」重建两文件并提交，同步 `useNav.ts` 与 `public/logo.svg` 清理。

## 关联

- 品牌规范：`docs/design/brand-v1.7.md`（§5 Logo 章节）、`logo-delivery/LOGO_DELIVERY.md`
- 前端组件：`frontend/src/components/BrandLogo/index.vue`
