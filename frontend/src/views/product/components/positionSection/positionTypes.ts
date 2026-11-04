import type { Position } from "@/api/types";
import type { ChannelTotals } from "../productPositionMetrics";

/**
 * 按账户（渠道）聚合后的一组持仓（#980 拆分时从父组件抽出）。
 *
 * 父组件负责聚合，子组件只负责画——所以类型必须放在两侧都能引用的地方，
 * 否则「网格」与「表格」两种形态会各自定义一份，字段名一漂就静默错位。
 */
export interface ChannelGroup extends ChannelTotals {
  key: string;
  name: string;
  /** 未归档持仓为 null：**没有落点**，渲染时不得给它套跳转 */
  ledgerId: number | null;
  rows: Position[];
}
