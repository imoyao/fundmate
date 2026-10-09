// frontend/src/utils/bondExternalLinks.ts
/**
 * 可转债外部数据源深链构造（#1971 · 一期只做外链卡，不做内部详情页）。
 *
 * ## 为什么可转债一期只给外链
 *
 * 可转债的决策核心是**条款博弈**（强赎 / 下修 / 回售），条款状态优先于行情。
 * 本地 `convertible_bond_terms` 只落了**静态条款**（见 `models.py` 注释），
 * YTM / 下修历史 / 正股 PB 等关键项仍缺（#1400）。与其用残缺数据做一个
 * 「看起来完整」的内部详情页，不如把深度分析交给集思录——它是这块数据的
 * 行业事实标准。
 *
 * ## 外链地址集中于此，禁止散落在模板里
 *
 * 便于集中改口径、加数据源，不必翻组件。
 *
 * ## 实测结论（2026-10-09，真机 Edge 验证，勿凭印象改）
 *
 * 1. 集思录**没有单券详情页**。`/data/cbnew/detail_<code>` 与
 *    `/data/cbnew/?bond_id=<code>` 都会**回落到可转债列表页**，
 *    区别只是把目标那行滚动定位到视口（实测 `getBoundingClientRect` 命中视口）。
 *    `cb_detail/?bond_id=` 才是真 404，故不使用。
 * 2. `bond_id` **就等于 6 位债券代码**（实测 113605→大参转债、118027→宏图转债），
 *    因此不需要单独维护代码→bond_id 映射表。
 * 3. **游客口径只返回前 30 条**（实测页面明示「共有 319 条转债记录，游客仅显示前 30 条」，
 *    实测 113050 / 128142 / 123285 三只深链打开后表内仍是那 30 只，页面连代码都不出现）。
 *    故外链**不能承诺**「跳过去就能看到这只债」，文案必须如实说明可见范围。
 *    用户登录后可见全量，深链定位随即生效。
 *
 * @see docs/working-notes/product-detail-page-design-2026-10-08.md §6（可转债一期只做外链）
 * @see #1400 （条款类数据源待定） #1971 （本卡）
 */

/** 可转债代码：沪市 `11xxxx`、深市 `12xxxx`（含EB，见 `convertible_bond_job.py` 同源判定）。 */
const BOND_CODE_PATTERN = /^1[12]\d{4}$/;

/** 集思录可转债中心（`?bond_id=` 深链会在列表页定位到该债）。 */
export const JISILU_CB_CENTER_URL = "https://www.jisilu.cn/data/cbnew/";

/** 集思录强赎进度追踪（登录态可见，游客受限）。 */
export const JISILU_CB_REDEEM_URL = "https://www.jisilu.cn/data/cbnew/redeem/";

/**
 * 东方财富转债单券页——**只在深市（`12xxxx`）实测可用**，沪市不可用，故本期不接。
 *
 * 实测（2026-10-09）：
 * - 深市 `https://quote.eastmoney.com/bond/sz128142.html` → 200，
 *   title 为「新乳转债(128142)_行情中心_东方财富网」（123285 / 123270 同样命中）；
 * - 沪市 `.../bond/sh113050.html` → **302 跳 `https://quote.eastmoney.com/q/1.113050.html`
 *   后 404**；写成 `sh.113050` / `1.113050` 同样 302→404。
 *
 * 即东财对沪市转债没有可用的单券页。可转债约一半在沪市，为避免给沪市转债一个
 * 必然 404 的链接，本期外链**只给集思录**（可转债行情的事实标准，且沪深都能定位）。
 * 深市若后续要接，走 `https://quote.eastmoney.com/bond/sz<code>.html` 并按市场分流。
 */
export function buildEastmoneyBondUrl(bondCode: string): string | null {
  if (!bondCode.startsWith("12")) return null;
  return `https://quote.eastmoney.com/bond/sz${bondCode}.html`;
}

/** 从标准化 symbol（如 `SH113050`）或裸 6 位代码中取出债券代码；取不出返回 null。 */
export function extractBondCode(symbolOrCode: string): string | null {
  const raw = (symbolOrCode ?? "").trim().toUpperCase();
  if (BOND_CODE_PATTERN.test(raw)) return raw;
  // 形如 SH113050 / SZ128142：前缀只用于确定市场，代码本身仍是 1x/2x 开头六位
  const stripped = raw.replace(/^(SH|SZ|BJ)/, "");
  return BOND_CODE_PATTERN.test(stripped) ? stripped : null;
}

/**
 * 构造可转债的外部数据源深链。
 *
 * @param symbolOrCode 标准化 symbol（`SH113050`）或裸 6 位债券代码
 * @param source       目标数据源。`jisilu` 沪深均可用；`eastmoney` **仅深市可用**，
 *                     沪市返回 `null`（见 `buildEastmoneyBondUrl` 的实测结论）
 * @returns 完整 URL；代码不合法或该源不支持此市场时返回 `null`（调用方据此不渲染
 *   外链，**不要**回退到数据源首页——那会让用户以为看的就是这只债）
 */
export function buildBondExternalUrl(
  symbolOrCode: string,
  source: "jisilu" | "eastmoney"
): string | null {
  const bondCode = extractBondCode(symbolOrCode);
  if (!bondCode) return null;

  switch (source) {
    case "jisilu":
      return `${JISILU_CB_CENTER_URL}?bond_id=${bondCode}`;
    case "eastmoney":
      return buildEastmoneyBondUrl(bondCode);
    default:
      return null;
  }
}

/**
 * 外链可见性说明（游客口径限制，见本文件顶部实测结论第 3 条）。
 *
 * 一期外链卡的文案必须带上这句，否则用户跳过去发现列表里没有自己的债，
 * 会以为是我们的数据错了或链接坏了。
 */
export const BOND_EXTERNAL_VISIBILITY_NOTE =
  "集思录未登录时仅展示前 30 只转债，列表会自动定位到该债所在位置；" +
  "若列表中找不到，说明它不在游客可见的前 30 只内，登录集思录即可查看全量（319 只）。";
