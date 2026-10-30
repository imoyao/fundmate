/**
 * 多标签栏（`.scroll-container`）缓存清洗。
 *
 * ## 为什么需要
 *
 * `multiTags` 在「标签页缓存」开启时整体存进 localStorage（key
 * `<ResponsiveStorageNameSpace>tags`）。这份缓存**跨版本存活**：一旦某个版本
 * 往里写过没有标题的条目，之后每次刷新都会把它读回来，在标签栏渲染成一个
 * **空白标签块**——宽度只剩关闭按钮，鼠标能点但点不出任何信息，控制台还会在
 * 后续 `handleTags` 里抛 `Cannot read properties of undefined (reading 'length')`
 * （旧写法 `tagVal?.meta?.title.length` 只保护了 `meta`，没保护 `title`）。
 *
 * 用户反馈的原话：「标签栏某个标签没有文字，块还在，宽度很小，能点」+「有报错」。
 *
 * ## 口径
 *
 * 一个标签要能显示，必须同时满足：
 * 1. `path` 是非空字符串——否则点击时无法 `router.push`；
 * 2. `meta.title` 是非空字符串——否则渲染出来就是空白块（本函数存在的理由）；
 * 3. 同 `path + query + params` 只保留第一条——缓存里可能攒下重复标签。
 *
 * 清洗在 store 初始化时执行一次，并把结果**写回缓存**：脏数据只清一次，
 * 不会每次刷新都重新长出来。纯函数，node 环境可直接测。
 */

export interface TagLike {
  path?: string | null;
  name?: string | null;
  meta?: { title?: string | null; [key: string]: unknown } | null;
  query?: unknown;
  params?: unknown;
}

/** query/params 的稳定序列化：仅用于去重键，不追求语义等价 */
function stableKey(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value !== "object") return String(value);
  const keys = Object.keys(value as Record<string, unknown>).sort();
  return keys
    .map(k => `${k}=${String((value as Record<string, unknown>)[k] ?? "")}`)
    .join("&");
}

/** 该标签是否**会渲染成一个可见标签**（供清洗与判据共用） */
export function isRenderableTag(tag: TagLike | null | undefined): boolean {
  if (!tag || typeof tag !== "object") return false;
  if (typeof tag.path !== "string" || tag.path.trim() === "") return false;
  const title = tag.meta?.title;
  return typeof title === "string" && title.trim() !== "";
}

/** 清洗标签缓存：剔除渲染不出文字的条目 + 去掉重复项 */
export function sanitizeTags<T extends TagLike>(
  tags: T[] | null | undefined
): T[] {
  if (!Array.isArray(tags)) return [];

  const seen = new Set<string>();
  const out: T[] = [];

  for (const tag of tags) {
    if (!isRenderableTag(tag)) continue;
    const key = `${tag.path}|${stableKey(tag.query)}|${stableKey(tag.params)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(tag);
  }

  return out;
}
