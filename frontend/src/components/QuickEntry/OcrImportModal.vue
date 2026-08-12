<template>
  <el-dialog
    v-model="visible"
    class="ocr-import-dialog"
    title="AI 批量导入"
    width="640px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <!-- 顶部：剩余次数提示（三态：正常 / 紧张 / 用尽） -->
    <div class="usage-banner" :class="usageStateClass">
      <span class="usage-banner__icon">
        <IconifyIconOffline :icon="usageIcon" />
      </span>
      <div class="usage-banner__main">
        <span class="usage-banner__label">今日 AI 导入额度</span>
        <span class="usage-banner__count">
          剩余 <strong>{{ remaining }}</strong> / {{ quota }} 次
        </span>
      </div>
      <span v-if="remainingText" class="usage-banner__hint">{{
        remainingText
      }}</span>
    </div>

    <el-tabs v-model="activeTab" class="ocr-tabs" @tab-change="handleTabChange">
      <!-- ── 图片识别 ── -->
      <el-tab-pane name="image" label="上传图片">
        <ImageUploader
          v-model="imageFile"
          tip="支持券商 / 天天基金等 App 持仓截图，文件不超过 5MB"
        />
      </el-tab-pane>

      <!-- ── 文本解析 ── -->
      <el-tab-pane name="text" label="粘贴文本">
        <el-input
          v-model="textContent"
          type="textarea"
          :rows="8"
          resize="vertical"
          class="ocr-textarea"
          placeholder="粘贴基金列表文本，例如：&#10;110011 易方达中小盘&#10;005827 易方达蓝筹精选"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 识别结果确认 -->
    <div v-if="candidates.length > 0" class="result-section">
      <div class="result-head">
        识别到 {{ candidates.length }} 条，可勾选导入
      </div>
      <div class="candidate-list">
        <div
          v-for="item in candidates"
          :key="item.code"
          class="candidate-row"
          :class="{ 'is-exists': item.exists }"
          @click="toggleCandidate(item)"
        >
          <el-checkbox
            :model-value="item.selected"
            :disabled="item.exists"
            @change="toggleCandidate(item)"
          />
          <span class="candidate-code">{{ item.code }}</span>
          <span class="candidate-name">{{ item.name }}</span>
          <el-tag
            v-if="item.exists"
            size="small"
            type="info"
            class="candidate-tag"
            >已在自选</el-tag
          >
        </div>
      </div>
    </div>

    <template #footer>
      <el-button size="large" @click="visible = false">取消</el-button>
      <el-button
        v-if="candidates.length === 0"
        type="primary"
        size="large"
        :loading="recognizing"
        :disabled="!canRecognize"
        @click="handleRecognize"
      >
        开始识别
      </el-button>
      <el-button
        v-else
        type="primary"
        size="large"
        :loading="importing"
        :disabled="selectedCount === 0"
        @click="handleImport"
      >
        导入选中（{{ selectedCount }}）
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import ImageUploader from "@/components/ImageUploader/index.vue";
import { parseImportText, recognizeImage, getOcrUsage } from "@/api/ocr";
import { createWatchlistItem, getWatchlistItems } from "@/api/watchlist";
import type { OcrImportItem } from "@/api/ocr";

const props = defineProps<{
  modelValue: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  imported: [count: number];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const activeTab = ref<"image" | "text">("image");
const imageFile = ref<File | null>(null);
const textContent = ref("");
const recognizing = ref(false);
const importing = ref(false);

const remaining = ref(0);
const quota = ref(5);
const occupied = ref(false);

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

interface Candidate extends OcrImportItem {
  exists: boolean;
  selected: boolean;
}
const candidates = ref<Candidate[]>([]);

const canRecognize = computed(() => {
  if (occupied.value || remaining.value <= 0) return false;
  if (activeTab.value === "image") return !!imageFile.value;
  return textContent.value.trim().length > 0;
});

const selectedCount = computed(
  () => candidates.value.filter(c => c.selected).length
);

const handleTabChange = () => {
  candidates.value = [];
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // 去掉 data URL 前缀，保留纯 base64
      const base64 = result.split(",")[1] ?? result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const toggleCandidate = (item: Candidate) => {
  if (item.exists) return;
  item.selected = !item.selected;
};

const handleRecognize = async () => {
  if (remaining.value <= 0) {
    ElMessage.warning("今日 AI 导入额度已用完，请明日再试");
    return;
  }
  recognizing.value = true;
  try {
    let items: OcrImportItem[] = [];
    if (activeTab.value === "image") {
      if (!imageFile.value) {
        ElMessage.warning("请先选择图片");
        return;
      }
      const base64 = await fileToBase64(imageFile.value);
      const res = await recognizeImage(base64);
      items = res.data?.items ?? [];
    } else {
      const text = textContent.value.trim();
      if (!text) {
        ElMessage.warning("请输入文本内容");
        return;
      }
      const res = await parseImportText(text);
      items = res.data?.items ?? [];
    }

    if (items.length === 0) {
      ElMessage.info("未能识别出基金，请检查图片清晰度或文本格式");
      // 识别成功但无有效内容：本次配额已消耗，刷新余量展示
      void fetchUsage();
      return;
    }

    const existingSet = await probeExisting(items);
    candidates.value = items.map(it => {
      const key = it.symbol || it.code;
      return {
        ...it,
        exists: existingSet.has(key),
        selected: !existingSet.has(key)
      };
    });
    // 识别成功已消耗 1 次配额，同步刷新余量展示
    void fetchUsage();
  } catch (e: any) {
    // 兜底：识别失败（超时/服务不可用）后端会返还配额，刷新余量避免显示虚低
    void fetchUsage();
    const status = e?.response?.status;
    if (status === 503) {
      ElMessage.error("AI 识别服务暂时繁忙，请稍后重试（失败不消耗次数）");
    } else if (status === 429) {
      ElMessage.warning("今日 AI 识别次数已用完，请明日再试");
    } else if (e?.code === "ECONNABORTED" || e?.message?.includes("timeout")) {
      ElMessage.error(
        "识别超时，图片内容可能较多，请稍后重试（失败不消耗次数）"
      );
    } else {
      const msg =
        e?.response?.data?.message || e?.message || "识别失败，请重试";
      ElMessage.error(msg);
    }
  } finally {
    recognizing.value = false;
  }
};

// 探测哪些代码已存在于自选（对批量候选，逐条查询看是否已存在，避免重复导入）
async function probeExisting(items: OcrImportItem[]): Promise<Set<string>> {
  const set = new Set<string>();
  for (const it of items) {
    try {
      // 用标准化 symbol 探测（场内如 SH600519），与后端查重口径一致
      const res = await getWatchlistItems({
        symbol: it.symbol || it.code,
        per_page: 1
      });
      const data = (res as any).data ?? [];
      if (data.length > 0) set.add(it.symbol || it.code);
    } catch {
      // 网络异常不阻断已存在判断，保守当作新项
    }
  }
  return set;
}

const handleImport = async () => {
  const toImport = candidates.value.filter(c => c.selected && !c.exists);
  if (toImport.length === 0) {
    ElMessage.info("没有需要导入的资产");
    return;
  }
  importing.value = true;
  let success = 0;
  let skipped = 0;
  const failed: string[] = [];
  for (const item of toImport) {
    try {
      // 透传后端反查的 type/market/venue/symbol，不再按 code 前缀猜类型
      // （否则股票 600519 / 深市 ETF 159915 会被误判为场外基金导入）
      await createWatchlistItem({
        symbol: item.symbol || item.code,
        asset_type: item.type || "fund",
        market: item.market,
        venue: item.venue || "OTC",
        add_reason: "AI 批量导入"
      });
      success++;
    } catch (e: any) {
      if (e?.response?.status === 409) {
        skipped++;
      } else {
        failed.push(item.code);
      }
    }
  }
  importing.value = false;

  if (failed.length > 0) {
    ElMessage.error(
      `导入完成：成功 ${success} 条，跳过已存在 ${skipped} 条，失败 ${
        failed.length
      } 条（${failed.join("、")}）`
    );
  } else {
    ElMessage.success(
      `导入成功 ${success} 条${skipped > 0 ? `，跳过已存在 ${skipped} 条` : ""}`
    );
  }

  if (success > 0) {
    emit("imported", success);
  }
  reset();
};

const fetchUsage = async () => {
  try {
    const res = await getOcrUsage();
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

const reset = () => {
  candidates.value = [];
  textContent.value = "";
  imageFile.value = null;
};

// 🔥 修复：组件挂载时弹窗处于关闭态（visible=false），onMounted 不会触发
// fetchUsage，导致 remaining 永远停留在初始值 0。改为监听 modelValue，
// 每次打开弹窗时拉取最新额度。
watch(
  () => props.modelValue,
  val => {
    if (val) fetchUsage();
  }
);

onMounted(() => {
  if (visible.value) {
    fetchUsage();
  }
});
</script>

<style scoped>
/* ============================================
   弹窗容器：对齐 design.md（大圆角 + 暖调模态阴影 + 头尾分隔线）
   ============================================ */
.ocr-import-dialog {
  :deep(.el-dialog) {
    overflow: hidden;
    background-color: var(--bg-card);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
  }

  :deep(.el-dialog__header) {
    padding: var(--space-standard) var(--space-standard) var(--space-compact);
    margin-right: 0;
    border-bottom: 1px solid var(--border-light);
  }

  :deep(.el-dialog__title) {
    font-size: var(--text-heading);
    font-weight: 600;
    color: var(--text-primary);
  }

  :deep(.el-dialog__body) {
    padding: var(--space-standard);
  }

  :deep(.el-dialog__footer) {
    padding: var(--space-compact) var(--space-standard);
    border-top: 1px solid var(--border-light);
  }
}

/* ============================================
   剩余次数提示条（三态：正常 / 紧张 / 用尽）
   ============================================ */
.usage-banner {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-compact) var(--space-5);
  margin-bottom: var(--space-5);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;

  &__icon {
    display: inline-flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    font-size: 18px;
    color: var(--brand-700);
    background: var(--brand-100);
    border-radius: var(--radius-pill);
  }

  &__main {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
  }

  &__label {
    font-size: var(--text-label);
    font-weight: 500;
    color: var(--text-secondary);
  }

  &__count {
    font-size: var(--text-small);
    color: var(--text-primary);

    strong {
      font-family: var(--font-mono);
      font-size: 18px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      color: var(--brand-700);
    }
  }

  &__hint {
    flex-shrink: 0;
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  /* 额度紧张：暖沙金警示 */
  &.is-low {
    background: var(--color-warning-20);
    border-color: var(--color-warning);

    .usage-banner__icon,
    .usage-banner__count strong {
      color: var(--text-primary);
    }
  }

  /* 额度用尽：危险警示 */
  &.is-used-up {
    background: var(--color-danger-20);
    border-color: var(--color-danger);

    .usage-banner__icon,
    .usage-banner__count strong {
      color: var(--color-danger);
    }

    .usage-banner__hint {
      color: var(--color-danger);
    }
  }
}

/* ============================================
   Tabs：品牌色激活态
   ============================================ */
.ocr-tabs {
  :deep(.el-tabs__nav-wrap::after) {
    height: 1px;
    background-color: var(--border-light);
  }

  :deep(.el-tabs__item) {
    font-size: var(--text-small);
    color: var(--text-secondary);

    &.is-active {
      color: var(--brand-700);
    }
  }

  :deep(.el-tabs__active-bar) {
    background-color: var(--brand-700);
  }
}

/* ============================================
   文本解析：textarea 圆角 + focus 环
   ============================================ */
.ocr-textarea {
  :deep(.el-textarea__inner) {
    font-family: var(--font-sans);
    border-radius: var(--radius-sm);
    box-shadow: 0 0 0 1px var(--border-default) inset;
    transition: box-shadow 0.2s ease;

    &:focus {
      box-shadow:
        0 0 0 1px var(--brand-700) inset,
        var(--focus-ring);
    }
  }
}

/* ============================================
   识别结果候选列表
   ============================================ */
.result-section {
  margin-top: var(--space-5);
}

.result-head {
  margin-bottom: var(--space-3);
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 240px;
  padding: var(--space-2);
  overflow-y: auto;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.candidate-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-small);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;

  &:hover {
    background: var(--bg-hover);
  }

  &.is-exists {
    opacity: 0.55;
  }

  .candidate-code {
    font-family: var(--font-mono);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text-primary);
  }

  .candidate-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .candidate-tag {
    border-radius: var(--radius-pill);
  }
}
</style>
