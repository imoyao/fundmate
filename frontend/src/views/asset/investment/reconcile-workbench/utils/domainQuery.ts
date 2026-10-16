import type { WorkbenchDomainKey } from "../constants/domainTabs";

/**
 * 把 URL 查询参数里的域标识收窄成合法的 `WorkbenchDomainKey`（#2151）。
 *
 * WHY 单独一个纯函数：域 D 的「横幅 → 工作台」跳转靠 `?domain=D` 落地，而浏览器
 * 地址栏是用户可改的输入面——`?domain=X`、`?domain=`、`?domain=A&domain=B`
 * （vue-router 对重复参数返回**数组**）都会进来。收窄规则要能脱离组件单测，
 * 而不是埋在 `index.vue` 里靠肉眼保证。
 *
 * 非法 / 缺失一律返回 `null`（由调用方决定回落值），而不是在此默认成某个域——
 * 「初值回落 B」与「地址栏改成非法值时不动 tab」是两条不同的策略，不该混在一个函数里。
 */
export function normalizeDomain(raw: unknown): WorkbenchDomainKey | null {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return v === "A" || v === "B" || v === "C" || v === "D" ? v : null;
}
