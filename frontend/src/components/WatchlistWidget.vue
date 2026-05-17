<template>
  <div class="watchlist-widget bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
    <!-- 头部 -->
    <div class="flex justify-between items-center mb-3">
      <h3 class="text-gray-800 font-bold">{{ tableTitle }}</h3>
      <div class="flex items-center gap-3">
        <button
          class="text-xs text-gray-400 hover:text-[#a6a6d2] transition-colors flex items-center gap-1"
          @click="emit('add')"
        >
          <IconifyIconOffline icon="ep:plus" class="text-base"/>
          添加
        </button>
        <router-link to="/the-road-not-taken" class="text-xs text-purple-400 hover:text-purple-600 ml-3">
          特别关注
        </router-link>
        <router-link
          to="/watchlist"
          class="text-xs text-gray-400 hover:text-[#a6a6d2] transition-colors"
        >
          查看全部
          <IconifyIconOffline icon="ep:arrow-right" class="ml-1 text-[10px]"/>
        </router-link>
      </div>
    </div>

    <!-- 说明文案 -->
    <p class="text-xs text-gray-400 mb-4">{{ description }}</p>

    <!-- 空状态 -->
    <div
      v-if="displayItems.length === 0 && !loading"
      class="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center text-gray-400 hover:border-[#a6a6d2] hover:text-[#a6a6d2] transition-all cursor-pointer"
      @click="emit('add')"
    >
      <IconifyIconOffline icon="ep:star" class="text-3xl mb-3 text-[#D4C5C7]"/>
      <p class="text-base font-medium mb-1">暂无自选资产</p>
      <p class="text-xs">点击此处或右上角「添加」按钮，开始关注资产</p>
    </div>

    <!-- 加载骨架 -->
    <div v-if="loading" class="space-y-3">
      <div v-for="n in 5" :key="n" class="h-10 bg-gray-100 rounded-lg animate-pulse"/>
    </div>

    <!-- 表格列表 -->
    <div v-if="!loading && displayItems.length > 0" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
        <tr class="text-left text-gray-400 text-xs border-b border-gray-100">
          <th class="pb-2 font-normal">代码/名称</th>
          <th class="pb-2 font-normal text-right">最新价</th>
          <th class="pb-2 font-normal text-right">涨跌幅</th>
          <th class="pb-2 font-normal text-right">持仓市值</th>
          <th class="pb-2 font-normal text-right">操作</th>
        </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
        <tr
          v-for="item in displayItems"
          :key="item.id"
          class="hover:bg-[#f5f7fa] transition-colors cursor-pointer"
          @click="handleItemClick(item)"
        >
          <td class="py-2.5 pr-4">
            <div class="flex items-center gap-2">
                <span v-if="item.is_pinned" class="text-yellow-500 text-xs" title="已置顶">
                  <IconifyIconOffline icon="ep:star-filled"/>
                </span>
              <div>
                <p class="font-medium text-gray-800 truncate max-w-[120px]">{{ item.display_name || item.symbol }}</p>
                <p class="text-xs text-gray-400 font-mono">{{ item.symbol }}</p>
              </div>
            </div>
          </td>
          <td class="py-2.5 text-right font-mono font-medium text-gray-800">
            {{ item.current_price != null ? item.current_price.toFixed(2) : '--' }}
          </td>
          <td class="py-2.5 text-right">
              <span
                v-if="item.change_pct != null"
                :class="[
                  'text-xs font-bold',
                  item.change_pct >= 0 ? 'text-red-500' : 'text-green-500'
                ]"
              >
                <IconifyIconOffline
                  :icon="item.change_pct >= 0 ? 'ep:caret-top' : 'ep:caret-bottom'"
                  class="mr-0.5 text-[10px]"
                />
                {{ Math.abs(item.change_pct).toFixed(2) }}%
              </span>
            <span v-else class="text-xs text-gray-400">--</span>
          </td>
          <td class="py-2.5 text-right text-gray-700 font-medium">
            {{ item.position_market_value != null ? item.position_market_value.toLocaleString() : '--' }}
          </td>
          <td class="py-2.5 text-right">
            <div class="flex items-center justify-end gap-1.5">
                <span
                  v-if="item.status === 'HOLDING'"
                  class="px-1.5 py-0.5 bg-red-50 text-red-400 text-[10px] rounded"
                >
                  持仓
                </span>
              <span
                v-if="item.venue === 'OTC'"
                class="px-1.5 py-0.5 bg-gray-50 text-gray-400 text-[10px] rounded"
              >
                  场外
                </span>
              <button
                class="p-1 rounded-full text-gray-300 hover:text-[#a6a6d2] hover:bg-gray-100 transition-colors"
                title="快速记账"
                @click.stop="emit('select', item)"
              >
                <IconifyIconOffline icon="ep:edit" class="text-xs"/>
              </button>
            </div>
          </td>
        </tr>
        </tbody>
      </table>
      <!-- 如果有超过10条，显示提示 -->
      <div v-if="items.length > 10" class="text-center mt-3">
        <router-link
          to="/watchlist"
          class="text-xs text-gray-400 hover:text-[#a6a6d2] transition-colors"
        >
          还有 {{ items.length - 10 }} 条，查看全部 →
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {ref, computed, onMounted} from "vue";
import {Icon as IconifyIconOffline} from "@iconify/vue";
import {getHomeSummary, type HomeSummaryItem} from "@/api/watchlist";

const emit = defineEmits<{
  add: [];
  select: [item: HomeSummaryItem];
}>();

const items = ref<HomeSummaryItem[]>([]);
const loading = ref(true);

const displayItems = computed(() => items.value);

const tableTitle = computed(() => {
  if (items.value.length === 0) return "自选资产";
  const hasPinned = items.value.some(i => i.is_pinned);
  return hasPinned ? "置顶资产" : "持仓市值最大资产";
});

const description = computed(() => {
  if (items.value.length === 0) return "点击右上角「添加」开始关注你的资产";
  const hasPinned = items.value.some(i => i.is_pinned);
  return hasPinned
    ? "您置顶的资产，可拖动排序或取消置顶"
    : "当前暂无置顶资产，展示您持仓市值最大的资产（可进入自选页面置顶）";
});

function handleItemClick(item: HomeSummaryItem) {
  emit('select', item);
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
</script>


<style scoped>
/* 保持简洁风格 */
</style>
