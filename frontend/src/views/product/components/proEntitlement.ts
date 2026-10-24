// frontend/src/views/product/components/proEntitlement.ts
import { PRO_NOT_ENTITLED_CODE } from "@/constants/errorCodes";

/**
 * Pro 区块的两条口径：**失败态分类**与**付费墙三态**（#2324 前端跟进）。
 * Pro 区块的两条口径：**失败态分类**与**付费墙三态**（#2324 前端跟进）。
 *
 * ## 为什么这两件事必须收口在一个纯函数模块里
 *
 * 1. **403 不都是故障**：三个 Pro 数据端点（`pro-insight` / `pro-risk` /
 *    `pro-allocation`）在家庭未开通时回 `403 + error_code=1007`
 *    （后端 `ErrorCode.PRO_NOT_ENTITLED = (1007, 'Pro 功能未开通', 403)`）。
 *    旧代码 `catch { failed = true }` 把它和超时 / 5xx 一视同仁，用户读到的是
 *    「暂时取不到，稍后再来看看」——对着一条**权益边界**说「稍后再来」，
 *    等于让用户无限期地等一个不会自己变好的状态。
 * 2. **付费墙不再是纯前端 flag**：后端 `/api/products/pro/` 的 `paywall_required`
 *    已按家庭权益计算（`backend/app/services/product_pro_status.py` 的
 *    `build_pro_status`）。env `VITE_PRO_PAYWALL_ENABLED` 与 URL
 *    `?pro_paywall=0|1` 都退化为**显式覆盖**（只管遮罩显隐），两者都未配置时
 *    才以后端为准；覆盖优先级见 `resolvePaywallEnabled` 的判据表。
 *
 * 判定写在模板的 `v-if` 里没法被单测钉住，抽成纯函数才能钉
 * （同族先例：`productIdentityFacts.ts`）。
 */

/** 后端 `ErrorCode.PRO_NOT_ENTITLED` 在本模块的公开名（源自 `@/constants/errorCodes`） */
export { PRO_NOT_ENTITLED_CODE };

/**
 * 区块失败态，三选一：
 *
 * - `none`：正常（含「取到数据」与「取到无数据」两种，都走各自的正常渲染分支）；
 * - `entitlement`：**权益未开通**——边界内的事，文案要讲清楚「开通后可见」；
 * - `error`：其它失败（超时、断网、5xx、解析异常）——「暂时取不到」才是对的。
 *
 * 刻意不给 `error` 起名叫 `failed`：两种态要显示不同文案，混成一个布尔值
 * 就会退回「403 与超时同一条提示」的老样子。
 */
export type ProPanelFailure = "none" | "entitlement" | "error";

/** 请求错误的窄化形状（只取判定需要的两个字段，不把 axios 类型漏进组件） */
interface ProRequestErrorLike {
  response?: {
    status?: number;
    data?: { error_code?: number | string };
  };
}

/**
 * 把一次请求异常归类为「权益未开通」或「其它失败」。
 *
 * 判据是**两个条件同时成立**：HTTP 403 **且** `error_code === 1007`。
 * 只看状态码不够——403 也可能是别的权限（后端其它 `ErrorCode` 同样是 403），
 * 那类要按故障处理，不能冒充「开通 Pro 就好」。
 */
export function classifyProPanelFailure(error: unknown): ProPanelFailure {
  const response = (error as ProRequestErrorLike | null | undefined)?.response;
  if (!response || response.status !== 403) return "error";
  const code = response.data?.error_code;
  if (typeof code === "number") {
    return code === PRO_NOT_ENTITLED_CODE ? "entitlement" : "error";
  }
  // 契约里 `error_code` 是 int；字符串形态一并认（别把健壮性押在序列化上）
  if (typeof code === "string" && Number(code) === PRO_NOT_ENTITLED_CODE) {
    return "entitlement";
  }
  return "error";
}

/**
 * 付费墙开关四态。**顺序有意义**，从高到低：
 * URL 运行时覆盖（`?pro_paywall=0|1`）> env 显式覆盖 > 后端 `paywall_required`。
 *
 * | 来源 | 取值 | 结果 |
 * |---|---|---|
 * | URL `pro_paywall` | `"1"` / `"true"` | 开（运行时强制展示遮罩，本地预览 / e2e 用） |
 * | URL `pro_paywall` | `"0"` / `"false"` | 关（运行时强制隐藏遮罩） |
 * | env `VITE_PRO_PAYWALL_ENABLED` | `"false"` | 关（构建期放行口，见 `playwright.config.ts`） |
 * | env `VITE_PRO_PAYWALL_ENABLED` | `"true"` | 开（构建期强制展示） |
 * | 以上都未配置 / 其它取值 | — | 用后端 `paywall_required`（已按家庭权益算） |
 *
 * 不认识的取值（如 `"yes"`、`"2"`）按**未配置**处理，逐层往下落：
 * 开关值不猜，猜错的代价是「已授权用户被遮住」或「未授权用户绕过遮罩」，
 * 两个都不该由拼写决定。
 *
 * **URL / env 只管遮罩显隐，不是权益事实**（#2523）：介绍卡两态的判据是后端
 * `paywall_required` 一个来源，挂 env 或 URL 都会让「e2e 关了遮罩，介绍卡
 * 也跟着消失」这类串味出现。遮罩表达的是「已确认未开通」的提示层，
 * `paywallRequired` 为 `null` / `undefined` ⇒ 状态位还没回来 ⇒ **不显示遮罩**：
 * 「还没问出来」不等于「未开通」，后者挂遮罩就是拿猜测当结论。
 *
 * URL 取值的读取形态（hash 路由）：`/#/fund/<symbol>?pro_paywall=1`——
 * 查询串在 hash 里，由 vue-router 解析进 `route.query`；本函数只收解析后的
 * 字符串，不自己碰 `window.location`（纯函数才能被单测钉住）。
 */
export function resolvePaywallEnabled(
  urlFlag: string | null | undefined,
  envFlag: string | null | undefined,
  paywallRequired: boolean | null | undefined
): boolean {
  const url = (urlFlag ?? "").trim();
  if (url === "1" || url === "true") return true;
  if (url === "0" || url === "false") return false;
  const env = (envFlag ?? "").trim();
  if (env === "false") return false;
  if (env === "true") return true;
  return paywallRequired === true;
}
