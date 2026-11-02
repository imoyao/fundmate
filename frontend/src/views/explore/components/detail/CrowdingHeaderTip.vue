<!--
  CrowdingHeaderTip · 带解释气泡的表头文字
  从 CrowdingTable 抽出（#980 批 B5）：这张表有 5 个表头需要一句口径说明
  （拥挤度怎么合成、成交额占比的分母是什么、60 线上占比的定义…），
  原先每处都套一层 `<el-tooltip><template #header>` 六行样板。

  口径说明不是装饰：这张表的每个数字都能被用户误读成「别的意思」，
  比如成交额占比在申万源不可用时会回退中证口径，两种口径**不可直接比较**——
  那句提示只出现在 tooltip 里，丢掉就等于放任用户横比。

  载体按字数自动选（2026-11-02，判据见 utils/tooltipText.ts）：表头说明多数只有一句话，
  走深色短语气泡；「成交额占比」那条实为 105 字、三句，在默认气泡里会铺成一整行
  （默认气泡此前没有宽度上限），现在自动升格成浅色说明卡并按句分行。
  调用方不必再自己判断「这条算不算长」。
-->
<template>
  <el-tooltip
    :content="useRich ? undefined : content"
    placement="top"
    :popper-class="tipClass"
  >
    <span><slot /></span>
    <template v-if="useRich" #content>
      <p v-for="(paragraph, i) in paragraphs" :key="i">{{ paragraph }}</p>
    </template>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  isRichTipText,
  tipParagraphs,
  tipPopperClass
} from "@/utils/tooltipText";

defineOptions({ name: "CrowdingHeaderTip" });

const props = defineProps<{
  /** 该列的口径说明（一句话讲清怎么算、边界是什么） */
  content: string;
}>();

const useRich = computed(() => isRichTipText(props.content));
const paragraphs = computed(() => tipParagraphs(props.content));
const tipClass = computed(() => tipPopperClass(props.content));
</script>
