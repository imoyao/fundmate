<script setup lang="ts">
import { computed } from "vue";
import type { ManagerHoldingsResult } from "@/api/products";
import { styleTierClass } from "./mgrModel";

/**
 * 代表作前十大重仓（#980 拆分，#1970 扩展）。
 *
 * 口径标签必须展示：否则「只披露 10 只」会被误读成「只买了 10 只」。
 *
 * 风格标签（#2044）：徽章文字直接用后端 label；依据 basis 走 tooltip；
 * 维度缺席即该徽章不出现，为空整行不渲染——不显示空容器、不渲染占位徽章。
 */
const props = defineProps<{
  holdings: ManagerHoldingsResult | null;
  failed: boolean;
}>();

const DASH = "—";

const styleBadges = computed(() =>
  (props.holdings?.style_labels ?? []).map(lb => ({
    ...lb,
    tierClass: styleTierClass(lb.key)
  }))
);
</script>

<template>
  <div v-if="holdings && holdings.rows.length" class="mgr-section__holdings">
    <div class="mgr-section__holdings-head">
      <h4 class="mgr-section__subtitle">重仓明细</h4>
      <span v-if="holdings.fund_name" class="mgr-section__holdings-fund">
        {{ holdings.fund_name }}
      </span>
    </div>
    <div v-if="styleBadges.length" class="mgr-section__styles">
      <span class="mgr-section__styles-label">风格</span>
      <ul class="mgr-section__styles-list" aria-label="风格标签">
        <li
          v-for="lb in styleBadges"
          :key="lb.key"
          class="mgr-section__style-item"
        >
          <el-tooltip :content="lb.basis" placement="top">
            <span
              class="mgr-section__style-badge"
              :class="lb.tierClass"
              tabindex="0"
            >
              {{ lb.label }}
            </span>
          </el-tooltip>
        </li>
      </ul>
    </div>
    <el-table :data="holdings.rows" size="small" class="mgr-section__table">
      <el-table-column label="#" width="48">
        <template #default="{ row }">{{ row.rank }}</template>
      </el-table-column>
      <el-table-column label="股票" min-width="140">
        <template #default="{ row }">
          <span class="mgr-section__stock">{{
            row.stock_name || row.stock_code
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="占净值比" align="right" width="110">
        <template #default="{ row }">
          <span class="mgr-section__ratio">
            {{ row.ratio == null ? DASH : row.ratio.toFixed(2) + "%" }}
          </span>
        </template>
      </el-table-column>
    </el-table>
    <p class="mgr-section__note">
      报告期 {{ holdings.report_period }}（{{ holdings.basis_label }}）
      <template v-if="holdings.total_ratio != null">
        ，前 {{ holdings.rows.length }} 大合计占净值
        {{ holdings.total_ratio.toFixed(2) }}%
      </template>
    </p>
  </div>
  <p v-else-if="failed" class="mgr-section__hint">重仓明细读取失败</p>
  <p v-else-if="holdings?.empty_reason" class="mgr-section__hint">
    {{ holdings.empty_reason }}
  </p>
</template>

<style lang="scss" scoped>
@use "./mgr-base";
</style>
