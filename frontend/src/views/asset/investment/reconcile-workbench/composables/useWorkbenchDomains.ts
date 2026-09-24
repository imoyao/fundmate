import { ref, computed } from "vue";
import { ElMessage } from "element-plus";
import {
  runReconciliation,
  listDiscrepancies,
  ignoreDiscrepancy,
  type DiscrepancyItem
} from "@/api/reconciliation";
import {
  getEaccountReconciliation,
  attributeEaccount,
  type ReconciliationItem
} from "@/api/eaccount";
import { confirmImport, confirmHoldingImport } from "@/api/importer";
import type { OcrHoldingRow } from "@/api/ocr";
import {
  useReconDraft,
  type RecognizerCandidate
} from "@/composables/useReconDraft";

/**
 * 对账工作台三域数据与操作（#980 拆分自 index.vue 的 composables/ 步骤，零行为变更）
 *
 * - 域 B：持仓快照差异（discrepancies）加载 / 运行对账 / 忽略 / 就地补充后的刷新；
 * - 域 A：E账户对账（eaccount）加载 / 归因覆盖 / 忽略；
 * - 识别候选草稿（#1250）：加载 / 确认入库（跨域触发对账）/ 丢弃。
 *
 * 三域动作存在交叉调用（确认入库后须同时刷新域 A/B/C），故合并为单一 composable，
 * 避免为消除表面耦合而引入回调注入的间接层（抽象克制原则 §3.5）。
 */
export function useWorkbenchDomains() {
  /** 识别候选草稿（P3-1 / #1250）：AI 识别结果落 recon-draft:recognizer，由工作台加载 */
  const { getRecognizerCandidates, clearRecognizerCandidates } =
    useReconDraft();
  const recognizerCandidates = ref<RecognizerCandidate[]>([]);
  const committing = ref(false);

  /** 差异数据 */
  const discs = ref<DiscrepancyItem[]>([]);
  const loading = ref(false);
  const running = ref(false);

  /** 域 A：E账户对账数据（P2 迁入） */
  const eItems = ref<ReconciliationItem[]>([]);
  const eLoading = ref(false);
  const actingRecordId = ref<number | null>(null);
  const actingAction = ref<"cover" | "ignore" | null>(null);

  /** 域 B 差异：仅展示待处理（pending）行，使下方表格与顶部「待裁决差异」口径一致（#1259） */
  const bDiscs = computed(() =>
    discs.value.filter(d => d.domain === "B" && d.status === "pending")
  );

  /** 全局待处理总数，仅用于 Banner 提醒（不要求与单表对齐） */
  const totalPending = computed(() => {
    const fromDiscs = discs.value.filter(d => d.status === "pending").length;
    const fromE = eItems.value.filter(i => i.status === "pending").length;
    return fromDiscs + fromE;
  });
  /** 数据日期：最近一次差异的 updated_at 或今日 */
  const dataDateLabel = computed(() => {
    const t = discs.value
      .map(d => d.updated_at)
      .filter(Boolean)
      .sort()
      .pop();
    return t ? t.slice(0, 10) : "—";
  });

  /** 是否有待处理差异（Banner 显示条件，用全局总数判断） */
  const hasPending = computed(() => totalPending.value > 0);

  /** 各域待处理 / 已忽略计数（域 A 来自 E账户链路 eItems，域 B/C 来自 discrepancies discs），
   *  用于顶部指标与 Tab 角标，使统计口径与用户当前可见域一致（#1259） */
  function domainPending(key: string): number {
    if (key === "A")
      return eItems.value.filter(i => i.status === "pending").length;
    return discs.value.filter(d => d.domain === key && d.status === "pending")
      .length;
  }
  function domainIgnored(key: string): number {
    if (key === "A")
      return eItems.value.filter(i => i.status === "ignored").length;
    return discs.value.filter(d => d.domain === key && d.status === "ignored")
      .length;
  }

  /** 加载识别候选草稿（P3-1 / #1250）：AI 识别结果落 recon-draft:recognizer，跨页/刷新承接不丢 */
  async function loadRecognizerCandidates(): Promise<void> {
    try {
      recognizerCandidates.value = await getRecognizerCandidates();
    } catch {
      recognizerCandidates.value = [];
    }
  }

  /** 确认入库（#1251 / #1252）：剥离 kind → 既有导入确认端点，再触发对应域对账 */
  async function commitCandidates(kind: "txn" | "holding"): Promise<void> {
    const list = recognizerCandidates.value.filter(c => c.kind === kind);
    if (list.length === 0) return;
    committing.value = true;
    try {
      // 候选行即 OCR 预览行，剥离 kind 后原样回传确认端点（txn/hodling 各自落库管线）
      const rows = list.map(c => {
        const { kind: _k, ...row } = c;
        return row;
      });
      if (kind === "txn") {
        const res = await confirmImport(rows);
        ElMessage.success(
          `已入库 ${res?.data?.imported ?? rows.length} 条交易，已触发域 C 对账`
        );
      } else {
        const res = await confirmHoldingImport(rows as OcrHoldingRow[]);
        ElMessage.success(
          `已入库 ${res?.data?.imported ?? rows.length} 条持仓，已刷新域 A 对账`
        );
      }
      await clearRecognizerCandidates(kind);
      await loadRecognizerCandidates();
      if (kind === "txn") {
        await runReconciliation("C");
      } else {
        await loadEAccount();
      }
      await loadDiscrepancies();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { message?: string } } };
      ElMessage.error(err.response?.data?.message || "入库失败");
    } finally {
      committing.value = false;
    }
  }

  /** 丢弃识别草稿 */
  async function discardCandidates(): Promise<void> {
    await clearRecognizerCandidates();
    await loadRecognizerCandidates();
    ElMessage.info("已丢弃识别草稿");
  }

  /** 加载差异列表 */
  async function loadDiscrepancies(): Promise<void> {
    loading.value = true;
    try {
      const res = await listDiscrepancies();
      discs.value = res.data ?? [];
    } catch {
      discs.value = [];
    } finally {
      loading.value = false;
    }
  }

  /** 加载 E账户对账中心数据（域 A） */
  async function loadEAccount(): Promise<void> {
    eLoading.value = true;
    try {
      const res = await getEaccountReconciliation();
      const data = (res as any).data ?? {};
      eItems.value = (data.items ?? []) as ReconciliationItem[];
    } catch {
      eItems.value = [];
    } finally {
      eLoading.value = false;
    }
  }

  /** 归因覆盖（危险操作：删除渠道原记录，P2 迁入工作台） */
  async function handleEAccountCover(row: ReconciliationItem): Promise<void> {
    actingRecordId.value = row.record_id;
    actingAction.value = "cover";
    try {
      const res = await attributeEaccount([
        {
          symbol: row.symbol,
          source_broker: row.source_broker || "",
          fund_manager: row.fund_manager || "",
          action: "cover"
        }
      ]);
      const result = (res as any).data ?? {};
      if (result.failed > 0) {
        ElMessage.warning(`归因覆盖完成，但有 ${result.failed} 条未成功`);
      } else {
        ElMessage.success("已归因覆盖");
      }
      await loadEAccount();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "归因覆盖失败");
    } finally {
      actingRecordId.value = null;
      actingAction.value = null;
    }
  }

  /** 忽略（E账户，导入自动跳过，可重新对账恢复） */
  async function handleEAccountIgnore(row: ReconciliationItem): Promise<void> {
    actingRecordId.value = row.record_id;
    actingAction.value = "ignore";
    try {
      const res = await attributeEaccount([
        {
          symbol: row.symbol,
          source_broker: row.source_broker || "",
          fund_manager: row.fund_manager || "",
          action: "ignore"
        }
      ]);
      const result = (res as any).data ?? {};
      if (result.failed > 0) {
        ElMessage.warning(`忽略完成，但有 ${result.failed} 条未成功`);
      } else {
        ElMessage.success("已忽略");
      }
      await loadEAccount();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "忽略失败");
    } finally {
      actingRecordId.value = null;
      actingAction.value = null;
    }
  }

  /** 运行对账（域 B） */
  async function handleRun(): Promise<void> {
    running.value = true;
    try {
      await runReconciliation("B");
      ElMessage.success("对账完成");
      await loadDiscrepancies();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "对账失败");
    } finally {
      running.value = false;
    }
  }

  /** 忽略一条差异（临时） */
  async function handleIgnore(row: DiscrepancyItem): Promise<void> {
    try {
      await ignoreDiscrepancy(row.id, { permanent: false });
      ElMessage.success("已忽略");
      await loadDiscrepancies();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "忽略失败");
    }
  }

  return {
    loading,
    running,
    discs,
    bDiscs,
    eItems,
    eLoading,
    recognizerCandidates,
    committing,
    totalPending,
    hasPending,
    dataDateLabel,
    domainPending,
    domainIgnored,
    loadDiscrepancies,
    loadEAccount,
    loadRecognizerCandidates,
    commitCandidates,
    discardCandidates,
    handleRun,
    handleIgnore,
    handleEAccountCover,
    handleEAccountIgnore
  };
}
