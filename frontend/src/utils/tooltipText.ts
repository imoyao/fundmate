/**
 * tooltip 文案的**载体判据**：短语与一段说明不该共用同一种气泡。
 *
 * 背景（2026-11-02 截图反馈）：ⓘ 提示走 el-tooltip 的默认深色气泡，而它**没有宽度
 * 上限**——「收益概览」那条口径说明（运行时约 110 字）在 1280 视口里铺成一整行、
 * 实测 1083×32，读起来是一根横条。
 *
 * 仓库里早有结论（#1942 第三轮，见 style/el-tooltip.css 的 rich-tip 段）：深底 / 窄宽 /
 * 居中的气泡适合**一个短语**，一段说明要塞进浅色说明卡。缺的只是这条判据没被
 * 「字符串」这条路径用上——`SectionHeader` 只对 `#info` 插槽挂 rich-tip，
 * 于是同一页里「插槽写的话题」是卡片，「字符串写的话题」仍是横条。
 *
 * 这里不做「调用方自己判断长短」：判断一旦交给调用方，同一页就会两种载体并存。
 * 载体跟着**渲染后的字数**走，调用方只管把话说清楚。
 */

/** 超长文案的宽度上限（与 style/el-tooltip.css 的 --tooltip-max-width-rich 同源） */
export const RICH_TIP_CLASS = "rich-tip";
/** 附加修饰：说明卡内是若干 `<p>`（一句一段），需要段间距 */
export const RICH_TIP_PARA_CLASS = "rich-tip--paragraphs";

/**
 * 升格阈值：**超过 48 字**（约两行）就换说明卡。
 *
 * 数据依据：全站 43 条 `info` 的**运行时**长度是双峰的——28 条 ≤33 字（短语），
 * 14 条 ≥51 字（2~4 句的说明），中间那条空带里没有任何一条（源码里有两条
 * `'共 ' + n + ' 条…'` 的动态文案看着是 44/46 字，实渲染只有 20 字上下，不参与）。
 *
 * 换算也支持同一个数：气泡限宽 320px（`--tooltip-max-width`）、字号 12px、左右内边距
 * 各 11px ⇒ 单行约 24 字，两行约 48 字。「超过两行就换载体」既是可解释的口径，
 * 也正好落在数据空带上。
 */
export const RICH_TIP_MIN_CHARS = 48;

/** 这段文案是否该走说明卡（而不是深色短语气泡） */
export function isRichTipText(text: string): boolean {
  return text.trim().length > RICH_TIP_MIN_CHARS;
}

/**
 * 说明卡里按句分行。
 *
 * 为什么逐句成行：口径说明天然是「一句一个意思」（当前口径是什么 / 这个指标怎么算 /
 * 与别处为什么不同），整段挤在 380px 的方块里仍要逐字找边界；按句分行等于免费得到
 * 几个小标题。
 *
 * 不能在每个 `。` 上一刀切：括号、引号里的句号属于同一句。两个真实例子：
 *
 *   · `按季报/半年报披露的重仓股，比较…（半年报全量 vs 季报前十大）的基金对不比较。`
 *     —— 句号在括号**外**，必须切；
 *   · `按「万份收益 × 持有份额」估算…（XIRR 衡量交易现金流的时间价值），两者不可相加；`
 *     —— 括号内没有句号，但换成 `（见上一节。那里有公式）` 就不能切。
 *
 * 所以按括号 / 引号深度判：深度 > 0 时遇到的句号不切。深度用 `Math.max(0, …)` 兜底，
 * 文案里多写一个右括号也不会让后面的句子永远不切。
 */
export function splitTipSentences(text: string): string[] {
  const OPEN = "（(「『【《";
  const CLOSE = "）)」』】》";
  const out: string[] = [];
  let depth = 0;
  let buf = "";

  // for…of 按码点遍历：中文标点与 ρ / × 这类字符不会被拆成半个代理对
  for (const ch of text) {
    buf += ch;
    if (OPEN.includes(ch)) {
      depth += 1;
    } else if (CLOSE.includes(ch)) {
      depth = Math.max(0, depth - 1);
    } else if (ch === "。" && depth === 0) {
      const sentence = buf.trim();
      if (sentence && sentence.replace(/[。\s]/g, "")) {
        out.push(sentence);
      } else if (sentence && out.length > 0) {
        // 连写两个句号（`…等等。。`）：残段并回上一段。单独成段会被 `<p>` 的段间距
        // 撑成一个空行，看着像文案在这里断了一拍——并回去则一个字都不丢
        out[out.length - 1] += sentence;
      }
      buf = "";
    }
  }

  // 末句常不带句号（`两者不可相加；本项已计入总资产` 这类），别丢
  const rest = buf.trim();
  if (rest) out.push(rest);
  return out;
}

/** 说明卡的段落（短文案返回空数组：深色气泡不需要分行） */
export function tipParagraphs(text: string): string[] {
  return isRichTipText(text) ? splitTipSentences(text) : [];
}

/**
 * 字符串型 tooltip 该挂的 popper-class（短文案返回空串 ⇒ Element Plus 默认深色气泡）。
 *
 * 两个载体（`SectionHeader` 的 `info`、`CrowdingHeaderTip` 的 `content`）都从这里取，
 * 免得一处写 `rich-tip`、另一处忘了挂修饰类，出现「同样是说明卡，段间距却不一样」。
 */
export function tipPopperClass(text: string): string {
  return isRichTipText(text) ? `${RICH_TIP_CLASS} ${RICH_TIP_PARA_CLASS}` : "";
}
