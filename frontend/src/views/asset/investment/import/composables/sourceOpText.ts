/**
 * 预览行「券商原文」的展示判据。
 *
 * 预览行的 `notes` 装的是券商原文操作名（解析器侧的 `raw_op_type`，落库时也会写进
 * 该笔流水的备注）。它在多数行上只是把操作列刚说过的话再说一遍：「证券买入」对应
 * 操作列的「买入 · 股票」——同一件事说两遍，还挤掉产品列里真正有信息量的那个位置。
 *
 * 判据只做字面包含（双向）：原文与已认定的操作标签互相包含，就认为没带来新信息。
 * 认不出来的原文（「债券兑息」「利息归本」「OTC现金宝交」）照常显示——用户正是靠它
 * 判断「券商这句话被认成了什么」，一律隐藏等于把唯一的核对线索藏起来。
 */

/** 比较时忽略的装饰性字符：避免「拆分/送股」与「送股」因为一个斜杠被判成两条不同的事 */
const IGNORABLE = /[\s·・/、,，。()（）[\]【】]/g;

function normalize(text: string): string {
  return text.replace(IGNORABLE, "");
}

/**
 * 原文是否只是「已认定的操作」的另一种写法。
 *
 * 单字标签（如「买」）拿去做包含判断几乎必中，此时宁可留着原文；`op_type_label`
 * 为空（解析失败 / 未映射）也一律返回 false——那种情况下原文才是唯一线索。
 */
export function isRedundantSourceOp(
  srcText?: string | null,
  opLabel?: string | null
): boolean {
  const raw = normalize(srcText || "");
  const label = normalize(opLabel || "");
  if (raw.length < 2 || label.length < 2) return false;
  return raw.includes(label) || label.includes(raw);
}

/** 产品列里该显示的原文；空串表示「这条不用再说一遍」 */
export function visibleSourceOp(row: {
  notes?: string | null;
  op_type_label?: string | null;
}): string {
  const text = (row.notes || "").trim();
  if (!text) return "";
  return isRedundantSourceOp(text, row.op_type_label) ? "" : text;
}
