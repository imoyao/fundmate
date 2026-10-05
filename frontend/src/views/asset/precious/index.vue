<template>
  <!-- 占位页（#1839）：此前此处是硬编码的示例市值（¥58,000 / +2.1% …）与无功能按钮。
       页面仍在路由里、菜单仍可进入，但**不展示任何示例数据**——
       用户可达位置上的假金额会被当成真实持仓，这是数据可信度问题，不是体验瑕疵。
       真接后端时替换本文件即可（届时才引入取数与 loading / 空态三态）。 -->
  <div class="placeholder-page">
    <SectionHeader title="贵金属" :info="SCOPE_NOTE" />
    <CardBlock>
      <el-empty :image-size="88" :description="EMPTY_DESC">
        <p class="placeholder-page__note">
          这一页尚未接入数据源，因此不展示任何示例金额——<br />
          避免把占位数字误当成你的真实持仓。
        </p>
      </el-empty>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";

defineOptions({ name: "PreciousMetals" });

/** 占位页口径说明（两页共用同一句，避免各写一套说辞） */
const SCOPE_NOTE = "占位页：尚未接入数据源，不展示示例数据";

const EMPTY_DESC = "贵金属管理正在建设中";
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
