<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { DASH } from "./perfFormat";
import type { PerfFactItem } from "./perfRows";

/**
 * 指标网格（#980 拆分）。
 *
 * 详情页里「标签 / 数值 / 口径副行」这套排版在业绩、同类分位、基准、回撤四处
 * 完全同构，只有数据形态不同。抽成一个展示件后，模板侧的重复只剩「传哪组行」。
 *
 * 样式不做本地 scoped：这些 `performance-section__*` 类名的声明仍留在父页，
 * 由父页 `:deep()` 穿透。理由见 ProductPerformanceSection.vue 的 style 注释——
 * 一份声明、一处口径，拆组件不产生视觉漂移。
 */
withDefaults(
  defineProps<{
    items: PerfFactItem[];
  }>(),
  {}
);
</script>

<template>
  <dl class="performance-section__facts">
    <div
      v-for="item in items"
      :key="item.key"
      class="performance-section__fact"
    >
      <!-- 指标解释（2026-10-17）：原生 title 不显眼且样式不可控，
           升级为 el-tooltip + 信息图标（与同类优选表头同款 tooltip） -->
      <dt class="performance-section__label">
        <template v-if="item.hint">
          <span class="performance-section__label-text">{{ item.label }}</span>
          <el-tooltip :content="item.hint" placement="top">
            <IconifyIconOffline
              icon="ep:info-filled"
              class="performance-section__tip-icon"
            />
          </el-tooltip>
        </template>
        <template v-else>{{ item.label }}</template>
      </dt>
      <dd class="performance-section__value">
        <RiseFallText v-if="item.num != null" :value="item.num" />
        <span v-else>{{ item.value ?? DASH }}</span>
      </dd>
      <dd v-if="item.sub" class="performance-section__sub">{{ item.sub }}</dd>
    </div>
  </dl>
</template>
