<template>
  <el-dialog
    v-model="visible"
    class="recognizer-import-dialog"
    title="AI 识别入库"
    width="720px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <!-- 额度提示（三态：正常 / 紧张 / 用尽） -->
    <div class="usage-banner" :class="usageStateClass">
      <IconifyIconOffline class="usage-banner__icon" :icon="usageIcon" />
      <span class="usage-banner__label">今日 AI 识别额度剩余</span>
      <span class="usage-banner__count">
        <strong :key="remaining">{{ remaining }}</strong> / {{ quota }} 次
      </span>
      <span v-if="remainingText" class="usage-banner__hint">{{
        remainingText
      }}</span>
    </div>

    <!-- 场景切换：交易识别 / 持仓识别（决定落入域 C / 域 A）；scenarioLock 时隐藏 -->
    <div
      v-if="!scenarioLock"
      class="ocr-segmented"
      role="tablist"
      aria-label="识别场景"
    >
      <button
        type="button"
        role="tab"
        class="ocr-segmented__item"
        :class="{ 'is-active': scenario === 'txn_import' }"
        :disabled="recognizing"
        @click="switchScenario('txn_import')"
      >
        交易识别
      </button>
      <button
        type="button"
        role="tab"
        class="ocr-segmented__item"
        :class="{ 'is-active': scenario === 'holding_import' }"
        :disabled="recognizing"
        @click="switchScenario('holding_import')"
      >
        持仓识别
      </button>
    </div>

    <!-- 交易识别需选择关联账户（域 C 对账按账本隔离） -->
    <div v-if="scenario === 'txn_import'" class="ledger-select">
      <span class="ledger-select__label">关联账户</span>
      <el-select
        v-model="selectedLedgerId"
        placeholder="选择交易账户（可选）"
        clearable
        class="ledger-select__input"
      >
        <el-option
          v-for="ledger in ledgers"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
        />
      </el-select>
    </div>

    <!-- 输入方式：上传图片 / 粘贴文本 -->
    <div class="ocr-segmented ocr-segmented--sub" role="tablist">
      <button
        type="button"
        role="tab"
        class="ocr-segmented__item"
        :class="{ 'is-active': activeTab === 'image' }"
        @click="switchTab('image')"
      >
        上传图片
      </button>
      <button
        type="button"
        role="tab"
        class="ocr-segmented__item"
        :class="{ 'is-active': activeTab === 'text' }"
        @click="switchTab('text')"
      >
        粘贴文本
      </button>
    </div>

    <div v-if="activeTab === 'image'" class="ocr-tab-panel">
      <ImageUploader
        v-model="imageFile"
        :tip="
          scenario === 'txn_import'
            ? '支持券商/基金 App 交易截图，文件不超过 5MB'
            : '支持持仓截图，文件不超过 5MB'
        "
      />
    </div>

    <div v-else class="ocr-tab-panel">
      <el-input
        ref="textareaRef"
        v-model="textContent"
        type="textarea"
        :rows="8"
        resize="vertical"
        class="ocr-textarea"
        :placeholder="
          scenario === 'txn_import'
            ? '在此粘贴交易记录，每行一只，如：110011 易方达中小盘 买入 10000'
            : '在此粘贴持仓，每行一只，如：110011 易方达中小盘 1000 2.5'
        "
        @input="textError = ''"
      />
      <p v-if="textError" class="ocr-textarea__error">{{ textError }}</p>
    </div>

    <!-- 识别结果预览（逐行核对，不自动入库，见 #935 必带兜底） -->
    <div v-if="previewRows.length > 0" class="result-section">
      <div class="result-head">
        识别到 {{ previewRows.length }} 条，核对无误后「确认进草稿」
      </div>
      <div class="preview-scroll">
        <el-table :data="previewRows" size="small" stripe class="preview-table">
          <el-table-column label="代码" prop="symbol" width="110" />
          <el-table-column label="名称" prop="name" min-width="120" />
          <template v-if="scenario === 'txn_import'">
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                {{ (row as OcrTxnRow).op_type_label || row.op_type }}
              </template>
            </el-table-column>
            <el-table-column
              label="数量"
              prop="quantity"
              width="100"
              align="right"
            />
            <el-table-column
              label="金额"
              prop="amount"
              width="110"
              align="right"
            />
            <el-table-column label="日期" prop="trade_date" width="120" />
          </template>
          <template v-else>
            <el-table-column
              label="份额"
              prop="quantity"
              width="110"
              align="right"
            />
            <el-table-column
              label="成本"
              prop="price"
              width="100"
              align="right"
            />
            <el-table-column label="快照日" prop="snapshot_date" width="120" />
          </template>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.is_duplicate" size="small" type="warning"
                >重复</el-tag
              >
              <el-tag v-else-if="row.error" size="small" type="danger"
                >错误</el-tag
              >
              <el-tag v-else size="small" type="success">可入库</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button class="ocr-cancel-btn" size="large" @click="visible = false"
        >取消</el-button
      >
      <el-button
        v-if="previewRows.length === 0"
        type="primary"
        size="large"
        :loading="recognizing"
        :disabled="!canRecognize"
        class="ocr-primary-btn"
        @click="handleRecognize"
      >
        {{ recognizing ? "识别中…" : "开始识别" }}
      </el-button>
      <template v-else>
        <el-button size="large" @click="resetPreview">重新识别</el-button>
        <el-button
          type="primary"
          size="large"
          :loading="saving"
          class="ocr-primary-btn"
          @click="handleSaveDraft"
        >
          确认进草稿（{{ previewRows.length }}）
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from "vue";
import { ElInput, ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import ImageUploader from "@/components/ImageUploader/index.vue";
import {
  recognizeImage,
  parseImportText,
  getOcrUsage,
  type OcrScenario,
  type OcrTxnRow,
  type OcrHoldingRow
} from "@/api/ocr";
import { getLedgers, type LedgerItem } from "@/api/ledger";
import {
  useReconDraft,
  type RecognizerCandidate
} from "@/composables/useReconDraft";

const props = defineProps<{
  modelValue: boolean;
  /** 锁定识别场景（隐藏场景切换 tab）。托盘/快捷入口只接单一场景时用，如 'txn_import' */
  scenarioLock?: OcrScenario;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [domain: "A" | "C"];
}>();

const { saveRecognizerCandidates } = useReconDraft();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const scenario = ref<OcrScenario>(props.scenarioLock ?? "txn_import");
const activeTab = ref<"image" | "text">("image");
const imageFile = ref<File | null>(null);
const textContent = ref("");
const recognizing = ref(false);
const saving = ref(false);
const textError = ref("");

const previewRows = ref<(OcrTxnRow | OcrHoldingRow)[]>([]);

// 额度
const remaining = ref(0);
const quota = ref(5);
const occupied = ref(false);

// 交易场景关联账户
const ledgers = ref<LedgerItem[]>([]);
const selectedLedgerId = ref<number | null>(null);

// 场景快照：识别在途时用户可切换场景，保存进草稿必须按"识别时"的场景路由，
// 否则会按错误 domain 入库（#1348 review）
const recognizedScenario = ref<OcrScenario | null>(null);
const recognizedLedgerId = ref<number | null>(null);

const usageFeature = computed(() =>
  scenario.value === "txn_import" ? "txn_import" : "holding_import"
);

const remainingText = computed(() => {
  if (occupied.value) return "额度已用尽，请明日再试";
  if (remaining.value <= 2) return "额度紧张，谨慎使用";
  return "";
});
const usageStateClass = computed(() => {
  if (occupied.value) return "is-used-up";
  if (remaining.value <= 2) return "is-low";
  return "";
});
const usageIcon = computed(() => {
  if (occupied.value) return "ep:warning";
  if (remaining.value <= 2) return "ep:bell";
  return "ep:magic-stick";
});

const canRecognize = computed(() => {
  if (occupied.value || remaining.value <= 0) return false;
  if (activeTab.value === "image") return !!imageFile.value;
  return textContent.value.trim().length > 0;
});

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1] ?? result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const textareaRef = ref<InstanceType<typeof ElInput>>();
const focusTextarea = () => nextTick(() => textareaRef.value?.focus());

function switchScenario(s: OcrScenario) {
  scenario.value = s;
  resetPreview();
  void fetchUsage();
}

function switchTab(tab: "image" | "text") {
  activeTab.value = tab;
  resetPreview();
  if (tab === "text") focusTextarea();
}

function resetPreview() {
  previewRows.value = [];
  recognizedScenario.value = null;
  recognizedLedgerId.value = null;
  textContent.value = "";
  imageFile.value = null;
  textError.value = "";
}

const handleRecognize = async () => {
  if (remaining.value <= 0) {
    ElMessage.warning("今日 AI 识别额度已用完，请明日再试");
    return;
  }
  recognizing.value = true;
  try {
    let rows: (OcrTxnRow | OcrHoldingRow)[] = [];
    if (activeTab.value === "image") {
      if (!imageFile.value) {
        ElMessage.warning("请先选择图片");
        return;
      }
      const base64 = await fileToBase64(imageFile.value);
      const res = await recognizeImage(
        base64,
        scenario.value,
        selectedLedgerId.value
      );
      rows = ((res.data as { rows?: (OcrTxnRow | OcrHoldingRow)[] }).rows ??
        []) as (OcrTxnRow | OcrHoldingRow)[];
    } else {
      const text = textContent.value.trim();
      if (!text) {
        ElMessage.warning("请输入文本内容");
        return;
      }
      const res = await parseImportText(
        text,
        scenario.value,
        selectedLedgerId.value
      );
      rows = ((res.data as { rows?: (OcrTxnRow | OcrHoldingRow)[] }).rows ??
        []) as (OcrTxnRow | OcrHoldingRow)[];
    }

    if (rows.length === 0) {
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
    const err = e as {
      response?: { status?: number; data?: { message?: string } };
      code?: string;
      message?: string;
    };
    const status = err.response?.status;
    if (status === 503) {
      ElMessage.error("AI 识别服务暂时繁忙，请稍后重试（失败不消耗次数）");
    } else if (status === 429) {
      ElMessage.warning(
        err.response?.data?.message || "今日 AI 识别次数已用完，请明日再试"
      );
    } else if (
      err.code === "ECONNABORTED" ||
      err.message?.includes("timeout")
    ) {
      ElMessage.error("识别超时，请稍后重试（失败不消耗次数）");
    } else {
      ElMessage.error(
        err.response?.data?.message || err.message || "识别失败，请重试"
      );
    }
  } finally {
    recognizing.value = false;
  }
};

// 确认进草稿（#1250 契约）：识别候选行序列化进 recon-draft:recognizer，
// 与导入草稿按 key 隔离；txn→域 C / holding→域 A，由工作台加载并参与对账。
const handleSaveDraft = async () => {
  if (previewRows.value.length === 0) return;
  // 按"识别时"的场景/账户路由，避免识别在途切换场景后按错误 domain 入库（#1348 review）
  const snapScenario = recognizedScenario.value ?? scenario.value;
  const snapLedgerId = recognizedLedgerId.value ?? selectedLedgerId.value;
  saving.value = true;
  try {
    const domain = snapScenario === "txn_import" ? "C" : "A";
    const candidates = previewRows.value.map(r => {
      const base = {
        ...r,
        kind: snapScenario === "txn_import" ? "txn" : "holding"
      } as Record<string, unknown>;
      // 交易场景：把关联账户 id 直接带入候选行，提交时无需再次选择（域 C 按账本隔离）
      if (snapScenario === "txn_import" && snapLedgerId) {
        base.ledger_id = snapLedgerId;
      }
      return base as unknown as RecognizerCandidate;
    });
    await saveRecognizerCandidates({
      domain,
      ledgerId: snapScenario === "txn_import" ? snapLedgerId : null,
      candidates
    });
    ElMessage.success("已存入对账草稿，可在工作台确认入库");
    emit("saved", domain);
    visible.value = false;
    resetPreview();
  } catch (e: unknown) {
    const err = e as { message?: string };
    ElMessage.error(err.message || "存入草稿失败");
  } finally {
    saving.value = false;
  }
};

const fetchUsage = async () => {
  try {
    const res = await getOcrUsage(usageFeature.value);
    const data = res.data;
    remaining.value = data?.remaining ?? 0;
    quota.value = data?.quota ?? 5;
    occupied.value = data?.remaining <= 0;
  } catch {
    remaining.value = 5;
    quota.value = 5;
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

watch(
  () => props.modelValue,
  val => {
    if (val) {
      void fetchUsage();
      void fetchLedgers();
      if (activeTab.value === "text") focusTextarea();
    }
  }
);

onMounted(() => {
  if (visible.value) {
    void fetchUsage();
    void fetchLedgers();
  }
});
</script>

<style scoped lang="scss">
.recognizer-import-dialog {
  :deep(.el-dialog) {
    overflow: hidden;
    background-color: var(--bg-card);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
  }

  :deep(.el-dialog__body) {
    padding: var(--space-standard);
    margin: 0;
  }
}

.usage-banner {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin-bottom: var(--space-standard);

  &__icon {
    display: inline-flex;
    align-self: center;
    font-size: 14px;
    color: var(--text-tertiary);
  }

  &__label {
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  &__count {
    font-size: var(--text-small);
    color: var(--text-secondary);

    strong {
      font-family: var(--font-mono);
      font-size: 14px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--brand-700);
    }
  }

  &__hint {
    margin-left: auto;
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }

  &.is-low .usage-banner__count strong {
    color: var(--text-primary);
  }

  &.is-used-up {
    .usage-banner__count strong,
    .usage-banner__hint {
      color: var(--color-danger);
    }
  }
}

.ocr-segmented {
  display: flex;
  gap: 4px;
  width: 100%;
  padding: 4px;
  margin-bottom: var(--space-standard);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);

  &--sub {
    margin-top: var(--space-standard);
  }

  &__item {
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: center;
    height: 28px;
    padding: 0 12px;
    font-size: 13px;
    line-height: 1;
    color: var(--text-secondary);
    cursor: pointer;
    background: transparent;
    border: none;
    border-radius: var(--radius-pill);
    transition: all 300ms cubic-bezier(0.34, 1.56, 0.64, 1);

    &:focus {
      outline: none;
    }

    &:focus-visible {
      outline: 1px solid var(--brand-400);
      outline-offset: 2px;
    }

    &:hover {
      color: var(--text-primary);
      background: var(--bg-hover);
    }

    &.is-active {
      color: var(--brand-700);
      background: var(--brand-100);
    }
  }
}

.ledger-select {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-standard);

  &__label {
    font-size: var(--text-small);
    color: var(--text-secondary);
    white-space: nowrap;
  }

  &__input {
    flex: 1;
  }
}

.ocr-tab-panel {
  min-height: 160px;
}

.ocr-textarea {
  :deep(.el-textarea__inner) {
    font-family: var(--font-mono);
    border-radius: var(--radius-sm);
    box-shadow: 0 0 0 1px var(--border-default) inset;
    transition: box-shadow 0.2s ease;

    &:focus {
      box-shadow:
        0 0 0 1px var(--brand-700) inset,
        0 0 0 3px color-mix(in srgb, var(--brand-400) 40%, transparent);
    }
  }
}

.ocr-textarea__error {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--color-danger-system);
}

.result-section {
  margin-top: var(--space-5);
}

.result-head {
  margin-bottom: var(--space-3);
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.preview-scroll {
  max-height: 280px;
  overflow-y: auto;
}

.ocr-primary-btn,
.ocr-cancel-btn {
  height: 40px;
  padding: 0 24px;
  font-size: 14px;
  border: none;
  border-radius: 6px;
  transition:
    transform 120ms ease,
    background-color 150ms ease;
}

.ocr-primary-btn:active:not(:disabled),
.ocr-cancel-btn:active:not(:disabled) {
  transform: translateY(1px);
}

.ocr-primary-btn {
  color: var(--text-inverse);
  background-color: var(--brand-700);
}

.ocr-primary-btn:hover:not(:disabled) {
  background-color: var(--brand-600);
}

.ocr-primary-btn:disabled {
  color: var(--text-disabled);
  cursor: not allowed;
  background-color: var(--bg-muted);
  box-shadow: none;
  transform: none;
}

.ocr-cancel-btn {
  color: var(--text-primary);
  background-color: var(--bg-soft);
}

.ocr-cancel-btn:hover:not(:disabled) {
  background-color: var(--bg-hover);
}
</style>
