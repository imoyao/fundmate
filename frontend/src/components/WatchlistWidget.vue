<template>
  <div
    class="watchlist-widget rounded-2xl p-6 h-full flex flex-col"
    :style="{
      backgroundColor: 'var(--bg-card)',
      boxShadow: 'var(--shadow-raised)',
      border: '1px solid var(--border-light)'
    }"
  >
    <div
      class="flex-none mb-4 border-b"
      :style="{ borderColor: 'var(--border-light)' }"
    >
      <p class="text-xs pb-3" :style="{ color: 'var(--text-tertiary)' }">
        {{ description }}
      </p>
    </div>

    <div class="flex-1 flex flex-col min-h-20">
      <!-- 空状态 -->
      <div
        v-if="displayItems.length === 0 && !loading"
        class="flex-1 flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer"
        :style="{
          borderColor: 'var(--border-light)',
          color: 'var(--text-tertiary)'
        }"
        @click="emit('add')"
      >
        <IconifyIconOffline
          icon="ep:star"
          class="text-3xl mb-3"
          :style="{ color: 'var(--text-tertiary)' }"
        />
        <p
          class="text-base font-medium mb-1"
          :style="{ color: 'var(--text-primary)' }"
        >
          暂无自选资产
        </p>
        <p class="text-xs">点击右上角「添加」开始关注资产</p>
      </div>

      <!-- 加载骨架 -->
      <div v-if="loading" class="space-y-3 w-full">
        <div
          v-for="n in 5"
          :key="n"
          class="h-10 rounded-lg animate-pulse"
          :style="{ backgroundColor: 'var(--bg-soft)' }"
        />
      </div>

      <!-- 表格 -->
      <div
        v-if="!loading && displayItems.length > 0"
        class="flex-1 flex flex-col overflow-x-auto"
      >
        <!-- 首页紧凑摘要表：独立于全站 el-table 统一基线（src/style/el-table.css），
             刻意保持原生 table 的轻量紧凑形态，样式留在此组件本地维护，勿改造成 el-table -->
        <table class="w-full text-sm">
          <thead>
            <tr
              class="text-left text-xs border-b"
              :style="{
                color: 'var(--text-tertiary)',
                borderColor: 'var(--border-light)'
              }"
            >
              <th class="pt-2 pb-3 font-normal w-[35%]">产品信息</th>
              <th class="pt-2 pb-3 font-normal text-right">最新价</th>
              <th class="pt-2 pb-3 font-normal text-right">涨跌幅</th>
              <th class="pt-2 pb-3 font-normal text-right">持仓市值</th>
              <th class="pt-2 pb-3 font-normal text-right">操作</th>
            </tr>
          </thead>
          <tbody
            class="divide-y"
            :style="{ borderColor: 'var(--border-light)' }"
          >
            <tr
              v-for="item in displayItems"
              :key="item.id"
              class="table-row-hover cursor-pointer"
              @click="handleItemClick(item)"
            >
              <td class="py-2.5 pr-4">
                <div class="flex items-center gap-2">
                  <!-- 置顶标记 -->
                  <span
                    v-if="item.is_pinned === true"
                    class="text-yellow-500 text-xs shrink-0"
                    title="已置顶"
                  >
                    <IconifyIconOffline icon="ep:star-filled" />
                  </span>

                  <!-- 产品信息 -->
                  <ProductDisplay
                    :name="item.display_name || item.symbol"
                    :symbol="item.symbol"
                    :type-label="item.type_label"
                  />

                  <!-- 基金标识（场外） -->
                  <AssetTypeBadge v-if="item.venue === 'OTC'" type="fund" />
                </div>
              </td>

              <!-- 最新价 -->
              <td class="py-2.5 text-right font-mono font-medium">
                <MoneyDisplay
                  v-if="item.current_price != null"
                  :value="item.current_price"
                  :show-sign="false"
                  :show-currency="false"
                  size="sm"
                />
                <span
                  v-else
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary)' }"
                  >--</span
                >
              </td>

              <!-- 涨跌幅 -->
              <td class="py-2.5 text-right">
                <RiseFallText
                  v-if="item.change_pct != null"
                  :value="item.change_pct"
                  suffix="%"
                  size="sm"
                />
                <span
                  v-else
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary)' }"
                  >--</span
                >
              </td>

              <!-- 持仓市值 -->
              <td class="py-2.5 text-right font-medium">
                <MoneyDisplay
                  v-if="item.position_market_value != null"
                  :value="item.position_market_value"
                  :show-sign="false"
                  size="sm"
                />
                <span
                  v-else
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary)' }"
                  >--</span
                >
              </td>

              <!-- 操作区 -->
              <td class="py-2.5 text-right">
                <div class="flex items-center justify-end gap-1.5">
                  <!-- 统一使用 AssetTypeBadge 替换原有内联标签 -->
                  <AssetTypeBadge
                    v-if="item.status === 'HOLDING'"
                    type="stock"
                    label="持仓"
                    variant="tag"
                  />
                  <AssetTypeBadge
                    v-if="item.venue === 'OTC'"
                    type="fund"
                    variant="tag"
                  />

                  <el-button
                    text
                    size="small"
                    title="快速记账"
                    @click.stop="emit('select', item)"
                  >
                    <IconifyIconOffline icon="ep:edit" class="text-sm" />
                  </el-button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 列表底部：查看全部 -->
        <div v-if="items.length > 10" class="mt-auto text-center pt-2">
          <router-link
            to="/watchlist"
            class="view-all-link text-xs transition-colors"
          >
            还有 {{ items.length - 10 }} 条，查看全部 →
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { getHomeSummary, type HomeSummaryItem } from "@/api/watchlist";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";

const emit = defineEmits<{
  add: [];
  select: [item: HomeSummaryItem];
}>();

const items = ref<HomeSummaryItem[]>([]);
const loading = ref(true);

const hasPinned = computed(() =>
  items.value.some(item => item.is_pinned === true)
);

const displayItems = computed(() => {
  if (hasPinned.value) {
    return items.value.filter(item => item.is_pinned === true);
  }
  return items.value;
});

const description = computed(() => {
  if (items.value.length === 0) return "点击右上角「添加」开始关注你的资产";
  return hasPinned.value
    ? "您置顶的资产，可拖动排序或取消置顶"
    : "当前暂无置顶资产，展示您持仓市值最大的资产（可进入自选页面置顶）";
});

function handleItemClick(item: HomeSummaryItem) {
  emit("select", item);
}

async function fetchData() {
  loading.value = true;
  try {
    const res = await getHomeSummary();
    items.value = res.data ?? [];
  } catch (e) {
    console.error("Failed to fetch home summary:", e);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
defineExpose({ hasPinned });
</script>

<style scoped>
.table-row-hover {
  background-color: var(--bg-card);
  transition: background-color 0.15s ease;
}

.table-row-hover:hover {
  background-color: var(--bg-hover) !important;
}

.view-all-link {
  color: var(--text-tertiary);
}

.view-all-link:hover {
  color: var(--brand-700);
}
</style>
