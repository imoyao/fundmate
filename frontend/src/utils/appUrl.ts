/**
 * 应用内绝对 URL（含 hash 模式适配）与「旧式路径 URL」归一化。
 *
 * ## 为什么需要这个文件（2026-10-24 实测故障）
 *
 * 应用站是 **hash 模式**（`VITE_ROUTER_HISTORY="hash"`），但回跳地址此前按**路径**拼：
 * `${window.location.origin}/reset-password`。浏览器打开这种链接时
 * `pathname=/reset-password`、`hash` 为空 —— vue-router 在 hash 模式下读不到路由，
 * 按根路由处理，已登录就被守卫送去 `/welcome`，地址栏于是出现
 * `http://localhost:8848/reset-password#/welcome` 这种「路径 + 另一个页面」的畸形 URL。
 *
 * 判据只有一条：**hash 模式的回跳必须写成 `${origin}${base}#${path}`**。
 * 因此 Supabase 的 `redirectTo` / `emailRedirectTo` 一律走 {@link buildAppUrl}，
 * 不要手拼字符串；旧邮件里的路径式链接由 {@link redirectLegacyUrlToHash} 兜底归一化。
 */

/** 文档站域名（隐私政策 / 用户协议在这里，与应用站分域，见 docs/ops/deployment.md） */
export const DOCS_SITE_URL = "https://docs.duoduobei.com";

export interface AppUrlOptions {
  /** 覆盖 origin（默认取 window.location.origin；纯函数测试用） */
  origin?: string;
  /** 覆盖 base（默认取 import.meta.env.BASE_URL） */
  base?: string;
  /** 覆盖路由历史模式（默认取 import.meta.env.VITE_ROUTER_HISTORY） */
  historyMode?: string;
}

/** 缺省按 hash 处理：漏配历史模式时，宁可生成 `#/x` 也不要生成会 404 的 `/x`。 */
const DEFAULT_HISTORY_MODE = "hash";

/** 当前（或给定）路由是否 hash 模式。 */
export function isHashHistory(
  mode: string | undefined = import.meta.env.VITE_ROUTER_HISTORY as
    string | undefined
): boolean {
  // 容忍 `.env` 里残留的成对引号（`VITE_ROUTER_HISTORY="hash"`）：Vite 通常会剥掉，
  // 但历史上出现过带引号被当真值的情况，这里不赌配置格式。
  return String(mode || DEFAULT_HISTORY_MODE)
    .trim()
    .replace(/^["']|["']$/g, "")
    .toLowerCase()
    .startsWith("hash");
}

/** base 统一成「以 / 开头、以 / 结尾」，避免拼出 `origin//x` 或 `origin/sub#/x`。 */
function normalizeBase(base: string | undefined): string {
  const raw = (base || "/").trim();
  const withLeading = raw.startsWith("/") ? raw : `/${raw}`;
  return withLeading.endsWith("/") ? withLeading : `${withLeading}/`;
}

/** 把应用内路径拼成可直接放进 redirectTo 的绝对 URL。 */
export function buildAppUrl(path = "/", opts: AppUrlOptions = {}): string {
  const origin = (
    opts.origin ?? (typeof window !== "undefined" ? window.location.origin : "")
  ).replace(/\/+$/, "");
  const base = normalizeBase(
    opts.base ?? (import.meta.env.BASE_URL as string | undefined)
  );
  const p = path.startsWith("/") ? path : `/${path}`;
  return isHashHistory(opts.historyMode)
    ? `${origin}${base}#${p}`
    : `${origin}${base.replace(/\/$/, "")}${p}`;
}

/**
 * 把「路径式 URL」换算成 hash 式（纯函数）。
 *
 * 只在 **pathname 带了一段不该出现在 hash 模式地址里的路径** 时才动手：
 *
 * | 输入 | 输出 | 说明 |
 * |---|---|---|
 * | `/reset-password?code=abc` | `/#/reset-password?code=abc` | 旧邮件里的路径式链接 |
 * | `/reset-password#/welcome` | `/#/welcome` | 畸形 URL：pathname 已经没用了，以 hash 路由为准 |
 * | `/reset-password#/` | `/#/reset-password` | `#/` 是空路由（vue-router 会把空 hash 规整成它） |
 * | `/#/welcome` | `null` | 正常地址，不动 |
 *
 * @returns 需要跳转的目标（`/` 开头的站内地址，含 search）；无需跳转返回 `null`
 */
export function toHashUrl(
  pathname: string,
  search = "",
  hash = "",
  opts: AppUrlOptions = {}
): string | null {
  if (!isHashHistory(opts.historyMode)) return null;

  // vue-router 建 history 时会把空 hash 规整成 `#/`，因此 `#/` 与「没有 hash」等价；
  // 只有 `#/x` 这类真实路由才算「已经有路由」，不能当成空 hash 再搬一次 pathname。
  const emptyHash = !hash || hash === "#" || hash === "#/";

  const base = normalizeBase(
    opts.base ?? (import.meta.env.BASE_URL as string | undefined)
  );
  const baseNoSlash = base.replace(/\/$/, "");
  if (
    !pathname ||
    pathname === "/" ||
    pathname === base ||
    pathname === baseNoSlash
  ) {
    return null;
  }

  let p = pathname;
  if (base !== "/" && (p === baseNoSlash || p.startsWith(base))) {
    p = `/${p.slice(base.length)}`;
  }

  // 走到这里说明 pathname 是站内深链接：它必须被搬进 hash，否则会留下
  // `/reset-password#/welcome` 这种「路径 + 另一个页面」的畸形地址。
  // 有真实 hash 路由时以 hash 为准 —— 那才是路由实际解析出的页面。
  const route = emptyHash ? `${p}${search}` : hash.slice(1);
  return `${base}#${route.startsWith("/") ? route : `/${route}`}`;
}

/**
 * 启动期兜底：旧邮件/旧书签里的路径式链接（`/reset-password?code=…`）自动换成
 * `/#/reset-password?code=…`，保住 query（PKCE 的 code 就在 query 里）。
 *
 * @returns 是否发生了跳转
 */
export function redirectLegacyUrlToHash(): boolean {
  if (typeof window === "undefined") return false;
  const target = toHashUrl(
    window.location.pathname,
    window.location.search,
    window.location.hash
  );
  if (!target) return false;
  window.history.replaceState(null, "", target);
  return true;
}
