<template>
  <!-- 占位页（#1840，方案 A）。此处原是 402 行 mock（零数据源，await / @/api 命中均为 0）。
       处理同 AssetManagement.vue：不接路由（会把假数据放上可达位置）、
       也不直接删（记下「规划过、缺数据源」，省得下一个接线的人重新考古）。 -->
  <div class="placeholder-page">
    <SectionHeader title="投资分析" :info="SCOPE_NOTE" />
    <CardBlock>
      <el-empty :image-size="88" :description="EMPTY_DESC">
        <p class="placeholder-page__note">
          这一页尚未接入数据源，因此不展示任何示例结论——<br />
          避免把占位数字误当成真实的收益分析。
        </p>
      </el-empty>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";

defineOptions({ name: "InvestmentAnalysis" });

/** 占位页口径说明（与贵金属 / 房产 / 资产管理页同一句） */
const SCOPE_NOTE = "占位页：尚未接入数据源，不展示示例数据";

const EMPTY_DESC = "投资分析正在建设中";
</script>

<style scoped>
.placeholder-page {
  padding: 24px;
}

.placeholder-page__note {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}
</style>
