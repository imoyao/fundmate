/**
 * 构建期拉取 FeedLog changelog，供docs 站渲染更新日志页。
 *
 * ## 为什么是构建期而不是浏览器端
 *
 * `/api/changelogs` 未返回 `Access-Control-Allow-Origin`，浏览器跨域直读会被拦。
 * 但 VitePress 的页面数据在**构建时于 Node 中执行**，无同源策略 ⇒ 可行。
 * 代价是构建依赖该API 可达（见降级处理）。
 *
 * ## 为什么不在本仓维护第二份
 *
 * 两份真值必然漂移——本项目已吃过这个亏：`docs/spec/changelog.md` 记的是 SPEC
 * **文档**修订号（v4.8.6 那套编号），与软件版本（6.2.0 → 0.1.0）是两套编号，
 * 且已于 2026-09-09 停止维护。**FeedLog 是唯一真值源**，docs 只做展示。
 *
 * 本文件是纯 JS（非 TS）以便 Node 直接执行测试；类型以 JSDoc 标注。
 */

/**
 * @typedef {Object} ChangelogEntry
 * @property {string} id
 * @property {string} slug
 * @property {string} title
 * @property {string} content        Markdown（FeedLog 返回原文）
 * @property {string[]} categories
 * @property {string|null} cover
 * @property {string|null} publishedAt
 * @property {string} [url]          本模块补：FeedLog 详情页绝对地址
 */

/**
 * @typedef {Object} ChangelogResult
 * @property {ChangelogEntry[]} entries
 * @property {boolean} degraded      数据源不可达时为 true，页面显示降级提示而非空白
 * @property {string} [sourceError]
 */

const FEEDLOG_API = 'https://feedback.duoduobei.com/api/changelogs'
const TIMEOUT_MS = 8000
const RETRIES = 3

const sleep = ms => new Promise(r => setTimeout(r, ms))

/**
 * 拉取 changelog 条目。失败时返回 degraded 状态而非抛错——
 * 构建不该因为外部站点抖动而整体失败。
 *
 * ## 为什么需要重试
 *
 * 2026-10-09 实测 feedback 站仍有间歇性 503（约 1/10，见 #2001）。
 * 单次 fetch 撞上 503 就会渲染出**空更新日志页**——这比报错更糟，
 * 因为它看起来是「本来就没有更新」。故失败/异常数据一律重试。
 *
 * @returns {Promise<ChangelogResult>}
 */
export async function loadChangelogEntries() {
  let lastError = ''

  for (let attempt = 1; attempt <= RETRIES; attempt++) {
    try {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
      const res = await fetch(FEEDLOG_API, { signal: controller.signal })
      clearTimeout(timer)

      if (!res.ok) {
        lastError = `HTTP ${res.status}`
        await sleep(500 * attempt)
        continue
      }

      const json = await res.json()
      const raw = json?.data
      if (!Array.isArray(raw)) {
        lastError = '响应缺少 data 数组'
        await sleep(500 * attempt)
        continue
      }

      const entries = raw.map(e => ({
        ...e,
        url: `https://feedback.duoduobei.com/changelog/${encodeURIComponent(e.slug)}`,
      }))
      return { entries, degraded: false }
    }
    catch (err) {
      lastError = err instanceof Error ? err.message : String(err)
      await sleep(500 * attempt)
    }
  }

  return { entries: [], degraded: true, sourceError: lastError || 'unknown' }
}

/**
 * 生成 FeedLog 侧更稳健的 slug 建议（ASCII + 日期 + 版本号）。
 *
 * 背景：FeedLog 的 `slugify()` 保留了中文（正则 `[^\w一-龥]+`），
 * 实测生成 `多多贝-0-1-0-家庭投资理财的账本精灵-375e8bda`。
 * 中文 slug 需百分号编码，分享/粘贴易失效——用户实测点击「查看完整页面」
 * 报「未找到该更新日志」。Vercel / Stripe 等成熟产品一律使用 ASCII slug。
 *
 * 注意：**已发布条目的 slug 不可改**（官方文档：URL 在首次保存时创建，
 * 改标题不改 URL）。本函数仅用于后续新建条目时参考。
 *
 * @param {string} version  如 '0.2.0' 或 'v0.2.0'
 * @param {Date}   [date]
 * @returns {string}  如 '2026-11-15-v0.2.0'
 */
export function suggestSlug(version, date = new Date()) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const v = String(version).replace(/^v/i, '').replace(/[^0-9A-Za-z.-]/g, '')
  return `${y}-${m}-${d}-v${v}`
}