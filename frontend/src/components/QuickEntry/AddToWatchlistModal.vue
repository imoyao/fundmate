<template>
  <el-dialog
    v-model="visible"
    class="add-watchlist-dialog"
    title="添加自选资产"
    width="520px"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="resetForm"
  >
    <!-- 搜索框 -->
    <el-form label-width="0px" class="asset-form">
      <el-form-item>
        <el-select
          v-model="selectedAsset"
          value-key="symbol"
          remote
          filterable
          reserve-keyword
          placeholder="输入代码或名称搜索..."
          :remote-method="remoteSearch"
          :loading="searchLoading"
          clearable
          class="w-full"
          @change="onAssetSelected"
        >
          <el-option
            v-for="item in searchResults"
            :key="item.symbol"
            :label="`${item.symbol} · ${item.name}`"
            :value="item"
          >
            <div class="flex justify-between items-center">
              <span class="text-sm font-medium">{{ item.symbol }}</span>
              <span
                class="text-xs ml-2"
                :style="{ color: 'var(--text-tertiary)' }"
                >{{ item.name }}</span
              >
              <span
                class="text-xs ml-2"
                :style="{ color: 'var(--text-tertiary)' }"
                >{{ getTypeLabel(item.type || "") }}</span
              >
              <span
                class="text-xs ml-2"
                :style="{ color: getMarketColor(item.market) }"
              >
                {{ item.market ? getMarketLabel(item.market) : "—" }}
              </span>
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <!-- 已选择资产信息 -->
      <div v-if="selectedAsset" class="selected-asset-card rounded-xl p-4 mb-4">
        <div class="flex justify-between items-center mb-2">
          <span class="font-bold" :style="{ color: 'var(--text-primary)' }">{{
            selectedAsset.name
          }}</span>
          <el-tag
            v-if="!assetAlreadyExists && selectedAsset.venue"
            size="small"
            class="venue-tag"
            :class="selectedAsset.venue === 'OTC' ? 'tag-otc' : 'tag-exchange'"
          >
            {{ getVenueLabel(selectedAsset.venue) }}
          </el-tag>
          <el-tag v-else type="warning" size="small">已在自选</el-tag>
        </div>
        <div
          class="grid grid-cols-2 gap-2 text-xs"
          :style="{ color: 'var(--text-secondary)' }"
        >
          <div>
            <span :style="{ color: 'var(--text-tertiary)' }">代码：</span
            >{{ selectedAsset.symbol }}
          </div>
          <div>
            <span :style="{ color: 'var(--text-tertiary)' }">市场：</span
            >{{
              selectedAsset.market ? getMarketLabel(selectedAsset.market) : "—"
            }}
          </div>
          <div>
            <span :style="{ color: 'var(--text-tertiary)' }">类型：</span
            >{{ getTypeLabel(selectedAsset.type) }}
          </div>
        </div>

        <!-- 置顶开关 -->
        <div
          v-if="!assetAlreadyExists"
          class="mt-3 flex items-center justify-between"
        >
          <span class="text-xs" :style="{ color: 'var(--text-secondary)' }"
            >置顶到首页</span
          >
          <el-switch v-model="pinToTop" size="small" />
        </div>

        <!-- 分组选择 -->
        <div class="mt-3">
          <span
            class="text-xs mb-1 block"
            :style="{ color: 'var(--text-secondary)' }"
            >加入分组（可选）</span
          >
          <div class="flex gap-2">
            <el-select
              ref="groupSelectRef"
              v-model="selectedGroupIds"
              multiple
              filterable
              placeholder="选择分组"
              class="w-full"
              size="small"
              @change="handleGroupSelect"
            >
              <el-option
                v-for="g in availableGroups"
                :key="g.id"
                :label="g.name"
                :value="g.id"
              >
                <div class="flex items-center gap-2">
                  <span
                    class="w-3 h-3 rounded-full"
                    :style="{
                      backgroundColor: g.color || 'var(--text-disabled)'
                    }"
                  />
                  <span>{{ g.name }}</span>
                </div>
              </el-option>
            </el-select>
            <el-button
              size="small"
              class="inline-add-btn"
              @click="groupFormVisible = true"
            >
              <IconifyIconOffline icon="ep:plus" />
            </el-button>
          </div>
        </div>

        <!-- 标签选择 -->
        <div class="mt-3">
          <span
            class="text-xs mb-1 block"
            :style="{ color: 'var(--text-secondary)' }"
            >标签（可选）</span
          >
          <div class="flex gap-2">
            <el-select
              ref="tagSelectRef"
              v-model="selectedTagIds"
              multiple
              filterable
              placeholder="选择标签"
              class="flex-1 tag-select"
              size="small"
              filter-placeholder="搜索标签"
              @change="tagChange"
            >
              <el-option
                v-for="tag in availableTags"
                :key="tag.id"
                :label="tag.name"
                :value="tag.id"
              >
                <div class="flex items-center gap-2">
                  <span
                    class="w-3 h-3 rounded-full"
                    :style="{
                      backgroundColor: tag.color || 'var(--text-disabled)'
                    }"
                  />
                  <span>{{ tag.name }}</span>
                </div>
              </el-option>
            </el-select>
            <el-button
              size="small"
              class="inline-add-btn"
              @click="tagFormVisible = true"
            >
              <IconifyIconOffline icon="ep:plus" />
            </el-button>
          </div>
        </div>
      </div>

      <!-- 关注理由 -->
      <el-form-item>
        <el-input
          v-model="addReason"
          type="textarea"
          :rows="2"
          placeholder="为什么关注？（选填）"
          maxlength="200"
          show-word-limit
          class="reason-input"
        />
      </el-form-item>

      <!-- 投资笔记 -->
      <el-form-item>
        <el-input
          v-model="notes"
          type="textarea"
          :rows="3"
          placeholder="投资笔记 / 交易手札（选填）"
          maxlength="2000"
          show-word-limit
          class="notes-input"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        v-if="!assetAlreadyExists"
        type="primary"
        :loading="submitting"
        :disabled="!selectedAsset"
        @click="handleSubmit"
      >
        添加自选
      </el-button>
      <el-tag v-else type="warning" size="large">该资产已在自选列表中</el-tag>
    </template>

    <!-- 复用全局「新建标签」弹窗，与「管理标签」体验一致 -->
    <TagFormDialog
      v-model="tagFormVisible"
      :used-colors="tagFormUsedColors"
      @created="onTagFormCreated"
      @saved="onTagFormSaved"
    />

    <!-- 复用全局「新建分组」弹窗 -->
    <GroupFormDialog
      v-model="groupFormVisible"
      :used-colors="groupFormUsedColors"
      @created="onGroupFormCreated"
      @saved="onGroupFormSaved"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  nextTick,
  type ComponentPublicInstance
} from "vue";
import { ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { useAssetSearch } from "@/composables/useAssetSearch";
import {
  getWatchlistGroups,
  getWatchlistTags,
  addItemToGroup,
  addTagToItem,
  getWatchlistItems,
  createWatchlistItem // ✅ 新增 API 封装
} from "@/api/watchlist";
import type {
  WatchlistGroup,
  WatchlistTag,
  WatchlistItem
} from "@/api/watchlist";
import { getTypeLabel } from "@/constants/assetType";
import { getMarketLabel, getVenueLabel } from "@/constants/market";
import TagFormDialog from "@/components/Watchlist/TagFormDialog.vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";

interface SearchAssetOption {
  symbol: string;
  name: string;
  market: string;
  type?: string;
  venue: string;
  searchType?: "sec" | "fund";
  subscription_rate?: number;
  is_money_fund?: boolean;
  code?: string;
}

const props = defineProps<{
  modelValue: boolean;
  initialGroupId?: number;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
  /** 弹窗内新建/编辑了标签或分组，通知父页面刷新全局目录，避免新建后页面不更新 */
  "catalog-changed": [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const searchLoading = ref(false);
const searchResults = ref<SearchAssetOption[]>([]);
const selectedAsset = ref<SearchAssetOption | null>(null);
const addReason = ref("");
const notes = ref("");
const pinToTop = ref(false);
const submitting = ref(false);
const assetAlreadyExists = ref(false);

const availableGroups = ref<WatchlistGroup[]>([]);
const selectedGroupIds = ref<number[]>([]);
const groupSelectRef = ref<ComponentPublicInstance | null>(null);

const availableTags = ref<WatchlistTag[]>([]);
const selectedTagIds = ref<number[]>([]);
const tagSelectRef = ref<ComponentPublicInstance | null>(null);

// 复用全局「新建标签 / 新建分组」弹窗，统一入口体验
const tagFormVisible = ref(false);
const groupFormVisible = ref(false);
const tagFormUsedColors = computed(() =>
  availableTags.value.map(t => t.color).filter((c): c is string => !!c)
);
const groupFormUsedColors = computed(() =>
  availableGroups.value.map(g => g.color).filter((c): c is string => !!c)
);

// 新建标签成功：直接并入可选项并自动选中，免去内联表单
const onTagFormCreated = (tag: WatchlistTag) => {
  if (!availableTags.value.find(t => t.id === tag.id)) {
    availableTags.value.push(tag);
  }
  if (!selectedTagIds.value.includes(tag.id)) {
    selectedTagIds.value.push(tag.id);
  }
  emit("catalog-changed");
};
// 编辑 / 其他变更：兜底刷新标签列表，保持与全局一致
const onTagFormSaved = () => {
  fetchTags();
  emit("catalog-changed");
};

// 新建分组成功：并入可选项并自动选中
const onGroupFormCreated = (group: WatchlistGroup) => {
  if (!availableGroups.value.find(g => g.id === group.id)) {
    availableGroups.value.push(group);
  }
  if (!selectedGroupIds.value.includes(group.id)) {
    selectedGroupIds.value.push(group.id);
  }
  emit("catalog-changed");
};
const onGroupFormSaved = () => {
  fetchGroups();
  emit("catalog-changed");
};

const handleGroupSelect = () => {
  const el = groupSelectRef.value as unknown as {
    query: string;
    visible: boolean;
  } | null;
  if (el) {
    el.query = "";
    el.visible = false;
  }
};

const tagChange = () => {
  const el = tagSelectRef.value as unknown as {
    query: string;
    visible: boolean;
  } | null;
  if (el) el.visible = false;
  nextTick(() => {
    const el2 = tagSelectRef.value as unknown as {
      query: string;
      visible: boolean;
    } | null;
    if (el2) el2.query = "";
  });
};

const fetchGroups = async () => {
  try {
    const res = await getWatchlistGroups();
    const allGroups: WatchlistGroup[] = res.data ?? [];
    availableGroups.value = allGroups.filter(g => !g.is_system && g.id != null);
  } catch (e) {
    console.error("获取分组失败：", e);
  }
};

const fetchTags = async () => {
  try {
    const res = await getWatchlistTags();
    availableTags.value =
      res.data.map((tag: WatchlistTag) => ({
        ...tag,
        color: tag.color || "var(--text-disabled)"
      })) ?? [];
  } catch (e) {
    console.error("获取标签失败：", e);
  }
};

// 查重序号：onAssetSelected 每次选择自增，慢响应到达时序号已过期则丢弃结果。
// 否则用户快速把 A（已在自选）切换到 B（不在）时，A 的慢响应后到会把
// assetAlreadyExists 误写成 true——B 明明没加过却提示「已在自选」（2026-09-09 用户实测误报）。
let checkSeq = 0;

const checkAssetExists = async (symbol: string, seq: number) => {
  // 空/空白代码不查重：后端对空 symbol 跳过过滤走「全部」分支，恒返回整页数据，
  // 会被误判成「已存在」（历史误报根因之一，与 OcrImportModal.probeExisting 同源）
  const key = (symbol || "").trim();
  if (!key) return false;
  try {
    // per_page: 1 查重只需知道有无，避免拉 20 条 enrich 数据
    const res = await getWatchlistItems({ symbol: key, per_page: 1 });
    const exists = (res.data ?? []).length > 0;
    // 时序守卫：仅最新一次选择的结果允许写入，过期响应直接丢弃
    return seq === checkSeq && exists;
  } catch {
    return false;
  }
};

// #1286：搜索改走全局唯一入口 useAssetSearch（后端聚合端点，五品种一次扇出），
// 本弹窗不再直调 securities/funds 搜索 API。
const { search: runUnifiedSearch, results: unifiedResults } = useAssetSearch();

const remoteSearch = async (query: string) => {
  if (!query) {
    searchResults.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    await runUnifiedSearch(query);
    // 统一信封 → 弹窗选项（code 与 symbol 同值，兼容既有模板与提交流程）
    searchResults.value = unifiedResults.value.map(item => ({
      symbol: item.code,
      name: item.name,
      market: item.market ?? "",
      type: item.type,
      venue: item.venue ?? "",
      searchType: item.type === "fund" ? ("fund" as const) : ("sec" as const)
    }));
  } finally {
    searchLoading.value = false;
  }
};

const onAssetSelected = async (option: SearchAssetOption | null) => {
  if (!option) return;
  selectedAsset.value = option;
  pinToTop.value = false;
  selectedGroupIds.value = props.initialGroupId ? [props.initialGroupId] : [];
  selectedTagIds.value = [];
  // 先重置为「未存在」再异步查重：切换标的瞬间不得沿用上一次的判定结果
  assetAlreadyExists.value = false;
  const seq = ++checkSeq;
  const exists = await checkAssetExists(option.symbol, seq);
  if (seq === checkSeq) {
    assetAlreadyExists.value = exists;
  }
};

const handleSubmit = async () => {
  if (!selectedAsset.value) {
    ElMessage.warning("请先选择要添加的资产！");
    return;
  }
  submitting.value = true;
  try {
    // 创建自选资产
    const itemRes = await createWatchlistItem({
      symbol: selectedAsset.value.symbol,
      market: selectedAsset.value.market,
      asset_type: selectedAsset.value.type,
      // venue 用 ?? 兜底：无市场实体（经理/组合）后端返回空串，须原样透传而非转 EXCHANGE
      venue:
        selectedAsset.value.venue ??
        (selectedAsset.value.type === "fund" ? "OTC" : "EXCHANGE"),
      add_reason: addReason.value || undefined,
      notes: notes.value || undefined,
      is_pinned: pinToTop.value
    });
    const newItem: WatchlistItem = itemRes.data;

    const promises: Promise<void>[] = [];
    for (const gid of selectedGroupIds.value) {
      promises.push(addItemToGroup(newItem.id, gid));
    }
    for (const tid of selectedTagIds.value) {
      promises.push(addTagToItem(newItem.id, tid));
    }
    await Promise.all(promises);

    ElMessage.success("资产已成功添加到自选！");
    visible.value = false;
    emit("submitted");
  } catch (e) {
    const err = e as {
      response?: { data?: { message?: string } };
      message?: string;
    };
    ElMessage.error(
      "添加失败：" + (err.response?.data?.message || err.message || "未知错误")
    );
  } finally {
    submitting.value = false;
  }
};

// 工具方法
const getMarketColor = (market: string): string => {
  const map: Record<string, string> = {
    HK: "var(--chart-04)",
    SH: "var(--chart-07)",
    SZ: "var(--chart-08)",
    US: "var(--chart-06)"
  };
  return map[market] || "var(--text-tertiary)";
};

const resetForm = () => {
  selectedAsset.value = null;
  searchResults.value = [];
  addReason.value = "";
  notes.value = "";
  pinToTop.value = false;
  selectedGroupIds.value = [];
  selectedTagIds.value = [];
  assetAlreadyExists.value = false;
};

onMounted(async () => {
  await fetchTags();
  await fetchGroups();
});
</script>

<style scoped>
/* 资产信息卡片背景 */
.selected-asset-card {
  background-color: var(--bg-warm);
}

/* 表单元素通用 */
.asset-form {
  padding: 0 5px;
  margin: 10px 0;
}

.reason-input {
  margin-top: 10px;
}

.reason-input :deep(.el-textarea__inner) {
  box-sizing: border-box;
  width: 100%;
  padding: 8px 12px;
  font-size: 14px;
  border-radius: 4px;
}

.reason-input :deep(.el-input__count) {
  right: 8px;
  bottom: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

:deep(.el-select) {
  box-sizing: border-box;
  width: 100%;
}

.add-watchlist-dialog :deep(.el-dialog__body) {
  padding: 20px;
  font-size: 15px;
}

/* 标签选中样式：使用品牌色系统 */
.tag-select :deep(.el-select__tags .el-tag) {
  padding: 0 8px;
  margin: 2px 4px 2px 0;
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

/* venue 类型标签 */
.venue-tag.tag-otc {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border: none;
}

.venue-tag.tag-exchange {
  color: var(--text-secondary);
  background-color: var(--bg-soft);
  border: none;
}

/* 行内「新建」入口按钮，与工具栏 icon-tool-btn 视觉一致 */
.inline-add-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.inline-add-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

/* 全局焦点环（确保所有可交互元素有键盘反馈） */
:deep(.el-button:focus-visible),
:deep(.el-input__wrapper:focus-within),
:deep(.el-select .el-input__wrapper:focus-within),
:deep(.el-switch:focus-visible .el-switch__core) {
  box-shadow: var(--focus-ring) !important;
}
</style>
