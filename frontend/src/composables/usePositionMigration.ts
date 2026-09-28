import { ElMessage } from "element-plus";
import { updatePosition } from "@/api/positions";
import { updateAsset } from "@/api/assets";
import type { LedgerDetailApi } from "./useLedgerDetail";

export interface LedgerPositionMigrationApi {
  /** 未归置持仓归入指定账户（单条，区别于 MigrationResolvePanel 的批量两段式迁移） */
  handleAssign: (itemId: number) => Promise<void>;
}

/**
 * 批量持仓迁移相关逻辑。
 * 注意：批量迁移的 preview / commit 两段式逻辑已抽至 MigrationResolvePanel.vue 组件，
 * 此处仅搬迁 detail.vue 中残留的「未归置持仓归入账户」单条迁移函数 handleAssign。
 * 共享状态（ledgers / assignMap / ledgerId / loadHoldings）由 useLedgerDetail 持有并传入。
 */
export function usePositionMigration(
  detail: LedgerDetailApi
): LedgerPositionMigrationApi {
  async function handleAssign(itemId: number) {
    const targetLedgerId = detail.assignMap.value[itemId];
    if (!targetLedgerId) return;
    const ledger = detail.ledgers.value.find(l => l.id === targetLedgerId);
    if (!ledger) return;
    try {
      if (itemId > 100000) {
        await updateAsset(itemId - 100000, { account_name: ledger.name });
      } else {
        // 归属迁移走 positions 域端点（PATCH /api/positions/<id>/ 接受 ledger_id）；
        // 原调 ledgers 域 updateLedgerPosition 传 account_name 会被后端静默丢弃（#965 修复）。
        await updatePosition(itemId, {
          ledger_id: targetLedgerId,
          account_name: ledger.name
        });
      }
      ElMessage.success(`已归入「${ledger.name}」`);
      detail.loadHoldings();
    } catch (e) {
      const err = e as { response?: { data?: { message?: string } } };
      ElMessage.error(err?.response?.data?.message || "归入失败");
    }
  }

  return { handleAssign };
}
