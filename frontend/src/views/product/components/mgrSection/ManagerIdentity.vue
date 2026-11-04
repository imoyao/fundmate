<script setup lang="ts">
import { computed } from "vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import type { ManagerProfileResult } from "@/api/products";
import { bestReturnClass, hasTenureData, tenureCaption } from "./mgrModel";

/**
 * 经理身份与指标卡（#980 拆分）。
 *
 * 数值直接用后端换算结果，**不在前端做二次换算**：后端存的是为计算而存的原值
 * （从业天数 5125、规模 307.94），展示口径收口在服务层单点（`tenure_display.py`），
 * 前端再写一次 ÷365 就是要消灭的那种重复，口径迟早漂移。
 */
const props = defineProps<{
  profile: ManagerProfileResult;
}>();

const DASH = "—";

const bestClass = computed(() => bestReturnClass(props.profile.best_return));
const caption = computed(() => tenureCaption(props.profile.tenure_display));
const missingTenure = computed(() => !hasTenureData(props.profile));
</script>

<template>
  <!-- 身份行：姓名 + 公司（重名靠公司消歧，库内 119 组重名） -->
  <div class="mgr-section__identity">
    <span class="mgr-section__name">{{ profile.name || DASH }}</span>
    <span class="mgr-section__company">{{ profile.company || DASH }}</span>
  </div>

  <!-- 指标卡：数值直接用后端换算结果，不在前端做二次换算 -->
  <MetricGrid class="mgr-section__metrics">
    <MetricCard
      title="从业年限"
      :value="profile.tenure_display?.text ?? DASH"
      :caption="caption"
    />
    <MetricCard
      title="管理规模"
      :value="profile.scale_display?.value ?? DASH"
      :unit="profile.scale_display ? profile.scale_display.unit : undefined"
      caption="现任基金合计"
    />
    <MetricCard
      title="最佳回报"
      :value="profile.best_return_display?.text ?? DASH"
      caption="现任基金中最高"
    />
    <MetricCard
      title="任职基金"
      :value="profile.fund_count"
      :unit="profile.fund_count ? '只' : undefined"
      :caption="
        profile.active_fund_count
          ? `在任 ${profile.active_fund_count} 只`
          : undefined
      "
    />
  </MetricGrid>

  <!-- 最佳回报涨跌色：视觉语义在前端，数据不带色 -->
  <p
    v-if="profile.best_return_display"
    class="mgr-section__best-return"
    :class="bestClass"
  >
    {{ profile.name }} 的现任基金最佳回报
    {{ profile.best_return_display.text }}
  </p>

  <!-- 任期类字段整片为空时给出定调说明，避免用户以为加载失败 -->
  <p v-if="missingTenure" class="mgr-section__note">
    从业年限与任期起止尚未同步，当前仅展示任职基金名单。
  </p>
</template>

<style lang="scss" scoped>
@use "./mgr-base";
</style>
