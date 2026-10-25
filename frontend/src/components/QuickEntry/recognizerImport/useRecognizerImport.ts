import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  getOcrUsage,
  parseImportText,
  recognizeImage,
  type OcrScenario
} from "@/api/ocr";
import { getLedgers, type LedgerItem } from "@/api/ledger";
import { useReconDraft } from "@/composables/useReconDraft";
import {
  DEFAULT_QUOTA,
  EMPTY_QUOTA_HINT,
  buildCandidates,
  canRecognizeOf,
  domainOf,
  fileToBase64,
  recognizeFailureOf,
  usageFeatureOf,
  usageHintOf,
  usageIconOf,
  usageStateClassOf,
  type ImportTab,
  type PreviewRow,
  type ScenarioOption
} from "./recognizerImportModel";

/**
 * 识别入库弹窗的全部状态与动作。
 *
 * 抽出来的原因不是「代码长」，而是这里有**两份容易漂移的快照**：
 * `scenario`（UI 当前选中）与 `recognizedScenario`（识别发生时的场景）。保存草稿必须
 * 按后者路由——识别在途用户可随意切场景，若用前者会把交易行写进域 A（#1348 review）。
 */
export function useRecognizerImport(opts: {
  /** 弹窗是否可见（在 setup 里读，别传值快照） */
  visible: () => boolean;
  /** 锁定的场景（托盘/快捷入口只接单一场景时用） */
  scenarioLock: () => OcrScenario | undefined;
  /** 存入草稿成功后的回调 */
  onSaved: (domain: "A" | "C") => void;
  /** 关闭弹窗 */
  onClose: () => void;
  /** 聚焦文本域（由输入面板子组件提供） */
  focusTextarea: () => void;
}) {
  const { saveRecognizerCandidates } = useReconDraft();

  const scenario = ref<ScenarioOption>(
    (opts.scenarioLock() as ScenarioOption) ?? "txn_import"
  );
  // scenarioLock 动态变化时同步锁定场景，避免与 `v-if="!scenarioLock"` 显隐切换不一致
  watch(
    () => opts.scenarioLock(),
    val => {
      if (val) scenario.value = val as ScenarioOption;
    }
  );

  const activeTab = ref<ImportTab>("image");
  const imageFile = ref<File | null>(null);
  const textContent = ref("");
  const recognizing = ref(false);
  const saving = ref(false);
  const textError = ref("");

  const previewRows = ref<PreviewRow[]>([]);

  // 额度
  const remaining = ref(0);
  const quota = ref(DEFAULT_QUOTA);
  const occupied = ref(false);

  // 交易场景关联账户
  const ledgers = ref<LedgerItem[]>([]);
  const selectedLedgerId = ref<number | null>(null);

  // 识别时快照：见上方说明
  const recognizedScenario = ref<ScenarioOption | null>(null);
  const recognizedLedgerId = ref<number | null>(null);

  const remainingText = computed(() =>
    usageHintOf(remaining.value, occupied.value)
  );
  const usageStateClass = computed(() =>
    usageStateClassOf(remaining.value, occupied.value)
  );
  const usageIcon = computed(() =>
    usageIconOf(remaining.value, occupied.value)
  );
  const canRecognize = computed(() =>
    canRecognizeOf({
      remaining: remaining.value,
      occupied: occupied.value,
      tab: activeTab.value,
      hasImage: !!imageFile.value,
      text: textContent.value
    })
  );

  function resetPreview() {
    previewRows.value = [];
    recognizedScenario.value = null;
    recognizedLedgerId.value = null;
    textContent.value = "";
    imageFile.value = null;
    textError.value = "";
  }

  function switchScenario(s: ScenarioOption) {
    scenario.value = s;
    resetPreview();
    void fetchUsage();
  }

  function switchTab(tab: ImportTab) {
    activeTab.value = tab;
    resetPreview();
    if (tab === "text") opts.focusTextarea();
  }

  const fetchUsage = async () => {
    try {
      const res = await getOcrUsage(usageFeatureOf(scenario.value));
      const data = res.data;
      remaining.value = data?.remaining ?? 0;
      quota.value = data?.quota ?? DEFAULT_QUOTA;
      occupied.value = data?.remaining <= 0;
    } catch {
      remaining.value = DEFAULT_QUOTA;
      quota.value = DEFAULT_QUOTA;
      occupied.value = false;
    }
  };

  const fetchLedgers = async () => {
    try {
      const res = await getLedgers();
      ledgers.value = (res.data ?? []) as LedgerItem[];
    } catch {
      ledgers.value = [];
    }
  };

  /** 调识别接口（图片 / 文本两条通道），返回预览行 */
  async function requestRows(): Promise<PreviewRow[]> {
    if (activeTab.value === "image") {
      if (!imageFile.value) {
        ElMessage.warning("请先选择图片");
        return [];
      }
      const base64 = await fileToBase64(imageFile.value);
      const res = await recognizeImage(
        base64,
        scenario.value,
        selectedLedgerId.value
      );
      return ((res.data as { rows?: PreviewRow[] }).rows ?? []) as PreviewRow[];
    }
    const text = textContent.value.trim();
    if (!text) {
      ElMessage.warning("请输入文本内容");
      return [];
    }
    const res = await parseImportText(
      text,
      scenario.value,
      selectedLedgerId.value
    );
    return ((res.data as { rows?: PreviewRow[] }).rows ?? []) as PreviewRow[];
  }

  const handleRecognize = async () => {
    if (remaining.value <= 0) {
      ElMessage.warning(EMPTY_QUOTA_HINT);
      return;
    }
    recognizing.value = true;
    try {
      const rows = await requestRows();
      if (rows.length === 0) {
        // 文本通道把错误落在输入框下方（用户视线在文本域上），图片通道走全局提示
        if (activeTab.value === "text") {
          textError.value = "未识别到有效记录，请检查格式或图片清晰度";
        } else {
          ElMessage.info("未能识别出记录，请检查图片清晰度或文本格式");
        }
        void fetchUsage();
        return;
      }
      previewRows.value = rows;
      recognizedScenario.value = scenario.value;
      recognizedLedgerId.value = selectedLedgerId.value;
      void fetchUsage();
    } catch (e: unknown) {
      void fetchUsage();
      const { message, level } = recognizeFailureOf(e);
      ElMessage[level](message);
    } finally {
      recognizing.value = false;
    }
  };

  // 确认进草稿（#1250 契约）：候选行序列化进 recon-draft:recognizer，
  // 与导入草稿按 key 隔离；txn→域 C / holding→域 A，由工作台加载并参与对账。
  const handleSaveDraft = async () => {
    if (previewRows.value.length === 0) return;
    // 按「识别时」的场景/账户路由，避免识别在途切换场景后按错误 domain 入库（#1348 review）
    const snapScenario =
      recognizedScenario.value ?? (scenario.value as ScenarioOption);
    const snapLedgerId = recognizedLedgerId.value ?? selectedLedgerId.value;
    saving.value = true;
    try {
      const domain = domainOf(snapScenario);
      await saveRecognizerCandidates({
        domain,
        ledgerId: snapScenario === "txn_import" ? snapLedgerId : null,
        candidates: buildCandidates(
          previewRows.value,
          snapScenario,
          snapLedgerId
        )
      });
      ElMessage.success("已存入对账草稿，可在工作台确认入库");
      opts.onSaved(domain);
      opts.onClose();
      resetPreview();
    } catch (e: unknown) {
      const err = e as { message?: string };
      ElMessage.error(err.message || "存入草稿失败");
    } finally {
      saving.value = false;
    }
  };

  watch(
    () => opts.visible(),
    val => {
      if (val) {
        void fetchUsage();
        void fetchLedgers();
        if (activeTab.value === "text") opts.focusTextarea();
      }
    }
  );

  onMounted(() => {
    if (opts.visible()) {
      void fetchUsage();
      void fetchLedgers();
    }
  });

  return {
    scenario,
    activeTab,
    imageFile,
    textContent,
    textError,
    recognizing,
    saving,
    previewRows,
    remaining,
    quota,
    occupied,
    ledgers,
    selectedLedgerId,
    remainingText,
    usageStateClass,
    usageIcon,
    canRecognize,
    switchScenario,
    switchTab,
    handleRecognize,
    handleSaveDraft,
    resetPreview
  };
}
