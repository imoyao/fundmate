import { parseFile, confirmImport as confirmImportApi } from "@/api/importer";
import { runReconciliation } from "@/api/reconciliation";
import { navCache } from "@/composables/useNavCache";
import type { UploadRequestOptions } from "element-plus";
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
import { getTypeLabel } from "@/constants/assetType";
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
import { isMissingAmount, recalcAfterEdit, smartFill } from "./cellEditLogic";

/**
 * 问题摘要面板的三卡片分类（#1791）。
 * 三类**互斥完备**：每行恰属一类，卡片条数之和恒等于总行数（验收②的和式不变量）。
 */
export type SummaryCategory = "complete" | "duplicate" | "fix";

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
    // 智能补价：有份额无价格但有金额 → 金额/份额（与文件解析预览同口径）
    normalized.forEach(row => {
      const qty = parseFloat(row.quantity),
        prc = parseFloat(row.price),
        amt = parseFloat(row.amount);
      if (!isNaN(qty) && qty > 0 && (isNaN(prc) || prc <= 0) && !isNaN(amt)) {
        row.price = parseFloat((amt / qty).toFixed(4));
        row.smartFilled = true;
      }
    });

    previewData.value = normalized;
    totalRows.value = normalized.length;
    duplicateCount.value = normalized.filter(r => r.is_duplicate).length;
    errorCount.value = normalized.filter(r => !!r.error).length;
    showFullTable.value = true;
    currentStep.value = 2;
    recalcValidRowsCount();
    selectAllValid();
  }

  const fundTypeColorMap: Record<string, string> = {
    股票型: "var(--asset-cat-stock)",
    混合型: "var(--asset-cat-fund)",
    债券型: "var(--asset-cat-bond)",
    货币型: "var(--asset-cat-money-fund)",
    指数型: "var(--asset-cat-etf)",
    QDII: "var(--asset-cat-fund)",
    FOF: "var(--asset-cat-portfolio)"
  };

  // 类型中文标签统一走后端唯一来源 frontend/src/constants/assetType（getTypeLabel），不再在此私藏副本（#1171 枚举一致性）。

  // 品种 → 颜色：真相源是 `--asset-cat-*`（#1602）。此处曾用 `--palette-*` 装饰色表达品种
  // （stock 用 muted-blue、fund 用 rose-taupe……），与 getLedgerColor 的 `--asset-cat-*` 并存，
  // 导致「同一个股票」在导入向导是蓝灰、在自选 / 买卖表单是紫 —— 这正是 colors.css 里
  // 「业务代码禁止再借用 --palette-* 装饰色表达品种」要拦的情形，本处属 #1604 漏改。
  // cash / static 在 12 槽位里无同名槽位：现金取货币基金（同属现金管理工具）、static 回退中性色。
  const typeColorMap: Record<string, string> = {
    stock: "var(--asset-cat-stock)",
    fund: "var(--asset-cat-fund)",
    bond: "var(--asset-cat-bond)",
    etf: "var(--asset-cat-etf)",
    crypto: "var(--asset-cat-crypto)",
    saving: "var(--asset-cat-saving)",
    cash: "var(--asset-cat-money-fund)",
    static: "var(--color-neutral)"
  };

  const ledgerTypeMap: Record<string, string> = {
    stock: "股票账户",
    fund: "基金账户",
    cash: "现金账户",
    general: "综合账户",
    family: "家庭账户"
  };

  const formatGuides = reactive({
    standard_stock: {
      title: "股票标准模板格式说明",
      tips: [
        "下载 CSV 模板填写数据，或直接上传同花顺等券商导出的 Excel/CSV 文件",
        "代码格式：A股 6 位数字，港股 5 位数字，美股字母代码",
        "日期格式：YYYY-MM-DD，如 2026-01-15",
        "业务类型：买入(BUY)、卖出(SELL)、现金分红(DIVIDEND_CASH)、送股(SPLIT)"
      ]
    },
    standard_fund: {
      title: "基金标准模板格式说明",
      tips: [
        "下载 CSV 模板填写数据，或直接上传基金平台导出的 CSV 文件",
        "代码为6位基金代码（如 014330）",
        "日期格式：YYYY-MM-DD，如 2023-06-01",
        "业务类型：申购(BUY)、赎回(SELL)、现金分红(DIVIDEND_CASH)、红利再投资(DIVIDEND_REINVEST)",
        "份额、净值为选填，手续费默认为0"
      ]
    },
    ths: {
      title: "同花顺交割单导出说明",
      tips: [
        "打开同花顺客户端 → 交易记录 → 历史交割单",
        '选择日期范围，点击"导出" → 选择"导出全部"',
        '导出格式选择"制表符分隔的文本文件"',
        "直接上传导出的文件即可，无需修改"
      ]
    },
    tiantian_fund: {
      title: "天天基金导入说明",
      tips: [
        "在天天基金网页版 → 我的 → 交易查询 → 对账单查询",
        "拖动选中历史交易明细表格 → Ctrl+C 复制",
        "打开基金标准模板 CSV 文件，粘贴数据覆盖示例行",
        "保存 CSV，在 多多贝 选择“天天基金”格式上传"
      ]
    },
    alipay_fund: {
      title: "支付宝导入说明",
      tips: [
        "在支付宝 → 我的 → 账单 → 更多 → 开具交易流水证明",
        "申请“用于个人对账”的流水，下载后解压得到 .csv 文件",
        "在 多多贝 选择“支付宝”格式上传该文件即可",
        "余额宝交易将自动归入活钱，不产生持仓"
      ]
    },
    alipay_pdf: {
      title: "支付宝 PDF 导入说明",
      tips: [
        "在支付宝 → 我的 → 账单 → 开具交易流水证明",
        "申请“基金交易明细”（PDF 格式）",
        "下载后直接上传该 PDF 文件即可",
        "自动提取确认日期、份额、净值、手续费等完整信息"
      ]
    }
  });

  // ── 步骤定义 ──
  const steps = [
    { title: "选择导入账户" },
    { title: "上传交易文件" },
    { title: "预览与修正" },
    { title: "导入完成" }
  ];

  // ── 核心状态 ──
  const currentStep = ref(0);
  const selectedMode = ref("standard");
  const previewData = ref<any[]>([]);
  const duplicateCount = ref(0);
  const errorCount = ref(0);
  const importedCount = ref(0);
  const skippedCount = ref(0);
  // #1010：银证转账在关联现金账户侧生成的反向记录数（后端独立计数，不混入 imported/skipped）
  const cashTransfersCreated = ref(0);
  const orphanCount = ref(0);
  const importing = ref(false);
  const parsing = ref(false);
  const uploading = ref(false);
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
  const newLedgerFeeConfig = ref<any>(null);
  const newLedgerSalesInstitutionId = ref<number | null>(null);
  /** 基金销售机构候选（AMAC 名录，向导内新建账户可选关联） */
  const salesInstitutionsForImport = ref<SalesInstitution[]>([]);
  /** 步骤3 软提示横幅：用户现场选中的现金账户 */
  const bannerCashLedgerId = ref<number | null>(null);
  const ledgerTouched = ref(false);
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
  const showFullTable = ref(true);
  /** 批量修正面板（#1792 起为摘要下方内联展开，由摘要卡【批量修正】/筛选栏按钮切换） */
  const showFixPanel = ref(false);
  const batchCodeInput = ref("");
  const importErrors = ref<any[]>([]);
  const duplicatesHandled = ref(false);
  const uploadError = ref("");
  const validRowsCount = ref(0);
  const isDragover = ref(false);

  // ── 计算属性 ──
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

  const templateNameForAccount = computed(() =>
    selectedMode.value === "standard_fund" ? "基金标准模板" : "股票标准模板"
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

  /**
   * 表格列（#1790 → #783 §6.1 口径）：数据列 9 + 勾选 + 操作 = **11 列**，
   * 最小宽合计（含勾选 50 / 操作 120）1060px，1200px 视口内无横向滚动。
   *
   * 数据列一律 `minWidth`——design.md「冻结列与横向滚动规范」第 4 条：只有冻结列
   * 才用固定 `width`（否则 EP 不把该列纳入余量分配，宽屏右侧留白，#1421 根因 2）；
   * §6.1 的 px 值即各列最小宽。
   *
   * 列收敛取舍（写明理由、不静默超宽，见 #1790 取舍说明）：
   * - 手续费（两模式）/ 合同编号 / 发生金额（股票模式）从表格退场——行数据仍完整
   *   携带、导入载荷不受影响，仅不再占列；
   * - 金额列 120→90 并接入行内编辑；勾选 80→50、状态 70→60、配置目标 120→110、
   *   备注 120→80 对齐 §6.1 明示宽度。
   */
  const tableColumns = computed(() => {
    if (isFundMode.value) {
      return [
        {
          prop: "status",
          label: "状态",
          minWidth: 60,
          slot: "status",
          align: "center"
        },
        { prop: "product", label: "产品信息", minWidth: 160, slot: "product" },
        { prop: "opType", label: "操作类型", minWidth: 110, slot: "opType" },
        { prop: "trade_date", label: "日期", minWidth: 100 },
        {
          prop: "quantity",
          label: "份额",
          minWidth: 90,
          slot: "quantity",
          align: "right"
        },
        {
          prop: "price",
          label: "确认净值",
          minWidth: 90,
          slot: "price",
          align: "right"
        },
        {
          prop: "amount",
          label: "金额",
          minWidth: 90,
          slot: "amount",
          align: "right"
        },
        {
          prop: "allocation",
          label: "配置目标",
          minWidth: 110,
          slot: "allocation"
        },
        { prop: "notes", label: "备注", minWidth: 80 }
      ];
    }
    return [
      {
        prop: "status",
        label: "状态",
        minWidth: 60,
        slot: "status",
        align: "center"
      },
      { prop: "product", label: "产品信息", minWidth: 160, slot: "product" },
      { prop: "opType", label: "操作类型", minWidth: 110, slot: "opType" },
      { prop: "trade_date", label: "日期", minWidth: 100 },
      {
        prop: "quantity",
        label: "数量",
        minWidth: 90,
        slot: "quantity",
        align: "right"
      },
      {
        prop: "price",
        label: "单价",
        minWidth: 90,
        slot: "price",
        align: "right"
      },
      {
        prop: "amount",
        label: "交易金额",
        minWidth: 90,
        slot: "amount",
        align: "right"
      },
      {
        prop: "allocation",
        label: "配置目标",
        minWidth: 110,
        slot: "allocation"
      },
      { prop: "notes", label: "备注", minWidth: 80 }
    ];
  });

  const blockedCount = computed(() => {
    return previewData.value.filter(
      row =>
        isRowBlocked(row) &&
        !row.is_duplicate &&
        !row.error &&
        !row.is_cash_transfer
    ).length;
  });

  const selectedCount = computed(() => selectedKeys.value.size);

  const nothingImported = computed(
    () =>
      importedCount.value === 0 &&
      orphanCount.value === 0 &&
      importErrors.value.length > 0
  );

  const showPriceUpdateTip = computed(() => {
    if (importedCount.value === 0) return false;
    return previewData.value.some(row => {
      if (!selectedKeys.value.has(row._rowKey)) return false;
      return ["stock", "fund", "etf", "bond"].includes(row.type);
    });
  });

  const allocationGroupsByType = computed(() => {
    const groups: Record<
      string,
      { label: string; count: number; currentAllocation: string }
    > = {};
    previewData.value.forEach(row => {
      if (
        row.is_duplicate ||
        row.error ||
        row.is_cash_transfer ||
        isRowBlocked(row) ||
        row._allocationManual
      )
        return;
      const type = row.type || "unknown";
      if (!groups[type])
        groups[type] = {
          label: getTypeLabel(type),
          count: 0,
          currentAllocation: row.allocation || "longterm"
        };
      groups[type].count++;
    });
    return Object.entries(groups).map(([type, data]) => ({ type, ...data }));
  });

  const currentAllocationGroups = computed(() => allocationGroupsByType.value);

  const errorSummary = computed(() => {
    const groups: Record<string, { count: number; items: string[] }> = {};
    importErrors.value.forEach(err => {
      const reason = err.error || "未知错误";
      const name = err.name || err.symbol || "--";
      if (!groups[reason]) groups[reason] = { count: 0, items: [] };
      groups[reason].count++;
      groups[reason].items.push(name);
    });
    return Object.entries(groups).map(([reason, data]) => ({
      reason,
      ...data
    }));
  });

  // ── 三卡片分类（#1791）：互斥完备，卡片计数 / fix 细分 / 表格状态过滤共用同一谓词 ──

  /** 代码未匹配（fixSectionRows 的 missingCode 分区谓词） */
  function isMissingCode(row: any): boolean {
    return !row.symbol || row.symbol === "UNKNOWN";
  }

  /** 金额不一致（fixSectionRows 的 mismatch 分区谓词）：有份额有价格但乘积与金额对不上 */
  function isAmountMismatch(row: any): boolean {
    const qty = Number(row.quantity),
      prc = Number(row.price),
      amt = Number(row.amount);
    return (
      !isNaN(qty) &&
      qty > 0 &&
      !isNaN(prc) &&
      prc > 0 &&
      !isNaN(amt) &&
      Math.abs(qty * prc - amt) > 0.01
    );
  }

  /**
   * 三卡片分类谓词——卡片条数、fix 细分统计、表格状态过滤三处共用（#1791 验收②：
   * 「卡片条数 = 展开后表格条数」靠共用谓词结构性成立，而不是两处各数一遍对数）。
   *
   * - duplicate：解析期已判重（(ledger_id, import_hash) 已在库）
   * - fix：解析错误 → 代码未匹配 → 数量/价格缺失 → 金额不一致（顺序对齐 fixSectionRows 分区）
   * - complete：其余——含资金划转行（数据完整，是否入库由后端统一裁决 #1010）、
   *   含 _ignored 行（数据完整是质量口径，勾没勾是选择口径，二者分开）
   */
  function categorizeRow(row: any): SummaryCategory {
    if (row.is_duplicate) return "duplicate";
    if (row.error) return "fix";
    if (row.is_cash_transfer) return "complete";
    if (isMissingCode(row)) return "fix";
    if (isRowBlocked(row)) return "fix";
    if (isAmountMismatch(row)) return "fix";
    return "complete";
  }

  /** 三卡片条数：遍历原始行分区计数，故 sum === totalRows（和式不变量） */
  const summaryCounts = computed(() => {
    const counts = { complete: 0, duplicate: 0, fix: 0 };
    previewData.value.forEach(row => counts[categorizeRow(row)]++);
    return counts;
  });

  /**
   * 四分区行源（#1792）：修正面板与 fixBreakdown 共用的唯一分桶。
   * 不变量：某行进入且仅进入一个分区 ⟺ categorizeRow(row) === "fix"——
   * 摘要卡「需要修正」条数 = 四分区行数之和，结构性成立（沿 #1791 验收② 的共谓词纪律）。
   */
  const fixSectionRows = computed<Record<FixSectionKey, any[]>>(() => {
    const rows: Record<FixSectionKey, any[]> = {
      error: [],
      missingCode: [],
      missingQtyPrice: [],
      mismatch: []
    };
    previewData.value.forEach(row => {
      if (row.is_duplicate || row.is_cash_transfer) return;
      if (row.error) rows.error.push(row);
      else if (isMissingCode(row)) rows.missingCode.push(row);
      else if (isRowBlocked(row)) rows.missingQtyPrice.push(row);
      else if (isAmountMismatch(row)) rows.mismatch.push(row);
    });
    return rows;
  });

  /** 「需要修正」卡的细分统计：四分区行数直取，四桶之和恒等于 fix 条数 */
  const fixBreakdown = computed(() => ({
    error: fixSectionRows.value.error.length,
    missingCode: fixSectionRows.value.missingCode.length,
    missingQtyPrice: fixSectionRows.value.missingQtyPrice.length,
    mismatch: fixSectionRows.value.mismatch.length
  }));

  // ── #1792 修正形态（#783 §4 阈值）与逐条卡片数据源 ──

  const fixSectionCounts = computed<SectionCounts>(() => ({
    error: fixSectionRows.value.error.length,
    missingCode: fixSectionRows.value.missingCode.length,
    missingQtyPrice: fixSectionRows.value.missingQtyPrice.length,
    mismatch: fixSectionRows.value.mismatch.length
  }));

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
  const singleFixRows = computed<Array<{ row: any; section: FixSectionKey }>>(
    () => {
      const keys: FixSectionKey[] =
        singleFixScope.value === "all"
          ? ["error", "missingCode", "missingQtyPrice", "mismatch"]
          : [singleFixScope.value];
      const out: Array<{ row: any; section: FixSectionKey }> = [];
      keys.forEach(key =>
        fixSectionRows.value[key].forEach(row =>
          out.push({ row, section: key })
        )
      );
      return out;
    }
  );

  /** 逆回购行：解析期由后端按代码模式识别（沪 204xxx / 深 1318xx），非问题分区——信息型 */
  const reverseRepoRows = computed(() =>
    previewData.value.filter(row => row.type === "reverse_repo")
  );

  /** 自动填充可推算行：只缺一个（数量或价格）且金额在——缺的那个 = 金额 ÷ 另一个 */
  const autoFillableRows = computed(() =>
    fixSectionRows.value.missingQtyPrice.filter(row => {
      const qty = Number(row.quantity),
        prc = Number(row.price),
        amt = Number(row.amount);
      const qtyMissing = isNaN(qty) || qty <= 0;
      const prcMissing = isNaN(prc) || prc <= 0;
      if (isNaN(amt) || amt <= 0) return false;
      return (qtyMissing && !prcMissing) || (!qtyMissing && prcMissing);
    })
  );

  /** 已自动填充过的行（_autoFilled 记录字段名）——【查看已填充数据】的数据源 */
  const filledRows = computed(() =>
    previewData.value.filter(row => row._autoFilled?.length > 0)
  );

  /**
   * 表格行过滤（状态 + 子分类 + 问题开关 + 关键词 + 类型）。
   * #1791 起分页数据与总条数共用本函数——此前是两处 90 行近重复实现，新增过滤键
   * 只改一边就会出现「分页显示与底部总条数对不上」的漂移。
   * 旧键 normal / problem / error 是 SummaryStats 胶囊 Tab 的写入值，胶囊已随本卡
   * 删除（#1791 要做的事 7：两套分类法合并），死分支一并移除。
   */
  function applyRowFilters(base: any[]): any[] {
    let list = base;
    const status = tableStatusFilter.value;
    if (status === "blocked")
      list = list.filter(
        row =>
          isRowBlocked(row) &&
          !row.is_duplicate &&
          !row.error &&
          !row.is_cash_transfer
      );
    else if (
      status === "complete" ||
      status === "duplicate" ||
      status === "fix"
    )
      // 三卡片状态键：与卡片计数同谓词（categorizeRow）
      list = list.filter(row => categorizeRow(row) === status);

    if (activeCategoryFilter.value === "missingCode")
      list = list.filter(
        row =>
          isMissingCode(row) &&
          !row.is_duplicate &&
          !row.error &&
          !row.is_cash_transfer
      );
    else if (activeCategoryFilter.value === "mismatch")
      list = list.filter(row => {
        if (row.is_duplicate || row.error || row.is_cash_transfer) return false;
        return isAmountMismatch(row);
      });
    else if (activeCategoryFilter.value === "error")
      list = list.filter(
        row => !!row.error && !row.is_duplicate && !row.is_cash_transfer
      );

    if (showProblemOnly.value)
      list = list.filter(row => {
        if (row.is_duplicate && row._duplicateHandled) return false;
        return (
          isRowBlocked(row) ||
          row.error ||
          row.is_duplicate ||
          row.isEditingQty ||
          row.isEditingPrice ||
          row.isEditingAmount
        );
      });
    if (tableFilterKeyword.value) {
      const kw = tableFilterKeyword.value.toLowerCase();
      list = list.filter(
        row =>
          String(row.symbol).toLowerCase().includes(kw) ||
          String(row.name).toLowerCase().includes(kw)
      );
    }
    if (tableTypeFilter.value.length > 0)
      list = list.filter(row => tableTypeFilter.value.includes(row.type));
    return list;
  }

  /** link_group 合并（分红 + 税折叠为一条净额行）——分页与计数共用，保证两者一致 */
  function mergeLinkGroups(list: any[]): any[] {
    const mergedList: any[] = [];
    const processedGroupIds = new Set<string>();
    for (const row of list) {
      const groupId = row.link_group_id;
      if (groupId && !processedGroupIds.has(groupId)) {
        const groupRows = list.filter(r => r.link_group_id === groupId);
        if (groupRows.length === 2) {
          const interestRow =
            groupRows.find(r => r.op_type === "dividend") || groupRows[0];
          const taxRow =
            groupRows.find(r => r.op_type === "tax") || groupRows[1];
          const netAmount = (interestRow.amount || 0) + (taxRow.amount || 0);
          const parentKey = `merged_${interestRow._rowKey}`;
          const detailRows = groupRows.map(r => ({ ...r }));
          mergedList.push({
            ...interestRow,
            _rowKey: parentKey,
            amount: netAmount,
            net_amount: netAmount,
            is_merged: true,
            children: detailRows,
            notes: `税前${interestRow.amount?.toFixed(2)}元，扣税${Math.abs(taxRow.amount || 0).toFixed(2)}元，实收${netAmount.toFixed(2)}元`,
            op_type_label: "利息收入"
          });
          processedGroupIds.add(groupId);
        } else {
          groupRows.forEach(r => mergedList.push(r));
          processedGroupIds.add(groupId);
        }
      } else if (!groupId) mergedList.push(row);
    }
    return mergedList;
  }

  /** 过滤 + 合并后的完整列表——分页切片与总条数的唯一来源 */
  const filteredMergedData = computed(() =>
    mergeLinkGroups(applyRowFilters(previewData.value))
  );

  const filteredPagedData = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value;
    return filteredMergedData.value.slice(start, start + pageSize.value);
  });

  const calculatedCount = computed(() => {
    return previewData.value.filter(row => row.is_calculated).length;
  });

  const enrichingNav = ref(false);

  // 需要填充净值的基金记录：非货币，有代码，有日期，但净值或份额为空
  const fundRecordsForNav = computed(() => {
    return previewData.value.filter(
      row =>
        row.type === "fund" &&
        row.type !== "money_fund" &&
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
            row.type !== "money_fund" &&
            row.trade_date === date &&
            row.symbol &&
            symbols.includes(row.symbol)
          ) {
            const nav = navMap[row.symbol];
            if (nav && nav > 0) {
              row.price = nav;
              row.quantity = row.amount / nav;
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
  function getTemplateKeyForLedger(ledger: LedgerItem | null): string {
    if (!ledger) return "";
    switch (ledger.ledger_type) {
      case "stock":
        return "standard_stock";
      case "fund":
      case "cash":
        return "standard_fund";
      default:
        return "";
    }
  }

  const lockedTemplateKey = computed(() =>
    getTemplateKeyForLedger(
      ledgers.value.find(l => l.id === selectedLedgerId.value) || null
    )
  );

  function isRowBlocked(row: any): boolean {
    if (row.is_cash_transfer || row.error || row.is_duplicate) return false;
    if (
      row.op_type === "tax" ||
      row.op_type === "dividend" ||
      row.op_type === "dividend_cash" ||
      row.op_type === "dividend_reinvest" ||
      row.op_type === "split"
    )
      return false;
    if (row.type === "money_fund" || row.type === "reverse_repo") return false;
    const qty = Number(row.quantity),
      prc = Number(row.price);
    return isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0;
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
  }

  function getFundTypeColor(typeName: string): string {
    return fundTypeColorMap[typeName] || "var(--palette-stone-gray)";
  }

  function getTypeColor(type: string): string {
    return typeColorMap[type] || "var(--palette-stone-gray)";
  }

  function addRowKeys(data: any[]) {
    return data.map((item, idx) => ({ ...item, _rowKey: `row_${idx}` }));
  }

  function isRowSelected(row: any): boolean {
    return selectedKeys.value.has(row._rowKey);
  }

  function recalcValidRowsCount() {
    validRowsCount.value = previewData.value.filter(
      row =>
        !row.is_duplicate &&
        !row.error &&
        !isRowBlocked(row) &&
        !row.is_cash_transfer
    ).length;
  }

  function updateSelectAllState() {
    // 按成员判定，不用尺寸比较：#1791 放开疑似重复行的勾选后 selectedKeys.size
    // 会因多选重复行而超出有效行数——「漏选 1 条有效行 + 多选 1 条重复行」尺寸恰好
    // 相等，会被误判为全选（表头复选框说谎）。eligible 口径与 selectAllValid 一致。
    let eligible = 0;
    let picked = 0;
    previewData.value.forEach(row => {
      if (
        !row.is_duplicate &&
        !row.error &&
        !isRowBlocked(row) &&
        !row.is_cash_transfer &&
        !row._ignored
      ) {
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
    orphanCount.value = 0;
    isAllSelected.value = false;
    isIndeterminate.value = false;
    importErrors.value = [];
    validRowsCount.value = 0;
    showFullTable.value = true;
    showFixPanel.value = false;
    fixModeOverride.value = null;
    singleFixScope.value = "all";
    fixUndoStack.value = [];
    tableFilterKeyword.value = "";
    tableTypeFilter.value = [];
    tableStatusFilter.value = "";
    duplicatesHandled.value = false;
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

  function handleUploadClick() {
    if (!selectedLedgerId.value) {
      ElMessage.warning("请先选择交易所属账户");
      const el = document.querySelector(".ledger-select-area .el-select");
      if (el) {
        el.classList.add("ledger-select-flash");
        setTimeout(() => el.classList.remove("ledger-select-flash"), 600);
      }
      ledgerTouched.value = true;
    }
  }

  function toggleFullTable() {
    showFullTable.value = !showFullTable.value;
    if (showFullTable.value) {
      showProblemOnly.value = false;
    }
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
      const rawData = (res as any).data ?? [];
      previewData.value = addRowKeys(rawData);
      totalRows.value = previewData.value.length;
      duplicateCount.value = (res as any).duplicate_count ?? 0;
      errorCount.value = (res as any).error_count ?? 0;

      const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
      const defaultAlloc = ledger?.default_allocation || "longterm";
      previewData.value.forEach(row => {
        row.account_name =
          row.account_name && row.account_name !== "默认证券账户"
            ? row.account_name
            : ledger?.name || "";
        if (row.allocation == null) row.allocation = defaultAlloc;
        if (
          !isRowBlocked(row) &&
          !row.is_cash_transfer &&
          !row.error &&
          !row.is_duplicate
        ) {
          const qty = parseFloat(row.quantity),
            prc = parseFloat(row.price),
            amt = parseFloat(row.amount);
          if (
            !isNaN(qty) &&
            qty > 0 &&
            (isNaN(prc) || prc <= 0) &&
            !isNaN(amt)
          ) {
            row.price = parseFloat((amt / qty).toFixed(4));
            row.smartFilled = true;
          }
        }
      });

      previewData.value = [...previewData.value];
      recalcValidRowsCount();
      selectAllValid();
      showFullTable.value = true;

      const warning = (res as any).compatibility_warning;
      if (warning) {
        await ElMessageBox.confirm(warning, "文件格式提醒", {
          confirmButtonText: "继续导入",
          cancelButtonText: "返回重选",
          type: "warning"
        })
          .then(() => (currentStep.value = 2))
          .catch(() => {
            parsing.value = false;
            return;
          });
      } else {
        ElMessage.success(`解析完成，共识别 ${totalRows.value} 条记录`);
        currentStep.value = 2;
      }
      // #1239 草稿层：进入预览步骤即保存草稿（含勾选状态，Set→数组序列化）
      await persistDraft();
      options.onSuccess(res);
    } catch (e: any) {
      const errorMsg =
        e?.response?.data?.message || e?.message || "文件解析失败";
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
    // ⚠️ 后端边界：commit_from_preview 仍无条件跳过 is_duplicate 行，且 import_hash
    // 唯一约束会二次拦截——「勾选保留」目前只到导入集合层面，落库由后续 issue 承接。
    const rowsToImport = previewData.value.filter(
      row =>
        selectedKeys.value.has(row._rowKey) &&
        !row.error &&
        !row._ignored &&
        !isRowBlocked(row)
    );
    if (rowsToImport.length === 0)
      return ElMessage.warning("没有可导入的有效记录");

    importing.value = true;
    try {
      const res = await confirmImportApi(rowsToImport);
      const result = (res as any).data ?? {};
      importedCount.value = result.imported ?? 0;
      skippedCount.value = result.skipped ?? 0;
      cashTransfersCreated.value = result.cash_transfers_created ?? 0;
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
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "导入失败");
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
        selectedLedgerId.value = draft.selectedLedgerId;
      }
      if (draft.selectedMode) selectedMode.value = draft.selectedMode;
      // 回填预览数据（行内编辑状态保留）
      previewData.value = addRowKeys(draft.rows);
      totalRows.value = previewData.value.length;
      // 回填勾选（数组 → Set）
      selectedKeys.value = new Set(draft.selectedKeySet);
      // 重算统计
      duplicateCount.value = previewData.value.filter(
        r => r.is_duplicate
      ).length;
      errorCount.value = previewData.value.filter(r => !!r.error).length;
      recalcValidRowsCount();
      updateSelectAllState();
      showFullTable.value = true;
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

  function selectAllValid() {
    const newKeys = new Set<string>();
    previewData.value.forEach(row => {
      if (
        !row.is_duplicate &&
        !row.error &&
        !isRowBlocked(row) &&
        !row.is_cash_transfer &&
        !row._ignored
      )
        newKeys.add(row._rowKey);
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

  function handleRowCheckboxChange(row: any, checked: boolean) {
    if (checked) selectedKeys.value.add(row._rowKey);
    else selectedKeys.value.delete(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
    updateSelectAllState();
  }

  /** 逐行忽略：标记该行不参与导入（与整类跳过 skipCategory 互补，针对单行）；再点一次恢复 */
  function toggleIgnoreRow(row: any) {
    row._ignored = !row._ignored;
    if (row._ignored) selectedKeys.value.delete(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
    previewData.value = [...previewData.value];
    updateSelectAllState();
  }

  async function fillNavForRecords(rows: any[]) {
    // 过滤出需要净值的记录：非货币、有代码、有日期、缺少价格或份额
    const needed = rows.filter(
      row =>
        row.type === "fund" &&
        row.type !== "money_fund" &&
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
              row.quantity = row.amount / nav;
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
    rows: any[]
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

  function pushUndo(scope: FixUndoEntry["scope"], label: string, rows: any[]) {
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
  async function batchFillCode(rows: any[], code: string) {
    if (!code.trim()) return ElMessage.warning("请输入有效的证券代码");
    pushUndo("code", `填充证券代码 ${code.trim()}`, rows);
    rows.forEach(r => (r.symbol = code.trim()));
    recalcValidRowsCount();
    updateSelectAllState();
    await nextTick();

    // 自动填充净值和份额
    await fillNavForRecords(rows);

    previewData.value = [...previewData.value];
    ElMessage.success(`已为 ${rows.length} 条记录设置代码「${code}」`);
  }

  async function batchFixAmount(rows?: any[]) {
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

  async function skipCategory(rows: any[]) {
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
    row: any,
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
  function repoDetectBasis(row: any): string {
    const code = String(row.symbol || "");
    if (/^204\d{3}$/.test(code)) return "沪市 204 模式";
    if (/^1318\d{2}$/.test(code)) return "深市 1318 模式";
    return "解析器识别";
  }

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
      // 隐藏所有重复行
      for (const row of data) {
        if (row.is_duplicate) {
          row._duplicateHandled = true;
          selectedKeys.value.delete(row._rowKey);
        }
      }
      selectedKeys.value = new Set(selectedKeys.value);
      duplicatesHandled.value = true;
    }

    // 2. 一次性替换，只触发一次响应式更新
    previewData.value = data;
    recalcValidRowsCount();
    updateSelectAllState();

    ElMessage.success(
      duplicatesHandled.value
        ? `已取消 ${duplicateCount.value} 条重复数据的展示`
        : "已恢复全部重复数据"
    );
  }

  function filterByCategory(key: string) {
    showFullTable.value = true;
    showProblemOnly.value = false;
    tableStatusFilter.value = "";
    if (key === "missingCode") activeCategoryFilter.value = "missingCode";
    else if (key === "missingQtyPrice") tableStatusFilter.value = "blocked";
    else if (key === "mismatch") activeCategoryFilter.value = "mismatch";
    else if (key === "error") activeCategoryFilter.value = "error";
  }

  // ── #1791 三卡片：展开/收起类别过滤 + 卡片复选框 ──

  /** 该类别当前是否展开（tableStatusFilter 就是展开状态：一套状态，两处读） */
  function isCategoryExpanded(key: SummaryCategory): boolean {
    return tableStatusFilter.value === key;
  }

  /**
   * 【展开查看】/【收起】（#1791 要做的事 2）：tableStatusFilter 在 key↔"" 间切换。
   * 展开时清掉子分类与「只看问题」开关——它们与三卡片是两套互斥的过滤视角，叠加会
   * 令「卡片条数 ≠ 表格条数」（验收②）；关键词/类型搜索是正交收窄，予以保留。
   */
  function toggleCategoryFilter(key: SummaryCategory) {
    if (tableStatusFilter.value === key) {
      tableStatusFilter.value = "";
      return;
    }
    tableStatusFilter.value = key;
    activeCategoryFilter.value = "";
    showProblemOnly.value = false;
    showFullTable.value = true;
    currentPage.value = 1;
  }

  /** 【展开全部数据】：清空全部过滤回完整表格；摘要面板不在过滤作用域内，始终可见（验收③） */
  function expandAllData() {
    tableStatusFilter.value = "";
    activeCategoryFilter.value = "";
    showProblemOnly.value = false;
    showFullTable.value = true;
    currentPage.value = 1;
  }

  /**
   * 卡片复选框的作用域 = 该类中「行复选框可勾」的行：
   * 解析错误 / 数量价格缺失（isRowBlocked）/ 资金划转行不可勾（表格行复选框同样禁用），
   * _ignored 是用户显式忽略、不参与卡片批量勾选；**疑似重复行可勾**（#1791 验收④）。
   */
  function isRowSelectable(row: any): boolean {
    return (
      !row.error && !row.is_cash_transfer && !row._ignored && !isRowBlocked(row)
    );
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

  /** 卡片复选框切换：勾选=选中该类全部可选行，取消=仅取消该类（不动其它类别） */
  function toggleCategorySelection(key: SummaryCategory, checked: boolean) {
    previewData.value.forEach(row => {
      if (categorizeRow(row) !== key || !isRowSelectable(row)) return;
      if (checked) selectedKeys.value.add(row._rowKey);
      else selectedKeys.value.delete(row._rowKey);
    });
    selectedKeys.value = new Set(selectedKeys.value);
    updateSelectAllState();
  }

  function onMatchComplete() {
    previewData.value = [...previewData.value];
    showFullTable.value = true;
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

  function applyAllocationGroupSetting(group: any, allocation: string) {
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

  function onRowAllocationChange(row: any) {
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
  function startEdit(row: any, field: string) {
    if (editingRowKey.value && editingRowKey.value !== row._rowKey) {
      saveAllEditingRows();
      closeAllEditing();
    } else if (editingRowKey.value === row._rowKey) {
      // 同行切格兜底：上一格按提交收尾（Tab 路径已自行 finishEdit），保住已改值
      if (row.isEditingQty) finishEdit(row, "quantity", true);
      else if (row.isEditingPrice) finishEdit(row, "price", true);
      else if (row.isEditingAmount) finishEdit(row, "amount", true);
    }
    row._oldValue = row[field];
    row.isEditingQty = field === "quantity";
    row.isEditingPrice = field === "price";
    row.isEditingAmount = field === "amount";
    editingRowKey.value = row._rowKey;
    previewData.value = [...previewData.value]; // 新增
  }

  function finishEdit(row: any, field: string, save: boolean = true) {
    const wasBlocked = isRowBlocked(row);
    if (!save) row[field] = row._oldValue;
    else {
      smartFill(row, field);
      recalcAfterEdit(row, field); // §6.2：改数量单价→重算金额；改金额→反算
    }
    delete row._oldValue;
    if (field === "quantity") row.isEditingQty = false;
    else if (field === "price") row.isEditingPrice = false;
    else row.isEditingAmount = false;
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

  function cancelEdit(row: any, field: string) {
    finishEdit(row, field, false);
  }

  function saveAllEditingRows() {
    previewData.value.forEach(row => {
      if (row.isEditingQty) finishEdit(row, "quantity", true);
      if (row.isEditingPrice) finishEdit(row, "price", true);
      if (row.isEditingAmount) finishEdit(row, "amount", true);
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
    });
    editingRowKey.value = null;
    previewData.value = [...previewData.value]; // 新增
  }

  function getRowClassName({ row }: { row: any }) {
    if (row.is_duplicate) return "row-duplicate";
    if (row.error || isRowBlocked(row)) return "row-blocked";
    return "";
  }

  function getCellClassName({ row, column }: { row: any; column: any }) {
    const prop = column.property;
    if (
      prop === "quantity" &&
      isRowBlocked(row) &&
      !row.is_duplicate &&
      !row.error
    )
      return "cell-blocked";
    if (
      prop === "price" &&
      isRowBlocked(row) &&
      !row.is_duplicate &&
      !row.error
    )
      return "cell-blocked";
    // cell-missing 随手续费列退场改挂金额列（#1790 列收敛，理由见 #1790 取舍说明）
    if (prop === "amount" && isMissingAmount(row)) return "cell-missing";
    return "";
  }

  function getCategoryDesc(key: string): string {
    const map: Record<string, string> = {
      error: "解析错误，无法在面板内修正",
      missingCode: "系统无法识别以下证券代码",
      missingQtyPrice: "数量或价格缺失",
      mismatch: "金额与数量×价格不符"
    };
    return map[key] || "";
  }

  function getCategoryTagType(
    key: string,
    count: number
  ): "danger" | "warning" | "success" | "info" {
    if (count > 200) return "danger";
    if (count > 50) return "warning";
    if (count > 10) return "info";
    return "success";
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
      ledgers.value = (res as any).data ?? [];
      salesInstitutionsForImport.value = instRes?.data ?? [];
    } catch (e) {
      console.error(e);
    }
  }

  function getMissingRowsByType(rows: any[], type: string) {
    return rows.filter((r: any) => r.type === type);
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

  /** 步骤3 预览含银证转账、且当前账户未关联现金账户 —— 显示软提示 */
  const showCashBindingBanner = computed(() => {
    if (currentStep.value !== 2) return false;
    if (selectedLedgerLinkedCash.value) return false;
    return previewData.value.some((r: any) => r.is_cash_transfer);
  });

  /** 在步骤3 横幅内直接关联现金账户并落库 */
  async function linkCashAccount() {
    if (!selectedLedgerId.value || !bannerCashLedgerId.value) return;
    try {
      await updateLedgerApi(selectedLedgerId.value, {
        linked_cash_ledger_id: bannerCashLedgerId.value
      });
      await fetchLedgers();
      ElMessage.success("已关联现金账户");
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "关联失败");
    }
  }

  async function createLedger() {
    const name = newLedgerName.value.trim();
    if (!name) return;
    const payload: any = { name };
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
    if (newLedgerAllocation.value)
      payload.default_allocation = newLedgerAllocation.value;
    try {
      const res = await createLedgerApi(payload);
      const ledger = (res as any).data;
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
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || "添加失败");
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
    showFullTable.value = true;
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
    importedCount,
    skippedCount,
    cashTransfersCreated,
    orphanCount,
    importing,
    parsing,
    uploading,
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
    bannerCashLedgerId,
    resetNewLedgerForm,
    openCreateCashFromBanner,
    cashLedgersForImport,
    selectedLedgerLinkedCash,
    showCashBindingBanner,
    linkCashAccount,
    ledgerTouched,
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
    showFullTable,
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
    isDragover,
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
    getTemplateKeyForLedger,
    isRowBlocked,
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
    toggleFullTable,
    beforeUpload,
    handleUpload,
    confirmImport,
    importNormalOnly,
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
    persistDraft,
    checkDraft,
    restoreDraft,
    discardCurrentDraft
  };
}
