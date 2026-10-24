<script setup lang="ts">
import { computed, ref } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import PnlDualLine from "@/components/PnlDualLine/index.vue";
import { confirmedPnl } from "@/composables/usePositionValuation";
import type { StrategyTag } from "@/api/strategy";
import StrategyTagCell from "./StrategyTagCell.vue";
import {
  type EnrichedHolding,
  type StrategyGroup,
  sliceGroupPage
} from "./strategyViewModel";

/**
 * 一个标签分组：组头（标签名 + 只数 + 组内市值/盈亏）+ 持仓表 + 组内分页。
 *
 * **组内页码是本组件的本地状态**：每个标签各翻各的页，父层不需要维护
 * 「标签名 → 页码」的映射（拆分前那张映射表的唯一用途就是喂分页器）。
 *
 * 组头里两个金额口径不同：市值/盈亏都是**组内合计**，而页面顶部是原始持仓合计——
 * 一只持仓带多个标签会同时计入多个组，两者本来就不相等（见 strategyViewModel 注释）。
 */
defineOptions({ name: "StrategyGroupSection" });

const props = defineProps<{
  group: StrategyGroup;
  allTags: StrategyTag[];
  /** 组内每页条数 */
  pageSize: number;
  /** 为某持仓新建并绑定标签；返回是否成功 */
  createTag: (positionId: number, name: string) => Promise<boolean>;
  /**
   * 当日预估盈亏 / 提示：由父层传入。
   *
   * **不能在子组件里再实例化 `usePositionValuation`**：父层用的是**原始持仓**
   * （每只一份），而本组件拿到的是分组副本（一只按标签出现在多个组里）。
   * 用副本实例化会让同一 symbol 出现多份、估值引擎按 symbol 查回时命中哪份不确定
   * （见 usePositionValuation 与父页的注释）。
   */
  estimatedPnl: (holding: EnrichedHolding) => number | null;
  estimateHint: (holding: EnrichedHolding) => string;
}>();

const emit = defineEmits<{
  (e: "unbind", payload: { positionId: number; tag: string }): void;
  (e: "update-tags", payload: { positionId: number; tags: string[] }): void;
}>();

const page = ref(1);

const rows = computed(() =>
  sliceGroupPage([props.group], props.group.tag, page.value, props.pageSize)
);
</script>

<template>
  <div class="mb-8">
    <div class="flex items-baseline justify-between mb-4">
      <h3 class="font-bold text-lg" :style="{ color: 'var(--text-primary)' }">
        {{ group.tag }}
        <span
          class="text-sm font-normal ml-2"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          {{ group.holdings.length }} 只持仓 · 市值
          <MoneyDisplay
            :value="group.totalMarketValue"
            :show-sign="false"
            :auto-color="false"
            size="xs"
          />
          <MoneyDisplay
            :value="group.totalPnl"
            size="xs"
            class="ml-1 font-medium"
          />
        </span>
      </h3>
    </div>

    <el-table v-if="group.holdings.length" :data="rows" stripe size="default">
      <!-- 产品信息：名称/代码 + 类型标签 -->
      <el-table-column label="名称 / 代码" min-width="180">
        <template #default="{ row }">
          <div class="product-cell">
            <span class="product-name">{{
              row.name || row.symbol || "--"
            }}</span>
            <div class="product-code-row">
              <span class="product-code"># {{ row.symbol || "--" }}</span>
              <span
                v-if="row.type_label"
                class="type-tag-inline ml-2 px-2 py-0.5 rounded-full text-xs"
                :style="{
                  backgroundColor: 'var(--bg-page)',
                  color: 'var(--text-secondary)'
                }"
              >
                {{ row.type_label }}
              </span>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="市值" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.marketValue || 0"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>

      <!-- 盈亏双线（#1104）：主行＝已确认，副行＝当日预估。
           组级汇总（totalPnl）仍是静态确认口径，不含预估——预估只做逐行参考。 -->
      <el-table-column label="盈亏" width="170" align="right">
        <template #default="{ row }">
          <PnlDualLine
            :confirmed="confirmedPnl(row as EnrichedHolding)"
            :estimated="estimatedPnl(row as EnrichedHolding)"
            :hint="estimateHint(row as EnrichedHolding)"
            :price-date="(row as EnrichedHolding).price_date"
            :settled-today="(row as EnrichedHolding).settled_today"
          />
        </template>
      </el-table-column>

      <el-table-column label="盈亏率" width="90" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.pnlRate || 0"
            :precision="2"
            suffix="%"
            size="sm"
          />
        </template>
      </el-table-column>

      <el-table-column label="所属账户" width="120">
        <template #default="{ row }">{{ row.account_name }}</template>
      </el-table-column>

      <!-- 策略标签列：点击弹出多选，可增删 -->
      <el-table-column label="策略标签" width="180">
        <template #default="{ row }">
          <StrategyTagCell
            :row="row as EnrichedHolding"
            :all-tags="allTags"
            :create-tag="name => createTag(row.id, name)"
            @unbind="tag => emit('unbind', { positionId: row.id, tag })"
            @update-tags="
              tags => emit('update-tags', { positionId: row.id, tags })
            "
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 分组内分页 -->
    <div v-if="group.holdings.length > pageSize" class="flex justify-end mt-4">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="group.holdings.length"
        layout="prev, pager, next"
        small
        background
      />
    </div>
  </div>
</template>
