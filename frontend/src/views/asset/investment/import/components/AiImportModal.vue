<template>
  <el-dialog
    v-model="visible"
    class="ai-import-dialog"
    title="AI 识别交易记录"
    width="680px"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <!-- 顶部：剩余次数提示（三态：正常 / 紧张 / 用尽，feature 独立限次）。
         #2724 起壳由 SoftBanner 承担：三态配色本就与 info/warning/danger 一一对应 -->
    <SoftBanner class="usage-banner" :variant="usageVariant" :icon="usageIcon">
      <div class="usage-banner__main">
        <span class="usage-banner__label">今日持仓识别额度</span>
        <span class="usage-banner__count">
          剩余 <strong>{{ remaining }}</strong> / {{ quota }} 次
        </span>
      </div>
      <template v-if="remainingText" #actions>
        <span class="usage-banner__hint">{{ remainingText }}</span>
      </template>
    </SoftBanner>

    <el-tabs v-model="activeTab" class="ai-tabs" @tab-change="handleTabChange">
      <!-- ── 图片识别 ── -->
      <el-tab-pane name="image" label="上传截图">
        <ImageUploader
          v-model="imageFile"
          tip="支持券商 / 基金 App 的持仓或交易截图（含买卖/日期/金额），文件不超过 5MB"
        />
      </el-tab-pane>

      <!-- ── 文本识别 ── -->
      <el-tab-pane name="text" label="粘贴文本">
        <el-input
          v-model="textContent"
          type="textarea"
          :rows="8"
          resize="vertical"
          class="ai-textarea"
          placeholder="粘贴交易记录，例如：&#10;易方达中小盘 110011 申购 5000 元 2026-08-01&#10;沪深300ETF 510300 卖出 100 股 2026-07-30"
        />
      </el-tab-pane>
    </el-tabs>

    <div v-if="recognitionHint" class="recognition-hint">
      <IconifyIconOffline icon="ep:info-filled" />
      识别结果仅供预填，<strong
        >日期 / 金额 / 份额请在下一步预览中人工核对后再确认入库</strong
      >
    </div>

    <template #footer>
      <el-button size="large" @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        size="large"
        :loading="recognizing"
        :disabled="!canRecognize"
        @click="handleRecognize"
      >
        <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
        开始识别
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import ImageUploader from "@/components/ImageUploader/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import { parseImportText, recognizeImage, getOcrUsage } from "@/api/ocr";
import type { OcrTxnRow } from "@/api/ocr";

const props = defineProps<{
  modelValue: boolean;
  /** 交易账户 id（后端据此回填账户名） */
  ledgerId: number | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  /** 识别完成，向父组件移交预览行（父组件负责并入既有预览表格与确认流程） */
  "rows-found": [rows: OcrTxnRow[]];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const activeTab = ref<"image" | "text">("image");
const imageFile = ref<File | null>(null);
const textContent = ref("");
const recognizing = ref(false);

const remaining = ref(0);
const quota = ref(5);
const occupied = ref(false);

const remainingText = computed(() => {
  if (occupied.value) return "额度已用尽，请明日再试";
  if (remaining.value <= 2) return "额度紧张，谨慎使用";
  return "";
});
// #2724：三态配色映射到 SoftBanner 的 variant（原 `is-low`/`is-used-up` 两个状态类
// 已删除——它们的唯一职责就是换底色/边框/文字色，现在由 variant 承担）
const usageVariant = computed<"info" | "warning" | "danger">(() => {
  if (occupied.value) return "danger";
  if (remaining.value <= 2) return "warning";
  return "info";
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

const recognitionHint = computed(() => remaining.value > 0);

const handleTabChange = () => {
  /* 切换输入源时无需清理，识别结果只在点击「开始识别」后产生 */
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

const handleRecognize = async () => {
  if (remaining.value <= 0) {
    ElMessage.warning("今日持仓识别额度已用完，请明日再试");
    return;
  }
  recognizing.value = true;
  try {
    let rows: OcrTxnRow[] = [];
    if (activeTab.value === "image") {
      if (!imageFile.value) {
        ElMessage.warning("请先选择图片");
        return;
      }
      const base64 = await fileToBase64(imageFile.value);
      const res = await recognizeImage(base64, "txn_import");
      const data = res.data as { rows: OcrTxnRow[]; usage: unknown };
      rows = data.rows ?? [];
    } else {
      const text = textContent.value.trim();
      if (!text) {
        ElMessage.warning("请输入文本内容");
        return;
      }
      const res = await parseImportText(text, "txn_import");
      const data = res.data as { rows: OcrTxnRow[]; usage: unknown };
      rows = data.rows ?? [];
    }

    // 识别成功已消耗 1 次对应场景配额，同步刷新余量展示
    void fetchUsage();

    if (rows.length === 0) {
      ElMessage.info(
        "未能识别出交易记录，请检查截图清晰度或文本是否包含基金/股票代码与金额"
      );
      return;
    }

    const warningCount = rows.filter(r => (r.warnings ?? []).length > 0).length;
    emit("rows-found", rows);
    visible.value = false;
    reset();
    if (warningCount > 0) {
      ElMessage.warning(
        `识别到 ${rows.length} 条，其中 ${warningCount} 条存在字段异常（如日期/金额未识别），请在预览中人工补填`
      );
    } else {
      ElMessage.success(`识别到 ${rows.length} 条交易记录，进入预览核对`);
    }
  } catch (e: any) {
    // 兜底：识别失败（超时/服务不可用）后端会返还配额，刷新余量避免显示虚低
    void fetchUsage();
    const status = e?.response?.status;
    if (status === 503) {
      ElMessage.error("AI 识别服务暂时繁忙，请稍后重试（失败不消耗次数）");
    } else if (status === 429) {
      const msg =
        e?.response?.data?.message || "今日持仓识别次数已用完，请明日再试";
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

const fetchUsage = async () => {
  try {
    const res = await getOcrUsage("txn_import");
    const data = res.data;
    remaining.value = data.remaining;
    quota.value = data.quota;
    occupied.value = data.remaining <= 0;
  } catch {
    // 用量查询失败不阻断识别主流程
  }
};

const reset = () => {
  imageFile.value = null;
  textContent.value = "";
};

watch(
  () => props.modelValue,
  val => {
    if (val) void fetchUsage();
  }
);
</script>

<!-- lang="scss" 必须保留：本文件使用 &__block 嵌套拼接语法，原生 CSS 嵌套不支持该写法，
     缺失会导致全部嵌套规则静默失效 -->
<style scoped lang="scss">
/* #2724：壳（display/gap/align-items/padding/margin/background/border/radius）
   由 SoftBanner 承担，此处只保留正文排版。
   `&__icon` 一并删除——图标改由 SoftBanner 的 icon prop 渲染，`--brand-700`
   （#e34f38 在 --bg-soft 上仅 3.41:1，文字级不达标；且属 tech-debt 的 --brand-*
   直调违规）随之消除。
   文字色统一回中性档：原用尽态 `--color-danger` #d4364a 在 --color-danger-20 底上
   仅 3.17:1，紧张态 `--color-warning-ink` 4.68:1 也只是勉强；改为
   --text-primary（12.99~12.39:1）/ --text-secondary（5.24~4.99:1）后均达标。
   语义由 variant 的底色 + 图标 + 边框承担，不染正文（#2726 口径）。 */
.usage-banner__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.usage-banner__label {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

/* 额度数字等宽：数字在 5→1 变化时不左右抖动（原实现未声明，本卡补齐）。
   颜色不再染品牌色——字重已足够强调，状态语义交给 variant 的底色 + 图标 + 边框。 */
.usage-banner__count {
  font-size: var(--text-body);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.usage-banner__count strong {
  font-size: var(--text-body);
  color: var(--text-primary);
}

.usage-banner__hint {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.recognition-hint {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: 8px 12px;
  margin-top: 14px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-md);

  strong {
    /* #2724：原为 --brand-700（#e34f38）——在 --bg-soft 上仅 3.41:1，**文字级不达标**；
       且属 tech-debt 的 --brand-* 直调违规。强调靠字重，不靠染色。 */
    color: var(--text-primary);
  }
}

.ai-textarea {
  :deep(textarea) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: var(--text-small);
  }
}
</style>
