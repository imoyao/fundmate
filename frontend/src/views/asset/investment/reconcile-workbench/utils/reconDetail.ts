/**
 * 处理区的数据上下文（2026-11-07 新增）。
 *
 * 队列是「用户要看什么」，处理区是「用户要动手做什么」。后者复用既有的域面板，
 * 因为它们承载了归因覆盖、删除重复交易、补全 / 回填 / 撤销等真实写路径与二次确认，
 * 重画一遍只会丢掉这些保护。本文件只定义传入这些面板的只读快照类型。
 */
import type { Acting } from "@/components/EaccountReconcilePanel/model";
import type { ReconciliationItem } from "@/api/eaccount";
import type {
  DanglingRefList,
  DiscrepancyItem,
  DividendTaxPendingItem,
  GhostDuplicateGroupItem,
  GhostDuplicateIgnore,
  OrphanLedgerList
} from "@/api/reconciliation";

export interface ReconDetailContext {
  bDiscs: DiscrepancyItem[];
  cDiscs: DiscrepancyItem[];
  loading: boolean;
  eItems: ReconciliationItem[];
  eLoading: boolean;
  eActing: Acting;
  ghostGroups: GhostDuplicateGroupItem[];
  ghostIgnored: GhostDuplicateIgnore[];
  ghostLoading: boolean;
  ghostDeletingId: number | null;
  ghostUndoingId: number | null;
  taxItems: DividendTaxPendingItem[];
  taxTotalCents: number;
  taxPendingCount: number;
  /** 按制度暂不扣税（未卖出）的笔数：不进待办，只在列表底部折叠说明 */
  taxDeferredCount: number;
  /** 依法免税（已卖出且持股满一年）的笔数 */
  taxExemptCount: number;
  taxLoading: boolean;
  danglingRefs: DanglingRefList | null;
  danglingLoading: boolean;
  orphanLedgers: OrphanLedgerList | null;
  orphanLoading: boolean;
  /** loader 失败原因，键见 `DETAIL_ERROR_KEY`；空对象表示全部加载成功 */
  errors: Record<string, string>;
}

/** 域 → 负责它的 loader 错误键。失败时只重试这一个 loader，不整页重跑。 */
export const DETAIL_ERROR_KEY: Record<string, string> = {
  A: "eaccount",
  B: "discrepancies",
  C: "discrepancies",
  D: "ghost",
  E: "tax",
  F: "dangling",
  G: "orphan"
};
