<template>
  <div class="space-y-3">
    <div
      v-for="group in currentDetailGroups"
      :key="group.name"
      class="border rounded-xl overflow-hidden cursor-pointer transition-shadow hover:shadow-sm"
      :style="{ borderColor: 'var(--border-default)' }"
      @click="handleGroupClick(group)"
    >
      <div
        class="px-5 py-3 flex justify-between items-center font-medium"
        :style="{ backgroundColor: 'var(--bg-soft)' }"
      >
        <span :style="{ color: 'var(--text-primary)' }">{{ group.name }}</span>
        <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          {{ group.items.length }} 项
        </span>
      </div>
      <div class="px-5 py-3 flex justify-between items-center text-sm">
        <div>
          <MoneyDisplay
            :value="group.total"
            size="sm"
            :show-sign="false"
            :show-currency="true"
          />
          <span class="ml-2 text-xs" :style="{ color: 'var(--text-tertiary)' }">
            占
            {{ ((Math.abs(group.total) / totalAssets) * 100).toFixed(1) }}%
          </span>
        </div>
        <MoneyDisplay :value="group.totalPnl" size="sm" :show-currency="true" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getPositionGroups, type GroupDimension } from "@/api/summary";
import { ElMessage } from "element-plus";

const props = defineProps<{
  detailView: string;
  totalAssets: number;
}>();

const router = useRouter();
const detailGroups = ref<any[]>([]);

// 后端分组数据（detailView 切换时按需拉取，字段后端为 snake_case）
const currentDetailGroups = computed(() =>
  detailGroups.value.map(g => ({
    name: g.name,
    total: g.total,
    totalPnl: g.total_pnl,
    items: g.items
  }))
);

function getTypeRoute(typeName: string): string {
  // 返回路由 name（路由经 formatTwoStageRoutes 拍平后 path 层级失效，用 name 跳转最稳妥）
  const routes: Record<string, string> = {
    股票: "AssetStocks",
    基金: "AssetFunds",
    可转债: "AssetStocks",
    ETF: "AssetStocks",
    虚拟货币: "AssetPrecious",
    银行存款: "AssetFunds"
  };
  return routes[typeName] || "AssetStocks";
}

function handleGroupClick(group: any) {
  if (props.detailView === "type") {
    router.push({ name: getTypeRoute(group.name) });
  } else if (props.detailView === "account") {
    router.push("/asset/ledgers");
  }
}

async function loadDetailGroups() {
  const dim = props.detailView;
  if (dim === "category") return;
  try {
    const res = await getPositionGroups(dim as GroupDimension);
    const raw = (res as any)?.data;
    detailGroups.value = Array.isArray(raw) ? raw : raw?.data || [];
  } catch (e: any) {
    detailGroups.value = [];
    ElMessage.error(e?.message || "分组加载失败");
  }
}

watch(() => props.detailView, loadDetailGroups);
onMounted(loadDetailGroups);
</script>
