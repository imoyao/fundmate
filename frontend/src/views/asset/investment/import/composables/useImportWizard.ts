import { parseFile, confirmImport as confirmImportApi } from "@/api/importer";
import type { ImportErrorItem, ImportParseError } from "@/api/importer";
import { runReconciliation } from "@/api/reconciliation";
import { navCache } from "@/composables/useNavCache";
import type { UploadRequestOptions } from "element-plus";
import type { EditField, PreviewRow } from "./previewRow";
import {
  ref,
  onMounted,
  onUnmounted,
  watch,
  computed,
  reactive,
  nextTick
} from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getLedgers,
  createLedger as createLedgerApi,
  updateLedger as updateLedgerApi,
  getSalesInstitutions
} from "@/api/ledger";
import type { LedgerItem, SalesInstitution } from "@/api/ledger";
import type { OcrTxnRow } from "@/api/ocr";
import { ALLOCATION_OPTIONS } from "@/constants";
import { useReconDraft, type ReconDomain } from "@/composables/useReconDraft";
import {
  classifyFixMode,
  snapshotRows,
  restoreRows,
  UNDO_STACK_LIMIT,
  type FixSectionKey,
  type FixMode,
  type FixUndoEntry,
  type SectionCounts
} from "./batchFixLogic";
import {
  clearFeeBreakdownOnEdit,
  recalcAfterEdit,
  smartFill
} from "./cellEditLogic";
import { fillSmartPrice, restoreSmartFilledPrice } from "./smartFillPrice";
import {
  isMissingCode,
  isRowBlocked,
  categorizeRow,
  feeDiffOf,
  taxTotalOf,
  isFeeExplained,
  isAmountMismatch,
  hasFixProblem,
  isAutoSelectableRow,
  QTY_PRICE_OPTIONAL_OPS,
  AMOUNT_INDEPENDENT_OPS,
  type SummaryCategory
} from "./previewPredicates";
import {
  ledgerTypeMap,
  getTemplateKeyForLedger,
  formatFileSize,
  getFundTypeColor,
  getTypeColor,
  addRowKeys,
  getRowClassName,
  getCellClassName,
  getCategoryDesc,
  getCategoryTagType
} from "./importPresentation";
import {
  createFormatGuides,
  IMPORT_WIZARD_STEPS,
  columnsForMode
} from "./importWizardData";
import {
  applyRowFilters,
  mergeLinkGroups,
  countBlockedRows,
  countHiddenSelectedDuplicates,
  shouldShowPriceUpdateTip,
  groupAllocationByType,
  summarizeErrors,
  countByCategory,
  countCompleteTransfers,
  bucketFixSections,
  sectionCountsOf,
  pickReverseRepoRows,
  pickAutoFillableRows,
  pickFilledRows,
  countPendingFix,
  countSelectedTransfers
} from "./previewPipeline";

/**
 * 问题摘要面板的三卡片分类（#1791）。
 * 三类**互斥完备**：每行恰属一类，卡片条数之和恒等于总行数（验收②的和式不变量）。
 * 类型定义已下沉到 ./previewPredicates，此处仅再导出，避免破坏既有类型消费者。
 */
export type { SummaryCategory } from "./previewPredicates";

/** element-plus `UploadRequestOptions.onError` 的入参类型（第三方类型，本仓不拥有） */
type UploadErrorPayload = Parameters<
  NonNullable<UploadRequestOptions["onError"]>
>[0];

/**
 * 后端错误信封里的 message（#2879：原本散落 4 处 `catch (e: any)` 直接点
 * `e?.response?.data?.message`）。异常是 `unknown`，取值必须显式收窄——
 * 否则「不是 axios 错误」时点下去就是 TypeError，而在错误处理路径里再抛错，
 * 用户看到的是另一个错。
 */
function backendMessageOf(e: unknown): string {
  const resp = (e as { response?: { data?: { message?: unknown } } } | null)
    ?.response;
  const msg = resp?.data?.message;
  return typeof msg === "string" ? msg : "";
}

/** 「按类型批量配置目标」的分组项（与 previewPipeline.groupAllocationByType 同源） */
type AllocationGroup = ReturnType<typeof groupAllocationByType>[number];

export function useImportWizard() {
  const router = useRouter();
  // #1239 草稿层：交易/交割单导入 = 域 C
  const { saveDraft, getDraftWithSet, discardDraft } = useReconDraft();
  const draftDomain: ReconDomain = "C";
  /** 当前页面是否正处于草稿恢复的可用状态（仅同域恢复） */
  const draftBannerVisible = ref(false);
  /** 恢复时读取到的草稿快照（用于 Banner 展示「恢复/丢弃」） */
  const pendingDraftMeta = ref<{
    savedAt: string;
    rowCount: number;
    ledgerId: number | null;
  } | null>(null);

  // ── #1789 草稿自动保存与离开提示 ──
  /** 脏标：预览关键状态自上次成功落盘后是否有未保存修改（仅保存成功才清，失败留待下轮重试） */
  const draftDirty = ref(false);
  /**
   * 是否存在值得提示「未保存」的导入工作——离开提示与 30s 自动保存的共同判据：
   * 有未保存修改 + 有已解析的行（只选了个账户不值得打断用户）+ 未到结果步骤（导入已完成无物可存）。
   */
  const hasUnsavedDraftWork = computed(
    () =>
      draftDirty.value && currentStep.value < 3 && previewData.value.length > 0
  );

  // ── #783 §8.1：草稿保存反馈（顶部「草稿·已保存 时分」，3 秒后淡出） ──
  /** 最近一次成功落盘的「时:分」；未保存过时为空串 */
  const draftSavedLabel = ref("");
  /** 提示显隐：每次保存成功重新计时，3 秒后自动淡出 */
  const draftSavedHintVisible = ref(false);
  let draftSavedHintTimer: ReturnType<typeof setTimeout> | null = null;

  /**
   * 展示「草稿·已保存」提示（#783 §8.1 第 2 条）。
   * 只在**落盘成功**后调用——失败时静默留脏标、交由下个 30s 周期重试，
   * 不能让「已保存」文案说谎。
   */
  function flashDraftSavedHint() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    draftSavedLabel.value = `${hh}:${mm}`;
    draftSavedHintVisible.value = true;
    if (draftSavedHintTimer) clearTimeout(draftSavedHintTimer);
    draftSavedHintTimer = setTimeout(() => {
      draftSavedHintVisible.value = false;
      draftSavedHintTimer = null;
    }, 3000);
  }

  const showMatchDrawer = ref(false);

  const showAiModal = ref(false);

  function openAiImport() {
    if (!selectedLedgerId.value) {
      ElMessage.warning("请先选择要导入的账户");
      return;
    }
    showAiModal.value = true;
  }

  // AI 识别成功后：把 txn 预览行并入既有预览表格与确认流程（与 handleUpload 同构）
  function onAiRowsFound(rows: OcrTxnRow[]) {
    if (rows.length === 0) return;
    // #2854：AI 识别不是文件通道，没有源文件行数可对照，清掉上一次文件解析的对账状态
    sourceRowCount.value = null;
    parseErrors.value = [];
    parseErrorCount.value = 0;
    ignoredRowCount.value = 0;
    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    const defaultAlloc = ledger?.default_allocation || "longterm";
    const normalized = addRowKeys(
      rows.map(row => ({
        ...row,
        account_name: ledger?.name || "",
        allocation: row.allocation ?? defaultAlloc,
        op_type: row.op_type || "buy",
        quantity: row.quantity || 0,
        price: row.price || 0
      }))
    );
    // 智能补价：有份额无价格但有金额 → 金额/份额。
    // #2903：判据抽到 smartFillPrice.ts，与文件上传通道共用同一份（原两处各写一份、
    // 守卫条件还不一致）。
    normalized.forEach(fillSmartPrice);

    previewData.value = normalized;
    totalRows.value = normalized.length;
    duplicateCount.value = normalized.filter(r => r.is_duplicate).length;
    errorCount.value = normalized.filter(r => !!r.error).length;
    currentStep.value = 2;
    recalcValidRowsCount();
    selectAllValid();
  }

  /** 文案见 importWizardData.ts；reactive 包一层保持每实例独立 */
  const formatGuides = reactive(createFormatGuides());

  // ── 步骤定义 ──
  const steps = IMPORT_WIZARD_STEPS;

  // ── 核心状态 ──
  const currentStep = ref(0);
  const selectedMode = ref("standard");
  const previewData = ref<PreviewRow[]>([]);
  const duplicateCount = ref(0);
  const errorCount = ref(0);
  // ── #2854 导入行数对账 ──
  /** 源文件数据行数（表头之外）；null = 非文件通道（AI 识别） */
  const sourceRowCount = ref<number | null>(null);
  /** 解析阶段未能纳入导入的行（未知操作名 / 行解析失败），带行号与原文操作名 */
  const parseErrors = ref<ImportParseError[]>([]);
  const parseErrorCount = ref(0);
  /** 声明式「有意忽略」的非交易记录行数 */
  const ignoredRowCount = ref(0);
  const importedCount = ref(0);
  const skippedCount = ref(0);
  // #1010：银证转账在关联现金账户侧生成的反向记录数（后端独立计数，不混入 imported/skipped）
  const cashTransfersCreated = ref(0);
  // #1882：勾选保留的疑似重复行——入库 / 去重拦截计数（回执如实展示）
  const keptCount = ref(0);
  const keptBlockedCount = ref(0);
  const orphanCount = ref(0);
  const importing = ref(false);
  const parsing = ref(false);
  const fileSize = ref("");
  const editingRowKey = ref<string | null>(null);
  const newLedgerAllocation = ref("longterm");
  const showAllocationGroupPanel = ref(false);
  const ledgers = ref<LedgerItem[]>([]);
  const selectedLedgerId = ref<number | null>(null);
  const showCreateLedgerDialog = ref(false);
  const newLedgerName = ref("");
  const newLedgerType = ref("stock");
  const newLedgerLinkedCashId = ref<number | null>(null);
  const newLedgerPortfolioId = ref<number | null>(null);
  const newLedgerFeeConfig = ref<Record<string, unknown> | null>(null);
  const newLedgerSalesInstitutionId = ref<number | null>(null);
  /** 归属家庭成员（#1173，null=未归属/家庭共有）：向导内新建账户同样要能指定归属 */
  const newLedgerOwnerMemberId = ref<number | null>(null);
  /** 基金销售机构候选（AMAC 名录，向导内新建账户可选关联） */
  const salesInstitutionsForImport = ref<SalesInstitution[]>([]);
  /** 步骤3 软提示横幅：用户现场选中的现金账户 */
  const bannerCashLedgerId = ref<number | null>(null);
  const activeCategoryFilter = ref("");
  const downloadLoading = ref(false);

  // 分页与筛选
  const currentPage = ref(1);
  const pageSize = ref(50);
  const totalRows = ref(0);
  const selectedKeys = ref<Set<string>>(new Set());
  const isAllSelected = ref(false);
  const isIndeterminate = ref(false);
  const showProblemOnly = ref(false);
  const tableFilterKeyword = ref("");
  const tableTypeFilter = ref<string[]>([]);
  const tableStatusFilter = ref("");
  /** 批量修正面板（#1792 起为摘要下方内联展开，由摘要卡【批量修正】/筛选栏按钮切换） */
  const showFixPanel = ref(false);
  const batchCodeInput = ref("");
  const importErrors = ref<ImportErrorItem[]>([]);
  const duplicatesHandled = ref(false);
  const uploadError = ref("");
  const validRowsCount = ref(0);

  // ── 计算属性 ──
  /**
   * #2854 行数对账：源文件 N 行必须能拆成「可导入 + 有意忽略 + 解析失败」。
   * 只在「有解析失败行」或「等式不成立」时返回对象——零差异时不打扰用户。
   * 旧实现里 total 天生是丢过行的数，用户连对账的锚点都没有。
   */
  const rowReconciliation = computed(() => {
    const source = sourceRowCount.value;
    if (source == null) return null;
    const imported = totalRows.value;
    const ignored = ignoredRowCount.value;
    const failed = parseErrorCount.value;
    const balanced = source === imported + ignored + failed;
    if (balanced && failed === 0) return null;
    const ops = [
      ...new Set(
        parseErrors.value
          .map(e => e.raw_value || e.message)
          .filter((v): v is string => !!v)
      )
    ];
    return { source, imported, ignored, failed, balanced, ops };
  });

  const selectedLedgerName = computed(() => {
    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    return ledger?.name || "未选择";
  });

  const ledgerType = computed(() => {
    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    return ledger?.ledger_type || "";
  });

  const ledgerTypeLabel = computed(() => {
    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    return ledger ? ledgerTypeMap[ledger.ledger_type] || "" : "";
  });

  const ledgerGroups = computed(() => {
    const groups: Record<string, { label: string; ledgers: LedgerItem[] }> = {};
    const order = ["stock", "fund", "cash", "general", "family"];
    for (const ledger of ledgers.value) {
      const type = ledger.ledger_type || "general";
      if (!groups[type])
        groups[type] = { label: ledgerTypeMap[type] || type, ledgers: [] };
      groups[type].ledgers.push(ledger);
    }
    // 组内按"最近使用"排序：最近有交易的账户排前面，无交易的沉底；
    // 同档再按创建时间倒序、名称升序，保证顺序稳定可预期、不随刷新乱跳。
    const byRecentUse = (a: LedgerItem, b: LedgerItem) => {
      const at = a.last_used_at ? Date.parse(a.last_used_at) : 0;
      const bt = b.last_used_at ? Date.parse(b.last_used_at) : 0;
      if (at !== bt) return bt - at; // 更近的在前
      const ac = a.created_at ? Date.parse(a.created_at) : 0;
      const bc = b.created_at ? Date.parse(b.created_at) : 0;
      if (ac !== bc) return bc - ac;
      return (a.name || "").localeCompare(b.name || "", "zh");
    };
    for (const key of order) {
      if (groups[key]) groups[key].ledgers.sort(byRecentUse);
    }
    return order.filter(o => groups[o]).map(o => groups[o]);
  });

  const availableModes = computed(() => {
    const allModes = [
      {
        label: "股票标准模板",
        value: "standard_stock",
        logo: "/logos/stock.svg"
      },
      { label: "同花顺交割单", value: "ths", logo: "/logos/tonghuashun.svg" },
      {
        label: "基金标准模板",
        value: "standard_fund",
        logo: "/logos/standard.svg"
      },
      {
        label: "天天基金",
        value: "tiantian_fund",
        logo: "/logos/tiantianjijin.svg"
      },
      {
        label: "支付宝（PDF）",
        value: "alipay_pdf",
        logo: "/logos/alipay.svg"
      },
      { label: "支付宝", value: "alipay_fund", logo: "/logos/alipay.svg" }
    ];
    if (ledgerType.value === "stock")
      return allModes.filter(
        m => m.value === "standard_stock" || m.value === "ths"
      );
    if (ledgerType.value === "fund" || ledgerType.value === "cash")
      return allModes.filter(
        m =>
          m.value === "standard_fund" ||
          m.value === "tiantian_fund" ||
          m.value === "alipay_fund" ||
          m.value === "alipay_pdf"
      );
    return allModes;
  });

  const isStandardMode = computed(
    () =>
      selectedMode.value === "standard_stock" ||
      selectedMode.value === "standard_fund"
  );

  /**
   * 模板名（**不含**「模板」二字）：调用方自己拼后缀。
   *
   * 曾经这里返回「股票标准模板」，而使用处又拼了一句「模板」，界面上就出现
   * 「下载股票标准模板模板」——字面重复看着像没做完。名字只留品种，后缀交给
   * 使用处决定，改词时只有一处要动。
   */
  const templateNameForAccount = computed(() =>
    selectedMode.value === "standard_fund" ? "基金标准" : "股票标准"
  );
  const accountType = computed(() =>
    selectedMode.value === "standard_fund" ? "基金" : "股票"
  );
  const templateFields = computed(() => {
    if (selectedMode.value === "standard_fund")
      return "确认日期、交易日期、基金代码、基金名称、业务类型、份额、金额、手续费、净值、账户名称";
    return "确认日期、交易日期、股票代码、股票名称、业务类型、数量(股)、成交均价、成交金额、手续费、账户名称";
  });
  const formatName = computed(() => {
    if (selectedMode.value === "ths") return "同花顺";
    if (selectedMode.value === "standard_fund") return "基金标准模板";
    if (selectedMode.value === "tiantian_fund") return "天天基金";
    return "股票标准模板";
  });

  const isFundMode = computed(
    () =>
      selectedMode.value === "standard_fund" ||
      selectedMode.value === "tiantian_fund"
  );

  /** 列定义、宽度预算与取舍理由见 importWizardData.ts */
  const tableColumns = computed(() => columnsForMode(isFundMode.value));

  /** 判据见 previewPipeline.ts 的 countBlockedRows */
  const blockedCount = computed(() => countBlockedRows(previewData.value));

  const selectedCount = computed(() => selectedKeys.value.size);

  /** #2274 判据见 previewPipeline.ts 的 countHiddenSelectedDuplicates */
  const hiddenSelectedDuplicateCount = computed(() =>
    countHiddenSelectedDuplicates(
      previewData.value,
      selectedKeys.value,
      duplicatesHandled.value
    )
  );

  const nothingImported = computed(
    () =>
      importedCount.value === 0 &&
      orphanCount.value === 0 &&
      importErrors.value.length > 0
  );

  const showPriceUpdateTip = computed(() =>
    shouldShowPriceUpdateTip(
      previewData.value,
      selectedKeys.value,
      importedCount.value
    )
  );

  const allocationGroupsByType = computed(() =>
    groupAllocationByType(previewData.value)
  );

  const currentAllocationGroups = computed(() => allocationGroupsByType.value);

  const errorSummary = computed(() => summarizeErrors(importErrors.value));

  /** 按显示单元计数的口径与 #2836 教训见 previewPipeline.ts 的 countByCategory */
  const summaryCounts = computed(() => countByCategory(previewData.value));

  /** #2281 口径见 previewPipeline.ts 的 countCompleteTransfers */
  const completeTransferCount = computed(() =>
    countCompleteTransfers(previewData.value)
  );

  /** 四分区行源（#1792）：分桶不变量见 previewPipeline.ts 的 bucketFixSections */
  const fixSectionRows = computed<Record<FixSectionKey, PreviewRow[]>>(() =>
    bucketFixSections(previewData.value)
  );

  const fixSectionCounts = computed<SectionCounts>(() =>
    sectionCountsOf(fixSectionRows.value)
  );

  /** 与 fixSectionCounts 同源：本文件曾逐字重复两份（#2876 合并），保留旧名避免改 4 个消费组件 */
  const fixBreakdown = fixSectionCounts;

  // ── #1792 修正形态（#783 §4 阈值）与逐条卡片数据源 ──

  /** §4 阈值判定（纯函数 classifyFixMode，单测覆盖 ≤10 / >10 切换） */
  const fixMode = computed<FixMode>(() =>
    classifyFixMode(fixSectionCounts.value)
  );

  /**
   * 手动覆盖：批量面板内【逐条修正】→ "single"（配 singleFixScope 圈定分区），
   * 卡片内【返回分类批量】→ null 回到阈值判定；null = 始终跟随 §4。
   */
  const fixModeOverride = ref<"single" | "batch" | null>(null);
  /** 逐条卡片范围：all = 全部问题行（阈值触发）；分区键 = 从该分区点入 */
  const singleFixScope = ref<FixSectionKey | "all">("all");

  const activeFixMode = computed<FixMode>(
    () => fixModeOverride.value ?? fixMode.value
  );

  /** 逐条修正卡片数据源：section 决定卡片内表单形态 */
  const singleFixRows = computed<
    Array<{ row: PreviewRow; section: FixSectionKey }>
  >(() => {
    const keys: FixSectionKey[] =
      singleFixScope.value === "all"
        ? ["error", "missingCode", "missingQtyPrice", "mismatch"]
        : [singleFixScope.value];
    const out: Array<{ row: PreviewRow; section: FixSectionKey }> = [];
    keys.forEach(key =>
      fixSectionRows.value[key].forEach(row => out.push({ row, section: key }))
    );
    return out;
  });

  /** 逆回购行：口径见 previewPipeline.ts 的 pickReverseRepoRows */
  const reverseRepoRows = computed(() =>
    pickReverseRepoRows(previewData.value)
  );

  /** 自动填充可推算行：入参是已算好的 missingQtyPrice 桶，口径见 previewPipeline.ts 的 pickAutoFillableRows */
  const autoFillableRows = computed(() =>
    pickAutoFillableRows(fixSectionRows.value.missingQtyPrice)
  );

  /** 已自动填充过的行：口径见 previewPipeline.ts 的 pickFilledRows */
  const filledRows = computed(() => pickFilledRows(previewData.value));

  /** 过滤 + 合并后的完整列表——分页切片与总条数的唯一来源
   *
   * 过滤口径（状态 + 子分类 + 问题开关 + 关键词 + 类型）见 previewPipeline.ts 的
   * applyRowFilters；合并口径与「只合并两行都没问题」的理由见同文件的 mergeLinkGroups。
   * 五个筛选键在此从 ref 展开成显式入参（#2876 增量 4b）——过滤函数从此不读任何
   * Vue 运行时状态，单测直接喂行对象即可。
   */
  const filteredMergedData = computed(() =>
    mergeLinkGroups(
      applyRowFilters(previewData.value, {
        tableStatusFilter: tableStatusFilter.value,
        activeCategoryFilter: activeCategoryFilter.value,
        showProblemOnly: showProblemOnly.value,
        tableFilterKeyword: tableFilterKeyword.value,
        tableTypeFilter: tableTypeFilter.value
      })
    )
  );

  const filteredPagedData = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value;
    return filteredMergedData.value.slice(start, start + pageSize.value);
  });

  // 筛选收缩后当前页可能越界：el-pagination 的 total 是筛选后的 filteredTotal，
  // 若停在旧的大页码上（如 7/7），切片会落到空区间 → 表格假性「空白」。
  // 统一在这里钳制，而不是指望每个筛选入口（开关/搜索/类型/类别胶囊）各自记得复位——
  // 入口会不断增加，漏一个就是静默空表。sync 是刻意的：钳制只写一个 ref，
  // 必须赶在下一次渲染前完成，否则会先画出一帧空表再跳页。
  watch(
    () => filteredMergedData.value.length,
    len => {
      const maxPage = Math.max(1, Math.ceil(len / pageSize.value));
      if (currentPage.value > maxPage) currentPage.value = maxPage;
    },
    { flush: "sync" }
  );

  const calculatedCount = computed(() => {
    return previewData.value.filter(row => row.is_calculated).length;
  });

  const enrichingNav = ref(false);

  // 需要填充净值的基金记录：非货币，有代码，有日期，但净值或份额为空
  // #2879：原条件里还有一条 `row.type !== "money_fund"`——上一行已把它钉成 'fund'，
  // 这条永远为真（类型化后才暴露的死分支）。删掉不改变任何行为，留着只会让人
  // 以为这里真的在排除货币基金。
  const fundRecordsForNav = computed(() => {
    return previewData.value.filter(
      row =>
        row.type === "fund" &&
        row.symbol &&
        row.symbol !== "__CASH__" &&
        row.trade_date &&
        (!row.price || !row.quantity || row.price === 0)
    );
  });

  const hasFundRecordsForNav = computed(
    () => fundRecordsForNav.value.length > 0
  );
  const fundRecordsCount = computed(() => fundRecordsForNav.value.length);

  async function fetchAndFillFundNav() {
    if (!fundRecordsForNav.value.length) return;

    // 按确认日期分组，收集代码
    const dateGroups: Record<string, string[]> = {};
    fundRecordsForNav.value.forEach(row => {
      const date = row.trade_date;
      if (!date) return;
      if (!dateGroups[date]) dateGroups[date] = [];
      if (!dateGroups[date].includes(row.symbol)) {
        dateGroups[date].push(row.symbol);
      }
    });

    enrichingNav.value = true;
    try {
      for (const [date, symbols] of Object.entries(dateGroups)) {
        // 经 useNavCache：本地缓存优先，未命中再 JSONP 直连（#1133）
        const navMap = await navCache.getNavs(symbols, date);

        previewData.value.forEach(row => {
          if (
            row.type === "fund" &&
            row.trade_date === date &&
            row.symbol &&
            symbols.includes(row.symbol)
          ) {
            const nav = navMap[row.symbol];
            if (nav && nav > 0) {
              row.price = nav;
              // 与 cellEditLogic / applyManualFill / batchFixAmount 同一修边口径：
              // toFixed(4) 后 parseFloat，避免长浮点直接进表格
              row.quantity = parseFloat((row.amount / nav).toFixed(4));
              row.is_calculated = true;
            }
          }
        });
      }
      previewData.value = [...previewData.value];
      ElMessage.success("已填充净值和份额，请检查确认");
    } catch {
      ElMessage.error("获取净值失败，请稍后重试");
    } finally {
      enrichingNav.value = false;
    }
  }

  function confirmAllCalculated() {
    previewData.value.forEach(row => {
      if (row.is_calculated) row.is_calculated = false;
    });
    previewData.value = [...previewData.value];
    ElMessage.success("所有推算数据已确认");
  }

  // 与分页共用同一管线（applyRowFilters + mergeLinkGroups）：总条数就是完整列表长度，
  // 与「共 N 条」的分页行数天然一致（#1791 验收②）
  const filteredTotal = computed(() => filteredMergedData.value.length);

  // ── 辅助函数 ──
  const lockedTemplateKey = computed(() =>
    getTemplateKeyForLedger(
      ledgers.value.find(l => l.id === selectedLedgerId.value) || null
    )
  );

  function isRowSelected(row: PreviewRow): boolean {
    return selectedKeys.value.has(row._rowKey);
  }

  function recalcValidRowsCount() {
    // 直接复用 isAutoSelectableRow：这里曾经手写了一份同样含义的判据，
    // 后来加「被配对消费」时改了一处漏了一处，「可导入 N 条」与实际能选中的
    // 行数就此漂移（#2836 又把「代码未匹配」喂进同一个坑）。谓词只留一份。
    validRowsCount.value = previewData.value.filter(isAutoSelectableRow).length;
  }

  /** 「暂不导入」条数（#2836）：判据与三次漂移教训见 previewPipeline.ts 的 countPendingFix */
  const pendingFixCount = computed(() => countPendingFix(previewData.value));

  /**
   * 底栏补数：未勾选条数 = 全部行 − 已选。
   *
   * 底栏此前写「另有 {pendingFixCount} 条暂不导入」，而 pendingFixCount 刻意排除了
   * 转账行（它数的是「待修问题行」），分母与左边的 selectedCount（含转账）不同：
   * 一边 169 一边 169，加起来却等于 338 而不是表格里的行数；旁边按钮又是
   * 「跳过这 169 条，导入 40 条」（169+40=209），三个数字来自三个分母，
   * 谁也验证不了谁——用户看到的正是「银证转账到底算不算在内」看不清（#2840）。
   *
   * 底栏只负责回答「这一按会导入多少」，故分母必须是同一份全量行；
   * 「其中多少条是问题行」由概览条与修正面板回答，不在这里说第三遍。
   */
  const unselectedCount = computed(() =>
    Math.max(0, previewData.value.length - selectedCount.value)
  );

  /** 已选行里的银证转账条数：让「已选择 169 条」自己说清转账在不在里面 */
  const selectedTransferCount = computed(() =>
    countSelectedTransfers(previewData.value, selectedKeys.value)
  );

  function updateSelectAllState() {
    // 按成员判定，不用尺寸比较：#1791 放开疑似重复行的勾选后 selectedKeys.size
    // 会因多选重复行而超出有效行数——「漏选 1 条有效行 + 多选 1 条重复行」尺寸恰好
    // 相等，会被误判为全选（表头复选框说谎）。
    //
    // 判据直接复用 isAutoSelectableRow（= selectAllValid 的谓词）。此前这里手抄了
    // 一份同样的条件，注释写着「与 selectAllValid 一致」，实际却漏了 isMissingCode：
    // 有缺代码行时 selectedKeys 永远追不上 eligible，表头复选框挂在半选态出不来
    // （#2840 顺手收口；同源漂移在本文件已复发过两次）。
    let eligible = 0;
    let picked = 0;
    previewData.value.forEach(row => {
      if (isAutoSelectableRow(row)) {
        eligible++;
        if (selectedKeys.value.has(row._rowKey)) picked++;
      }
    });
    if (eligible > 0 && picked >= eligible) {
      isAllSelected.value = true;
      isIndeterminate.value = false;
    } else if (picked > 0) {
      isAllSelected.value = false;
      isIndeterminate.value = true;
    } else {
      isAllSelected.value = false;
      isIndeterminate.value = false;
    }
  }

  function clearImportState() {
    previewData.value = [];
    selectedKeys.value = new Set();
    duplicateCount.value = 0;
    errorCount.value = 0;
    // #2854：换文件 / 重来时行数对账状态一并清空，避免上一份文件的差额挂在新预览上
    sourceRowCount.value = null;
    parseErrors.value = [];
    parseErrorCount.value = 0;
    ignoredRowCount.value = 0;
    orphanCount.value = 0;
    isAllSelected.value = false;
    isIndeterminate.value = false;
    importErrors.value = [];
    validRowsCount.value = 0;
    showFixPanel.value = false;
    fixModeOverride.value = null;
    singleFixScope.value = "all";
    fixUndoStack.value = [];
    tableFilterKeyword.value = "";
    tableTypeFilter.value = [];
    tableStatusFilter.value = "";
    duplicatesHandled.value = false;
    // #2281：转账行提示横幅的关闭态是会话级，新导入会话（换文件 / 重新导入）
    // 重置，确保能力提示重新出现
    cashBindingBannerDismissed.value = false;
    uploadError.value = "";
    parsing.value = false;
  }

  // ── 流程控制 ──
  function onAccountSelected(ledgerId: number) {
    const ledger = ledgers.value.find(l => l.id === ledgerId);
    if (!ledger) return;
    const templateKey = getTemplateKeyForLedger(ledger);
    selectedMode.value = templateKey || "standard_fund";
    currentStep.value = 1;
  }

  function handleDownloadTemplate() {
    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    if (!ledger) return;
    const key = getTemplateKeyForLedger(ledger);
    const urlMap: Record<string, string> = {
      standard_fund: "/api/importers/template/fund/",
      standard_stock: "/api/importers/template/stock/"
    };
    const url = urlMap[key] || "/api/importers/template/standard/";
    downloadLoading.value = true;
    window.open(url);
    setTimeout(() => (downloadLoading.value = false), 1500);
  }

  /**
   * #2904：这里原本还有一段「给 `.ledger-select-area .el-select` 加 600ms
   * `ledger-select-flash` 类」的 DOM 操作，想在未选账户时闪一下提示。它两层都失效，且不可修：
   * 账户选择搬到了第 0 步（`LedgerSelectStep`），`.ledger-select-area` 里现在只有
   * 只读 el-tag + 「更换账户」按钮，`querySelector` 恒返回 null；而那个类全仓也没有 CSS 定义。
   * 故一并删除（含只写不读的 `ledgerTouched`），只留下面这条兜底提示。
   */
  function handleUploadClick() {
    if (!selectedLedgerId.value) ElMessage.warning("请先选择交易所属账户");
  }

  const uploadAccept = computed(() => {
    return selectedMode.value === "alipay_pdf" ? ".pdf" : ".csv,.xls,.xlsx";
  });

  function beforeUpload(file: File) {
    if (!selectedLedgerId.value) {
      ElMessage.warning("请先选择交易所属账户");
      return false;
    }
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();

    if (selectedMode.value === "alipay_pdf") {
      // PDF 模式专用校验
      if (ext !== ".pdf") {
        ElMessage.error("仅支持 PDF 文件");
        return false;
      }
      if (file.size > 10 * 1024 * 1024) {
        // PDF 可能稍大，放宽至 10MB
        ElMessage.error("文件大小不能超过10MB");
        return false;
      }
    } else {
      // 原有逻辑
      const allowedExtensions = [".csv", ".xls", ".xlsx"];
      if (!allowedExtensions.includes(ext)) {
        ElMessage.error("仅支持 CSV、Excel 文件");
        return false;
      }
      if (file.size > 5 * 1024 * 1024) {
        ElMessage.error("文件大小不能超过5MB");
        return false;
      }
    }

    fileSize.value = formatFileSize(file.size);
    uploadError.value = "";
    return true;
  }
  async function handleUpload(options: UploadRequestOptions) {
    const file = options.file as File;
    if (!selectedLedgerId.value) return ElMessage.warning("请先选择一个账户");

    parsing.value = true;
    uploadError.value = "";
    await new Promise(resolve => setTimeout(resolve, 50));

    try {
      const res = await parseFile(
        file,
        selectedMode.value,
        selectedLedgerId.value
      );
      const rawData = res.data ?? [];
      previewData.value = addRowKeys(rawData);
      totalRows.value = previewData.value.length;
      duplicateCount.value = res.duplicate_count ?? 0;
      errorCount.value = res.error_count ?? 0;
      // #2854 行数对账：errors 曾经只写不读，未知操作名整行静默消失，
      // 连 total 都是「丢过行」的数。这里接住后端下发的明细与源文件行数。
      sourceRowCount.value = res.source_row_count ?? null;
      parseErrors.value = res.parse_errors ?? [];
      parseErrorCount.value = res.parse_error_count ?? 0;
      ignoredRowCount.value = res.ignored_row_count ?? 0;

      const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
      const defaultAlloc = ledger?.default_allocation || "longterm";
      previewData.value.forEach(row => {
        row.account_name =
          row.account_name && row.account_name !== "默认证券账户"
            ? row.account_name
            : ledger?.name || "";
        if (row.allocation == null) row.allocation = defaultAlloc;
        // 智能补价：#2903 起与 OCR 通道共用 smartFillPrice 的判据。
        // 旧守卫 `!isRowBlocked && !is_cash_transfer && !row.error && !is_duplicate` 把
        // 条件写反了——isRowBlocked 在「单价缺失」时恒为 true，与补价前提互斥，
        // 于是该补的普通成交行一个没补、不该补的豁免类型（税额/兑付/分红）全补了。
        fillSmartPrice(row);
      });

      previewData.value = [...previewData.value];
      recalcValidRowsCount();
      selectAllValid();

      const warning = res.compatibility_warning;
      if (warning) {
        let confirmed = false;
        try {
          await ElMessageBox.confirm(warning, "文件格式提醒", {
            confirmButtonText: "继续导入",
            cancelButtonText: "返回重选",
            type: "warning"
          });
          confirmed = true;
        } catch {
          // 用户点「返回重选」：交给下面的放弃分支，不在这里 return
        }
        if (!confirmed) {
          // #2901「返回重选」= 放弃本次导入。旧写法在 .catch 回调里 return，
          // 只退出回调、退不出 handleUpload，于是照样落草稿并向上报成功。
          // clearImportState() 会清空 previewData，使 hasUnsavedDraftWork 判假，
          // 避免 30s 自动保存（2714-2728）把这份被放弃的草稿又写回去。
          clearImportState();
          // totalRows 不在 clearImportState 的重置清单里（它的另外 3 个调用点
          // :1612/:1620/:1629 各自语义不同，本卡不扩大到那里），
          // 这里单独归零，避免「已放弃的解析」留下一个行数残值。
          totalRows.value = 0;
          options.onError?.(new Error("用户取消导入") as UploadErrorPayload);
          return;
        }
        currentStep.value = 2;
      } else {
        ElMessage.success(`解析完成，共识别 ${totalRows.value} 条记录`);
        currentStep.value = 2;
      }
      // #1239 草稿层：进入预览步骤即保存草稿（含勾选状态，Set→数组序列化）
      await persistDraft();
      options.onSuccess(res);
    } catch (e) {
      const errorMsg =
        backendMessageOf(e) ||
        (e instanceof Error ? e.message : "") ||
        "文件解析失败";
      uploadError.value = errorMsg;
      options.onError(e);
    } finally {
      parsing.value = false;
    }
  }

  async function confirmImport() {
    if (!selectedLedgerId.value)
      return ElMessage.warning("请先在第二步选择导入账户");

    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    if (!ledger) return ElMessage.error("所选账户无效，请重新选择");

    saveAllEditingRows();

    previewData.value.forEach(row => {
      if (!row._allocationManual)
        row.allocation =
          row.allocation || ledger.default_allocation || "longterm";
      row.account_name = ledger.name;
    });

    // #1010：转账行不再前端剔除，交由后端统一裁决（已关联现金账户时生成现金侧记录）
    // #1791（验收④）：疑似重复行不再无条件剔除——默认就没被勾中（selectAllValid 排除），
    // 用户显式勾选保留的随集合提交；解析错误 / 已忽略 / 数量价格缺失行仍剔除。
    // #1882（决策 (a)）：勾选保留行随行携带 keep_duplicate 标记，后端真插入
    // （import_hash 加 :keep 后缀绕开唯一约束），回执按 kept_duplicates 如实计数。
    const rowsToImport = previewData.value
      .filter(
        row =>
          selectedKeys.value.has(row._rowKey) &&
          !row.error &&
          !row._ignored &&
          !isRowBlocked(row)
      )
      .map(row => (row.is_duplicate ? { ...row, keep_duplicate: true } : row));
    if (rowsToImport.length === 0)
      return ElMessage.warning("没有可导入的有效记录");

    importing.value = true;
    try {
      const res = await confirmImportApi(rowsToImport);
      const result = res.data;
      importedCount.value = result.imported ?? 0;
      skippedCount.value = result.skipped ?? 0;
      cashTransfersCreated.value = result.cash_transfers_created ?? 0;
      keptCount.value = result.kept_duplicates ?? 0;
      keptBlockedCount.value = result.kept_duplicates_blocked ?? 0;
      orphanCount.value = result.orphan_count ?? 0;
      importErrors.value = result.errors ?? [];
      currentStep.value = 3;
      // #1232 P1 域 C：导入 commit 成功后自动触发对账（fire-and-forget，与导入事务解耦，§6.2）。
      // 不阻塞导入完成流程；孤儿流水 → 工作台差异，用户可后续处理。
      triggerDomainCReconciliation();
      // #1239 草稿层：导入完成即丢弃草稿，避免残留
      await discardDraft().catch(() => {});
      // #1789：导入已完成、无物可存——清脏标，避免结果页离开时误提示「未保存」
      draftDirty.value = false;
    } catch (e) {
      ElMessage.error(backendMessageOf(e) || "导入失败");
    } finally {
      importing.value = false;
    }
  }

  /**
   * 域 C 对账（导入后自动触发，§6.2）。
   * 静默失败：对账是增值行为，不阻断导入主流程。
   */
  async function triggerDomainCReconciliation(): Promise<void> {
    try {
      await runReconciliation("C");
    } catch {
      /* 静默：对账失败不影响导入结果展示 */
    }
  }

  // ── #1239 草稿层：保存 / 恢复 / 丢弃 ──
  /** 把当前预览状态持久化为草稿（交易导入=域 C，恢复至 Step 2 预览修正） */
  async function persistDraft(): Promise<void> {
    try {
      await saveDraft({
        domain: draftDomain,
        ledgerId: selectedLedgerId.value,
        currentStep: currentStep.value >= 2 ? 2 : currentStep.value,
        rows: previewData.value,
        selectedKeys: selectedKeys.value,
        selectedLedgerId: selectedLedgerId.value,
        selectedMode: selectedMode.value
      });
      // 落盘成功才清脏标。await 会让出执行权，期间变更监听（flush 'pre'）先置脏、
      // 此处后清标——顺序天然正确；失败则不清，30s 周期自动重试。
      draftDirty.value = false;
      // #783 §8.1：同步给出「草稿·已保存 时分」反馈（3 秒淡出，不占位不打断）
      flashDraftSavedHint();
    } catch (e) {
      console.warn("保存草稿失败", e);
    }
  }

  /** 检查是否存在同域（C）草稿；存在则返回草稿元数据供 Banner 展示 */
  async function checkDraft(): Promise<boolean> {
    try {
      const draft = await getDraftWithSet();
      if (!draft) return false;
      // 仅同域（C）直接恢复；跨域草稿交由组件弹窗处理（§5.8）
      if (draft.domain !== draftDomain) return false;
      pendingDraftMeta.value = {
        savedAt: draft.savedAt,
        rowCount: draft.rows.length,
        ledgerId: draft.ledgerId
      };
      draftBannerVisible.value = true;
      return true;
    } catch {
      return false;
    }
  }

  /** 恢复草稿：回填 previewData / selectedKeys / selectedLedgerId，跳至 Step 2 预览修正 */
  async function restoreDraft(): Promise<void> {
    try {
      const draft = await getDraftWithSet();
      if (!draft || draft.domain !== draftDomain) return;
      // 回填账本上下文（Step 0 产出，否则预览页丢失账本上下文）
      if (draft.selectedLedgerId != null) {
        // 账户存在性前置校验：onMounted 先 fetchLedgers 再 checkDraft，
        // 点恢复时列表已就绪；列表为空（fetch 失败）时不校验，避免误判。
        // 账户已删除则拒绝恢复并丢弃草稿——否则带着死 ledgerId 一路走到
        // confirmImport 才报「所选账户无效」，用户修正完数据才发现，
        // 失败点太晚；且草稿已无归属，保留只会在下次进页面反复踩同一坑。
        if (
          ledgers.value.length > 0 &&
          !ledgers.value.some(l => l.id === draft.selectedLedgerId)
        ) {
          await discardDraft().catch(() => {});
          draftBannerVisible.value = false;
          pendingDraftMeta.value = null;
          ElMessage.warning(
            "草稿关联的账户已被删除，无法恢复，请重新选择账户导入"
          );
          return;
        }
        selectedLedgerId.value = draft.selectedLedgerId;
      }
      if (draft.selectedMode) selectedMode.value = draft.selectedMode;
      // 回填预览数据（行内编辑状态保留）
      previewData.value = addRowKeys(draft.rows);
      totalRows.value = previewData.value.length;
      // #2274：行级 _duplicateHandled 随草稿行持久化，但 duplicatesHandled
      // 开关本身不入草稿——恢复时按行标回推，避免按钮文案与实际显隐状态说谎
      // （隐藏过的重复行恢复后仍处于隐藏态，按钮应显示「恢复查看重复行」）
      duplicatesHandled.value = previewData.value.some(
        r => r.is_duplicate && r._duplicateHandled
      );
      // 回填勾选（数组 → Set）
      selectedKeys.value = new Set(draft.selectedKeySet);
      // 重算统计
      duplicateCount.value = previewData.value.filter(
        r => r.is_duplicate
      ).length;
      errorCount.value = previewData.value.filter(r => !!r.error).length;
      recalcValidRowsCount();
      updateSelectAllState();
      currentStep.value = 2;
      draftBannerVisible.value = false;
      pendingDraftMeta.value = null;
      ElMessage.success("已恢复未完成的导入草稿");
      // 恢复出的状态与盘上草稿一致：等变更监听刷完（flush 'pre' 是微任务）再清脏标，
      // 否则「先清标、后置脏」顺序反了，离开时会误提示未保存。
      await nextTick();
      draftDirty.value = false;
    } catch {
      ElMessage.error("恢复草稿失败，请重新导入");
    }
  }

  /** 丢弃草稿（Banner「丢弃」入口） */
  async function discardCurrentDraft(): Promise<void> {
    await discardDraft().catch(() => {});
    draftBannerVisible.value = false;
    pendingDraftMeta.value = null;
  }

  async function importNormalOnly() {
    clearAllSelection();
    selectAllValid();
    await confirmImport();
  }

  /**
   * 全部行都是疑似重复（#783 §十 边界场景一）：没有任何一行可正常导入。
   * 判据逐行取 `is_duplicate`（与 categorizeRow 的分区口径同源），不做条数相减——
   * 重复行可能同时带解析告警，条数比较会在混合态下判错。
   */
  const allRowsDuplicate = computed(
    () =>
      previewData.value.length > 0 &&
      previewData.value.every(row => row.is_duplicate)
  );

  /** 【全部跳过，返回上一步】（#783 §十）：丢弃草稿 + 清空预览，退回上传步骤重选文件 */
  async function skipAllDuplicatesAndBack() {
    await discardDraft().catch(() => {});
    draftBannerVisible.value = false;
    pendingDraftMeta.value = null;
    clearImportState();
    currentStep.value = 1;
    ElMessage.info("已跳过本次导入，请重新选择文件");
  }

  function resetImport() {
    const savedLedgerId = selectedLedgerId.value;
    const savedMode = selectedMode.value;
    clearImportState();
    selectedLedgerId.value = savedLedgerId;
    selectedMode.value = savedMode;
    currentStep.value = 0;
  }

  function continueImport() {
    const savedLedgerId = selectedLedgerId.value;
    const savedMode = selectedMode.value;
    clearImportState();
    selectedLedgerId.value = savedLedgerId;
    selectedMode.value = savedMode;
    currentStep.value = 1;
  }

  function reimport() {
    resetImport();
  }

  // ── 选择与勾选 ──
  function handleHeaderCheckboxChange(checked: boolean) {
    checked ? selectAllValid() : clearAllSelection();
  }

  /**
   * 全选 / 恢复忽略行的勾选取止：疑似重复行默认不勾（要导自己手动勾，#1882），
   * 解析错误 / 数量价格缺失 / 资金划转 / 已忽略行不参与。
   * selectAllValid 与 toggleIgnoreRow 恢复分支共用，保证两处口径一致。
   */

  function selectAllValid() {
    const newKeys = new Set<string>();
    previewData.value.forEach(row => {
      if (isAutoSelectableRow(row)) newKeys.add(row._rowKey);
    });
    selectedKeys.value = newKeys;
    isAllSelected.value = true;
    isIndeterminate.value = false;
  }

  function clearAllSelection() {
    selectedKeys.value = new Set();
    isAllSelected.value = false;
    isIndeterminate.value = false;
  }

  function handleRowCheckboxChange(row: PreviewRow, checked: boolean) {
    if (checked) selectedKeys.value.add(row._rowKey);
    else selectedKeys.value.delete(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
    updateSelectAllState();
  }

  /** 逐行忽略：标记该行不参与导入（与整类跳过 skipCategory 互补，针对单行）；再点一次恢复 */
  function toggleIgnoreRow(row: PreviewRow) {
    row._ignored = !row._ignored;
    if (row._ignored) {
      selectedKeys.value.delete(row._rowKey);
    } else if (isAutoSelectableRow(row)) {
      // 恢复忽略 = 回到全选默认态：可勾的重新勾上（#783 终审遗留小问题）。
      // 只补谓词内的行——重复行要导仍需用户手动勾（#1882），
      // 解析错误 / 待补全 / 资金划转行本就不可勾，恢复后同样不勾。
      selectedKeys.value.add(row._rowKey);
    }
    selectedKeys.value = new Set(selectedKeys.value);
    previewData.value = [...previewData.value];
    updateSelectAllState();
  }

  async function fillNavForRecords(rows: PreviewRow[]) {
    // 过滤出需要净值的记录：非货币、有代码、有日期、缺少价格或份额
    const needed = rows.filter(
      row =>
        row.type === "fund" &&
        row.symbol &&
        row.symbol !== "__CASH__" &&
        row.trade_date &&
        (!row.price || !row.quantity || row.price === 0)
    );
    if (!needed.length) return;

    // 按确认日期分组，收集唯一的 symbol
    const dateGroups: Record<string, string[]> = {};
    needed.forEach(row => {
      const dt = row.trade_date;
      if (!dt) return;
      if (!dateGroups[dt]) dateGroups[dt] = [];
      if (!dateGroups[dt].includes(row.symbol)) {
        dateGroups[dt].push(row.symbol);
      }
    });

    // 逐日请求
    for (const [date, symbols] of Object.entries(dateGroups)) {
      try {
        // 经 useNavCache：本地缓存优先，未命中再 JSONP 直连（#1133）
        const navMap = await navCache.getNavs(symbols, date);

        // 更新所有相关行
        needed.forEach(row => {
          if (row.trade_date === date && symbols.includes(row.symbol)) {
            const nav = navMap[row.symbol];
            if (nav && nav > 0) {
              row.price = nav;
              // 修边口径同 fetchAndFillFundNav：toFixed(4) 后 parseFloat，
              // 避免长浮点直接进表格
              row.quantity = parseFloat((row.amount / nav).toFixed(4));
              row.is_calculated = true;
            } else {
              row.price = 0;
              row.is_calculated = false;
              row._dataMissing = true;
            }
          }
        });
      } catch {
        // 静默失败，不影响主流程
      }
    }
    // 刷新表格视图
    previewData.value = [...previewData.value];
  }

  // ── 撤销栈（#1792 要做的事 3：批量修正操作栈，至少支持撤销一层）──

  const fixUndoStack = ref<FixUndoEntry[]>([]);
  /** autoFix 组合操作期间挂起逐项入栈，完成后整组入一条（一步撤净） */
  let undoSuppressed = false;

  const canUndo = computed(() => fixUndoStack.value.length > 0);
  /** 栈顶操作的分区归属——分区级【撤销】按此决定是否可用，防止撤错对象 */
  const undoTopScope = computed<FixUndoEntry["scope"] | null>(
    () => fixUndoStack.value[fixUndoStack.value.length - 1]?.scope ?? null
  );

  /** 变更前拍照（行字段）+ 记录选择集（跳过类操作只动选择） */
  function makeUndoEntry(
    scope: FixUndoEntry["scope"],
    label: string,
    rows: PreviewRow[]
  ): FixUndoEntry {
    return {
      scope,
      label,
      rows: snapshotRows(rows),
      beforeSelection: [...selectedKeys.value]
    };
  }

  function pushUndoEntry(entry: FixUndoEntry) {
    fixUndoStack.value.push(entry);
    if (fixUndoStack.value.length > UNDO_STACK_LIMIT)
      fixUndoStack.value.shift();
  }

  function pushUndo(
    scope: FixUndoEntry["scope"],
    label: string,
    rows: PreviewRow[]
  ) {
    if (undoSuppressed) return;
    pushUndoEntry(makeUndoEntry(scope, label, rows));
  }

  /**
   * 撤销上一次批量修正：弹栈 → 行字段快照写回 → 选择集写回 → 重算统计。
   * expected 传分区归属时仅当栈顶匹配才撤销（分区级【撤销】按钮语义）。
   */
  function undoLastFix(expected?: FixUndoEntry["scope"]): boolean {
    const stack = fixUndoStack.value;
    const top = stack[stack.length - 1];
    if (!top || (expected && top.scope !== expected)) return false;
    stack.pop();
    restoreRows(previewData.value, top.rows);
    selectedKeys.value = new Set(top.beforeSelection);
    recalcValidRowsCount();
    updateSelectAllState();
    previewData.value = [...previewData.value];
    ElMessage.success(`已撤销：${top.label}`);
    return true;
  }

  // ── 批量修正 ──
  async function batchFillCode(rows: PreviewRow[], code: string) {
    if (!code.trim()) return ElMessage.warning("请输入有效的证券代码");
    pushUndo("code", `填充证券代码 ${code.trim()}`, rows);
    rows.forEach(r => (r.symbol = code.trim()));
    recalcValidRowsCount();
    // #2836：补代码的目的就是「这些行要导入」。而「代码未匹配」的行原先默认不入选、
    // 也不可勾（没产品可落），补完代码后如果还要用户再勾一次，等于修完还得记着去点一下。
    // 只补「现在确实能入选」的行——它们可能还缺数量/价格，那部分仍留给用户处理。
    rows.forEach(r => {
      if (isAutoSelectableRow(r)) selectedKeys.value.add(r._rowKey);
    });
    updateSelectAllState();
    await nextTick();

    // 自动填充净值和份额
    await fillNavForRecords(rows);

    previewData.value = [...previewData.value];
    ElMessage.success(`已为 ${rows.length} 条记录设置代码「${code}」`);
  }

  async function batchFixAmount(rows?: PreviewRow[]) {
    // 默认目标 = mismatch 分区（旧实现读 row.problems，但全仓无写者，回退恒为空数组）
    const target = rows || fixSectionRows.value.mismatch;
    if (!target.length) return;
    pushUndo("amount", `修正 ${target.length} 条记录的金额`, target);
    target.forEach(r => {
      const qty = Number(r.quantity),
        prc = Number(r.price);
      if (!isNaN(qty) && !isNaN(prc))
        r.amount = parseFloat((qty * prc).toFixed(2));
    });
    recalcValidRowsCount();
    updateSelectAllState();
    await nextTick();
    previewData.value = [...previewData.value];
    ElMessage.success(`已修正 ${target.length} 条记录的金额`);
  }

  async function skipCategory(rows: PreviewRow[]) {
    if (!rows.length) return;
    pushUndo("skip", `跳过 ${rows.length} 条记录`, rows);
    rows.forEach(row => selectedKeys.value.delete(row._rowKey));
    selectedKeys.value = new Set(selectedKeys.value);
    updateSelectAllState();
    await nextTick();
    previewData.value = [...previewData.value];
    ElMessage.success(`已跳过 ${rows.length} 条记录`);
  }

  /**
   * 自动填充缺失数量/价格（四分区之二）：可推算行的缺项 = 金额 ÷ 另一项；
   * 填充后解除阻塞的行自动勾选（对齐 finishEdit 的既有行为）。
   *
   * #2903：这是**用户显式点按钮**触发的第三条路径，与装载时的智能补价
   * （`smartFillPrice.fillSmartPrice`）刻意不共用实现，两点理由：
   * - 它还要处理**缺数量**方向（金额 ÷ 单价），而 `fillSmartPrice` 只补价；
   * - 候选集来自 `isRowBlocked` 为真的行（`fixSectionRows.missingQtyPrice`），
   *   豁免类型（tax / dividend / bond_redeem / money_fund / reverse_repo）天然不在其中，
   *   排除面已等价，再套一层是重复判据。
   *
   * 反过来说：装载路径原先把 `!isRowBlocked` 当门禁，方向恰好写反——见
   * `smartFillPrice.ts` 头注释。两处对同一个谓词的用法相反，是本卡的核心证据。
   */
  async function autoFillMissing() {
    const targets = autoFillableRows.value;
    if (!targets.length) {
      ElMessage.info(
        "没有可自动填充的行（数量与价格同时缺失的行无法推算，请逐条补录）"
      );
      return;
    }
    pushUndo("fill", `自动填充 ${targets.length} 条缺失数量/价格`, targets);
    targets.forEach(row => {
      const qty = Number(row.quantity),
        prc = Number(row.price),
        amt = Number(row.amount);
      const qtyMissing = isNaN(qty) || qty <= 0;
      if (qtyMissing) row.quantity = parseFloat((amt / prc).toFixed(4));
      else row.price = parseFloat((amt / qty).toFixed(4));
      const filled = qtyMissing ? "quantity" : "price";
      row._autoFilled = [...new Set([...(row._autoFilled || []), filled])];
    });
    targets.forEach(row => {
      if (!isRowBlocked(row)) selectedKeys.value.add(row._rowKey);
    });
    selectedKeys.value = new Set(selectedKeys.value);
    recalcValidRowsCount();
    updateSelectAllState();
    await nextTick();
    previewData.value = [...previewData.value];
    ElMessage.success(`已自动填充 ${targets.length} 条记录的缺失项`);
  }

  /** 逐条卡片的「应用」：写入草稿值，对侧仍缺失时按金额推算（smartFill 既有语义） */
  async function applyManualFill(
    row: PreviewRow,
    draft: { quantity?: string; price?: string }
  ) {
    const qty = parseFloat(draft.quantity ?? ""),
      prc = parseFloat(draft.price ?? "");
    const setQty = !isNaN(qty) && qty > 0,
      setPrc = !isNaN(prc) && prc > 0;
    if (!setQty && !setPrc) return ElMessage.warning("请输入有效的数量或单价");
    // 先拍照再写（顺序颠倒会让撤销恢复成已改的值，等于没撤）
    pushUndo(
      "fill",
      `逐条填充「${row.name || row.symbol || row.trade_date}」`,
      [row]
    );
    if (setQty) row.quantity = qty;
    if (setPrc) row.price = prc;
    smartFill(row, setQty ? "price" : "quantity");
    recalcAfterEdit(row, setQty ? "quantity" : "price"); // §6.2：填数后金额同步
    const gotQty = Number(row.quantity) > 0,
      gotPrc = Number(row.price) > 0;
    const touched = [
      ...(setQty ? ["quantity"] : []),
      ...(setPrc ? ["price"] : []),
      ...(!setQty && gotQty ? ["quantity"] : []),
      ...(!setPrc && gotPrc ? ["price"] : [])
    ];
    if (touched.length)
      row._autoFilled = [...new Set([...(row._autoFilled || []), ...touched])];
    if (!isRowBlocked(row)) selectedKeys.value.add(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
    recalcValidRowsCount();
    updateSelectAllState();
    previewData.value = [...previewData.value];
    ElMessage.success(`已填充「${row.name || row.symbol}」的缺失项`);
  }

  /**
   * #2902【恢复原始值】：把装载期补价退回用户上传时的原始单价。
   *
   * 刻意不入撤销栈（撤的是批量修正，不是解析期规范化，理由见 smartFillPrice.ts 头注释）。
   * 恢复会让行重新变成「单价缺失」被拦，故必须同步撤勾选并重算统计，
   * 否则底栏「已选择 N 条」会带着一条导不进去的行说谎。
   */
  function restoreOriginalPrice(row: PreviewRow): void {
    if (!restoreSmartFilledPrice(row)) return;
    if (isRowBlocked(row)) selectedKeys.value.delete(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
    recalcValidRowsCount();
    updateSelectAllState();
    previewData.value = [...previewData.value];
    ElMessage.success("已恢复原始单价");
  }

  /**
   * 逆回购分区【撤销】（四分区之四）：撤的是解析期自动置的配置目标（活钱 → 长期增值）。
   * 类型识别本身是按代码模式（沪 204xxx / 深 1318xx）得出的解析事实，不提供撤销；
   * 用户手动改过的行（_allocationManual）不在撤销范围。
   */
  function revertRepoAllocation() {
    const targets = reverseRepoRows.value.filter(
      row => row.allocation === "liquid" && !row._allocationManual
    );
    if (!targets.length) {
      ElMessage.info("没有可撤销的逆回购配置目标转换（手动设置过的不受影响）");
      return;
    }
    pushUndo(
      "repo",
      `撤销逆回购配置目标自动转换（${targets.length} 条）`,
      targets
    );
    targets.forEach(row => (row.allocation = "longterm"));
    previewData.value = [...previewData.value];
    ElMessage.success(`已撤销 ${targets.length} 条逆回购的配置目标转换`);
  }

  /** 识别依据（【查看转换结果】展示用）：按代码前缀回溯解析期规则 */
  function repoDetectBasis(row: PreviewRow): string {
    const code = String(row.symbol || "");
    if (/^204\d{3}$/.test(code)) return "沪市 204 模式";
    if (/^1318\d{2}$/.test(code)) return "深市 1318 模式";
    return "解析器识别";
  }

  /**
   * 「取消显示重复行」/「恢复查看重复行」（#2274）：只切显隐，绝不动勾选。
   *
   * 导入载荷（confirmImport 按 selectedKeys 取行）与「已选择 N 条」计数
   * （selectedKeys.size）都以 selectedKeys 为唯一真相源，与显隐解耦——
   * 用户手动勾选保留的重复行（keep_duplicate 真插入）不应被一个显隐按钮
   * 悄悄从 selectedKeys 里删掉。历史上该按钮会静默删除勾选且「恢复查看」
   * 不还原，导致导入意图被丢（#2274）。
   *
   * 隐藏行若仍被勾选，由 hiddenSelectedDuplicateCount 暴露给 UI 给出提示，
   * 避免用户看不见自己要导入的内容。
   */
  function deselectAllDuplicates() {
    // 1. 先浅拷贝一份（避免直接修改原数组触发大量响应式更新）
    const data = [...previewData.value];

    if (duplicatesHandled.value) {
      // 恢复所有重复行
      for (const row of data) {
        if (row.is_duplicate) row._duplicateHandled = false;
      }
      duplicatesHandled.value = false;
    } else {
      // 隐藏所有重复行（仅显隐；勾选原样保留，见函数注释）
      for (const row of data) {
        if (row.is_duplicate) row._duplicateHandled = true;
      }
      duplicatesHandled.value = true;
    }

    // 2. 一次性替换，只触发一次响应式更新
    previewData.value = data;
    recalcValidRowsCount();
    updateSelectAllState();

    const hiddenSelected = hiddenSelectedDuplicateCount.value;
    ElMessage.success(
      duplicatesHandled.value
        ? `已取消 ${duplicateCount.value} 条重复数据的展示` +
            (hiddenSelected > 0
              ? `，其中 ${hiddenSelected} 条已勾选，仍将参与导入`
              : "")
        : "已恢复全部重复数据"
    );
  }

  function filterByCategory(key: string) {
    showProblemOnly.value = false;
    tableStatusFilter.value = "";
    if (key === "missingCode") activeCategoryFilter.value = "missingCode";
    else if (key === "missingQtyPrice") tableStatusFilter.value = "blocked";
    else if (key === "mismatch") activeCategoryFilter.value = "mismatch";
    else if (key === "error") activeCategoryFilter.value = "error";
  }

  // ── #1791 概览条：点类别筛选 + 类别复选框（2026-11-02 由三卡片改为一行胶囊） ──

  /** 该类别当前是否展开（tableStatusFilter 就是展开状态：一套状态，两处读） */
  function isCategoryExpanded(key: SummaryCategory): boolean {
    return tableStatusFilter.value === key;
  }

  /**
   * 点类别胶囊：tableStatusFilter 在 key↔"" 间切换。
   * 展开时清掉子分类与「只看问题」开关——它们与类别筛选是两套互斥的过滤视角，叠加会
   * 令「胶囊条数 ≠ 表格条数」（验收②）；关键词/类型搜索是正交收窄，予以保留。
   *
   * 筛到「需要修正」时顺手展开批量修正面板：点这个胶囊的人下一步必然是修它，
   * 让他再去找按钮是一次多余的往返。只自动打开、不自动关闭（收起由面板自己管），
   * 否则每点一次胶囊面板就闪一下。
   */
  function toggleCategoryFilter(key: SummaryCategory) {
    if (tableStatusFilter.value === key) {
      tableStatusFilter.value = "";
      return;
    }
    tableStatusFilter.value = key;
    activeCategoryFilter.value = "";
    showProblemOnly.value = false;
    currentPage.value = 1;
    if (key === "fix" && !showFixPanel.value && summaryCounts.value.fix > 0) {
      showFixPanel.value = true;
      showAllocationGroupPanel.value = false;
      fixModeOverride.value = null;
      singleFixScope.value = "all";
    }
  }

  /** 【全部】胶囊：清空全部过滤回完整表格；概览条不在过滤作用域内，始终可见（验收③） */
  function expandAllData() {
    tableStatusFilter.value = "";
    activeCategoryFilter.value = "";
    showProblemOnly.value = false;
    currentPage.value = 1;
  }

  /**
   * 卡片复选框的作用域 = 该类中「行复选框可勾」的行：
   * 解析错误 / 数量价格缺失（isRowBlocked）/ 资金划转行不可勾（表格行复选框同样禁用），
   * _ignored 是用户显式忽略、不参与卡片批量勾选；**疑似重复行可勾**（#1791 验收④）。
   */
  /**
   * 行可手动勾选。#2281：转账行在关联现金账户后才可勾（放开前一律禁用，
   * tooltip 指路「请先关联现金账户」）；其余行沿用错误 / 已忽略 / 待补全排除。
   * 与 isAutoSelectableRow 的两处语义差异：本谓词允许重复行（卡片可勾），
   * 且转账行能否勾选取决于现金账户关联状态。
   */
  function isRowSelectable(row: PreviewRow): boolean {
    // #2836：被配对规则消费的行不可勾——勾了后端也跳过，让复选框说谎不如直接禁用
    if (row.consumed_by) return false;
    if (row.error || row._ignored || isRowBlocked(row)) return false;
    // #2836：与 isAutoSelectableRow 同源——代码未匹配的行既不能默认可勾、
    // 也不能手动勾（「默认勾上」和「能勾」是两件事，这里必须一起挡住）
    if (isMissingCode(row)) return false;
    if (row.is_cash_transfer) return Boolean(selectedLedgerLinkedCash.value);
    return true;
  }

  /** 卡片复选框三态：该类可勾行全选 / 部分选 / 未选 */
  function categoryCheckState(key: SummaryCategory): "all" | "some" | "none" {
    let total = 0;
    let picked = 0;
    for (const row of previewData.value) {
      if (categorizeRow(row) !== key || !isRowSelectable(row)) continue;
      total++;
      if (selectedKeys.value.has(row._rowKey)) picked++;
    }
    if (picked === 0) return "none";
    return picked === total ? "all" : "some";
  }

  /**
   * 卡片复选框切换：勾选=选中该类全部可批量纳入行，取消=取消该类全部可勾行。
   * #2281：勾选方向排除转账行（可勾但不默认勾——批量动作不代替用户做显式决定）；
   * 取消方向走宽口径，用户手动勾上的转账行随卡片取消一并清除（与重复行同语义）。
   */
  function toggleCategorySelection(key: SummaryCategory, checked: boolean) {
    previewData.value.forEach(row => {
      if (categorizeRow(row) !== key || !isRowSelectable(row)) return;
      if (checked) {
        if (row.is_cash_transfer) return;
        selectedKeys.value.add(row._rowKey);
      } else {
        selectedKeys.value.delete(row._rowKey);
      }
    });
    selectedKeys.value = new Set(selectedKeys.value);
    updateSelectAllState();
  }

  function onMatchComplete() {
    previewData.value = [...previewData.value];
    recalcValidRowsCount();
    selectAllValid();
    updateSelectAllState();
    showFixPanel.value = false;
    tableStatusFilter.value = "";
    activeCategoryFilter.value = "";
  }

  function batchSetAllocation(target: string) {
    let applied = 0;
    previewData.value.forEach(row => {
      if (
        selectedKeys.value.has(row._rowKey) &&
        !row.is_cash_transfer &&
        !row.is_duplicate &&
        !row.error
      ) {
        row.allocation = target;
        row._allocationManual = true;
        applied++;
      }
    });
    previewData.value = [...previewData.value];
    ElMessage.success(
      applied > 0
        ? `已将 ${applied} 条已选数据的配置目标设为「${ALLOCATION_OPTIONS.find(o => o.value === target)?.label}」`
        : "没有可设置的数据"
    );
  }

  function applyAllocationGroupSetting(
    group: AllocationGroup,
    allocation: string
  ) {
    previewData.value.forEach(row => {
      if (
        row.is_duplicate ||
        row.error ||
        row.is_cash_transfer ||
        isRowBlocked(row)
      )
        return;
      if (row.type === group.type) {
        row.allocation = allocation;
        row._allocationManual = true;
      }
    });
    previewData.value = [...previewData.value];
    ElMessage.success(
      `已将「${group.label}」的配置目标设为「${ALLOCATION_OPTIONS.find(o => o.value === allocation)?.label}」`
    );
  }

  function onRowAllocationChange(row: PreviewRow) {
    row._allocationManual = true;
  }

  function toggleAllocationPanel() {
    showAllocationGroupPanel.value = !showAllocationGroupPanel.value;
  }

  /**
   * 展开/收起批量修正面板（#1792 起为摘要下方内联面板，不再是右侧抽屉）。
   * 每次打开时重置手动覆盖，回到 §4 阈值判定的形态。
   */
  function toggleFixPanel() {
    showFixPanel.value = !showFixPanel.value;
    showAllocationGroupPanel.value = false;
    if (showFixPanel.value) {
      fixModeOverride.value = null;
      singleFixScope.value = "all";
    }
  }

  /**
   * 诚实一键：只自动处理程序确实能做的三类可处理项，绝不静默跳过必须人工补全的缺失。
   * - mismatch：以 quantity×price 重算 amount（batchFixAmount）
   * - 基金记录：按交易日自动抓取净值并推算份额（fetchAndFillFundNav）
   * - 已推算数据：批量确认（confirmAllCalculated）
   * missingCode / missingQtyPrice 结构性无法自动补全，如实留在表中等待用户手动处理。
   */
  async function autoFix(): Promise<void> {
    // 组合操作合成一条撤销记录：先拍照（含操作前选择集），执行期间挂起逐项入栈，
    // 结束后整组入一条——撤销一步即可回到 autoFix 之前（要做的事 3 的「至少一层」）。
    const touched = [
      ...new Set([
        ...fixSectionRows.value.mismatch,
        ...fundRecordsForNav.value,
        ...previewData.value.filter(r => r.is_calculated)
      ])
    ];
    const entry = makeUndoEntry("batch", "自动修复可处理项", touched);
    undoSuppressed = true;
    try {
      batchFixAmount();
      if (hasFundRecordsForNav.value) {
        await fetchAndFillFundNav();
      }
      confirmAllCalculated();
    } finally {
      undoSuppressed = false;
    }
    pushUndoEntry(entry);
  }

  // ── 行编辑 ──
  function startEdit(row: PreviewRow, field: EditField) {
    if (editingRowKey.value && editingRowKey.value !== row._rowKey) {
      saveAllEditingRows();
      closeAllEditing();
    } else if (editingRowKey.value === row._rowKey) {
      // 同行切格兜底：上一格按提交收尾（Tab 路径已自行 finishEdit），保住已改值
      if (row.isEditingQty) finishEdit(row, "quantity", true);
      else if (row.isEditingPrice) finishEdit(row, "price", true);
      else if (row.isEditingAmount) finishEdit(row, "amount", true);
      else if (row.isEditingFee) finishEdit(row, "fee", true);
    }
    row._oldValue = row[field];
    row.isEditingQty = field === "quantity";
    row.isEditingPrice = field === "price";
    row.isEditingAmount = field === "amount";
    row.isEditingFee = field === "fee";
    editingRowKey.value = row._rowKey;
    previewData.value = [...previewData.value]; // 新增
  }

  function finishEdit(row: PreviewRow, field: EditField, save: boolean = true) {
    const wasBlocked = isRowBlocked(row);
    if (!save) row[field] = row._oldValue;
    else {
      // 手改手续费总额 → 同步清空 #2137 四列拆分：只改总额会让
      // `Transaction.before_insert` 的「拆分之和 == fee」不变量失败，
      // 整批导入抛 ValueError（用户只看到「导入失败」）。
      if (clearFeeBreakdownOnEdit(row, field)) {
        ElMessage.warning("已按新手续费总额入账，原有费用明细拆分已清除");
      }
      smartFill(row, field);
      recalcAfterEdit(row, field); // §6.2：改数量单价→重算金额；改金额→反算
    }
    delete row._oldValue;
    if (field === "quantity") row.isEditingQty = false;
    else if (field === "price") row.isEditingPrice = false;
    else if (field === "amount") row.isEditingAmount = false;
    else if (field === "fee") row.isEditingFee = false;
    editingRowKey.value = null;

    const nowBlocked = isRowBlocked(row);
    if (wasBlocked && !nowBlocked) {
      selectedKeys.value.add(row._rowKey);
      selectedKeys.value = new Set(selectedKeys.value);
      if (showProblemOnly.value) {
        showProblemOnly.value = false;
        ElMessage.success("数据已修正，已自动切换为全部数据视图");
      } else ElMessage.success("数据已自动勾选");
    } else if (!wasBlocked && nowBlocked) {
      selectedKeys.value.delete(row._rowKey);
      selectedKeys.value = new Set(selectedKeys.value);
    }
    previewData.value = [...previewData.value];
    recalcValidRowsCount();
    updateSelectAllState();
  }

  function cancelEdit(row: PreviewRow, field: EditField) {
    finishEdit(row, field, false);
  }

  function saveAllEditingRows() {
    previewData.value.forEach(row => {
      if (row.isEditingQty) finishEdit(row, "quantity", true);
      if (row.isEditingPrice) finishEdit(row, "price", true);
      if (row.isEditingAmount) finishEdit(row, "amount", true);
      if (row.isEditingFee) finishEdit(row, "fee", true);
    });
  }

  function closeAllEditing() {
    previewData.value.forEach(row => {
      if (row.isEditingQty) {
        row.isEditingQty = false;
        delete row._oldValue;
      }
      if (row.isEditingPrice) {
        row.isEditingPrice = false;
        delete row._oldValue;
      }
      if (row.isEditingAmount) {
        row.isEditingAmount = false;
        delete row._oldValue;
      }
      if (row.isEditingFee) {
        row.isEditingFee = false;
        delete row._oldValue;
      }
    });
    editingRowKey.value = null;
    previewData.value = [...previewData.value]; // 新增
  }

  function isCategoryActive(key: string): boolean {
    if (key === "missingCode")
      return activeCategoryFilter.value === "missingCode";
    if (key === "missingQtyPrice") return tableStatusFilter.value === "blocked";
    if (key === "mismatch") return activeCategoryFilter.value === "mismatch";
    if (key === "error") return activeCategoryFilter.value === "error";
    return false;
  }

  // ── 导航 ──
  function goToTransactions() {
    router.push("/transactions");
  }

  function goToManualEntry() {
    // 路由经 formatTwoStageRoutes 拍平后注册为 /investment/manual，用 name 跳转最稳妥
    router.push({ name: "InvestmentManual" });
  }

  function goToLiabilityForm() {
    router.push("/asset/asset-entry");
  }

  function goToImportGuide() {
    ElMessage.info("当前支持买入、卖出、分红操作类型。其他类型暂不支持。");
  }

  // ── 数据获取 ──
  async function fetchLedgers() {
    try {
      const [res, instRes] = await Promise.all([
        getLedgers(),
        getSalesInstitutions()
      ]);
      ledgers.value = res.data ?? [];
      salesInstitutionsForImport.value = instRes?.data ?? [];
    } catch (e) {
      console.error(e);
    }
  }

  function getMissingRowsByType(rows: PreviewRow[], type: string) {
    return rows.filter(r => r.type === type);
  }

  function resetNewLedgerForm() {
    newLedgerName.value = "";
    // #1101 后统一以 channel_category（渠道分组）为创建入参，后端据其派生 ledger_type；
    // 勿再写旧 ledger_type 值（如 'stock'），否则后端回退映射会派生出错误类型。
    newLedgerType.value = "securities";
    newLedgerLinkedCashId.value = null;
    newLedgerPortfolioId.value = null;
    newLedgerFeeConfig.value = null;
    newLedgerSalesInstitutionId.value = null;
    newLedgerOwnerMemberId.value = null;
    newLedgerAllocation.value = "longterm";
  }

  /** 步骤3 软提示横幅：现场新建现金账户时预置类型并打开弹窗 */
  function openCreateCashFromBanner() {
    newLedgerName.value = "";
    newLedgerType.value = "bank";
    newLedgerLinkedCashId.value = null;
    newLedgerPortfolioId.value = null;
    newLedgerFeeConfig.value = null;
    newLedgerSalesInstitutionId.value = null;
    newLedgerOwnerMemberId.value = null;
    newLedgerAllocation.value = "liquid";
    showCreateLedgerDialog.value = true;
  }

  /** 候选现金账户（仅银行账户） */
  const cashLedgersForImport = computed(() =>
    ledgers.value.filter(l => l.ledger_type === "bank")
  );

  /** 当前选中账户已关联的现金账户 id（未关联为 null） */
  const selectedLedgerLinkedCash = computed(() => {
    const l = ledgers.value.find(l => l.id === selectedLedgerId.value);
    return l?.linked_cash_ledger_id ?? null;
  });

  /**
   * #2281 感知层：转账行提示横幅双态。
   * - 引导态（showCashBindingBanner）：有转账行、未关联现金账户。不可关闭——
   *   它是关联操作入口，且 RowSelectionCell 的 tooltip 指向本横幅；
   * - 轻量提示态（showCashTransferHint）：已关联仍告知「转账行可勾选导入」，
   *   修复关联后横幅立即消失、能力隐身的断点；默认不勾选由用户决定。
   * 关闭轻量态后本次导入会话不再显示（clearImportState 重置，换文件重现）。
   */
  const cashBindingBannerDismissed = ref(false);
  const hasCashTransferRows = computed(() =>
    previewData.value.some(r => r.is_cash_transfer)
  );

  /** 引导态：有转账行、未关联现金账户 */
  const showCashBindingBanner = computed(() => {
    if (currentStep.value !== 2) return false;
    if (selectedLedgerLinkedCash.value) return false;
    return hasCashTransferRows.value;
  });

  /** 轻量提示态：已关联现金账户、有转账行、用户未关闭 */
  const showCashTransferHint = computed(() => {
    if (currentStep.value !== 2) return false;
    if (cashBindingBannerDismissed.value) return false;
    if (!selectedLedgerLinkedCash.value) return false;
    return hasCashTransferRows.value;
  });

  /** 关联的现金账户名（轻量提示态展示用） */
  const linkedCashLedgerName = computed(() => {
    const id = selectedLedgerLinkedCash.value;
    if (!id) return "";
    return ledgers.value.find(l => l.id === id)?.name || "";
  });

  function dismissCashBindingBanner() {
    cashBindingBannerDismissed.value = true;
  }

  /**
   * 转账行批量勾选。
   *
   * 摘要卡只告诉用户「含 131 条银证转账，可勾选导入」——一个说得出条数、却要逐行
   * 点勾的提示等于把活推回给用户（131 次点击）。这里给同一批行一个入口。
   *
   * 作用域刻意与 `completeTransferCount` 同一个谓词（转账行 && 归「数据完整」卡），
   * 保证「按钮处理的行数 == 卡片上写的行数」。疑似重复的转账行归 duplicate 卡、
   * 不在作用域内：#1882 定下「重复行要导需手动勾」，批量入口不能替用户做这个决定。
   */
  function transferToggleRows(): PreviewRow[] {
    return previewData.value.filter(
      row => row.is_cash_transfer && categorizeRow(row) === "complete"
    );
  }

  /** 作用域内是否已全部勾上（按钮据此在「全选 / 取消」之间切换） */
  const transferRowsAllSelected = computed(() => {
    const rows = transferToggleRows();
    return (
      rows.length > 0 && rows.every(r => selectedKeys.value.has(r._rowKey))
    );
  });

  function toggleAllTransferRows() {
    // 未关联现金账户时转账行不可勾（isRowSelectable 同口径）——入口在模板里已隐藏，
    // 函数自己再挡一道，避免以后别处调用时勾出一批「勾了也导不进去」的行
    if (!selectedLedgerLinkedCash.value) return;
    const rows = transferToggleRows();
    if (!rows.length) return;
    const next = new Set(selectedKeys.value);
    if (transferRowsAllSelected.value) {
      rows.forEach(r => next.delete(r._rowKey));
    } else {
      rows.forEach(r => next.add(r._rowKey));
    }
    selectedKeys.value = next;
    updateSelectAllState();
  }

  /** 在步骤3 横幅内直接关联现金账户并落库 */
  async function linkCashAccount() {
    if (!selectedLedgerId.value || !bannerCashLedgerId.value) return;
    try {
      await updateLedgerApi(selectedLedgerId.value, {
        linked_cash_ledger_id: bannerCashLedgerId.value
      });
      await fetchLedgers();
      ElMessage.success("已关联现金账户");
    } catch (e) {
      ElMessage.error(backendMessageOf(e) || "关联失败");
    }
  }

  async function createLedger() {
    const name = newLedgerName.value.trim();
    if (!name) return;
    const payload: Parameters<typeof createLedgerApi>[0] = { name };
    // #1101：统一以 channel_category 为创建入参（后端据其派生 ledger_type）。
    // 旧代码把渠道分组值当 ledger_type 下发，会命中后端「ledger_type→channel_category」
    // 的向后兼容回退映射（仅认 bank/stock/fund/property/e_account/family），产生错误类型。
    if (newLedgerType.value) payload.channel_category = newLedgerType.value;
    if (newLedgerLinkedCashId.value)
      payload.linked_cash_ledger_id = newLedgerLinkedCashId.value;
    if (newLedgerPortfolioId.value)
      payload.portfolio_id = newLedgerPortfolioId.value;
    if (newLedgerFeeConfig.value) payload.fee_config = newLedgerFeeConfig.value;
    if (newLedgerSalesInstitutionId.value)
      payload.sales_institution_id = newLedgerSalesInstitutionId.value;
    // 归属成员（#1173）：null=家庭共有，不下发（后端默认未归属）
    if (newLedgerOwnerMemberId.value)
      payload.owner_member_id = newLedgerOwnerMemberId.value;
    if (newLedgerAllocation.value)
      payload.default_allocation = newLedgerAllocation.value;
    try {
      const res = await createLedgerApi(payload);
      const ledger = res.data;
      const newId = ledger?.id;
      const newType = ledger?.ledger_type;
      await fetchLedgers();
      showCreateLedgerDialog.value = false;
      resetNewLedgerForm();
      if (!newId) return;
      if (currentStep.value === 0) {
        // 步骤1（选账户）：选中新建账户并自动进入上传步骤
        selectedLedgerId.value = newId;
        onAccountSelected(newId);
        ElMessage.success(`已创建账户「${name}」`);
      } else if (currentStep.value === 2) {
        // 步骤3（预览）：现场新建现金账户，自动回填进横幅并落库
        if (newType === "bank") {
          bannerCashLedgerId.value = newId;
          await linkCashAccount();
        }
        ElMessage.success(`已创建现金账户「${name}」`);
      } else {
        ElMessage.success(`已创建账户「${name}」`);
      }
    } catch (e) {
      ElMessage.error(backendMessageOf(e) || "添加失败");
    }
  }

  function handleSizeChange(val: number) {
    pageSize.value = val;
    currentPage.value = 1;
  }

  function handlePageChange(val: number) {
    currentPage.value = val;
  }

  const missingFundNames = computed(() => {
    const groups: Record<string, number> = {};
    previewData.value.forEach(row => {
      if (!row.symbol && row.name && row.type === "fund") {
        groups[row.name] = (groups[row.name] || 0) + 1;
      }
    });
    return Object.entries(groups).map(([name, count]) => ({ name, count }));
  });

  function handleSelectionChange() {}

  // ── 调试快进（仅开发环境 import.meta.env.DEV 生效，生产构建不包含）──
  // 用途：调试向导 UI 时，跳过真实解析/上传直接跳到目标步骤，省去每次等待。
  const devMode = import.meta.env.DEV;

  // 模拟预览行：字段对齐真实解析结果，仅用于查看布局与交互，切勿当作真实数据。
  const devMockRows = [
    {
      symbol: "600519",
      name: "贵州茅台",
      op_type: "BUY",
      trade_date: "2026-03-12",
      quantity: 100,
      price: 1680.5,
      amount: 168050,
      fee: 42.01,
      allocation: "longterm",
      type: "stock",
      status: "normal"
    },
    {
      symbol: "000858",
      name: "五粮液",
      op_type: "BUY",
      trade_date: "2026-03-18",
      quantity: 200,
      price: 152.3,
      amount: 30460,
      fee: 7.62,
      allocation: "longterm",
      type: "stock",
      status: "normal"
    },
    {
      symbol: "510300",
      name: "沪深300ETF",
      op_type: "BUY",
      trade_date: "2026-04-01",
      quantity: 5000,
      price: 3.92,
      amount: 19600,
      fee: 4.9,
      allocation: "longterm",
      type: "etf",
      status: "normal"
    },
    {
      symbol: "014330",
      name: "易方达品质动能",
      op_type: "BUY",
      trade_date: "2026-04-10",
      quantity: 3000,
      price: 0.85,
      amount: 2550,
      fee: 0,
      allocation: "longterm",
      type: "fund",
      status: "normal"
    }
  ];

  function devInjectMockPreview() {
    if (previewData.value.length > 0) return;
    // 没有选中真实账户时补一个占位账户，避免预览页头部/现金账户联动显示异常
    if (!selectedLedgerId.value) {
      selectedLedgerId.value = -1;
      ledgers.value.push({
        id: -1,
        name: "调试账户（模拟）",
        ledger_type: "stock",
        default_allocation: "longterm"
      } as unknown as LedgerItem);
    }
    previewData.value = addRowKeys(devMockRows.map(r => ({ ...r })));
    totalRows.value = previewData.value.length;
    duplicateCount.value = 0;
    errorCount.value = 0;
    recalcValidRowsCount();
    selectAllValid();
  }

  /**
   * 调试快进：直接设置 currentStep，不做前序步骤的解析/上传/写库。
   * @param targetStep 目标步骤 0=选账户 1=上传 2=预览 3=结果
   * @param withMock   true 时若跳到预览/结果且暂无数据，自动注入模拟预览行
   */
  function devJump(targetStep: number, withMock = false) {
    if (!devMode) return;
    if (withMock && (targetStep === 2 || targetStep === 3)) {
      devInjectMockPreview();
    }
    if (targetStep === 3) {
      importedCount.value = previewData.value.length;
      skippedCount.value = 0;
      orphanCount.value = 0;
      keptCount.value = 0;
      keptBlockedCount.value = 0;
    }
    currentStep.value = targetStep;
  }

  // ── #1789：脏标监听 + 30s 自动保存 ──
  // 深层监听预览关键状态：行内编辑 / 勾选（Set 的 add·delete）/ 账户 / 步骤 / 模板
  // 任一变化即视为未保存。deep 对 ref 内 Set 同样生效（Vue 3 把 ref 值转为响应式代理）。
  watch(
    [previewData, selectedKeys, selectedLedgerId, currentStep, selectedMode],
    () => {
      draftDirty.value = true;
    },
    { deep: true }
  );

  const AUTOSAVE_INTERVAL_MS = 30_000;
  let autosaveTimer: ReturnType<typeof setInterval> | null = null;

  /**
   * 30s 自动保存（#1789）：脏标为真且有可保存内容时落盘，成功即清标。
   * 「停留 >30 分钟静默保存」由此覆盖——保存永远静默、无弹窗，状态最长滞后一个周期。
   * 失败不打断用户：留脏标，下个周期自动重试（离开提示与 beforeunload 仍是兜底）。
   */
  function startAutosave() {
    if (autosaveTimer) return;
    autosaveTimer = setInterval(() => {
      if (!hasUnsavedDraftWork.value || importing.value || parsing.value)
        return;
      void persistDraft();
    }, AUTOSAVE_INTERVAL_MS);
  }

  function stopAutosave() {
    if (autosaveTimer) {
      clearInterval(autosaveTimer);
      autosaveTimer = null;
    }
  }

  onMounted(async () => {
    await fetchLedgers();
    // #1239 草稿层：页面加载后检查是否有同域草稿可恢复
    await checkDraft();
    // #1789：30s 自动保存随页面挂载启动（真实卸载时由 onUnmounted 停止；
    // keep-alive 激活态下继续跑也无害——脏标为假时每 tick 只读三个 ref）
    startAutosave();
  });

  onUnmounted(() => {
    stopAutosave();
    if (draftSavedHintTimer) {
      clearTimeout(draftSavedHintTimer);
      draftSavedHintTimer = null;
    }
  });

  return {
    router,
    showMatchDrawer,
    showAiModal,
    formatGuides,
    steps,
    currentStep,
    selectedMode,
    previewData,
    duplicateCount,
    errorCount,
    // #2854 行数对账
    sourceRowCount,
    parseErrors,
    parseErrorCount,
    ignoredRowCount,
    rowReconciliation,
    importedCount,
    skippedCount,
    cashTransfersCreated,
    keptCount,
    keptBlockedCount,
    orphanCount,
    importing,
    parsing,
    fileSize,
    editingRowKey,
    newLedgerAllocation,
    showAllocationGroupPanel,
    ledgers,
    selectedLedgerId,
    showCreateLedgerDialog,
    newLedgerName,
    newLedgerType,
    newLedgerLinkedCashId,
    newLedgerPortfolioId,
    newLedgerFeeConfig,
    salesInstitutionsForImport,
    newLedgerSalesInstitutionId,
    newLedgerOwnerMemberId,
    bannerCashLedgerId,
    resetNewLedgerForm,
    openCreateCashFromBanner,
    cashLedgersForImport,
    selectedLedgerLinkedCash,
    showCashBindingBanner,
    showCashTransferHint,
    linkedCashLedgerName,
    dismissCashBindingBanner,
    transferRowsAllSelected,
    toggleAllTransferRows,
    completeTransferCount,
    linkCashAccount,
    activeCategoryFilter,
    downloadLoading,
    currentPage,
    pageSize,
    totalRows,
    selectedKeys,
    isAllSelected,
    isIndeterminate,
    showProblemOnly,
    tableFilterKeyword,
    tableTypeFilter,
    tableStatusFilter,
    // #1791 问题摘要三卡片
    summaryCounts,
    fixBreakdown,
    isCategoryExpanded,
    toggleCategoryFilter,
    expandAllData,
    isRowSelectable,
    categoryCheckState,
    toggleCategorySelection,
    showFixPanel,
    batchCodeInput,
    importErrors,
    duplicatesHandled,
    uploadError,
    validRowsCount,
    // #2836：「暂不导入」条数（= 默认选不中的行数），底栏与「跳过这 N 条」同源
    pendingFixCount,
    // #2840：底栏补数与构成，与 selectedCount 同一分母（可互算）
    unselectedCount,
    selectedTransferCount,
    // #2836：默认勾选谓词（= selectAllValid 的判据），供测试与「暂不导入」共用
    isAutoSelectableRow,
    selectedLedgerName,
    ledgerType,
    ledgerTypeLabel,
    ledgerGroups,
    availableModes,
    isStandardMode,
    templateNameForAccount,
    accountType,
    templateFields,
    formatName,
    isFundMode,
    tableColumns,
    blockedCount,
    selectedCount,
    // #2274：隐藏但仍勾选的重复行提示（显隐与勾选解耦后的可见性兜底）
    hiddenSelectedDuplicateCount,
    nothingImported,
    showPriceUpdateTip,
    allocationGroupsByType,
    currentAllocationGroups,
    // ── #1792 四分区 / 修正形态 / 撤销栈 ──
    fixSectionRows,
    fixSectionCounts,
    fixMode,
    fixModeOverride,
    activeFixMode,
    singleFixScope,
    singleFixRows,
    reverseRepoRows,
    repoDetectBasis,
    autoFillableRows,
    filledRows,
    canUndo,
    undoTopScope,
    undoLastFix,
    autoFillMissing,
    applyManualFill,
    restoreOriginalPrice,
    revertRepoAllocation,
    errorSummary,
    filteredPagedData,
    calculatedCount,
    enrichingNav,
    fundRecordsForNav,
    hasFundRecordsForNav,
    fundRecordsCount,
    filteredTotal,
    lockedTemplateKey,
    uploadAccept,
    missingFundNames,
    openAiImport,
    onAiRowsFound,
    fetchAndFillFundNav,
    confirmAllCalculated,
    // #2876 增量 2：展示/格式化 helper 已下沉到 ./importPresentation，以下名字继续经返回值导出，组件与 spec 零感知。
    getTemplateKeyForLedger,
    isRowBlocked,
    // 共谓词（#1791）：卡片计数 / 分区 / 表格过滤 / 回归测试共用同一判据
    categorizeRow,
    // 费用容差三件套（2026-11-02）：状态列三态 / 金额列 tooltip 共用
    feeDiffOf,
    isFeeExplained,
    isAmountMismatch,
    // #2836：状态标签判据（composables/statusKind.ts）需要它——「代码未匹配」
    // 是 fix 分类里最容易漏配标签的一档，行本身字段齐全，漏了就会显示成「正常」
    isMissingCode,
    // #2876 增量 1：以下原组合式内联常量/谓词已下沉至 ./previewPredicates，
    // 此处继续随返回值导出，消除任何隐藏消费者风险（行为零变化）。
    taxTotalOf,
    hasFixProblem,
    QTY_PRICE_OPTIONAL_OPS,
    AMOUNT_INDEPENDENT_OPS,
    formatFileSize,
    getFundTypeColor,
    getTypeColor,
    addRowKeys,
    isRowSelected,
    recalcValidRowsCount,
    updateSelectAllState,
    clearImportState,
    onAccountSelected,
    handleDownloadTemplate,
    handleUploadClick,
    beforeUpload,
    handleUpload,
    confirmImport,
    importNormalOnly,
    allRowsDuplicate,
    skipAllDuplicatesAndBack,
    resetImport,
    continueImport,
    reimport,
    handleHeaderCheckboxChange,
    selectAllValid,
    clearAllSelection,
    handleRowCheckboxChange,
    toggleIgnoreRow,
    fillNavForRecords,
    batchFillCode,
    batchFixAmount,
    skipCategory,
    deselectAllDuplicates,
    filterByCategory,
    onMatchComplete,
    batchSetAllocation,
    applyAllocationGroupSetting,
    onRowAllocationChange,
    toggleAllocationPanel,
    toggleFixPanel,
    autoFix,
    startEdit,
    finishEdit,
    cancelEdit,
    smartFill,
    saveAllEditingRows,
    closeAllEditing,
    getRowClassName,
    getCellClassName,
    getCategoryDesc,
    getCategoryTagType,
    isCategoryActive,
    goToTransactions,
    goToManualEntry,
    goToLiabilityForm,
    goToImportGuide,
    fetchLedgers,
    getMissingRowsByType,
    createLedger,
    handleSizeChange,
    handlePageChange,
    handleSelectionChange,
    ledgerTypeMap,
    devMode,
    devJump,
    draftBannerVisible,
    pendingDraftMeta,
    // #1789：离开提示与自动保存的接线点（useImportLeaveGuard 消费）
    draftDirty,
    hasUnsavedDraftWork,
    // #783 §8.1：草稿保存反馈
    draftSavedLabel,
    draftSavedHintVisible,
    persistDraft,
    checkDraft,
    restoreDraft,
    discardCurrentDraft
  };
}
