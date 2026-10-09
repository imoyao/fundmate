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
 * 行业事实标准，且有真正的单券详情页。
 *
 * ## 外链地址集中于此，禁止散落在模板里
 *
 * 便于集中改口径、加数据源，不必翻组件。
 *
 * ## 实测结论（2026-10-09，curl + 真机 Edge 双重验证，勿凭印象改）
 *
 * 1. **集思录有单券详情页**：`/data/convert_bond_detail/<bond_id>`
 *    （如 `/data/convert_bond_detail/127089` =晶澳转债）。
 *    **但游客访问一律 302 跳登录页**——跳转目标为 `account/login/url-<base64>`，
 *    base64 解码回**原路径本身**（实测 `L2RhdGEvY29udmVydF9ib25kX2RldGFpbC8xMjcwODk=`
 *    → `/data/convert_bond_detail/127089`），证明路由真实存在、只是有登录墙，
 *    **不是 404**；登录后跳回原页，故对已登录用户是好入口。
 * 2. **`bond_id` 就等于 6 位债券代码**（实测 113605→大参转债、118027→宏图转债，
 *    127089→晶澳转债经东财反查确认），因此不需要维护代码→bond_id 映射表。
 * 3. **列表页 `?bond_id=<code>` 只定位不跳转**：`/data/cbnew/?bond_id=` 与
 *    `/data/cbnew/detail_<code>` 都回落到列表页，仅把目标行滚动定位到视口
 *    （实测 `getBoundingClientRect` 命中视口）。定位式跳转**无需登录**，
 *    可作为详情页的游客降级入口。
 * 4. **游客列表口径只有 30/319 只**（页面明示「共有 319 条转债记录，游客仅显示前 30 条」）。
 *    且深链对不可见的债**彻底失效**——113050 / 128142 / 123285 深链打开后
 *    表内仍是那 30 只，页面连代码都不出现。
 *
 * ### 由此得出的文案约束（两条都要写进 UI）
 *
 * - 详情页入口会撞登录墙 → 必须说明「需登录集思录」，否则用户以为是坏链接；
 * - 游客列表定位对多数券失效 → 故**同时**给列表页入口，登录前后都有可用出路。
 *
 * @see docs/working-notes/product-detail-page-design-2026-10-08.md §6（可转债一期只做外链）
 * @see #1400 （条款类数据源待定） #1971 （本卡）
 */

/** 可转债代码：沪市 `11xxxx`、深市 `12xxxx`（含EB，见 `convertible_bond_job.py` 同源判定）。 */
const BOND_CODE_PATTERN = /^1[12]\d{4}$/;

/** 集思录单券详情页（**有登录墙**：游客 302 跳登录页，非 404；登录后跳回原页）。 */
export function buildJisiluBondDetailUrl(symbolOrCode: string): string | null {
  const bondCode = extractBondCode(symbolOrCode);
  if (!bondCode) return null;
  return `https://www.jisilu.cn/data/convert_bond_detail/${bondCode}`;
}

/** 集思录可转债中心列表页（`?bond_id=` 会在列表中定位到该债）。游客可用，但只见前 30 只。 */
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
 *必然 404 的链接，本期外链**不接东财**（可转债行情的事实标准仍是集思录）。
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
 * @param source       `jisilu` = 单券详情页（有登录墙，**首选**）；
 *                     `jisiluList` = 列表定位（游客可用，但只见前 30 只，**降级用**）；
 *                     `eastmoney` 仅深市可用，沪市返回 `null`
 * @returns 完整 URL；代码不合法或该源不支持此市场时返回 `null`（调用方据此不渲染
 *   外链，**不要**回退到数据源首页——那会让用户以为看的就是这只债）
 */
export function buildBondExternalUrl(
  symbolOrCode: string,
  source: "jisilu" | "jisiluList" | "eastmoney"
): string | null {
  const bondCode = extractBondCode(symbolOrCode);
  if (!bondCode) return null;

  switch (source) {
    case "jisilu":
      return buildJisiluBondDetailUrl(symbolOrCode);
    case "jisiluList":
      return `${JISILU_CB_CENTER_URL}?bond_id=${bondCode}`;
    case "eastmoney":
      return buildEastmoneyBondUrl(bondCode);
    default:
      return null;
  }
}

/**
 * 详情页登录墙提示。
 *
 * 实测游客 302 跳登录页，若不说明，用户会以为链接坏了——文案必须点出需登录。
 */
export const BOND_DETAIL_LOGIN_NOTE =
  "单券详情页需登录集思录查看（未登录会跳转到登录页，登录后自动回到该转债）。";

/**
 * 游客列表可见范围说明（实测限制）。
 *
 * 游客口径只有 30/319 只，且深链对不可见的债完全失效；不写清楚的话，
 * 用户跳过去发现列表里没有自己的债，会以为是我们的数据错了或链接坏了。
 */
export const BOND_EXTERNAL_VISIBILITY_NOTE =
  "未登录时集思录列表只展示前 30 只转债，且会自动定位到该债所在位置；" +
  "若列表中找不到，说明它不在游客可见的前 30 只内，登录后即可查看全量（319 只）。";
