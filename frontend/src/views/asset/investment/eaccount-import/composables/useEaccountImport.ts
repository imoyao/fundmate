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
import { useReconDraft, type ReconDomain } from "@/composables/useReconDraft";

/**
 * E账户导入页面状态单体（#980 P1-B 结构拆分）：
 * 草稿 / 上传解析 / AI 识别 / 对账结果四段共享的状态与动作都收敛在这里，
 * index.vue 只做编排，子组件经 `page` prop 注入同一实例（P1-A profile/welcome 同款模式）。
 * onMounted 在此注册，挂载到调用方（index.vue）组件实例，与拆分前时序一致。
 */
export function useEaccountImport() {
  // #1239 草稿层：E账户导入 = 域 A；恢复至预览/对账步骤（currentStep=1）
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
  const importMode = ref<"file" | "ai">("file");
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

  function switchMode(mode: "file" | "ai") {
    if (parsedOk.value) return;
    importMode.value = mode;
    if (mode === "ai") fetchAiUsage();
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

  /** 开始对账：error 行禁提交（有失败行直接阻止整个提交） */
  async function handleReconcile() {
    if (errorCount.value > 0) {
      ElMessage.warning(
        `存在 ${errorCount.value} 条解析失败记录，请更换文件后重试`
      );
      return;
    }
    if (previewRows.value.length === 0) {
      ElMessage.warning("没有可对账的记录，请先上传文件");
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
  }

  /** 重新上传：清空解析结果，恢复大上传卡片 */
  function resetUpload() {
    uploadError.value = "";
    previewRows.value = [];
    parseMeta.value = { total: 0, error_count: 0 };
    fileName.value = "";
    previewPage.value = 1;
  }

  // ── #1239 草稿层：保存 / 恢复 / 丢弃（E账户导入=域 A）──
  /** 把当前预览状态持久化为草稿 */
  async function persistDraft(): Promise<void> {
    try {
      await saveDraft({
        domain: draftDomain,
        ledgerId: null, // E账户导入无显式账户选择，对账结果按快照域聚合
        currentStep: 1, // 恢复至预览/对账结果步骤
        rows: previewRows.value
      });
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

  /** 恢复草稿：回填 previewRows */
  async function restoreDraft(): Promise<void> {
    try {
      const draft = await getDraftWithSet();
      if (!draft || draft.domain !== draftDomain) return;
      previewRows.value = draft.rows;
      parseMeta.value = {
        total: draft.rows.length,
        error_count: draft.rows.filter(r => !!r.error).length
      };
      currentStep.value = 1;
      draftBannerVisible.value = false;
      pendingDraftMeta.value = null;
      ElMessage.success("已恢复未完成的 E账户导入草稿");
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
    // 尚无调用点的草稿持久化入口，随 #1239 草稿层原样保留（返回以免成为死代码告警）
    persistDraft
  };
}
