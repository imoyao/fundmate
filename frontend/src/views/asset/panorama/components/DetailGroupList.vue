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
        class="border rounded-xl overflow-hidden transition-shadow hover:shadow-sm"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <!-- 头部行：点击 = 展开/收起逐持仓明细（#1813）；原「跳转到品种页/账户页」
             收进右侧「进入 ›」入口（点它不触发展开）。
             allocation 维度没有可跳的页面，不渲染入口。 -->
        <div
          class="px-5 py-3 flex justify-between items-center font-medium cursor-pointer"
          :style="{ backgroundColor: 'var(--bg-soft)' }"
          role="button"
          tabindex="0"
          :aria-expanded="expandedName === group.name"
          @click="toggleExpand(group.name)"
          @keydown.enter="toggleExpand(group.name)"
        >
          <span
            class="flex items-center gap-1"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ group.name }}
            <IconifyIconOffline
              v-if="group.items.length > 0"
              icon="ep:arrow-down"
              class="group-card__chevron text-sm"
              :class="{ 'is-open': expandedName === group.name }"
            />
          </span>
          <span
            class="flex items-center gap-2 text-xs"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            {{ group.items.length }} 项
            <el-button
              v-if="navTargetOf(group)"
              text
              size="small"
              class="group-card__nav"
              @click.stop="goGroup(group)"
            >
              进入 ›
            </el-button>
          </span>
        </div>

        <div
          class="px-5 py-3 flex justify-between items-center text-sm cursor-pointer"
          role="button"
          tabindex="0"
          @keydown.enter="toggleExpand(group.name)"
          @click="toggleExpand(group.name)"
        >
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
              {{
                totalAssets > 0
                  ? ((Math.abs(group.total) / totalAssets) * 100).toFixed(1) +
                    "%"
                  : "--"
              }}
            </span>
          </div>
          <MoneyDisplay
            :value="group.totalPnl"
            size="sm"
            :show-currency="true"
          />
        </div>

        <!-- 逐持仓明细（#1813）：items 接口一直在下发，此前只是没渲染。
             单线（后端 pnl 口径）：本页无实时链路，且 GroupItem 无 avg_price，
             预估副行接不了（见 usePositionValuation.estimatedPnl 的守卫说明）。 -->
        <div v-if="expandedName === group.name" class="group-detail">
          <div
            v-for="item in group.items"
            :key="item.id ?? item.symbol"
            class="group-detail__row"
          >
            <div class="group-detail__product">
              <ProductDisplay
                :name="item.name"
                :symbol="item.symbol"
                :type-label="item.type_label"
              />
            </div>
            <div class="group-detail__value">
              <MoneyDisplay
                :value="item.market_value"
                size="sm"
                :show-sign="false"
                :auto-color="false"
              />
            </div>
            <div class="group-detail__value">
              <MoneyDisplay :value="item.pnl" size="sm" />
            </div>
          </div>
          <p
            v-if="group.items.length === 0"
            class="text-xs text-center py-2"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            该分组暂无明细
          </p>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
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

/** 当前展开的分组（手风琴：同时只展开一个，避免长列表越拉越长） */
const expandedName = ref<string | null>(null);

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

/** 分组的跳转目标（#1813）：type → 品种页；account → 账户列表；allocation 无 → null */
function navTargetOf(group: {
  name: string;
}): string | { name: string } | null {
  if (props.detailView === "type") return { name: getTypeRoute(group.name) };
  if (props.detailView === "account") return "/asset/ledgers";
  return null;
}

function goGroup(group: { name: string }) {
  const target = navTargetOf(group);
  if (!target) return;
  router.push(target as never);
}

function toggleExpand(name: string) {
  expandedName.value = expandedName.value === name ? null : name;
}

async function loadDetailGroups() {
  const token = ++loadToken;
  const dim = props.detailView;
  // 先清空上一维度的数据（#1717）：否则会先把上一维度的分组展示出来、再被新数据替换，
  // 视觉上就是「闪一下」；同时避免切回 category 时残留旧列表。
  // 展开态一并重置：切维度后分组名都变了，保留展开 key 会落到错误的分组上。
  detailGroups.value = [];
  expandedName.value = null;
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
/* 展开指示箭头：旋转表达开合，避免再加一套「展开/收起」文案 */
.group-card__chevron {
  transition: transform 0.2s ease;
}

.group-card__chevron.is-open {
  transform: rotate(180deg);
}

/* 「进入 ›」：与「N 项」同排，弱化为次级文字，避免和展开操作抢主次 */
.group-card__nav {
  height: auto;
  padding: 0;
  font-size: 12px;
}

/* 逐持仓明细区：市值 / 盈亏 两列右对齐定宽，与上方合计行的右缘对齐 */
.group-detail {
  padding: 2px 20px 10px;
  border-top: 1px solid var(--border-subtle);
}

.group-detail__row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 7px 0;
}

.group-detail__row + .group-detail__row {
  border-top: 1px dashed var(--border-subtle);
}

.group-detail__product {
  flex: 1;
  min-width: 0;
}

.group-detail__value {
  flex-shrink: 0;
  width: 108px;
  text-align: right;
}
</style>
