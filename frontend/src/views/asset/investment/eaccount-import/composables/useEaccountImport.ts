import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { UploadRequestOptions } from "element-plus";
import {
  parseHoldings,
  reconcileEaccount,
  type HoldingParseRow,
  type ReconcileResult
} from "@/api/eaccount";
import {
  recognizeImage,
  parseImportText,
  getOcrUsage,
  type OcrHoldingRow
} from "@/api/ocr";
import { confirmHoldingImport } from "@/api/importer";
import { getLedgers, type LedgerItem } from "@/api/ledger";
import { useReconDraft, type ReconDomain } from "@/composables/useReconDraft";

/**
 * 手动录入草稿行（#1788）：用户在表格里逐字填的内容。
 * 与 `OcrHoldingRow`（提交契约）分离——草稿不含账户 / 溯源字段，
 * 那些在「生成预览」时按当次选中的账户统一补齐，避免用户逐行重复填账户。
 */
export interface ManualHoldingDraft {
  /** v-for 稳定 key：删除行后索引会平移，用索引作 key 会让输入框内容错位 */
  key: number;
  symbol: string;
  name: string;
  /** 资产类型（asset_type）：决定 venue 是场内还是场外，缺省 fund 见 _build_holding_data */
  type: string;
  quantity: number;
  price: number;
  /** 快照日 YYYY-MM-DD */
  snapshot_date: string;
}

/** 单调递增的行 key 序列（仅前端展示用，不入提交 payload） */
let manualRowSeq = 0;

/** 空白手动行：类型默认基金（用户拍板），快照日默认今天 */
function emptyManualRow(): ManualHoldingDraft {
  return {
    key: ++manualRowSeq,
    symbol: "",
    name: "",
    type: "fund",
    quantity: 0,
    price: 0,
    snapshot_date: new Date().toISOString().slice(0, 10)
  };
}

/**
 * 「导入持仓快照」页状态单体（#980 P1-B 结构拆分，#1788 增补手动录入段）：
 * 草稿 / 上传解析 / AI 识别 / 手动录入 / 对账结果五段共享的状态与动作都收敛在这里，
 * index.vue 只做编排，子组件经 `page` prop 注入同一实例（P1-A profile/welcome 同款模式）。
 * onMounted 在此注册，挂载到调用方（index.vue）组件实例，与拆分前时序一致。
 */
export function useEaccountImport() {
  // #1239 草稿层：导入持仓快照 = 域 A（E账户对账域，域名沿用工作台口径）；恢复落回步骤 0「上传与预览」——
  // result 不随草稿保存，落步骤 1 会因 v-else-if="result" 不成立而内容区空白（#1694）
  const draftDomain: ReconDomain = "A";
  const { saveDraft, getDraftWithSet, discardDraft } = useReconDraft();
  const draftBannerVisible = ref(false);
  const pendingDraftMeta = ref<{ savedAt: string; rowCount: number } | null>(
    null
  );

  /** 兼容「信封 {data}」与「直接返回」两种响应形态（并行 lane 契约以直接返回为准） */
  function unwrap<T>(res: unknown): T {
    const r = res as { data?: T } | null;
    if (r && typeof r === "object" && "data" in r && r.data != null)
      return r.data;
    return res as T;
  }

  function errMsg(e: unknown, fallback: string): string {
    const err = e as {
      response?: { data?: { message?: string } };
      message?: string;
    };
    return err?.response?.data?.message || err?.message || fallback;
  }

  const router = useRouter();

  const STEPS = [{ title: "上传与预览" }, { title: "对账结果" }];

  const currentStep = ref(0);
  const parsing = ref(false);
  const reconciling = ref(false);
  const uploadError = ref("");
  const previewRows = ref<HoldingParseRow[]>([]);
  const parseMeta = ref({ total: 0, error_count: 0 });
  const result = ref<ReconcileResult | null>(null);
  const fileName = ref("");
  /** 预览表格客户端分页：当前页码 + 每页条数（默认 50） */
  const previewPage = ref(1);
  const previewPageSize = ref(50);

  const errorCount = computed(
    () => previewRows.value.filter(row => !!row.error).length
  );

  /** 解析成功（有行数据且无错误）→ 上传卡片折叠为一行状态条 */
  const parsedOk = computed(
    () => previewRows.value.length > 0 && !uploadError.value
  );

  /* ===== AI 识别持仓（holding_import 独立持仓管线，不建交易流水，见 #1018） ===== */
  const importMode = ref<"file" | "ai" | "manual">("file");
  const aiTab = ref<"text" | "image">("text");
  const aiText = ref("");
  const aiImageFile = ref<File | null>(null);
  const aiRecognizing = ref(false);
  const aiUsage = ref({ used: 0, limit: 10 });
  // #1695：用 ?? 而非 ||——limit=0（配额耗尽）是合法值，|| 会吞成 10 使展示失真
  const aiQuota = computed(() => aiUsage.value.limit ?? 10);
  const aiRemaining = computed(() =>
    Math.max(0, aiQuota.value - aiUsage.value.used)
  );

  /* ===== 手动录入分段（#1788，承接 #929 路径 1「手动表单只落持仓不建流水」）=====
     两条后端硬约束决定了这里的形状：
     ① `upsert_from_holding` 要求 symbol + ledger_id 必填（position_service.py:568），
        缺 ledger_id 整行导入失败 —— 故必须有账户。按用户口径做成**面板级**
        「先选账户、再录该账户下的持仓」，不逐行重复选；
     ② 提交必须走 `holdings/confirm` 而非本页原有的 `e-account/reconcile`：后者会建
        ledger_id=NULL 的影子记录并按 source_broker 做渠道归因，手动录入没有渠道，
        走它会把每条持仓都变成对账中心里一条待处理冲突。 */
  const manualLedgerId = ref<number | null>(null);
  const manualLedgers = ref<LedgerItem[]>([]);
  const manualRows = ref<ManualHoldingDraft[]>([emptyManualRow()]);
  /** 生成预览后的全量提交行（含账户 / 溯源字段），确认时原样交给 holdings/confirm */
  const manualPreviewRows = ref<OcrHoldingRow[]>([]);

  async function switchMode(mode: "file" | "ai" | "manual") {
    if (parsedOk.value) return;
    importMode.value = mode;
    if (mode === "ai") fetchAiUsage();
    if (mode === "manual") await ensureManualLedgers();
  }

  /** 拉账户列表：首次切到手动录入时才请求；剔除 property（静态资产账户放不了可交易持仓）。
   *  **不自动选中第一个账户** —— 持仓归属是用户决策，替他默认等于把仓位记到错误的账本上。 */
  async function ensureManualLedgers(): Promise<void> {
    if (manualLedgers.value.length > 0) return;
    try {
      const res = await getLedgers();
      manualLedgers.value = (res.data ?? []).filter(
        l => l.ledger_type !== "property"
      );
    } catch {
      /* 拉取失败不阻断页面：面板内显示加载失败并提供重试入口 */
    }
  }

  /** 追加一条空白持仓行 */
  function addManualRow(): void {
    manualRows.value.push(emptyManualRow());
  }

  /** 删除指定持仓行；删到只剩 0 行时补一条空行，保证面板始终有可录入的行 */
  function removeManualRow(index: number): void {
    manualRows.value.splice(index, 1);
    if (manualRows.value.length === 0) addManualRow();
  }

  async function fetchAiUsage() {
    try {
      const res = await getOcrUsage("holding_import");
      const d = res.data;
      // #1695：后端字段是 used（读 count 会得到 undefined → aiRemaining 恒 NaN）
      aiUsage.value = { used: d.used, limit: d.quota };
    } catch {
      /* 额度查询失败不阻断识别 */
    }
  }

  const canAiRecognize = computed(() =>
    aiTab.value === "text"
      ? aiText.value.trim().length > 0
      : !!aiImageFile.value
  );

  /** File → base64 字符串（去 data: 前缀），与 OcrImportModal 同一套转换 */
  function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        resolve(result.split(",")[1] ?? "");
      };
      reader.onerror = () => reject(new Error("图片读取失败"));
      reader.readAsDataURL(file);
    });
  }

  function mapHoldingRow(r: OcrHoldingRow): HoldingParseRow {
    return {
      symbol: r.symbol,
      name: r.name,
      quantity: Number(r.quantity) || 0,
      price: Number(r.price) || 0,
      snapshot_date: r.snapshot_date || "",
      error: r.error || ""
    };
  }

  async function handleAiRecognize() {
    if (!canAiRecognize.value || aiRemaining.value <= 0) return;
    aiRecognizing.value = true;
    try {
      let resp;
      if (aiTab.value === "text") {
        resp = await parseImportText(aiText.value, "holding_import");
      } else {
        const file = aiImageFile.value;
        if (!file) return;
        const base64 = await fileToBase64(file);
        resp = await recognizeImage(base64, "holding_import");
      }
      const rows = (resp.rows || []) as OcrHoldingRow[];
      if (!rows.length) {
        ElMessage.warning("未识别到有效持仓，请检查文本或图片内容");
        return;
      }
      previewRows.value = rows.map(mapHoldingRow);
      parseMeta.value = {
        total: rows.length,
        error_count: rows.filter(r => r.error).length
      };
      fileName.value =
        aiTab.value === "text"
          ? "AI 识别文本(持仓)"
          : (aiImageFile.value?.name ?? "AI 识别图片(持仓)");
      // AI 识别同样是「解析成功」，与文件路径一致落草稿（#1694）
      await persistDraft();
      importMode.value = "ai";
      ElMessage.success(`识别成功，共 ${rows.length} 条持仓`);
      await fetchAiUsage();
    } catch (e: any) {
      ElMessage.error(e?.message || "AI 识别失败，请稍后重试");
    } finally {
      aiRecognizing.value = false;
    }
  }

  /** 预览表格分页切片：在全量解析行上切片（errorCount / 状态条 / SectionHeader 统计均保持全量口径） */
  const pagedPreviewRows = computed(() => {
    const start = (previewPage.value - 1) * previewPageSize.value;
    return previewRows.value.slice(start, start + previewPageSize.value);
  });

  const conflictList = computed(() => result.value?.conflict_list ?? []);
  const failedList = computed(() => result.value?.failed_rows ?? []);

  /** 解析行数值可能为字符串（CSV），统一转 number，无效返回 null */
  function toNumber(value: number | string | undefined): number | null {
    if (value === undefined || value === null || value === "") return null;
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function beforeUpload(file: File): boolean {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (![".csv", ".xls", ".xlsx"].includes(ext)) {
      ElMessage.error("仅支持 CSV、Excel 文件");
      return false;
    }
    if (file.size > 5 * 1024 * 1024) {
      ElMessage.error("文件大小不能超过 5MB");
      return false;
    }
    return true;
  }

  /** 上传入口：el-upload 的 http-request 模式（与交易导入 UploadArea 同构） */
  async function handleUpload(options: UploadRequestOptions) {
    const file = options.file as File;
    parsing.value = true;
    uploadError.value = "";
    try {
      const res = await parseHoldings(file);
      // 后端 /holdings/parse 返回信封：data 即行数组，total/error_count 在顶层
      const rows = Array.isArray(res.data) ? res.data : [];
      previewRows.value = rows;
      parseMeta.value = {
        total: res.total ?? rows.length,
        error_count: res.error_count ?? 0
      };
      fileName.value = file.name;
      // #1694：文件解析成功即存草稿（与 useImportWizard L1069 同一时机），刷新可恢复
      await persistDraft();
      options.onSuccess(res);
    } catch (e) {
      uploadError.value = errMsg(e, "文件解析失败");
      options.onError(e);
    } finally {
      parsing.value = false;
    }
  }

  /** 有 error 的行标红（row-blocked 为 el-table.css 基线内置类） */
  function getRowClassName({ row }: { row: HoldingParseRow }): string {
    return row.error ? "row-blocked" : "";
  }

  /** 校验手动录入行，返回首条问题的中文提示；全部合法返回 null */
  function validateManualRows(): string | null {
    const rows = manualRows.value;
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      const line = `第 ${i + 1} 行`;
      if (!r.symbol.trim()) return `${line}：请填写代码`;
      if (!r.name.trim()) return `${line}：请填写名称`;
      if (!(r.quantity > 0)) return `${line}：份额必须大于 0`;
      if (!(r.price > 0)) return `${line}：成本价必须大于 0`;
      if (!r.snapshot_date) return `${line}：请选择快照日`;
    }
    return null;
  }

  /** 手动录入 → 与文件 / AI 同一种预览行：补齐账户与溯源字段后交给同一张预览表逐行核对 */
  async function generateManualPreview(): Promise<void> {
    if (manualLedgerId.value == null) {
      ElMessage.warning("请先选择归属账户");
      return;
    }
    if (manualRows.value.length === 0) {
      ElMessage.warning("请至少填写一条持仓");
      return;
    }
    const invalid = validateManualRows();
    if (invalid) {
      ElMessage.warning(invalid);
      return;
    }
    await ensureManualLedgers();
    const accountName =
      manualLedgers.value.find(l => l.id === manualLedgerId.value)?.name ?? "";
    const rows: OcrHoldingRow[] = manualRows.value.map(r => ({
      symbol: r.symbol.trim(),
      name: r.name.trim(),
      type: r.type,
      quantity: r.quantity,
      price: r.price,
      // 市值是派生值：后端只有一个 price（同时当成本价与现价用，见 _build_holding_data），
      // 所以 份额×成本价 才与落库口径一致，不给独立编辑以免出现「市值≠份额×单价」的自相矛盾
      amount: Math.round(r.quantity * r.price * 100) / 100,
      snapshot_date: r.snapshot_date,
      account_name: accountName,
      ledger_id: manualLedgerId.value as number,
      source: "manual",
      // 留空：import_hash 由后端按 (source, ledger_id, symbol, snapshot_date) 补算，
      // 前端算不了（哈希算法在 core/哈希函数里）也不该重复实现
      import_hash: ""
    }));
    manualPreviewRows.value = rows;
    // OcrHoldingRow 结构上是 HoldingParseRow 的超集，可直接喂给同一张预览表
    previewRows.value = rows;
    parseMeta.value = { total: rows.length, error_count: 0 };
    fileName.value = "手动录入";
    previewPage.value = 1;
  }

  /** 手动录入确认：走 holdings/confirm 落 positions（**绝不建交易流水**，#1788 / #1018 契约） */
  async function handleManualImport(): Promise<void> {
    const rows = manualPreviewRows.value;
    if (rows.length === 0) return;
    reconciling.value = true;
    try {
      const res = await confirmHoldingImport(rows);
      const d = unwrap<{
        imported?: number;
        skipped?: number;
        errors?: Array<{ symbol?: string; error?: string }>;
      }>(res);
      const imported = d?.imported ?? rows.length;
      const skipped = d?.skipped ?? 0;
      const failed = d?.errors?.length ?? 0;
      if (failed > 0) {
        ElMessage.warning(
          `导入完成：成功 ${imported} 条，失败 ${failed} 条（${d?.errors?.[0]?.error ?? "未知原因"}）`
        );
      } else {
        ElMessage.success(
          `已导入 ${imported} 条持仓${skipped ? `，跳过 ${skipped} 条` : ""}`
        );
      }
      clearManualPreview();
      manualRows.value = [emptyManualRow()];
    } catch (e) {
      ElMessage.error(errMsg(e, "导入失败"));
    } finally {
      reconciling.value = false;
    }
  }

  /** 清掉手动预览（导入成功后回到底部录入面板） */
  function clearManualPreview(): void {
    manualPreviewRows.value = [];
    previewRows.value = [];
    parseMeta.value = { total: 0, error_count: 0 };
    fileName.value = "";
    previewPage.value = 1;
  }

  /** 预览确认：error 行禁提交。手动录入走 holdings/confirm；文件 / AI 走 E账户对账归因 */
  async function handleReconcile() {
    if (errorCount.value > 0) {
      ElMessage.warning(
        importMode.value === "manual"
          ? `存在 ${errorCount.value} 条无效记录，请修正后重试`
          : `存在 ${errorCount.value} 条解析失败记录，请更换文件后重试`
      );
      return;
    }
    if (previewRows.value.length === 0) {
      ElMessage.warning(
        importMode.value === "manual"
          ? "没有可导入的记录，请先填写持仓行"
          : "没有可对账的记录，请先上传文件"
      );
      return;
    }
    if (importMode.value === "manual") {
      await handleManualImport();
      return;
    }
    reconciling.value = true;
    try {
      const res = await reconcileEaccount(previewRows.value);
      result.value = unwrap<ReconcileResult>(res);
      currentStep.value = 1;
      // #1239 草稿层：进入对账结果即丢弃草稿（数据已落库）
      await discardDraft().catch(() => {});
    } catch (e) {
      ElMessage.error(errMsg(e, "对账失败"));
    } finally {
      reconciling.value = false;
    }
  }

  function goToReconcileCenter() {
    router.push({ name: "InvestmentReconcile" });
  }

  function resetFlow() {
    currentStep.value = 0;
    previewRows.value = [];
    parseMeta.value = { total: 0, error_count: 0 };
    result.value = null;
    uploadError.value = "";
    fileName.value = "";
    previewPage.value = 1;
    // 手动录入一并复位（#1788）：manualRows 保留不清，只清全量提交行
    manualPreviewRows.value = [];
    // #1694：主动重置即丢弃草稿（对账成功路径已在 handleReconcile 丢过，此处为兜底幂等）
    discardCurrentDraft();
  }

  /** 从预览退回录入：清空解析结果，恢复大上传卡片 / AI 面板 / 手动录入面板。
   *  手动模式下 `manualRows` **不清** —— 用户点「返回修改」是要接着改已填的行，不是重来。 */
  function resetUpload() {
    uploadError.value = "";
    previewRows.value = [];
    parseMeta.value = { total: 0, error_count: 0 };
    fileName.value = "";
    previewPage.value = 1;
    manualPreviewRows.value = [];
    // #1694：用户放弃当前解析 → 草稿一并丢弃，防止下次进页 Banner 复活已重置的行
    discardCurrentDraft();
  }

  // ── #1239 草稿层：保存 / 恢复 / 丢弃（导入持仓快照=域 A，#1694 接线）──
  /** 把当前预览状态持久化为草稿（解析成功后调用；空行不存，恢复无意义） */
  async function persistDraft(): Promise<void> {
    if (previewRows.value.length === 0) return;
    // 手动录入不入草稿（#1788）：域 A 草稿存的是「解析出来的行」，恢复路径只还原
    // previewRows，还原不了 manualRows 的可编辑态——半还原比不还原更糟（回去改都没得改）。
    if (importMode.value === "manual") return;
    try {
      await saveDraft({
        domain: draftDomain,
        // 文件 / AI 两档无显式账户选择（后端按快照域聚合），故恒为 null；
        // 手动录入有 ledger_id 但不走这条路径
        ledgerId: null,
        // 恢复落步骤 0 上传与预览：result 不随草稿保存，写 1 会让恢复后的内容区空白（#1694）
        currentStep: 0,
        rows: previewRows.value
      });
      // 新解析已覆盖存储中的草稿，挂载时留下的旧 Banner 语义失效（其内容就是当前预览），收起
      draftBannerVisible.value = false;
      pendingDraftMeta.value = null;
    } catch (e) {
      console.warn("保存草稿失败", e);
    }
  }

  /** 检查是否存在同域（A）草稿；存在则返回元数据供 Banner 展示 */
  async function checkDraft(): Promise<boolean> {
    try {
      const draft = await getDraftWithSet();
      if (!draft || draft.domain !== draftDomain) return false;
      pendingDraftMeta.value = {
        savedAt: draft.savedAt,
        rowCount: draft.rows.length
      };
      draftBannerVisible.value = true;
      return true;
    } catch {
      return false;
    }
  }

  /** 恢复草稿：回填 previewRows 并落回步骤 0 预览（#1694：result 不随草稿保存，
   *  落步骤 1 会因模板 v-else-if="result" 不成立而只剩页头与步骤条） */
  async function restoreDraft(): Promise<void> {
    try {
      const draft = await getDraftWithSet();
      if (!draft || draft.domain !== draftDomain) return;
      previewRows.value = draft.rows;
      // 草稿只会来自文件 / AI（persistDraft 对 manual 已早退）。若用户先切到手动分段
      // 再点「恢复草稿」，必须把模式钉回 file —— 否则会把文件行喂给 holdings/confirm
      // 而行里没有 ledger_id，整批导入失败。
      importMode.value = "file";
      manualPreviewRows.value = [];
      parseMeta.value = {
        total: draft.rows.length,
        error_count: draft.rows.filter(r => !!r.error).length
      };
      currentStep.value = 0;
      previewPage.value = 1; // 分页回首页，防止沿用恢复前的页码
      fileName.value = "恢复的草稿"; // 草稿不存文件名，给状态条一个可读占位（#1694）
      draftBannerVisible.value = false;
      pendingDraftMeta.value = null;
      ElMessage.success("已恢复未完成的导入草稿");
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

  // 页面加载后检查同域草稿
  onMounted(() => {
    checkDraft();
  });

  return {
    STEPS,
    currentStep,
    parsing,
    reconciling,
    uploadError,
    previewRows,
    parseMeta,
    result,
    fileName,
    previewPage,
    previewPageSize,
    errorCount,
    parsedOk,
    importMode,
    aiTab,
    aiText,
    aiImageFile,
    aiRecognizing,
    aiQuota,
    aiRemaining,
    // 手动录入分段（#1788）
    manualLedgerId,
    manualLedgers,
    manualRows,
    manualPreviewRows,
    ensureManualLedgers,
    addManualRow,
    removeManualRow,
    generateManualPreview,
    validateManualRows,
    switchMode,
    canAiRecognize,
    handleAiRecognize,
    pagedPreviewRows,
    conflictList,
    failedList,
    toNumber,
    beforeUpload,
    handleUpload,
    getRowClassName,
    handleReconcile,
    goToReconcileCenter,
    resetFlow,
    resetUpload,
    draftBannerVisible,
    pendingDraftMeta,
    restoreDraft,
    discardCurrentDraft,
    // #1694 接线：解析成功（文件 / AI 识别两条路径）后持久化草稿
    persistDraft
  };
}
