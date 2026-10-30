import { ref, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  runReconciliation,
  listDiscrepancies,
  ignoreDiscrepancy,
  listGhostDuplicates,
  listGhostDuplicateIgnores,
  ignoreGhostDuplicate,
  undoGhostDuplicateIgnoreById,
  listDividendTaxPending,
  type DividendTaxPendingItem,
  type DiscrepancyItem,
  type GhostDuplicateGroupItem,
  type GhostDuplicateIgnore,
  type GhostDuplicateTxn
} from "@/api/reconciliation";
import { deleteTransaction } from "@/api/transaction";
import {
  getEaccountReconciliation,
  type ReconciliationItem
} from "@/api/eaccount";
import { useEaccountActions } from "@/components/EaccountReconcilePanel/useActions";
import type { Acting } from "@/components/EaccountReconcilePanel/model";
import { confirmImport, confirmHoldingImport } from "@/api/importer";
import type { OcrHoldingRow, OcrTxnRow } from "@/api/ocr";
import {
  useReconDraft,
  type RecognizerCandidate
} from "@/composables/useReconDraft";

/**
 * 对账中心三域数据与操作（#980 拆分自 index.vue 的 composables/ 步骤，零行为变更）
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

  /** 域 D：跨账本重复交易（#2151）——未忽略组 + 已忽略清单 */
  const ghostGroups = ref<GhostDuplicateGroupItem[]>([]);
  const ghostIgnored = ref<GhostDuplicateIgnore[]>([]);
  const ghostLoading = ref(false);
  const ghostDeletingId = ref<number | null>(null);
  const ghostUndoingId = ref<number | null>(null);

  /** 域 E：红利税待办（#541）——粒度是「一笔分红」，每行要么该补记、要么该核对 */
  const taxItems = ref<DividendTaxPendingItem[]>([]);
  const taxTotalCents = ref(0);
  /** 其中「未扣」的笔数（比例异常的项不算待补记，但仍列出来供核对） */
  const taxPendingCount = ref(0);
  const taxLoading = ref(false);

  /** 域 A：E账户对账数据（P2 迁入） */
  const eItems = ref<ReconciliationItem[]>([]);
  const eLoading = ref(false);

  /** 域 B 差异：仅展示待处理（pending）行，使下方表格与顶部「待裁决差异」口径一致（#1259） */
  const bDiscs = computed(() =>
    discs.value.filter(d => d.domain === "B" && d.status === "pending")
  );

  /** 域 C 差异：导入后自动对账产出的孤儿持仓（有仓位、没有对应流水）。
   *  后端域 C 目前只做孤儿检测、不做数量比对（`reconciliation_service.py` §6.2），
   *  所以这里拿到的 `discrepancy_type` 只会是 `orphan`。 */
  const cDiscs = computed(() =>
    discs.value.filter(d => d.domain === "C" && d.status === "pending")
  );

  /** 全局待处理总数，仅用于 Banner 提醒（不要求与单表对齐） */
  const totalPending = computed(() => {
    const fromDiscs = discs.value.filter(d => d.status === "pending").length;
    const fromE = eItems.value.filter(i => i.status === "pending").length;
    // 域 D/E 是实时派生扫描，不进 discrepancies 表，单独计数
    return fromDiscs + fromE + ghostGroups.value.length + taxItems.value.length;
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
    // 域 D 不走 discrepancies 表（它是实时派生扫描），待处理数即未忽略的组数
    if (key === "D") return ghostGroups.value.length;
    // 域 E 同理：待办项实时派生，没有「已忽略」概念（记完税即自然消失）
    if (key === "E") return taxItems.value.length;
    return discs.value.filter(d => d.domain === key && d.status === "pending")
      .length;
  }
  function domainIgnored(key: string): number {
    if (key === "A")
      return eItems.value.filter(i => i.status === "ignored").length;
    if (key === "D") return ghostIgnored.value.length;
    if (key === "E") return 0;
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
      // 候选行即 OCR 预览行，剥离 kind 后原样回传确认端点（txn/holding 各自落库管线）。
      // 分支内用类型守卫收窄 discriminated union：`c.kind === kind`（变量比较）TS 推不动
      // 收窄，不收窄会把 OcrHoldingRow（quantity/price 为 string|number）混进 txn 分支。
      if (kind === "txn") {
        const rows: OcrTxnRow[] = list
          .filter((c): c is OcrTxnRow & { kind: "txn" } => c.kind === "txn")
          .map(({ kind: _k, ...row }) => row);
        const res = await confirmImport(rows);
        ElMessage.success(
          `已入库 ${res?.data?.imported ?? rows.length} 条交易，已触发域 C 对账`
        );
      } else {
        const rows: OcrHoldingRow[] = list
          .filter(
            (c): c is OcrHoldingRow & { kind: "holding" } =>
              c.kind === "holding"
          )
          .map(({ kind: _k, ...row }) => row);
        const res = await confirmHoldingImport(rows);
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

  /** 加载域 E：分红未记扣税（#541）。
   *
   * 这个 GET 顺带幂等写一条站内提醒（后端 `dedup_key` 含年份，同标的同年只留一条），
   * 因此它也是「首页消息条能看到这条提醒」的触发点——用户不必专门来对账台，
   * 只要打开过任意一次工作台，铃铛就会有东西。失败静默：本域不是首屏主体，
   * 一次超时不该把整个工作台带崩。 */
  async function loadDividendTax(): Promise<void> {
    taxLoading.value = true;
    try {
      const res = await listDividendTaxPending();
      taxItems.value = res.data?.items ?? [];
      taxTotalCents.value = res.data?.total_cents ?? 0;
      taxPendingCount.value = res.data?.pending_count ?? 0;
    } catch {
      taxItems.value = [];
      taxTotalCents.value = 0;
      taxPendingCount.value = 0;
    } finally {
      taxLoading.value = false;
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

  /**
   * 域 A 归因 / 忽略：复用共用 composable，**不在本文件本地实现**。
   *
   * 此前这里手写了两个几乎相同的函数，且漏了 `ElMessageBox.confirm`——
   * 「归因覆盖」会删除渠道原记录（不可撤销），不确认等于单击即毁数据。
   * 收敛到 `useEaccountActions` 后与独立对账中心走同一条确认链路。
   * `loadEAccount` 是函数声明（提升），此处引用安全。
   */
  const { actingRecordId, actingAction, runAttribution } =
    useEaccountActions(loadEAccount);

  /** 传给域 A 面板的「哪个按钮在转圈」快照 */
  const eActing = computed<Acting>(() => ({
    recordId: actingRecordId.value,
    action: actingAction.value
  }));

  function handleEAccountCover(row: ReconciliationItem): void {
    void runAttribution(row, "cover");
  }

  function handleEAccountIgnore(row: ReconciliationItem): void {
    void runAttribution(row, "ignore");
  }

  /** 运行对账（域 B） */
  async function handleRun(): Promise<void> {
    running.value = true;
    try {
      await runReconciliation("B");
      ElMessage.success("对账完成");
      // 域 B 是「算差异」，域 E 是「看有没有漏记税」——两件事但同一入口，
      // 一起刷新才符合用户对「运行对账」的预期（跑完看到的都是最新）。
      await Promise.all([loadDiscrepancies(), loadDividendTax()]);
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

  /** 加载域 D：未忽略组 + 已忽略清单（一个接口拿不到两者，两次调用并发） */
  async function loadGhostDuplicates(): Promise<void> {
    ghostLoading.value = true;
    try {
      const [groupsRes, ignoredRes] = await Promise.all([
        listGhostDuplicates(),
        listGhostDuplicateIgnores()
      ]);
      ghostGroups.value = groupsRes.data?.groups ?? [];
      ghostIgnored.value = ignoredRes.data ?? [];
    } catch {
      ghostGroups.value = [];
      ghostIgnored.value = [];
    } finally {
      ghostLoading.value = false;
    }
  }

  /** 忽略一组跨账本重复（幂等）；成功后重拉，未忽略组与已忽略清单同步变化 */
  async function handleGhostIgnore(
    group: GhostDuplicateGroupItem
  ): Promise<void> {
    try {
      await ignoreGhostDuplicate(group.fingerprint);
      ElMessage.success("已忽略该组，可在下方撤销");
      await loadGhostDuplicates();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "忽略失败");
    }
  }

  /** 撤销忽略（带乐观提示，以服务端返回的 deleted 为准） */
  async function handleGhostUndoIgnore(
    item: GhostDuplicateIgnore
  ): Promise<void> {
    ghostUndoingId.value = item.id;
    try {
      const res = await undoGhostDuplicateIgnoreById(item.id);
      ElMessage.success(res.data?.deleted ? "已撤销忽略" : "该记录已不存在");
      await loadGhostDuplicates();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "撤销失败");
    } finally {
      ghostUndoingId.value = null;
    }
  }

  /**
   * 删除组内某一笔流水（「留一份、删一份」的主路径）。
   *
   * 这里给二次确认：删除 `transactions` 会**连带重算持仓**（`DELETE /api/transactions/<id>/`
   * 后端行为），是不可逆操作，且域 D 的每一条都是用户自己录进来的真实数据。
   * 文案刻意不说「保留真实的那一份」——后端 `transactions.source` 为 NULL 时
   * 无法指出哪一份权威，这种断言是后端支撑不了的（见 issue 讨论）。
   */
  async function handleGhostDeleteTxn(txn: GhostDuplicateTxn): Promise<void> {
    try {
      await ElMessageBox.confirm(
        `确认删除「${txn.ledger_name}」中的这一笔？删除后会重算该账本持仓，无法撤销。`,
        "删除重复交易",
        { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
      );
    } catch {
      return; // 用户取消
    }
    ghostDeletingId.value = txn.id;
    try {
      await deleteTransaction(txn.id);
      ElMessage.success("已删除，持仓已重算");
      // 删除后指纹里的账本集合可能变化，整组重新扫描比本地摘一条更可靠
      await loadGhostDuplicates();
      await loadDiscrepancies();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "删除失败");
    } finally {
      ghostDeletingId.value = null;
    }
  }

  return {
    loading,
    running,
    discs,
    bDiscs,
    cDiscs,
    eItems,
    eLoading,
    eActing,
    recognizerCandidates,
    committing,
    totalPending,
    hasPending,
    dataDateLabel,
    domainPending,
    domainIgnored,
    ghostGroups,
    ghostIgnored,
    ghostLoading,
    ghostDeletingId,
    ghostUndoingId,
    taxItems,
    taxTotalCents,
    taxPendingCount,
    taxLoading,
    loadDividendTax,
    loadDiscrepancies,
    loadEAccount,
    loadGhostDuplicates,
    handleGhostIgnore,
    handleGhostUndoIgnore,
    handleGhostDeleteTxn,
    loadRecognizerCandidates,
    commitCandidates,
    discardCandidates,
    handleRun,
    handleIgnore,
    handleEAccountCover,
    handleEAccountIgnore
  };
}
