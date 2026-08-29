<template>
  <div>
    <div class="flex justify-between items-center mb-6">
      <div class="balance-switch">
        <button
          class="balance-btn"
          :class="{ active: balanceTab === 'assets' }"
          @click="balanceTab = 'assets'"
        >
          资产端
        </button>
        <button
          class="balance-btn"
          :class="{ active: balanceTab === 'liabilities' }"
          @click="balanceTab = 'liabilities'"
        >
          负债端
        </button>
      </div>
      <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
        {{ balanceTab === "assets" ? "资产构成" : "负债明细" }}
      </span>
    </div>

    <table v-if="balanceTab === 'assets'" class="w-full text-sm">
      <thead
        class="text-left text-xs border-b"
        :style="{
          color: 'var(--text-tertiary)',
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
          color: 'var(--text-tertiary)',
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

const props = defineProps<{
  distributions: any;
  totalAssets: number;
  totalLiabilities: number;
}>();

const router = useRouter();
const balanceTab = ref<"assets" | "liabilities">("assets");

const assetBalanceRows = computed(() => {
  const total = props.totalAssets;
  if (total === 0) return [];
  const labelMap: Record<string, { color: string; categoryKey: string }> = {
    流动资金: { color: "var(--tag-mint-green)", categoryKey: "cash" },
    固定资产: { color: "var(--tag-warm-taupe)", categoryKey: "fixed" },
    投资理财: { color: "var(--tag-periwinkle)", categoryKey: "investment" },
    应收款: { color: "var(--tag-stone-gray)", categoryKey: "receivable" },
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
.balance-switch {
  display: flex;
  gap: 4px;
}

/* 资产端/负债端切换按钮：胶囊形（与下方 el-tag/el-segmented 的胶囊风格统一）。
   原 4px 圆角已提升为 9999px；下方独立的 .balance-btn 重复块已合并到此处，
   见 design.md 胶囊规范。 */
.balance-btn {
  position: relative;
  padding: 4px 14px;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-tertiary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 9999px;
  transition: color 0.2s;
}

.balance-btn.active {
  font-weight: 600;
  color: var(--text-primary);
}

.balance-btn.active::after {
  position: absolute;
  right: 8px;
  bottom: 0;
  left: 8px;
  height: 2px;
  content: "";
  background: var(--brand-700);
  border-radius: 1px;
}
</style>
