<template>
  <el-dialog
    v-model="visible"
    class="ocr-import-dialog"
    title="AI 批量导入"
    width="640px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <!-- 顶部：剩余次数提示（三态：正常 / 紧张 / 用尽）。极简通栏，弱化存在感，聚焦「粘贴区」与「开始识别」 -->
    <div class="usage-banner" :class="usageStateClass">
      <IconifyIconOffline class="usage-banner__icon" :icon="usageIcon" />
      <span class="usage-banner__label">今日 AI 导入额度剩余</span>
      <span class="usage-banner__count">
        <!-- :key 触发动画：额度变化时数字轻微跳动，直给「扣了一次额度」的反馈 -->
        <strong :key="remaining">{{ remaining }}</strong> / {{ quota }} 次
      </span>
      <span v-if="remainingText" class="usage-banner__hint">{{
        remainingText
      }}</span>
    </div>

    <!-- 两个互斥选项 → 手写分段控制器（24px 胶囊，design.md「Segmented」）。
         弃用 el-segmented：其绝对定位滑块与原生默认层级难以彻底掌控，原生 button 完全可控最干净 -->
    <div class="ocr-segmented" role="tablist" aria-label="导入方式">
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

    <!-- ── 图片识别 ── -->
    <div v-if="activeTab === 'image'" class="ocr-tab-panel">
      <ImageUploader
        v-model="imageFile"
        tip="支持券商 / 基金 App 等持仓截图，文件不超过 5MB"
      />
    </div>

    <!-- ── 文本解析 ── -->
    <div v-else class="ocr-tab-panel">
      <!-- 格式说明：每行一只，6 位代码必填，名称可选（后端按代码反查名称） -->
      <div class="ocr-format-hint">
        <div class="ocr-format-hint__title">
          <IconifyIconOffline icon="ep:info" class="mr-1" />
          格式说明
        </div>
        <p class="ocr-format-hint__line">每行一只，支持6位代码，名称可不填</p>
        <p class="ocr-format-hint__example">示例：110011 易方达中小盘</p>
      </div>
      <el-input
        ref="textareaRef"
        v-model="textContent"
        type="textarea"
        :rows="8"
        resize="vertical"
        class="ocr-textarea"
        placeholder="在此粘贴基金/股票代码，一行一个"
        @input="textError = ''"
      />
      <!-- 行内错误提示（非全局弹红，design.md 危险色） -->
      <p v-if="textError" class="ocr-textarea__error">{{ textError }}</p>
    </div>

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
      <el-button class="ocr-cancel-btn" size="large" @click="visible = false"
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
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from "vue";
import { ElInput, ElMessage } from "element-plus";
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
// 文本域行内错误（design.md：错误提示走行内小字 + --color-danger-system，不用全局弹红）
const textError = ref("");

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

// 手写分段控制器：切换激活项并清空上一次识别结果；切到文本 tab 自动聚焦输入框
const switchTab = (tab: "image" | "text") => {
  activeTab.value = tab;
  handleTabChange();
  if (tab === "text") focusTextarea();
};

// 自动聚焦文本域（生命感：打开弹窗/切到粘贴文本时，光标直达输入区）
const textareaRef = ref<InstanceType<typeof ElInput>>();
const focusTextarea = () => {
  nextTick(() => textareaRef.value?.focus());
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
      items =
        (res.data as { items: OcrImportItem[]; usage: unknown }).items ?? [];
    } else {
      const text = textContent.value.trim();
      if (!text) {
        ElMessage.warning("请输入文本内容");
        return;
      }
      const res = await parseImportText(text);
      items =
        (res.data as { items: OcrImportItem[]; usage: unknown }).items ?? [];
    }

    if (items.length === 0) {
      // 文本：行内错误提示（不弹全局）；图片：无行内锚点，保留全局轻提示
      if (activeTab.value === "text") {
        textError.value = "未识别到有效代码，请检查每行是否包含 6 位代码";
      } else {
        ElMessage.info("未能识别出基金，请检查图片清晰度或文本格式");
      }
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
      // 可能是配额用完（3004）或限流（3005），用后端 message 区分
      const msg =
        e?.response?.data?.message || "今日 AI 识别次数已用完，请明日再试";
      ElMessage.warning(msg);
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
    // 空/空白代码必须跳过：后端对空 symbol 跳过过滤走「全部」分支返回整页数据，
    // 会被误判成「已存在」——无代码的候选（如只有组合名的投顾行）一律保守当作新项
    const key = (it.symbol || it.code || "").trim();
    if (!key) continue;
    try {
      // 用标准化 symbol 探测（场内如 SH600519），与后端查重口径一致
      const res = await getWatchlistItems({ symbol: key, per_page: 1 });
      const data = (res as any).data ?? [];
      if (data.length > 0) set.add(key);
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
  textError.value = "";
};

// 🔥 修复：组件挂载时弹窗处于关闭态（visible=false），onMounted 不会触发
// fetchUsage，导致 remaining 永远停留在初始值 0。改为监听 modelValue，
// 每次打开弹窗时拉取最新额度。
watch(
  () => props.modelValue,
  val => {
    if (val) {
      fetchUsage();
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
/* 额度数字跳动：扣除次数时轻微缩放反馈 */
@keyframes usage-pop {
  0% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.18);
  }

  100% {
    transform: scale(1);
  }
}

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
  background-color: var(--brand-700);
}

.ocr-primary-btn:hover:not(:disabled) {
  background-color: var(--brand-600);
}

/* 禁用态：无内容/无图片时变浅灰，明确不可点击 */
.ocr-primary-btn:disabled {
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
   剩余次数提示（三态：正常 / 紧张 / 用尽）
   极简通栏：--bg-warm 暖底 + 无边框 + 线性小图标，弱化「通知」属性增强「辅助」属性
   ============================================ */

/* 额度提示：无背景无边框，纯文字分层留白（图标 --text-tertiary / 说明 --text-secondary /
   数字等宽加粗 --brand-700），用空间代替色块，高级感来自留白 */
.usage-banner {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin-bottom: var(--space-standard);
  transition: color 0.2s ease;

  &__icon {
    display: inline-flex;
    flex-shrink: 0;
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
      display: inline-block;
      font-family: var(--font-mono);
      font-size: 14px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--brand-700);
      animation: usage-pop 0.2s ease; /* :key 变化时重放：额度扣除的微小「跳动」 */
    }
  }

  &__hint {
    flex-shrink: 0;
    margin-left: auto;
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }

  /* 额度紧张：仅数字/图标变色，不新增背景块 */
  &.is-low .usage-banner__count strong {
    color: var(--text-primary);
  }

  /* 额度用尽：数字/提示变危险色，不新增背景块 */
  &.is-used-up {
    .usage-banner__count strong,
    .usage-banner__hint {
      color: var(--color-danger);
    }
  }
}

/* ============================================
   手写分段控制器（充满生命感）
   - 轨道：--bg-soft 暖米色（--bg-muted 是淡灰蓝 #f5f7fa，在暖白弹窗上几乎不可见，
     会呈现"孤立文字"观感；暖米色轨道才有明显容器感）
   - 选中态：软按钮仅 --brand-100 底 + --brand-700 字（不加边框/inset，避免多红线视觉过载）
   - 切换：果冻回弹 cubic-bezier(0.34, 1.56, 0.64, 1)
   ============================================ */
.ocr-segmented {
  display: flex;
  gap: 4px;
  width: 100%;
  padding: 4px;
  margin-bottom: var(--space-standard);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);

  &__item {
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: center;
    height: 24px;
    padding: 0 12px;
    font-size: 13px;
    line-height: 1;
    color: var(--text-secondary);
    cursor: pointer;
    background: transparent;
    border: none;
    border-radius: var(--radius-pill);
    transition: all 300ms cubic-bezier(0.34, 1.56, 0.64, 1); /* 果冻回弹 */

    /* 原生 button 点击后残留浏览器默认 focus 外框（粗红线观感的来源），鼠标点击不画框 */
    &:focus {
      outline: none;
    }

    /* 键盘导航仍保留细描边（无障碍兜底，仅 Tab 聚焦时出现） */
    &:focus-visible {
      outline: 1px solid var(--brand-400);
      outline-offset: 2px;
    }

    &:hover {
      color: var(--text-primary);
      background: rgb(0 0 0 / 3%);
    }

    /* 选中态只靠浅红底 + 深红字区分，不加任何边框（避免多红线视觉过载） */
    &.is-active {
      color: var(--brand-700);
      background: var(--brand-100);
    }
  }
}

.ocr-tab-panel {
  min-height: 180px; /* 压缩留白，避免弹窗空洞 */
}

/* ============================================
   文本解析：格式说明 + textarea 圆角/focus 环 + 行内错误
   ============================================ */

/* 格式说明：无背景色块，纯排版留白区分层级（遵循「留白即背景」） */
.ocr-format-hint {
  padding: 0;
  margin-bottom: var(--space-standard); /* 24px 呼吸感，与 textarea 拉开距离 */

  &__title {
    display: flex;
    align-items: center;
    margin-bottom: var(--space-2);
    font-size: var(--text-label);
    font-weight: 500;
    color: var(--text-tertiary); /* 标题弱化为浅灰，突出正文 */

    /* 线性浅色小图标（--text-tertiary），弱化「通知」属性 */
    :deep(svg) {
      color: var(--text-tertiary);
    }
  }

  &__line {
    margin: 0;
    font-size: var(--text-body);
    line-height: 1.6;
    color: var(--text-primary); /* 正文为主黑，形成排版层 */
  }

  /* 示例纯文本化：仅等宽字体 + 品牌红字色，不加背景块/边框（聚焦靠留白与色彩层级） */
  &__example {
    margin: var(--space-2) 0 0;
    font-family: var(--font-mono);
    font-size: var(--text-label);
    font-style: italic; /* 微倾斜增加层次 */
    font-variant-numeric: tabular-nums;
    color: var(--brand-700);
  }
}

.ocr-textarea {
  :deep(.el-textarea__inner) {
    font-family: var(--font-mono); /* 代码等宽，数字纵向对齐 */
    border-radius: var(--radius-sm);
    box-shadow: 0 0 0 1px var(--border-default) inset;
    transition: box-shadow 0.2s ease;

    &:focus {
      /* 轻聚焦：仅 1px 品牌红内边 + 浅色光晕。
         不用全局 --focus-ring（它是 2px 白圈+4px 实红双环，本输入区因自动聚焦常驻显示，
         重环会呈现「报错红框」观感），改用 brand-40% 柔光，聚焦感清晰但不施压 */
      box-shadow:
        0 0 0 1px var(--brand-700) inset,
        0 0 0 3px color-mix(in srgb, var(--brand-400) 40%, transparent);
    }
  }
}

/* 行内错误提示：危险色小字，不弹全局红提示 */
.ocr-textarea__error {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--color-danger-system);
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

/* 候选列表：去容器背景与边框，改用行间细分隔线（--border-light 极浅暖灰）保持清爽 */
.candidate-list {
  display: flex;
  flex-direction: column;
  max-height: 240px;
  overflow-y: auto;
}

.candidate-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-compact) var(--space-2);
  font-size: var(--text-small);
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  transition: background-color 0.15s ease;

  &:last-child {
    border-bottom: none;
  }

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

/* ============================================
   弹窗容器：对齐 design.md（大圆角 + 暖调模态阴影 + 头尾分隔线）
   ============================================ */
</style>
