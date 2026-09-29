<template>
  <div class="space-y-3">
    <!-- 加载占位（#1717）：切换维度要重新拉分组，此前没有加载态——容器会先塌成 0 高、
         数据到达后再撑开，页面看起来「闪一下」。占位卡与真实分组卡同形（头部条 + 数值行），
         切换前后高度基本不变，只换内容不跳布局。 -->
    <template v-if="loading">
      <div
        v-for="i in SKELETON_ROWS"
        :key="`detail-group-skeleton-${i}`"
        class="border rounded-xl overflow-hidden"
        :style="{ borderColor: 'var(--border-default)' }"
        aria-hidden="true"
      >
        <div
          class="px-5 py-3 flex justify-between items-center"
          :style="{ backgroundColor: 'var(--bg-soft)' }"
        >
          <span class="detail-group-skeleton__bar w-24" />
          <span class="detail-group-skeleton__bar w-10" />
        </div>
        <div class="px-5 py-3 flex justify-between items-center">
          <span class="detail-group-skeleton__bar w-32" />
          <span class="detail-group-skeleton__bar w-16" />
        </div>
      </div>
    </template>

    <template v-else>
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
          <span :style="{ color: 'var(--text-primary)' }">{{
            group.name
          }}</span>
          <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
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
            <span
              class="ml-2 text-xs"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              占
              {{ ((Math.abs(group.total) / totalAssets) * 100).toFixed(1) }}%
            </span>
          </div>
          <MoneyDisplay
            :value="group.totalPnl"
            size="sm"
            :show-currency="true"
          />
        </div>
      </div>
    </template>
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
const loading = ref(false);

/** 加载占位卡数量：只决定占位高度，与真实分组数无关（产品类型 6 组 / 账户 / 配置目标） */
const SKELETON_ROWS = 4;

/** 竞态令牌：连点分段控制器时先发的请求可能后到，只接受最后一次请求的结果 */
let loadToken = 0;

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
  const token = ++loadToken;
  const dim = props.detailView;
  // 先清空上一维度的数据（#1717）：否则会先把上一维度的分组展示出来、再被新数据替换，
  // 视觉上就是「闪一下」；同时避免切回 category 时残留旧列表
  detailGroups.value = [];
  if (dim === "category") {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const res = await getPositionGroups(dim as GroupDimension);
    if (token !== loadToken) return;
    const raw = (res as any)?.data;
    detailGroups.value = Array.isArray(raw) ? raw : raw?.data || [];
  } catch (e: any) {
    if (token !== loadToken) return;
    detailGroups.value = [];
    ElMessage.error(e?.message || "分组加载失败");
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

watch(() => props.detailView, loadDetailGroups);
onMounted(loadDetailGroups);
</script>

<style scoped>
/* 占位条：与 PageSkeleton 同一「纯 CSS 流光」语言（background-size 动画，GPU 合成，不占主线程） */
.detail-group-skeleton__bar {
  height: 14px;
  background-color: var(--bg-soft);
  background-image: linear-gradient(
    90deg,
    var(--bg-soft) 25%,
    var(--bg-hover) 37%,
    var(--bg-soft) 63%
  );
  background-size: 400% 100%;
  border-radius: var(--radius-sm);
  animation: detail-group-skeleton-wave 1.8s ease-in-out infinite;
}

@keyframes detail-group-skeleton-wave {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}
</style>
