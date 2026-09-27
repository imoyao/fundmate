<template>
  <div>
    <div class="flex justify-between items-center mb-6">
      <!-- 资产端 / 负债端切换（#1731 收敛）：原手写 `.balance-switch` 的注释自称「胶囊形」，
           实现却是「透明底 + 选中态 2px --brand-700 下划线」的 tab——注释与实现不符；
           且这是全仓唯一的下划线 tab 实现（design.md / components.md 均未登记该语言）。
           改为 SegmentedControl：同页上方（panorama/index.vue 的多维视图切换）本就是它，
           收敛后同一张卡片里不再并存两套切换外观。 -->
      <SegmentedControl
        v-model="balanceTab"
        :options="BALANCE_TAB_OPTIONS"
        size="small"
        aria-label="资产端 / 负债端切换"
      />
      <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
        {{ balanceTab === "assets" ? "资产构成" : "负债明细" }}
      </span>
    </div>

    <table v-if="balanceTab === 'assets'" class="w-full text-sm">
      <thead
        class="text-left text-xs border-b"
        :style="{
          color: 'var(--text-tertiary-ink)',
          borderColor: 'var(--border-light)'
        }"
      >
        <tr>
          <th class="py-3 pl-4 font-normal">资产大类</th>
          <th class="py-3 font-normal text-right w-24">占比</th>
          <th class="py-3 pr-4 font-normal text-right w-36">价值</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in assetBalanceRows"
          :key="item.name"
          class="border-b cursor-pointer transition-colors"
          :style="{ borderColor: 'var(--border-light)' }"
          @click="goToInventory(item.categoryKey)"
        >
          <td class="py-3 pl-4 flex items-center gap-3">
            <span
              class="w-2.5 h-2.5 rounded-full shrink-0"
              :style="{ backgroundColor: item.color }"
            />
            <span class="font-medium" :style="{ color: 'var(--text-primary)' }">
              {{ item.name }}
            </span>
          </td>
          <td
            class="py-3 text-right"
            :style="{ color: 'var(--text-secondary)' }"
          >
            <div class="flex items-center justify-end gap-2">
              <div
                class="h-1.5 w-16 rounded-full overflow-hidden"
                :style="{ backgroundColor: 'var(--bg-soft)' }"
              >
                <div
                  class="h-full rounded-full"
                  :style="{
                    backgroundColor: item.color,
                    width: item.percent + '%'
                  }"
                />
              </div>
              <span>{{ item.percent }}%</span>
            </div>
          </td>
          <td class="py-3 text-right pr-4">
            <MoneyDisplay
              :value="item.value"
              size="sm"
              :show-sign="false"
              :show-currency="true"
            />
          </td>
        </tr>
      </tbody>
      <tfoot>
        <tr :style="{ borderTop: '2px solid var(--border-light)' }">
          <td
            class="py-3 pl-4 font-medium"
            :style="{ color: 'var(--text-primary)' }"
          >
            合计
          </td>
          <td
            class="py-3 text-right"
            :style="{ color: 'var(--text-secondary)' }"
          >
            100%
          </td>
          <td class="py-3 text-right pr-4">
            <MoneyDisplay
              :value="totalAssets"
              size="sm"
              :show-sign="false"
              :show-currency="true"
            />
          </td>
        </tr>
      </tfoot>
    </table>

    <table v-else class="w-full text-sm">
      <thead
        class="text-left text-xs border-b"
        :style="{
          color: 'var(--text-tertiary-ink)',
          borderColor: 'var(--border-light)'
        }"
      >
        <tr>
          <th class="py-3 pl-4 font-normal">负债项目</th>
          <th class="py-3 font-normal text-right w-24">占比</th>
          <th class="py-3 pr-4 font-normal text-right w-36">金额</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in liabilityBalanceRows"
          :key="item.name"
          class="border-b cursor-pointer transition-colors"
          :style="{ borderColor: 'var(--border-light)' }"
          @click="goToInventory('liability')"
        >
          <td class="py-3 pl-4 flex items-center gap-3">
            <span
              class="w-2.5 h-2.5 rounded-full shrink-0"
              :style="{ backgroundColor: item.color }"
            />
            <span class="font-medium" :style="{ color: 'var(--text-primary)' }">
              {{ item.name }}
            </span>
          </td>
          <td
            class="py-3 text-right"
            :style="{ color: 'var(--text-secondary)' }"
          >
            <div class="flex items-center justify-end gap-2">
              <div
                class="h-1.5 w-16 rounded-full overflow-hidden"
                :style="{ backgroundColor: 'var(--bg-soft)' }"
              >
                <div
                  class="h-full rounded-full"
                  :style="{
                    backgroundColor: 'var(--color-neutral)',
                    width: item.percent + '%'
                  }"
                />
              </div>
              <span>{{ item.percent }}%</span>
            </div>
          </td>
          <td class="py-3 text-right pr-4">
            <MoneyDisplay
              :value="item.value"
              size="sm"
              :show-sign="false"
              :show-currency="true"
            />
          </td>
        </tr>
      </tbody>
      <tfoot>
        <tr :style="{ borderTop: '2px solid var(--border-light)' }">
          <td
            class="py-3 pl-4 font-medium"
            :style="{ color: 'var(--text-primary)' }"
          >
            合计
          </td>
          <td
            class="py-3 text-right"
            :style="{ color: 'var(--text-secondary)' }"
          >
            100%
          </td>
          <td class="py-3 text-right pr-4">
            <MoneyDisplay
              :value="totalLiabilities"
              size="sm"
              :show-sign="false"
              :show-currency="true"
            />
          </td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";

const props = defineProps<{
  distributions: any;
  totalAssets: number;
  totalLiabilities: number;
}>();

const router = useRouter();
const balanceTab = ref<"assets" | "liabilities">("assets");

/** 资产端 / 负债端分段选项（#1731）：`as const` 保留字面量类型，供 SegmentedControl 泛型推断 */
const BALANCE_TAB_OPTIONS = [
  { label: "资产端", value: "assets" },
  { label: "负债端", value: "liabilities" }
] as const;

const assetBalanceRows = computed(() => {
  const total = props.totalAssets;
  if (total === 0) return [];
  const labelMap: Record<string, { color: string; categoryKey: string }> = {
    流动资金: { color: "var(--palette-mint-green)", categoryKey: "cash" },
    固定资产: { color: "var(--palette-warm-taupe)", categoryKey: "fixed" },
    投资理财: { color: "var(--palette-periwinkle)", categoryKey: "investment" },
    应收款: { color: "var(--palette-stone-gray)", categoryKey: "receivable" },
    保险项目: { color: "var(--color-accent)", categoryKey: "insurance" }
  };
  // 消费后端 category_distribution（后端唯一聚合出口，含汇率换算）
  const categoryMap: Record<string, any> = {};
  for (const item of props.distributions?.category_distribution ?? []) {
    categoryMap[item.name] = {
      name: item.name,
      value: item.value,
      ...(labelMap[item.name] || {
        color: "var(--text-tertiary)",
        categoryKey: item.name
      })
    };
  }
  return Object.values(categoryMap)
    .filter(item => item.value > 0)
    .map(item => ({
      ...item,
      percent: +((item.value / total) * 100).toFixed(1)
    }));
});

const liabilityBalanceRows = computed(() => {
  const totalLiab = props.totalLiabilities;
  if (totalLiab === 0) return [];
  // 消费后端 liability_distribution（正数金额，负债明细按名称聚合）
  return (props.distributions?.liability_distribution ?? []).map(item => ({
    name: item.name,
    value: item.value,
    color: "var(--color-neutral)",
    percent: +((item.value / totalLiab) * 100).toFixed(1)
  }));
});

function goToInventory(categoryKey: string) {
  router.push(`/asset/inventory?tab=${categoryKey}`);
}
</script>

<style scoped>
/* 资产端 / 负债端切换的外观已全部移交 SegmentedControl（#1731 收敛）：
   原先这里有两块手写样式（`.balance-switch` 布局 + `.balance-btn` 胶囊外壳 +
   `.balance-btn.active::after` 的 2px `--brand-700` 下划线），注释自称「胶囊形」而实现是下划线 tab。
   现不保留任何视觉声明——手写分段控制器样式是 #1717 / #1731 反复回潮的起点，
   守卫 `scripts/guard_segmented.py` 会在 CI 拦下。 */
</style>
