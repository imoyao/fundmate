<!--
  CrowdingHeaderTip · 带解释气泡的表头文字
  从 CrowdingTable 抽出（#980 批 B5）：这张表有 5 个表头需要一句口径说明
  （拥挤度怎么合成、成交额占比的分母是什么、60 线上占比的定义…），
  原先每处都套一层 `<el-tooltip><template #header>` 六行样板。

  口径说明不是装饰：这张表的每个数字都能被用户误读成「别的意思」，
  比如成交额占比在申万源不可用时会回退中证口径，两种口径**不可直接比较**——
  那句提示只出现在 tooltip 里，丢掉就等于放任用户横比。
-->
<template>
  <el-tooltip :content="content" placement="top">
    <span><slot /></span>
  </el-tooltip>
</template>

<script setup lang="ts">
defineOptions({ name: "CrowdingHeaderTip" });

defineProps<{
  /** 该列的口径说明（一句话讲清怎么算、边界是什么） */
  content: string;
}>();
</script>
