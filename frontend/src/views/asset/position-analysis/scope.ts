/**
 * 三级口径（家庭 / 账户 / 组合）→ 面板 props 的**唯一出口**（#2595）。
 *
 * ## 为什么值得单独一个文件
 *
 * #2595 的真实事故不是「算错了」，而是「**漏传了**」：组合详情页复用穿透面板时没传
 * `portfolio-id`，面板按默认值拉家庭级数据，界面上却挂在组合详情页里——同一块面板
 * 显示的是另一个口径的数，肉眼看不出来。
 *
 * 事故的结构性原因是：切换器到面板之间是**四段各写一遍的三元表达式**
 * （`kind === 'ledger' ? id : undefined`）。这种写法每加一个面板就复制一次，漏一边
 * 不会报错、不会红，只会安静地显示错口径。收敛成一个函数后，「传不传」只有一处
 * 可以写错，且能被单测钉住。
 *
 * ## 两条约束
 *
 * 1. **`family` 必须返回空对象**，不能返回 `{ ledgerId: null }`：`null` 会被面板当作
 *    「显式传了一个空作用域」，与「不传」在语义上不同（后端对 `null` 与缺参的处理
 *    未必一致）。
 * 2. **没选对象（`id == null`）时同样返回空对象**：此时页面显示的是「请选择账户」，
 *    若把 `undefined` 之外的脏 id 传下去，面板会拉到错误口径或 400。
 */

/** 口径档位：与切换器的三个 radio 一一对应 */
export type ScopeKind = "family" | "ledger" | "portfolio";

/** 面板 props：`ledgerId` 与 `portfolioId` 互斥（后端对同时传 400） */
export interface ScopeProps {
  ledgerId?: number;
  portfolioId?: number;
}

/**
 * 把「当前档位 + 选中对象」翻译成面板 props。
 *
 * @param kind 当前档位
 * @param id 选中的账户 / 组合 id；家庭档或未选择时为 `null`
 * @returns 家庭档 / 未选对象 → `{}`；账户档 → `{ ledgerId }`；组合档 → `{ portfolioId }`
 */
export function toScopeProps(
  kind: ScopeKind,
  id: number | null | undefined
): ScopeProps {
  if (id == null) return {};
  if (kind === "ledger") return { ledgerId: id };
  if (kind === "portfolio") return { portfolioId: id };
  return {};
}
