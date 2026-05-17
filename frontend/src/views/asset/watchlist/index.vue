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
        <el-button @click="exportData">
          <IconifyIconOffline icon="ep:download" class="mr-1"/>
          导出
        </el-button>
        <el-button @click="showTagManager = true">
          <IconifyIconOffline icon="ep:setting" class="mr-1" />
          管理标签
        </el-button>
        <el-button @click="fetchData">
          <IconifyIconOffline icon="ep:refresh"/>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 主区域：分组 + 表格 -->
    <div class="flex gap-6 flex-wrap">
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
      <div class="flex-1 min-w-[600px] bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
        <!-- 修复标签筛选跨行问题：重构布局为flex-wrap -->
        <div class="flex flex-wrap items-center justify-between mb-4 gap-2">
          <p class="text-xs text-gray-400 shrink-0">
            {{ activeGroupLabel }} · {{ totalItems }} 项
          </p>
          <!-- 标签筛选器：优化布局 -->
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-xs text-gray-400 shrink-0">标签筛选：</span>
            <el-select
              v-model="selectedFilterTagIds"
              multiple
              filterable
              clearable
              placeholder="选择标签"
              size="small"
              class="w-56 min-w-[180px]"
              @change="handleTagFilterChange"
            >
              <el-option
                v-for="tag in allTags"
                :key="tag.id"
                :label="tag.name"
                :value="tag.id"
              >
                <div class="flex items-center gap-2">
                  <span class="w-3 h-3 rounded-full" :style="{ backgroundColor: tag.color || '#C5C9B8' }"></span>
                  <span>{{ tag.name }}</span>
                </div>
              </el-option>
            </el-select>
          </div>
        </div>
        <el-button text size="small" @click="resetFilters">重置筛选</el-button>

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
                <span v-if="row.favorite" class="text-purple-400" title="特别关注">
                  <IconifyIconOffline icon="ep:star" class="text-sm"/>
                </span>
              </div>
            </template>
          </el-table-column>
          <!-- 代码/名称列 -->
            <el-table-column label="代码/名称" min-width="180">
              <template #default="{ row }">
                <div>
                  <p class="font-medium text-gray-800">{{ row.display_name || row.symbol }}</p>
                  <p class="text-xs text-gray-400 font-mono">{{ row.symbol }}</p>
                  <!-- 标签区域：始终显示添加按钮 -->
                  <div class="flex flex-wrap gap-1 mt-1">
                    <!-- 已有标签列表 -->
                    <template v-if="row.tag_ids && row.tag_ids.length > 0">
                      <TransitionGroup name="tag-fade" tag="div" class="flex flex-wrap gap-1 mt-1">
                        <el-tag
                          v-for="tagId in row.tag_ids.slice(0, 3)"
                          :key="tagId"
                          size="small"
                          class="text-[10px] px-1.5 py-0.5 rounded border-none"
                          :style="{
                            backgroundColor: getTagColor(tagId) + '20',
                            color: '#333333',
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
                    </template>
                    <!-- 添加/编辑标签按钮（始终可见） -->
                    <el-tooltip content="添加/编辑标签" placement="top">
                      <el-button
                        circle
                        size="small"
                        class="add-tag-btn"
                        @click.stop="openTagEditor(row)"
                      >
                        <IconifyIconOffline icon="ep:plus" class="text-xs" />
                      </el-button>
                    </el-tooltip>
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
              <el-tooltip :content="row.favorite ? '取消特别关注' : '特别关注'" placement="top">
          <el-button circle size="small" @click.stop="handleToggleFavorite(row)">
            <IconifyIconOffline :icon="row.favorite ? 'ep:star-filled' : 'ep:star'" />
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

    <!-- 弹窗组件：按功能归类 -->
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

    <!-- 标签管理对话框：修复编辑功能 -->
    <el-dialog v-model="showTagManager" title="管理标签" width="500px">
      <div class="space-y-4">
        <!-- 标签列表：使用可搜索多选 Select -->
        <el-select
          v-model="selectedTagIdsForManager"
          multiple
          filterable
          placeholder="选择标签进行编辑或删除"
          class="w-full"
          size="small"
        >
          <el-option
            v-for="tag in allTags"
            :key="tag.id"
            :label="tag.name"
            :value="tag.id"
          >
            <div class="flex items-center justify-between w-full">
              <div class="flex items-center gap-2">
                <span
                  class="w-4 h-4 rounded-full"
                  :style="{ backgroundColor: editingTagId === tag.id ? editTagColor : (tag.color || '#C5C9B8') }"
                ></span>
                <!-- 编辑状态显示输入框 -->
                <template v-if="editingTagId === tag.id">
                  <el-input
                    v-model="editTagName"
                    size="small"
                    class="w-20"
                    @blur="saveEditTag(tag.id)"
                    @keyup.enter="saveEditTag(tag.id)"
                  />
                </template>
                <span v-else>{{ tag.name }}</span>
              </div>
              <div class="flex gap-1" @click.stop>
                <el-button link size="small" @click="startEditTag(tag)">
                  {{ editingTagId === tag.id ? '保存' : '编辑' }}
                </el-button>
                <el-popconfirm title="确定删除？" @confirm="deleteTag(tag.id)">
                  <template #reference>
                    <el-button link size="small" type="danger" :disabled="usedTagIds.has(tag.id)">
                      删除
                    </el-button>
                  </template>
                </el-popconfirm>
              </div>
            </div>
          </el-option>
        </el-select>

        <!-- 新建标签区域 -->
        <div class="flex items-end gap-2 mt-4">
          <el-input v-model="newTagNameInManager" placeholder="新标签名" size="small" class="w-24" />
          <div class="flex gap-1">
            <button v-for="c in presetColors" :key="c"
              class="w-5 h-5 rounded-full border-2 transition-colors cursor-pointer"
              :class="newTagColorInManager === c ? 'border-gray-800 scale-110' : 'border-transparent'"
              :style="{ backgroundColor: c }"
              @click="newTagColorInManager = c" />
          </div>
          <el-button type="primary" size="small" @click="addNewTagInManager">添加</el-button>
        </div>

        <!-- 编辑标签颜色选择器（新增） -->
        <div v-if="editingTagId" class="flex items-end gap-2 mt-2">
          <span class="text-xs text-gray-500">修改标签颜色：</span>
          <div class="flex gap-1">
            <button v-for="c in presetColors" :key="c"
              class="w-5 h-5 rounded-full border-2 transition-colors cursor-pointer"
              :class="editTagColor === c ? 'border-gray-800 scale-110' : 'border-transparent'"
              :style="{ backgroundColor: c }"
              @click="editTagColor = c" />
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showTagManager = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 行内标签编辑弹窗 -->
    <el-dialog v-model="showTagEditor" title="编辑标签" width="420px">
      <div class="mb-4">
        <span class="text-sm text-gray-500">
          为 <strong>{{ editingItem?.display_name || editingItem?.symbol }}</strong> 添加或移除标签
        </span>
      </div>

      <!-- 已有标签 -->
      <div v-if="editingItem && editingItem.tag_ids.length > 0" class="mb-4">
        <span class="text-xs text-gray-400 mb-2 block">已有标签</span>
        <div class="flex flex-wrap gap-2">
          <el-tag
            v-for="tagId in editingItem.tag_ids"
            :key="tagId"
            size="small"
            closable
            :style="{
              backgroundColor: getTagColor(tagId) + '20',
              color: '#333333',
              border: '1px solid ' + getTagColor(tagId)
            }"
            @close="removeTagFromEditingItem(tagId)"
          >
            {{ getTagName(tagId) }}
          </el-tag>
        </div>
      </div>

      <!-- 添加标签选择器 -->
      <div class="mb-4">
        <span class="text-xs text-gray-400 mb-2 block">添加标签</span>
        <div class="flex gap-2">
          <el-select
            v-model="editingItemNewTagIds"
            multiple
            filterable
            placeholder="选择标签"
            class="flex-1"
            size="small"
          >
            <el-option
              v-for="tag in availableTagsForEditor"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full" :style="{ backgroundColor: tag.color || '#C5C9B8' }"></span>
                <span>{{ tag.name }}</span>
              </div>
            </el-option>
          </el-select>
          <el-button size="small" @click="showNewTagFormInEditor = true">
            <IconifyIconOffline icon="ep:plus" />
          </el-button>
        </div>

        <!-- 新建标签（内联） -->
        <div v-if="showNewTagFormInEditor" class="mt-2 p-3 bg-gray-50 rounded-lg flex items-end gap-2">
          <el-input v-model="newTagNameInEditor" placeholder="标签名" size="small" class="w-24" />
          <div class="flex gap-1">
            <button
              v-for="c in presetColors"
              :key="c"
              class="w-5 h-5 rounded-full border-2 transition-colors cursor-pointer"
              :class="newTagColorInEditor === c ? 'border-gray-800 scale-110' : 'border-transparent'"
              :style="{ backgroundColor: c }"
              @click="newTagColorInEditor = c"
            />
          </div>
          <el-button type="primary" size="small" @click="createTagInEditor">确定</el-button>
          <el-button size="small" @click="showNewTagFormInEditor = false">取消</el-button>
        </div>
      </div>

      <template #footer>
        <el-button @click="showTagEditor = false">取消</el-button>
        <el-button type="primary" :loading="savingTags" @click="saveTagChanges">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from "vue";
import { Search } from "@element-plus/icons-vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { ElMessage } from "element-plus";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import {
  getWatchlistItems,
  getWatchlistGroups,
  createWatchlistGroup,
  updateWatchlistItem,
  deleteWatchlistItem,
  removeItemFromGroup,
  getWatchlistTags,
  updateWatchlistTag,
  deleteWatchlistTag,
  addTagToItem,
  removeTagFromItem,
  createWatchlistTag,
  type WatchlistItem,
  type WatchlistGroup,
  type WatchlistTag
} from "@/api/watchlist";

defineOptions({ name: "Watchlist" });

// ─────────────────────────────────────────────
// 基础配置
// ─────────────────────────────────────────────
// 视图切换配置
const currentView = ref("all");
const viewOptions = [
  { label: "全部", value: "all" },
  { label: "场内", value: "exchange" },
  { label: "场外", value: "otc" },
];

// 系统分组配置（莫兰迪配色）
const systemGroups = [
  { key: "all", label: "全部", color: "#949599", filter: {} },
  { key: "holding", label: "持仓", color: "#e07a5f", filter: { status: "HOLDING" } },
  { key: "watching", label: "观察中", color: "#81b29a", filter: { status: "WATCHING" } },
  { key: "cleared", label: "已清仓", color: "#f2cc8f", filter: { cleared: true } },
  { key: "exchange", label: "场内资产", color: "#819cd1", filter: { venue: "EXCHANGE" } },
  { key: "otc", label: "场外基金", color: "#9d81a9", filter: { venue: "OTC" } },
  { key: "favorite", label: "特别关注", color: "#a89f94", filter: { favorite: true } },
];

// 标签预设颜色
const presetColors = ["#B8A99A", "#9CAF88", "#8DA3B8", "#C4A0A8", "#9B9EB0", "#B6B09C"];

// ─────────────────────────────────────────────
// 响应式数据
// ─────────────────────────────────────────────
// 分组相关
const activeGroup = ref("holding");
const allGroups = ref<any[]>([]);
const customGroups = ref<WatchlistGroup[]>([]);

// 表格相关
const items = ref<WatchlistItem[]>([]);
const loading = ref(false);
const searchKeyword = ref("");
const currentPage = ref(1);
const pageSize = ref(20);
const totalItems = ref(0);

// 标签相关
const allTags = ref<WatchlistTag[]>([]);
const selectedFilterTagIds = ref<number[]>([]);
const showTagManager = ref(false);
const editingTagId = ref<number | null>(null);
const editTagName = ref("");
const editTagColor = ref("#B6B09C");
const selectedTagIdsForManager = ref<number[]>([]); // 新增：管理弹窗选中的标签ID

// 弹窗相关
const showAddModal = ref(false);
const showGroupDialog = ref(false);
const newGroupName = ref("");
const removeDialogVisible = ref(false);
const removingItem = ref<WatchlistItem | null>(null);
const removeScope = ref("all");

// 标签编辑弹窗状态
const showTagEditor = ref(false);
const editingItem = ref<WatchlistItem | null>(null);
const editingItemNewTagIds = ref<number[]>([]);
const savingTags = ref(false);
const showNewTagFormInEditor = ref(false);
const newTagNameInEditor = ref("");
const newTagColorInEditor = ref("#B6B09C");

// 编辑器可用标签（排除已绑定的）
const availableTagsForEditor = computed(() => {
  if (!editingItem.value) return allTags.value;
  const existingIds = new Set(editingItem.value.tag_ids);
  return allTags.value.filter(t => !existingIds.has(t.id));
});

// 打开标签编辑器
const openTagEditor = (row: WatchlistItem) => {
  editingItem.value = row;
  editingItemNewTagIds.value = [];
  showNewTagFormInEditor.value = false;
  showTagEditor.value = true;
};

// 管理弹窗新建标签专用变量
const newTagNameInManager = ref("");
const newTagColorInManager = ref("#B6B09C");
const showNewTagFormInManager = ref(false);  // 如果保留折叠设计

// 管理弹窗中新建标签
const addNewTagInManager = async () => {
  if (!newTagNameInManager.value.trim()) return;
  try {
    const res = await createWatchlistTag({
      name: newTagNameInManager.value.trim(),
      color: newTagColorInManager.value,
    });
    const newTag = (res as any).data;
    allTags.value.push({ id: newTag.id, name: newTag.name, color: newTag.color || newTagColorInManager.value });
    newTagNameInManager.value = "";
    newTagColorInManager.value = "#B6B09C";
    ElMessage.success(`标签「${newTag.name}」已创建`);
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning("该标签已存在");
    } else {
      ElMessage.error("创建标签失败");
    }
  }
};

// 在编辑器中移除标签（直接从当前资产解绑）
const removeTagFromEditingItem = async (tagId: number) => {
  if (!editingItem.value) return;
  try {
    await removeTagFromItem(editingItem.value.id, tagId);
    // 更新本地数据
    editingItem.value.tag_ids = editingItem.value.tag_ids.filter(id => id !== tagId);
    ElMessage.success("标签已移除");
  } catch (e) {
    ElMessage.error("移除标签失败");
  }
};

// 在编辑器中新建标签
const createTagInEditor = async () => {
  if (!newTagNameInEditor.value.trim()) return;
  try {
    const res = await createWatchlistTag({
      name: newTagNameInEditor.value.trim(),
      color: newTagColorInEditor.value
    });
    const newTag = (res as any).data;
    allTags.value.push({ id: newTag.id, name: newTag.name, color: newTag.color || newTagColorInEditor.value });
    editingItemNewTagIds.value.push(newTag.id);
    showNewTagFormInEditor.value = false;
    newTagNameInEditor.value = "";
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning("该标签已存在");
    } else {
      ElMessage.error("创建标签失败");
    }
  }
};

// 保存标签更改（批量添加）
const saveTagChanges = async () => {
  if (!editingItem.value) return;
  savingTags.value = true;
  try {
    const itemId = editingItem.value.id;
    for (const tagId of editingItemNewTagIds.value) {
      await addTagToItem(itemId, tagId);
    }
    ElMessage.success("标签已更新");
    showTagEditor.value = false;
    // 刷新列表
    await fetchData();
    await fetchTags();
  } catch (e) {
    ElMessage.error("保存标签失败");
  } finally {
    savingTags.value = false;
  }
};

// ─────────────────────────────────────────────
// 计算属性
// ─────────────────────────────────────────────
// 当前分组名称
const activeGroupLabel = computed(() => {
  const group = allGroups.value.find(g => g.key === activeGroup.value);
  return group?.label || "全部";
});

// 是否为自定义分组
const currentIsCustom = computed(() => {
  return activeGroup.value.startsWith("custom_");
});

// 当前自定义分组ID
const activeCustomGroupId = computed(() => {
  if (currentIsCustom.value) {
    const idStr = activeGroup.value.replace("custom_", "");
    // 增加类型安全检查
    return /^\d+$/.test(idStr) ? parseInt(idStr) : undefined;
  }
  return undefined;
});

// 已使用的标签ID集合
const usedTagIds = computed(() => {
  const ids = new Set<number>();
  if (!Array.isArray(items.value)) return ids;

  items.value.forEach(item => {
    // 确保 tag_ids 存在且是数组
    const tagIds = item?.tag_ids;
    if (Array.isArray(tagIds)) {
      tagIds.forEach(id => {
        // 确保ID是有效数字
        if (typeof id === 'number' && !isNaN(id)) {
          ids.add(id);
        }
      });
    }
  });
  return ids;
});

// 请求参数
const fetchParams = computed(() => {
  const params: Record<string, any> = {
    page: currentPage.value,
    per_page: pageSize.value,
  };

  // 标签筛选
  if (selectedFilterTagIds.value.length > 0) {
    params.tag_ids = selectedFilterTagIds.value.join(',');
  }

  // 分组筛选
  const groupKey = activeGroup.value;
  if (groupKey.startsWith("custom_")) {
    const groupId = activeCustomGroupId.value;
    if (groupId) params.group_id = groupId;
  } else {
    const group = systemGroups.find(g => g.key === groupKey);
    if (group && group.filter) {
      Object.entries(group.filter).forEach(([k, v]) => {
        params[k === "cleared" ? "status" : k] = k === "cleared" ? "cleared" : v;
      });
    }
  }

  // 视图筛选
  if (currentView.value === "exchange") params.venue = "EXCHANGE";
  else if (currentView.value === "otc") params.venue = "OTC";

  // 搜索关键词
  if (searchKeyword.value) params.q = searchKeyword.value;

  return params;
});

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────
// 获取分组数量（占位）
function getGroupCount(key: string): number {
  return 0;
}

// 获取标签名称
function getTagName(tagId: number): string {
  return allTags.value.find(t => t.id === tagId)?.name || '?';
}

function getTagColor(tagId: number): string {
  return allTags.value.find(t => t.id === tagId)?.color || '#d9d9d9';
}
// 根据分组key获取筛选条件
function getSystemFilter(key: string): Record<string, any> {
  const map: Record<string, Record<string, any>> = {
    all: {},
    holding: { status: 'HOLDING' },
    watching: { status: 'WATCHING' },
    cleared: { status: 'cleared' },
    exchange: { venue: 'EXCHANGE' },
    otc: { venue: 'OTC' },
    favorite: { favorite: true },
  };
  return map[key] || {};
}

// 搜索防抖
let searchTimer: number | undefined;
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    currentPage.value = 1;
    fetchData();
  }, 300);
}

// ─────────────────────────────────────────────
// 数据请求
// ─────────────────────────────────────────────
// 获取自选列表
async function fetchData() {
  loading.value = true;
  try {
    const res = await getWatchlistItems(fetchParams.value);
    items.value = (res as any).data ?? [];
    totalItems.value = (res as any).total ?? items.value.length;
  } catch (e) {
    ElMessage.error("获取自选列表失败");
    console.error("获取自选列表错误：", e);
  } finally {
    loading.value = false;
  }
}

// 获取分组列表
async function fetchGroups() {
  try {
    const res = await getWatchlistGroups();
    const data: WatchlistGroup[] = (res as any).data ?? [];
    const system: any[] = [];
    const custom: WatchlistGroup[] = [];

    data.forEach((g) => {
      if (g.is_system) {
        system.push({
          key: g.key!,
          label: g.label || g.name || g.key,
          color: g.color,
          count: g.count || 0, // 确保count有默认值
          filter: getSystemFilter(g.key!),
        });
      } else {
        custom.push(g);
        system.push({
          key: `custom_${g.id}`,
          label: g.name,
          color: g.color || systemGroups[0].color, // 提供默认颜色
          count: g.count || 0,
          filter: { group_id: g.id },
        });
      }
    });

    allGroups.value = system;
    customGroups.value = custom;
  } catch (e) {
    console.error("获取分组失败：", e);
  }
}

// 获取标签列表
async function fetchTags() {
  try {
    const res = await getWatchlistTags();
    allTags.value = (res as any).data ?? [];
  } catch (e) {
    console.error("获取标签失败：", e);
  }
}

// ─────────────────────────────────────────────
// 事件处理
// ─────────────────────────────────────────────
// 视图切换
function handleViewChange(val: string) {
  activeGroup.value = val === "exchange" || val === "otc" ? val : "all";
}

// 标签筛选变化
function handleTagFilterChange() {
  currentPage.value = 1;
  fetchData();
}

// 重置筛选条件
function resetFilters() {
  searchKeyword.value = "";
  activeGroup.value = "holding";
  currentView.value = "all";
  selectedFilterTagIds.value = [];
}

// 行操作：置顶/取消置顶
async function handleTogglePin(row: WatchlistItem) {
  try {
    await updateWatchlistItem(row.id, { is_pinned: !row.is_pinned });
    ElMessage.success(row.is_pinned ? "已取消置顶" : "已置顶");
    fetchData();
  } catch (e) {
    ElMessage.error("置顶操作失败");
    console.error("置顶错误：", e);
  }
}

// 行操作：关注/取消关注
async function handleToggleFavorite(row: WatchlistItem) {
  try {
    await updateWatchlistItem(row.id, { favorite: !row.favorite });
    ElMessage.success(row.favorite ? "已取消特别关注" : "已设为特别关注");
    fetchData();
  } catch (e) {
    ElMessage.error("关注操作失败");
    console.error("关注错误：", e);
  }
}

// 行点击（预留扩展）
function handleRowClick(row: WatchlistItem) {}

// 确认移除自选
function confirmRemove(row: WatchlistItem) {
  removingItem.value = row;
  removeScope.value = "all";
  removeDialogVisible.value = true;
}

// 执行移除操作
async function executeRemove() {
  const item = removingItem.value;
  if (!item) return;

  try {
    if (removeScope.value === "current" && activeCustomGroupId.value) {
      await removeItemFromGroup(item.id, activeCustomGroupId.value);
      ElMessage.success("已从当前分组移除");
    } else {
      await deleteWatchlistItem(item.id);
      ElMessage.success("已移除自选");
    }
    removeDialogVisible.value = false;
    fetchData();
  } catch (e) {
    ElMessage.error("移除操作失败");
    console.error("移除错误：", e);
  }
}

// 导出数据
async function exportData() {
  try {
    const params = new URLSearchParams(fetchParams.value as any).toString();
    window.open(`/api/watchlist/items/export/?${params}`, '_blank');
  } catch (e) {
    ElMessage.error("导出失败");
    console.error("导出错误：", e);
  }
}

// 添加自选成功回调
function onItemAdded() {
  showAddModal.value = false;
  fetchData();
  fetchTags();
}

// 打开新建分组弹窗
function handleAddGroup() {
  showGroupDialog.value = true;
  newGroupName.value = "";
}

// 创建分组
async function createGroup() {
  const groupName = newGroupName.value.trim();
  if (!groupName) {
    ElMessage.warning("请输入分组名称");
    return;
  }

  try {
    await createWatchlistGroup({ name: groupName });
    ElMessage.success("分组已创建");
    showGroupDialog.value = false;
    fetchGroups();
  } catch (e) {
    ElMessage.error("创建分组失败");
    console.error("创建分组错误：", e);
  }
}

// 编辑标签 - 初始化编辑状态
const startEditTag = (tag: WatchlistTag) => {
  editingTagId.value = tag.id;
  editTagName.value = tag.name;
  editTagColor.value = tag.color || "#B6B09C";
  // 自动聚焦到输入框（需要nextTick）
  nextTick(() => {
    const input = document.querySelector(`.el-input[placeholder="请输入内容"]`);
    if (input) (input as HTMLElement).focus();
  });
};

// 保存标签编辑 - 完善保存逻辑
const saveEditTag = async (tagId: number) => {
  const originalTag = allTags.value.find(t => t.id === tagId);
  if (!originalTag) return;

  const newName = editTagName.value.trim();
  if (!newName) {
    ElMessage.warning("请输入标签名称");
    // 恢复原名称
    editTagName.value = originalTag.name;
    return;
  }

  // 无变化直接退出
  if (newName === originalTag.name && editTagColor.value === (originalTag.color || '#B6B09C')) {
    editingTagId.value = null;
    return;
  }

  try {
    await updateWatchlistTag(tagId, {
      name: newName,
      color: editTagColor.value
    });
    ElMessage.success("标签已更新");
    editingTagId.value = null;
    await fetchTags(); // 重新获取标签列表
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning("标签名称已存在");
      // 恢复原名称
      editTagName.value = originalTag.name;
    } else {
      ElMessage.error("更新标签失败");
    }
  }
};

// 删除标签
const deleteTag = async (tagId: number) => {
  // 双重检查标签是否被使用
  if (usedTagIds.value.has(tagId)) {
    ElMessage.warning("该标签正被使用，无法删除");
    return;
  }

  try {
    await deleteWatchlistTag(tagId);
    ElMessage.success("标签已删除");
    await fetchTags();
  } catch (e) {
    ElMessage.error("删除标签失败");
    console.error("删除标签错误：", e);
  }
};

// ─────────────────────────────────────────────
// 生命周期
// ─────────────────────────────────────────────
onMounted(() => {
  fetchGroups();
  fetchTags();
  fetchData();

  // 监听分组切换
  watch(activeGroup, () => {
    currentPage.value = 1;
    fetchData();
  });
});
</script>

<style scoped>
.marker-column .cell {
  padding: 0 !important;
}

.add-tag-btn {
  opacity: 0;
  transition: opacity 0.2s;
  width: 20px;
  height: 20px;
  min-height: 20px;
}
.el-table__row:hover .add-tag-btn {
  opacity: 1;
}

/* 无标签时按钮直接显示（覆盖 opacity 0） */
.add-tag-btn:only-child {
  opacity: 1;
}

/* 修复标签筛选区域响应式布局 */
@media (max-width: 768px) {
  .watchlist-page .flex-wrap {
    flex-direction: column;
  }
  .watchlist-page .min-w-\[600px\] {
    min-width: 100%;
  }
}
</style>
