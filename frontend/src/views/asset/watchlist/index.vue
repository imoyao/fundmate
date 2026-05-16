<template>
  <div class="watchlist-page p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 顶部操作栏 -->
    <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
      <div class="flex items-center gap-4">
        <el-segmented
          v-model="currentView"
          :options="viewOptions"
          @change="handleViewChange"
        />
        <el-input
          v-model="searchKeyword"
          placeholder="搜索当前自选列表..."
          clearable
          class="w-48"
          :prefix-icon="Search"
          @input="debounceSearch"
        />
        <el-tooltip content="在当前自选列表中按代码或名称过滤" placement="top">
          <IconifyIconOffline icon="ep:info-filled" class="text-gray-400 text-sm cursor-help"/>
        </el-tooltip>
      </div>
      <div class="flex items-center gap-2">
        <el-button type="primary" @click="showAddModal = true">
          <IconifyIconOffline icon="ep:plus" class="mr-1"/>
          添加自选
        </el-button>
        <el-button @click="fetchData">
          <IconifyIconOffline icon="ep:refresh"/>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 主区域：分组 + 表格 -->
    <div class="flex gap-6">
      <!-- 左侧分组树 -->
      <div class="w-56 shrink-0 bg-white rounded-2xl shadow-sm border border-gray-100 p-4 h-fit">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-bold text-gray-700">分组</h3>
          <button class="text-xs text-gray-400 hover:text-[#a6a6d2]" @click="handleAddGroup">
            <IconifyIconOffline icon="ep:plus"/>
          </button>
        </div>
        <div class="space-y-1">
          <div
            v-for="group in allGroups"
            :key="group.key"
            class="flex items-center justify-between px-3 py-1.5 rounded-lg text-sm cursor-pointer"
            :class="activeGroup === group.key ? 'bg-[#f0eef8] text-[#a6a6d2] font-medium' : 'text-gray-600 hover:bg-gray-50'"
            @click="activeGroup = group.key"
          >
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: group.color }"/>
              <span>{{ group.label }}</span>
            </div>
            <span class="text-xs text-gray-400">{{ group.count }}</span>
          </div>
        </div>
      </div>

      <!-- 右侧表格 -->
      <div class="flex-1 bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <div class="flex items-center justify-between mb-4">
          <p class="text-xs text-gray-400">
            {{ activeGroupLabel }} · {{ totalItems }} 项
          </p>
          <el-button text size="small" @click="resetFilters">重置筛选</el-button>
        </div>

        <el-table
          v-loading="loading"
          :data="items"
          stripe
          size="default"
          :row-style="{ height: '60px' }"
          @row-click="handleRowClick"
        >

          <!-- 标记列：置顶 + 特别关注 -->
          <el-table-column width="50" align="center" class-name="marker-column">
            <template #default="{ row }">
              <div class="flex items-center justify-center gap-0.5">
              <span v-if="row.is_pinned" class="text-yellow-500" title="已置顶">
                <IconifyIconOffline icon="mdi:pin-outline" class="text-sm"/>
              </span>
                <span v-if="row.bookmarked" class="text-purple-400" title="特别关注">
                <IconifyIconOffline icon="ep:star" class="text-sm"/>
              </span>
              </div>
            </template>
          </el-table-column>

          <!-- 代码/名称列 -->
          <el-table-column label="代码/名称" min-width="180">
            <!-- 置顶、特别关注标记 -->
            <template #default="{ row }">
              <div>
                <p class="font-medium text-gray-800">{{ row.display_name || row.symbol }}</p>
                <p class="text-xs text-gray-400 font-mono">{{ row.symbol }}</p>
                <!-- 标签区域 -->
                <div v-if="row.tag_ids && row.tag_ids.length > 0" class="flex flex-wrap gap-1 mt-1">
                  <TransitionGroup name="tag-fade" tag="div" class="flex flex-wrap gap-1 mt-1">
                    <el-tag
                      v-for="tagId in row.tag_ids.slice(0, 3)"
                      :key="tagId"
                      size="small"
                      class="text-[10px] px-1.5 py-0.5 rounded border-none"
                      :style="{
                      backgroundColor: getTagColor(tagId) + '20',
                      color: '#333333',  // 深色文字
                      border: '1px solid ' + getTagColor(tagId)
                    }"
                    >
                      {{ getTagName(tagId) }}
                    </el-tag>
                    <el-tooltip
                      v-if="row.tag_ids.length > 3"
                      content="点击查看全部标签"
                      placement="top"
                    >
                      <span class="text-xs text-gray-400 mt-0.5 cursor-pointer">+{{ row.tag_ids.length - 3 }}</span>
                    </el-tooltip>
                  </TransitionGroup>
                </div>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="current_price" label="最新价" width="100" align="right">
            <template #default="{ row }">
              {{ row.current_price != null ? row.current_price.toFixed(2) : '--' }}
            </template>
          </el-table-column>
          <el-table-column prop="change_pct" label="涨跌幅" width="90" align="right">
            <template #default="{ row }">
              <span
                v-if="row.change_pct != null"
                :class="row.change_pct >= 0 ? 'text-red-500' : 'text-green-500'"
              >
                {{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct.toFixed(2) }}%
              </span>
              <span v-else>--</span>
            </template>
          </el-table-column>
          <el-table-column prop="position_market_value" label="持仓市值" width="120" align="right">
            <template #default="{ row }">
              {{ row.position_market_value != null ? row.position_market_value.toLocaleString() : '--' }}
            </template>
          </el-table-column>

          <el-table-column label="操作" width="120" align="center" fixed="right">
            <template #default="{ row }">
              <el-tooltip :content="row.is_pinned ? '取消置顶' : '置顶'" placement="top">
                <el-button circle size="small" @click.stop="handleTogglePin(row)">
                  <IconifyIconOffline :icon="row.is_pinned ? 'mdi:pin' : 'mdi:pin-outline'"/>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="row.bookmarked ? '取消特别关注' : '特别关注'" placement="top">
                <el-button circle size="small" @click.stop="handleToggleBookmark(row)">
                  <IconifyIconOffline :icon="row.bookmarked ? 'ep:star-filled' : 'ep:star'"/>
                </el-button>
              </el-tooltip>
              <el-tooltip
                :content="row.status === 'HOLDING' ? '持仓资产无法直接从自选移除' : '移除'"
                placement="top"
              >
                <el-button
                  circle
                  size="small"
                  type="danger"
                  :disabled="row.status === 'HOLDING'"
                  @click.stop="confirmRemove(row)"
                >
                  <IconifyIconOffline icon="ep:delete"/>
                </el-button>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>

        <div class="flex justify-end mt-4">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="totalItems"
            layout="prev, pager, next"
            small
            background
            @current-change="fetchData"
          />
        </div>
      </div>
    </div>

    <!-- 添加自选弹窗 -->
    <AddToWatchlistModal v-model="showAddModal" :initial-group-id="activeCustomGroupId" @submitted="onItemAdded"/>

    <!-- 新建分组弹窗 -->
    <el-dialog v-model="showGroupDialog" title="新建分组" width="320px">
      <el-input v-model="newGroupName" placeholder="分组名称"/>
      <template #footer>
        <el-button @click="showGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="createGroup">确定</el-button>
      </template>
    </el-dialog>

    <!-- 移除确认对话框 -->
    <el-dialog v-model="removeDialogVisible" title="移除自选" width="400px">
      <p>确定要移除 <strong>{{ removingItem?.display_name || removingItem?.symbol }}</strong> 吗？</p>
      <div v-if="removingItem && removingItem.group_ids && removingItem.group_ids.length > 0" class="mt-4">
        <el-radio-group v-model="removeScope">
          <el-radio value="all">从所有分组移除并删除</el-radio>
          <el-radio value="current" :disabled="!currentIsCustom">仅从当前分组移除</el-radio>
        </el-radio-group>
      </div>
      <template #footer>
        <el-button @click="removeDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="executeRemove">确定</el-button>
      </template>
    </el-dialog>

    <!-- 添加自选弹窗 -->
    <AddToWatchlistModal v-model="showAddModal" :initial-group-id="activeCustomGroupId" @submitted="onItemAdded"/>
  </div>
</template>

<script setup lang="ts">
import {ref, computed, onMounted, watch} from "vue";
import {Search} from "@element-plus/icons-vue";
import {Icon as IconifyIconOffline} from "@iconify/vue";
import {ElMessage, ElMessageBox} from "element-plus";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import {
  getWatchlistItems,
  getWatchlistGroups,
  createWatchlistGroup,
  updateWatchlistItem,
  deleteWatchlistItem,
  removeItemFromGroup,
  getWatchlistTags,
  type WatchlistItem,
  type WatchlistGroup,
  type WatchlistTag
} from "@/api/watchlist";

defineOptions({name: "Watchlist"});

// ── 视图 ──
const currentView = ref("all");
const viewOptions = [
  {label: "全部", value: "all"},
  {label: "场内", value: "exchange"},
  {label: "场外", value: "otc"},
];

const allTags = ref<WatchlistTag[]>([]);

// ── 分组 ──
const activeGroup = ref("holding");
const customGroups = ref<WatchlistGroup[]>([]);


// 系统分组定义（包括"全部"）
const systemGroups = [
  {key: "all", label: "全部", color: "#999", filter: {}},
  {key: "holding", label: "持仓", color: "#ff4d4f", filter: {status: "HOLDING"}},
  {key: "watching", label: "观察中", color: "#52c41a", filter: {status: "WATCHING"}},
  {key: "cleared", label: "已清仓", color: "#fa8c16", filter: {cleared: true}},
  {key: "exchange", label: "场内资产", color: "#1890ff", filter: {venue: "EXCHANGE"}},
  {key: "otc", label: "场外基金", color: "#722ed1", filter: {venue: "OTC"}},
  {key: "bookmarked", label: "特别关注", color: "#a6a6d2", filter: {bookmarked: true}},
];

const activeGroupLabel = computed(() => {
  const group = allGroups.value.find(g => g.key === activeGroup.value);
  return group?.label || "全部";
});


// ── 表格数据 ──
const items = ref<WatchlistItem[]>([]);
const loading = ref(false);
const searchKeyword = ref("");
const currentPage = ref(1);
const pageSize = ref(20);
const totalItems = ref(0);

// 请求参数
// src/views/asset/watchlist/index.vue 中的 fetchParams 部分
const fetchParams = computed(() => {
  const params: Record<string, any> = {
    page: currentPage.value,
    per_page: pageSize.value,
  };

  const groupKey = activeGroup.value;

  // 处理自定义分组（key 为 custom_xxx）
  if (groupKey.startsWith("custom_")) {
    const groupId = parseInt(groupKey.replace("custom_", ""));
    params.group_id = groupId;
  } else {
    // 系统分组
    const group = systemGroups.find((g) => g.key === groupKey);
    if (group && group.filter) {
      Object.entries(group.filter).forEach(([k, v]) => {
        if (k === "cleared") {
          params.status = "cleared"; // 传递特殊参数给后端
        } else {
          params[k] = v;
        }
      });
    }
  }

  // 视图筛选
  if (currentView.value === "exchange") {
    params.venue = "EXCHANGE";
  } else if (currentView.value === "otc") {
    params.venue = "OTC";
  }

  if (searchKeyword.value) {
    params.q = searchKeyword.value;
  }

  return params;
});

function getGroupCount(key: string): number {
  // 简略实现，后续可优化
  return 0;
}

async function fetchTags() {
  try {
    const res = await getWatchlistTags();
    allTags.value = (res as any).data ?? [];
  } catch (e) {
    console.error("获取标签失败", e);
  }
}

function getTagName(tagId: number): string {
  return allTags.value.find(t => t.id === tagId)?.name || '';
}

function getTagColor(tagId: number): string {
  return allTags.value.find(t => t.id === tagId)?.color || '#C5C9B8';
}


async function fetchData() {
  loading.value = true;
  try {
    const res = await getWatchlistItems(fetchParams.value);
    items.value = (res as any).data ?? [];
    totalItems.value = (res as any).total ?? items.value.length;
  } catch (e) {
    ElMessage.error("获取自选列表失败");
    console.error(e);
  } finally {
    loading.value = false;
  }
}

// ── 搜索去抖 ──
let searchTimer: number | undefined;

function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    currentPage.value = 1;
    fetchData();
  }, 300);
}

// ── 分组切换 ──
watch(activeGroup, () => {
  currentPage.value = 1;
  fetchData();
});

// ── 视图切换 ──
function handleViewChange(val: string) {
  if (val === "exchange") activeGroup.value = "exchange";
  else if (val === "otc") activeGroup.value = "otc";
  else activeGroup.value = "all";
}

function resetFilters() {
  searchKeyword.value = "";
  activeGroup.value = "all";
  currentView.value = "all";
}

// ── 行操作 ──
async function handleTogglePin(row: WatchlistItem) {
  try {
    await updateWatchlistItem(row.id, {is_pinned: !row.is_pinned});
    ElMessage.success(row.is_pinned ? "已取消置顶" : "已置顶");
    fetchData();
  } catch (e) {
    ElMessage.error("操作失败");
  }
}

async function handleToggleBookmark(row: WatchlistItem) {
  try {
    await updateWatchlistItem(row.id, {bookmarked: !row.bookmarked});
    ElMessage.success(row.bookmarked ? "已取消特别关注" : "已设为特别关注");
    fetchData();
  } catch (e) {
    ElMessage.error("操作失败");
  }
}

function handleRowClick(row: WatchlistItem) {
  // 可扩展
}

// ── 移除自选 ──
const removeDialogVisible = ref(false);
const removingItem = ref<WatchlistItem | null>(null);
const removeScope = ref("all");

const currentIsCustom = computed(() => {
  // 判断当前 activeGroup 是否为自定义分组
  return activeGroup.value.startsWith("custom_");
});

const activeCustomGroupId = computed(() => {
  if (activeGroup.value.startsWith("custom_")) {
    return parseInt(activeGroup.value.replace("custom_", ""));
  }
  return undefined;
});

function confirmRemove(row: WatchlistItem) {
  removingItem.value = row;
  removeScope.value = "all";
  removeDialogVisible.value = true;
}

async function executeRemove() {
  const item = removingItem.value;
  if (!item) return;
  try {
    if (removeScope.value === "current" && activeCustomGroupId.value) {
      // 仅从当前分组移除
      await removeItemFromGroup(item.id, activeCustomGroupId.value);
      ElMessage.success("已从当前分组移除");
    } else {
      // 从所有分组删除自选
      await deleteWatchlistItem(item.id);
      ElMessage.success("已移除自选");
    }
    removeDialogVisible.value = false;
    fetchData();
  } catch (e) {
    ElMessage.error("操作失败");
  }
}

// ── 添加自选弹窗 ──
const showAddModal = ref(false);

function onItemAdded() {
  showAddModal.value = false;
  fetchData();
  fetchTags();
}

// ── 自定义分组 ──
const showGroupDialog = ref(false);
const newGroupName = ref("");

function handleAddGroup() {
  showGroupDialog.value = true;
  newGroupName.value = "";
}

async function createGroup() {
  if (!newGroupName.value.trim()) return;
  try {
    await createWatchlistGroup({name: newGroupName.value.trim()});
    ElMessage.success("分组已创建");
    showGroupDialog.value = false;
    fetchGroups();
  } catch (e) {
    ElMessage.error("创建分组失败");
  }
}

const allGroups = ref<any[]>([]);

async function fetchGroups() {
  try {
    const res = await getWatchlistGroups();
    const data: WatchlistGroup[] = (res as any).data ?? [];

    // 分离系统分组和自定义分组
    const system: any[] = [];
    const custom: WatchlistGroup[] = [];

    data.forEach((g) => {
      if (g.is_system) {
        system.push({
          key: g.key!,
          label: g.label || g.name || g.key,
          color: g.color,
          count: g.count,
          filter: getSystemFilter(g.key!),  // 根据 key 生成筛选条件
        });
      } else {
        custom.push(g);
        // 同时加入 allGroups，key 为 custom_{id}
        system.push({
          key: `custom_${g.id}`,
          label: g.name,
          color: g.color,
          count: g.count,
          filter: {group_id: g.id},
        });
      }
    });

    allGroups.value = system;
    customGroups.value = custom;
  } catch (e) {
    console.error("获取分组失败", e);
  }
}

// 辅助函数：根据系统分组 key 生成筛选条件
function getSystemFilter(key: string): Record<string, any> {
  const map: Record<string, Record<string, any>> = {
    all: {},
    holding: {status: 'HOLDING'},
    watching: {status: 'WATCHING'},
    cleared: {status: 'cleared'},
    exchange: {venue: 'EXCHANGE'},
    otc: {venue: 'OTC'},
    bookmarked: {bookmarked: true},
  };
  return map[key] || {};
}

onMounted(() => {
  fetchGroups();
  fetchTags();
  fetchData();
});
</script>
<style>
.marker-column .cell {
  padding: 0 !important;
}

.tag-fade-enter-active,
.tag-fade-leave-active {
  transition: all 0.3s ease;
}
.tag-fade-enter-from,
.tag-fade-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}
</style>
