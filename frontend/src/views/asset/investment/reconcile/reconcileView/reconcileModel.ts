/**
 * E账户对账页的纯函数层（#980 拆分）。
 *
 * 收进来的三类东西，都是「改一处漏一处会静默出错」的：
 * 1. 状态枚举（`STATUS_OPTIONS` / `STATUS_META`）——筛选器和状态标签各用一份字段，
 *    新增状态时漏改一处就是「筛得出来、标签却白屏」；
 * 2. 差异涨跌色（`diffClass`）——正红负绿，写反了只有用户看得出来；
 * 3. 归因 / 忽略的请求体与确认文案——两条操作唯一的区别就是 action 与措辞，
 *    复制两份就一定会漂移。
 *
 * 不 import 组件 / 路由 / 请求，保证可在 node 环境直接跑。
 */
import type { ReconciliationItem } from "@/api/eaccount";

export type ReconcileStatus = ReconciliationItem["status"];

/** 归因动作：覆盖（破坏性）/ 忽略（非破坏性，可重新对账恢复） */
export type AttributionAction = "cover" | "ignore";

/** 筛选器的「全部」哨兵值——后端没有这个状态，只存在于前端筛选 */
export const STATUS_ALL = "all";

/** 一级状态筛选选项（SegmentedControl） */
export const STATUS_OPTIONS: { label: string; value: string }[] = [
  { label: "全部", value: STATUS_ALL },
  { label: "待处理", value: "pending" },
  { label: "已归因", value: "attributed" },
  { label: "已忽略", value: "ignored" },
  { label: "已核对", value: "verified" }
];

/** 状态标签元信息：标签文字 + 自定义色类（四态语义区分） */
export const STATUS_META: Record<
  ReconcileStatus,
  { label: string; className: string }
> = {
  pending: { label: "待处理", className: "status-tag--pending" },
  attributed: { label: "已归因", className: "status-tag--attributed" },
  ignored: { label: "已忽略", className: "status-tag--ignored" },
  verified: { label: "已核对", className: "status-tag--verified" }
};

/** 兼容「信封 {data}」与「直接返回」两种响应形态（并行 lane 契约以直接返回为准） */
export function unwrap<T>(res: unknown): T {
  const r = res as { data?: T } | null;
  if (r && typeof r === "object" && "data" in r && r.data != null)
    return r.data;
  return res as T;
}

/** 统一错误文案提取：后端信封 message 优先，其次 Error.message */
export function errMsg(e: unknown, fallback: string): string {
  const err = e as {
    response?: { data?: { message?: string } };
    message?: string;
  };
  return err?.response?.data?.message || err?.message || fallback;
}

/** 客户端过滤：`all` 走全量，其余按状态精确匹配（四态计数保持全量口径） */
export function filterByStatus(
  items: ReconciliationItem[],
  status: string
): ReconciliationItem[] {
  if (status === STATUS_ALL) return items;
  return items.filter(item => item.status === status);
}

/** 客户端分页：在**筛选结果**上切片，只翻页不改过滤口径 */
export function slicePage<T>(items: T[], page: number, pageSize: number): T[] {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

/**
 * 差异涨跌语义：正=E账户多于系统（涨红）、负=少于系统（跌绿）、零=中性。
 * 符号与数字同色（design.md「正负符号强制约束」），故符号在模板里与数字同格。
 */
export function diffClass(diff: number): string {
  if (diff > 0) return "is-rise";
  if (diff < 0) return "is-fall";
  return "is-zero";
}

/**
 * 归因 / 忽略的确认框配置。
 *
 * 两条操作只有措辞与危险级别不同：覆盖会**删除**渠道原记录（不可撤销），
 * 所以确认按钮要染成危险色（`reconcile-confirm-danger` 走全局样式，因为
 * ElMessageBox 渲染在 body 下，scoped 样式不可达）；忽略可恢复，走默认主按钮。
 */
export const ACTION_META: Record<
  AttributionAction,
  {
    title: string;
    type: "warning" | "info";
    confirmText: string;
    /** 危险操作的确认按钮类名；非危险操作不设 */
    confirmClass?: string;
    okMessage: string;
    /** 部分失败时的前缀，末尾拼「N 条未成功」 */
    partialPrefix: string;
  }
> = {
  cover: {
    title: "归因覆盖",
    type: "warning",
    confirmText: "确认覆盖",
    confirmClass: "reconcile-confirm-danger",
    okMessage: "归因覆盖完成",
    partialPrefix: "归因覆盖完成，但有"
  },
  ignore: {
    title: "忽略该记录",
    type: "info",
    confirmText: "确认忽略",
    okMessage: "已忽略该记录",
    partialPrefix: "忽略完成，但有"
  }
};

/** 确认框正文：覆盖要明说会删掉渠道原记录，忽略要明说可以恢复 */
export function confirmMessageOf(
  action: AttributionAction,
  row: Pick<ReconciliationItem, "name" | "symbol">
): string {
  const who = row.name || row.symbol;
  return action === "cover"
    ? `将以 E账户快照覆盖「${who}」在对应销售渠道的旧持仓，删除渠道原记录。此操作不可撤销。`
    : `忽略后「${who}」在后续 E账户导入中自动跳过，可稍后重新对账恢复。`;
}

/**
 * 归因请求体。
 * 三个字段后端都按字符串收，`null` 会落到 NOT NULL 约束上，故一律回落空串。
 */
export function attributionPayload(
  row: Pick<ReconciliationItem, "symbol" | "source_broker" | "fund_manager">,
  action: AttributionAction
) {
  return {
    symbol: row.symbol,
    source_broker: row.source_broker || "",
    fund_manager: row.fund_manager || "",
    action
  };
}

/** 当前正在执行归因/忽略的记录（行内按钮 loading 定位） */
export interface Acting {
  recordId: number | null;
  action: AttributionAction | null;
}

/**
 * 某个按钮是否处于 loading。
 * 页面持有 `Acting`、表格按行查询，两边共用这一个判定——写两遍就会出现
 * 「点了 A 行、B 行也在转」这种只在长列表上才看得见的错位。
 */
export function isActingOf(
  acting: Acting,
  recordId: number,
  action: AttributionAction
): boolean {
  return acting.recordId === recordId && acting.action === action;
}

/** 结果文案：全部成功走 okMessage，部分失败降级为 warning 并带上条数 */
export function attributionResultMessage(
  action: AttributionAction,
  failed: number
): { type: "success" | "warning"; message: string } {
  const meta = ACTION_META[action];
  if (failed > 0)
    return {
      type: "warning",
      message: `${meta.partialPrefix} ${failed} 条未成功`
    };
  return { type: "success", message: meta.okMessage };
}
