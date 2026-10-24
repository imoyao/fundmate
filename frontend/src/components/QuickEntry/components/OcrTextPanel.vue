<!--
  粘贴文本面板（#980 拆分产物）：格式说明 + textarea + 行内错误。
  多根片段而不是再包一层 div——外层 `.ocr-tab-panel` 留在弹窗里，
  这里若再包一层就会多一个 DOM 节点（拆分不该改变页面结构）。
-->
<template>
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
    v-model="text"
    type="textarea"
    :rows="8"
    resize="vertical"
    class="ocr-textarea"
    placeholder="在此粘贴基金/股票代码，一行一个"
    @input="emit('edited')"
  />
  <!-- 行内错误提示（非全局弹红，design.md 危险色） -->
  <p v-if="error" class="ocr-textarea__error">{{ error }}</p>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElInput } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";

defineOptions({ name: "OcrTextPanel" });

/** 粘贴的原始文本（父层持有：切 tab / 关闭时要清空、脏基线也要读它） */
const text = defineModel<string>({ required: true });

defineProps<{
  /** 行内错误文案（识别无结果时由父层写入） */
  error: string;
}>();

const emit = defineEmits<{
  /** 用户改动了文本：父层据此清掉上一次的行内错误 */
  (e: "edited"): void;
}>();

const textareaRef = ref<InstanceType<typeof ElInput>>();

/** 自动聚焦（生命感：打开弹窗 / 切到「粘贴文本」时，光标直达输入区） */
function focus(): void {
  textareaRef.value?.focus();
}

defineExpose({ focus });
</script>

<style lang="scss" scoped>
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
    color: var(--text-tertiary-ink); /* 标题弱化为浅灰，突出正文 */

    /* 线性浅色小图标（--text-tertiary），弱化「通知」属性 */
    :deep(svg) {
      color: var(--text-tertiary-ink);
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

/* 文本域走 #1772 输入基线令牌：等宽字体直接写在容器上（EP 内部
   `font-family: inherit` 会继承下来），圆角 / 静态描边 / 过渡 / 焦点光晕
   全部由令牌表达，不再 :deep。
   ⚠️ 焦点刻意**不用**全局 --focus-ring（2px 间隙圈 + 4px 实红双环）——
   本输入区因自动聚焦常驻显示，重环会呈现「报错红框」观感；
   改用 brand-40% 柔光，聚焦感清晰但不施压。 */
.ocr-textarea {
  --input-focus-shadow:
    0 0 0 1px var(--brand-700) inset,
    0 0 0 3px color-mix(in srgb, var(--brand-400) 40%, transparent);
  --input-transition: box-shadow 0.2s ease;

  font-family: var(--font-mono); /* 代码等宽，数字纵向对齐 */
}

/* 行内错误提示：危险色小字，不弹全局红提示 */
.ocr-textarea__error {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--color-danger);
}
</style>
