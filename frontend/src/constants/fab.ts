// src/constants/fab.ts
/**
 * 全局悬浮控件（右下角「记一笔」FAB 与「回到顶部」）的**隐藏清单**。
 *
 * 为什么要有这份清单：这两枚浮标由 `layout/index.vue` 全局渲染，页面自身管不到它们；
 * 而「哪些页面不该显示」通常有结构性原因（整页就是输入区的对话页、本身就是录入流程的页面），
 * 且不需要每页各写一套判断。集中在清单里 ⇒ 新增一个屏蔽目标只改一行（#1775）。
 *
 * 两种用法，**就近优先**：
 * 1. **本清单**：适合「一整类 / 前缀级」目标——如 `/agent` 前缀下的全部对话页；
 * 2. **路由 meta `hideQuickEntry: true`**：适合「单个页面，且希望在路由定义处一眼看到」
 *    的场景（现有 8 个记账 / 录入类页面用的是这种）。
 * 判定顺序：`meta.hideQuickEntry === true` 命中即隐藏；否则再看本清单。
 *
 * ⚠️ 与安全区令牌的配对关系：命中隐藏的页面**无需**再为 FAB 预留
 * `--layout-fab-safe`（留白反而难看）；反之，若把某页面从清单或 meta 上摘掉，
 * **必须同时恢复预留**，否则贴底操作区会被 FAB 压住（#1773 实测：发送按钮被压成半个圆）。
 */
export const QUICK_ENTRY_HIDDEN_ROUTES: readonly string[] = [
  // 账本精灵：整页就是一个输入区，FAB 只会跟发送按钮抢位（#1773 实测被压住）
  "/agent"
];

/** 路径是否命中隐藏清单（前缀匹配：`/agent` 覆盖 `/agent/chat`；忽略末尾斜杠） */
export function isQuickEntryHiddenPath(pathname: string): boolean {
  const path = (pathname || "").replace(/\/+$/, "") || "/";
  return QUICK_ENTRY_HIDDEN_ROUTES.some(
    prefix => path === prefix || path.startsWith(`${prefix}/`)
  );
}

/** 统一判定：路由 meta 优先（就近声明），其次集中清单 */
export function isQuickEntryHidden(
  pathname: string,
  metaFlag?: unknown
): boolean {
  return metaFlag === true || isQuickEntryHiddenPath(pathname);
}
