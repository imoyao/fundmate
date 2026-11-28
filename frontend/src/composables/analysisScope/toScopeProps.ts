/**
 * 三级口径（家庭 / 账户 / 组合）→ 面板 props 与 API 查询参数的**唯一出口**（#2595 / #3287）。
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
 *
 * ⚠️ 约束 2 有个反作用：空对象在面板里**就是家庭级**。所以调用方必须先判
 * `isReady`（`composable/analysisScope` 提供），**没选对象时根本不渲染面板**，
 * 不能靠「传空对象」蒙混——那正是 #2595 的形态。
 */

/** 口径档位：与切换器的三档一一对应 */
export type ScopeKind = "family" | "ledger" | "portfolio";

/**
 * 档位 → 界面文案。**唯一一份**：切换器的选项、面包屑式的「当前口径」说明、
 * 降级提示都要引用它。各写一遍必然漂移（出现过「全家庭 / 家庭」两种叫法同屏）。
 */
export const SCOPE_KIND_LABELS: Record<ScopeKind, string> = {
  family: "全家庭",
  ledger: "单账户",
  portfolio: "组合"
};

/** 面板 props：`ledgerId` 与 `portfolioId` 互斥（后端对同时传 400） */
export interface ScopeProps {
  ledgerId?: number;
  portfolioId?: number;
}

/** 切换器的可选项：账户与组合共用同一形态，只有 id 与显示名 */
export interface ScopeOption {
  id: number;
  name: string;
}

/**
 * 接口查询参数：各端点参数名不统一（cash-flow 用 `scope` + id、snapshots 只认
 * `ledger_id`），但**含义只有一份**。这里给出最完整的一种形态，调用方按需取字段，
 * 不要再各自拼 `scope === 'ledger' ? ...` 的三元。
 *
 * `scope` 恒有值（家庭档也要显式发 `family`）：cash-flow 等端点对「两个 id 都不传」
 * 回 400，靠推断会漏。
 */
export interface ScopeQuery {
  scope: ScopeKind;
  ledger_id?: number;
  portfolio_id?: number;
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

/**
 * 把「当前档位 + 选中对象」翻译成接口查询参数。
 *
 * **`scope` 永远等于当前档位**，未选对象时只是不带 id —— 绝不退回 `family`。
 * 这条很关键：退回 family 等于**主动请求家庭级数据**，而界面上写着「单账户」，
 * 比缺参被后端 400 拦下坏得多（后者至少会报错）。调用方本就不该在 `isReady=false`
 * 时取数，这里只是保证「万一取了」也不会静默换口径。
 *
 * @example
 * // 账户档、已选 3 号账户 → { scope: 'ledger', ledger_id: 3 }
 * // 账户档、未选         → { scope: 'ledger' }
 * // 家庭档              → { scope: 'family' }
 */
export function toScopeQuery(
  kind: ScopeKind,
  id: number | null | undefined
): ScopeQuery {
  if (kind === "ledger") {
    return id != null
      ? { scope: "ledger", ledger_id: id }
      : { scope: "ledger" };
  }
  if (kind === "portfolio") {
    return id != null
      ? { scope: "portfolio", portfolio_id: id }
      : { scope: "portfolio" };
  }
  return { scope: "family" };
}
