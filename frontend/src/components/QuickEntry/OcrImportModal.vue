<!--
  AI 批量导入弹窗（#2106 / #1835）：上传截图或粘贴文本 → 识别 → 勾选 → 导入自选。

  #980 拆分后本文件只剩「弹窗外壳」：额度通栏 / 分段切换 / 两个输入面板 /
  结果确认区 / 底栏按钮的接线。内在逻辑分在四处：
  - composables/useOcrQuota.ts        额度三态（紧张线、图标、文案）
  - composables/useOcrRecognize.ts    识别链路（图片转 base64、探测已存在、候选派生）
  - composables/useOcrImport.ts       导入动作（逐条 POST、409 记跳过、结果文案）
  - composables/useOcrGroupPicker.ts  导入时的分组选择（只列自定义分组）
  - ocrImportModel.ts                 纯函数：候选派生 / 请求体 / 结果文案
-->
<template>
  <el-dialog
    v-model="visible"
    class="ocr-import-dialog"
    title="AI 批量导入"
    width="640px"
    destroy-on-close
    :close-on-click-modal="false"
    :before-close="onBeforeClose"
  >
    <!-- 顶部：剩余次数提示（三态：正常 / 紧张 / 用尽） -->
    <OcrUsageBanner
      :remaining="remaining"
      :quota="quota"
      :state-class="usageStateClass"
      :icon="usageIcon"
      :hint="remainingText"
    />

    <!-- 两个互斥选项 → SegmentedControl small 档（design.md「Segmented」唯一实现，
         见 docs/design/components.md）；轨道用 --bg-soft 暖米色：--bg-muted 是淡灰蓝
         #f5f7fa，在暖白弹窗上几乎不可见，会呈现「孤立文字」观感 -->
    <SegmentedControl
      :model-value="activeTab"
      :options="IMPORT_TAB_OPTIONS"
      size="small"
      block
      aria-label="导入方式"
      class="ocr-import-tabs"
      @change="switchTab"
    />

    <!-- ── 图片识别 ── -->
    <div v-if="activeTab === 'image'" class="ocr-tab-panel">
      <ImageUploader
        v-model="imageFile"
        tip="支持券商 / 基金 App 等持仓截图，文件不超过 5MB"
      />
    </div>

    <!-- ── 文本解析 ── -->
    <div v-else class="ocr-tab-panel">
      <OcrTextPanel
        ref="textPanelRef"
        v-model="textContent"
        :error="textError"
        @edited="textError = ''"
      />
    </div>

    <!-- 识别结果确认 -->
    <OcrCandidateList
      v-if="candidates.length > 0"
      v-model="selectedGroupIds"
      v-model:group-form-visible="groupFormVisible"
      :candidates="candidates"
      :groups="availableGroups"
      @toggle="toggleCandidate"
      @group-created="onGroupCreated"
    />

    <template #footer>
      <el-button class="ocr-cancel-btn" size="large" @click="requestClose"
        >取消</el-button
      >
      <el-button
        v-if="candidates.length === 0"
        type="primary"
        size="large"
        :loading="recognizing"
        :disabled="!canRecognize"
        class="ocr-primary-btn"
        @click="handleRecognize"
      >
        {{ recognizing ? "识别中…" : "开始识别" }}
      </el-button>
      <el-button
        v-else
        type="primary"
        size="large"
        :loading="importing"
        :disabled="selectedCount === 0"
        class="ocr-primary-btn"
        @click="handleImport"
      >
        导入选中（{{ selectedCount }}）
      </el-button>
    </template>

    <!-- 复用全局「新建分组」弹窗（#2106）：与自选页分组管理体验一致 -->
    <GroupFormDialog
      v-model="groupFormVisible"
      :used-colors="groupFormUsedColors"
      @created="onGroupCreated"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import ImageUploader from "@/components/ImageUploader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";
import OcrUsageBanner from "./components/OcrUsageBanner.vue";
import OcrTextPanel from "./components/OcrTextPanel.vue";
import OcrCandidateList from "./components/OcrCandidateList.vue";
import { IMPORT_TAB_OPTIONS } from "./ocrImportModel";
import { useOcrQuota } from "./composables/useOcrQuota";
import { useOcrRecognize } from "./composables/useOcrRecognize";
import { useOcrImport } from "./composables/useOcrImport";
import { useOcrGroupPicker } from "./composables/useOcrGroupPicker";
import {
  useFormDirty,
  useUnsavedChangesGuard
} from "@/composables/useUnsavedChangesGuard";

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
// 文本域行内错误（design.md：错误提示走行内小字 + --color-danger，不用全局弹红）
const textError = ref("");

const {
  remaining,
  quota,
  occupied,
  remainingText,
  usageStateClass,
  usageIcon,
  fetchUsage
} = useOcrQuota();

const {
  recognizing,
  candidates,
  canRecognize,
  selectedCount,
  toggleCandidate,
  clearCandidates,
  handleRecognize
} = useOcrRecognize({
  activeTab,
  imageFile,
  textContent,
  textError,
  occupied,
  remaining,
  fetchUsage
});

const {
  availableGroups,
  selectedGroupIds,
  groupFormUsedColors,
  fetchGroups,
  onGroupCreated,
  resetGroupSelection
} = useOcrGroupPicker();
const groupFormVisible = ref(false);

const { importing, handleImport } = useOcrImport({
  candidates,
  selectedGroupIds,
  onImported: count => emit("imported", count),
  onFinished: () => reset()
});

// 自动聚焦文本域（生命感：打开弹窗/切到粘贴文本时，光标直达输入区）
const textPanelRef = ref<InstanceType<typeof OcrTextPanel> | null>(null);
function focusTextarea(): void {
  void nextTick(() => textPanelRef.value?.focus());
}

// 分段控制器切档：切换激活项并清空上一次识别结果；切到文本 tab 自动聚焦输入框
function switchTab(tab: "image" | "text"): void {
  activeTab.value = tab;
  clearCandidates();
  if (tab === "text") focusTextarea();
}

// ── 未保存离开保护（#1835）──
//关闭按钮 / ESC 走 before-close；底部「取消」是程序化 close，走不到它。
// 脏基线只取「用户真正输入过的东西」：识别**结果**不算改动（candidates 是派生出来的，
// 识别完不给钱的是它，但用户重开一次识别不贵；而要求用户先导入才让关，反而误伤）。
const { isDirty, markClean } = useFormDirty(() => ({
  tab: activeTab.value,
  file: imageFile.value?.name ?? null,
  fileSize: imageFile.value?.size ?? 0,
  text: textContent.value
}));

const { onBeforeClose, requestClose: confirmThenClose } =
  useUnsavedChangesGuard(() => isDirty.value, {
    message: "已输入内容，确定放弃吗？"
  });

/** 底部「取消」：程序化 close 走不到 before-close，必须自己问一遍 */
async function requestClose(): Promise<void> {
  await confirmThenClose(() => (visible.value = false));
}

// 打开时记基线（不用 @open：它在动画结束后才触发，期间的改动会被误判）
watch(
  () => props.modelValue,
  open => {
    if (open) markClean();
  },
  { immediate: true }
);

function reset(): void {
  clearCandidates();
  textContent.value = "";
  imageFile.value = null;
  textError.value = "";
  resetGroupSelection();
  // 与表单一起清基线：reset 跑在「导入成功」与「放弃后关闭」两条路上，
  // 只清表单不清基线的话，关闭后再开弹窗会直接是脏的（#1845 同源）。
  markClean();
}

// 🔥 修复：组件挂载时弹窗处于关闭态（visible=false），onMounted 不会触发
// fetchUsage，导致 remaining 永远停留在初始值 0。改为监听 modelValue，
// 每次打开弹窗时拉取最新额度。
watch(
  () => props.modelValue,
  val => {
    if (val) {
      fetchUsage();
      // 分组只在确认区出现（识别后），打开即取一次，避免识别完才拉导致的空窗
      void fetchGroups();
      // 打开弹窗且当前在文本 tab 时，自动聚焦输入框
      if (activeTab.value === "text") focusTextarea();
    }
  }
);

onMounted(() => {
  if (visible.value) {
    fetchUsage();
  }
});
</script>

<!-- lang="scss" 必须保留：本文件使用 &__block 嵌套拼接语法，原生 CSS 嵌套不支持该写法，
     缺失会导致全部嵌套规则静默失效（分段控制器裸按钮问题的根因） -->
<style scoped lang="scss">
/* 「重置式」而非「覆盖式」：先把 el-dialog 内部原生 margin/padding 归零，
   再按 design.md 的 --space-standard(24px) / --space-compact(16px) 重新注入呼吸感 */
.ocr-import-dialog {
  :deep(.el-dialog) {
    overflow: hidden;
    background-color: var(--bg-card);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
  }

  :deep(.el-dialog__header) {
    padding: var(--space-standard) var(--space-standard) var(--space-compact);
    margin: 0;
    border-bottom: 1px solid var(--border-light);
  }

  :deep(.el-dialog__title) {
    font-size: var(--text-heading);
    font-weight: 600;
    color: var(--text-primary);
  }

  :deep(.el-dialog__body) {
    padding: var(--space-standard);
    margin: 0;
  }

  :deep(.el-dialog__footer) {
    padding: var(--space-standard) var(--space-standard) var(--space-standard);
    margin: 0;
    border-top: 1px solid var(--border-light);
  }
}

/* ============================================
   按钮组：主按钮实底品牌红 / 次按钮浅灰软按钮
   统一 40px 高 + 6px 圆角 + padding 0 24px + 按压反馈（translateY(1px)）
   禁用态：浅灰底 + 禁用灰字 + not-allowed，且无按压反馈
   ============================================ */
.ocr-primary-btn,
.ocr-cancel-btn {
  height: 40px;
  padding: 0 24px;
  font-size: var(--text-small);
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
  background-color: var(--brand-solid);
}

.ocr-primary-btn:hover:not(:disabled) {
  background-color: var(--brand-solid-hover);
}

/* 禁用态：无内容/无图片时变浅灰，明确不可点击 */
.ocr-primary-btn:disabled {
  /* audit-text-contrast: exempt .ocr-primary-btn:disabled 为**真禁用**控件，按 WCAG 1.4.3 对 inactive component 的豁免；**「无数据占位符」不适用本豁免**（那是信息，须用 --text-tertiary-ink）。登记见 docs/spec/tech-debt.md（#1599） */
  color: var(--text-disabled);
  cursor: not-allowed;
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

/* ============================================
   分段控制器（SegmentedControl）：只补与下方面板的间距，外观全部由组件负责
   ============================================ */
.ocr-import-tabs {
  margin-bottom: var(--space-standard);
}

.ocr-tab-panel {
  min-height: 180px; /* 压缩留白，避免弹窗空洞 */
}
</style>
