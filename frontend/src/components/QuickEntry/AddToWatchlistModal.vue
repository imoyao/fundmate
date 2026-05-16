<template>
  <el-dialog
    class="add-watchlist-dialog"
    v-model="visible"
    title="⭐ 添加自选资产"
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
          @change="onAssetSelected"
          clearable
          class="w-full"
        >
          <el-option
            v-for="item in searchResults"
            :key="item.symbol"
            :label="`${item.symbol} · ${item.name}`"
            :value="item"
          >
            <div class="flex justify-between items-center">
              <span class="text-sm font-medium">{{ item.symbol }}</span>
              <span class="text-xs text-gray-400 ml-2">{{ item.name }}</span>
              <span class="text-xs ml-2" :style="{ color: getMarketColor(item.market) }">
                {{ getMarketLabel(item.market) }}
              </span>
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <!-- 已选择资产信息 -->
      <div v-if="selectedAsset" class="bg-[#f5f7fa] rounded-xl p-4 mb-4">
        <div class="flex justify-between items-center mb-2">
          <span class="font-bold text-gray-800">{{ selectedAsset.name }}</span>
          <el-tag v-if="!assetAlreadyExists" size="small" :color="getVenueColor(selectedAsset.venue)">
            {{ selectedAsset.venue === 'OTC' ? '场外' : '场内' }}
          </el-tag>
          <el-tag v-else type="warning" size="small">已在自选</el-tag>
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs text-gray-500">
          <div><span class="text-gray-400">代码：</span>{{ selectedAsset.symbol }}</div>
          <div><span class="text-gray-400">市场：</span>{{ getMarketLabel(selectedAsset.market) }}</div>
          <div><span class="text-gray-400">类型：</span>{{ getTypeLabel(selectedAsset.type) }}</div>
        </div>

        <!-- 置顶开关（不在自选时显示） -->
        <div v-if="!assetAlreadyExists" class="mt-3 flex items-center justify-between">
          <span class="text-xs text-gray-500">置顶到首页</span>
          <el-switch v-model="pinToTop" size="small"/>
        </div>

        <!-- 分组选择（多选，仅自定义分组） -->
        <div class="mt-3">
          <span class="text-xs text-gray-500 mb-1 block">加入分组（可选）</span>
          <el-select
            v-model="selectedGroupIds"
            multiple
            filterable
            placeholder="选择分组"
            class="w-full"
            size="small"
            @change="handleGroupSelect"
            ref="groupSelectRef"
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
                  :style="{ backgroundColor: g.color || '#C5C9B8' }"
                ></span>
                <span>{{ g.name }}</span>
              </div>
            </el-option>
          </el-select>
        </div>

        <!-- 标签选择 【最终稳定版】 -->
        <div class="mt-3">
          <span class="text-xs text-gray-500 mb-1 block">标签（可选）</span>
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
                  <span class="w-3 h-3 rounded-full" :style="{backgroundColor: tag.color || '#C5C9B8'}"></span>
                  <span>{{ tag.name }}</span>
                </div>
              </el-option>
            </el-select>
            <el-button size="small" @click="showNewTagForm = true">
              <IconifyIconOffline icon="ep:plus"/>
            </el-button>
          </div>

          <!-- 新建标签内联表单 -->
          <div v-if="showNewTagForm" class="mt-2 p-3 bg-gray-50 rounded-lg flex items-end gap-2">
            <el-input
              v-model="newTagName"
              placeholder="标签名"
              size="small"
              class="w-24"
            />
            <div class="flex gap-1">
              <button
                v-for="c in presetColors"
                :key="c"
                class="w-5 h-5 rounded-full border-2 transition-colors cursor-pointer"
                :class="newTagColor === c ? 'border-gray-800 scale-110' : 'border-transparent'"
                :style="{ backgroundColor: c }"
                @click="newTagColor = c"
              />
            </div>
            <el-button type="primary" size="small" @click="addNewTag">确定</el-button>
            <el-button size="small" @click="showNewTagForm = false">取消</el-button>
          </div>
        </div>
      </div>

      <!-- 关注理由（可选） -->
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
  </el-dialog>
</template>

<script setup lang="ts">
import {ref, computed, onMounted, nextTick} from "vue";
import {ElMessage} from "element-plus";
import {searchSecurities} from "@/api/securities";
import {searchFunds} from "@/api/funds";
import {http} from "@/utils/http";
import {
  getWatchlistGroups,
  getWatchlistTags,
  createWatchlistTag,
  addItemToGroup,
  addTagToItem,
  getWatchlistItems,
} from "@/api/watchlist";
import type {WatchlistGroup, WatchlistTag} from "@/api/watchlist";

// Props & Emits
const props = defineProps<{
  modelValue: boolean;
  initialGroupId?: number;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

// 基础状态
const searchLoading = ref(false);
const searchResults = ref<any[]>([]);
const selectedAsset = ref<any>(null);
const addReason = ref("");
const pinToTop = ref(false); // 响应式变量
const submitting = ref(false);
const assetAlreadyExists = ref(false);

// 分组
const availableGroups = ref<WatchlistGroup[]>([]);
const selectedGroupIds = ref<number[]>([]);
const groupSelectRef = ref<any>(null);

// 标签
const availableTags = ref<WatchlistTag[]>([]);
const selectedTagIds = ref<number[]>([]);
const showNewTagForm = ref(false);
const newTagName = ref("");
const newTagColor = ref("#B6B09C");
const presetColors = ["#B8A99A", "#9CAF88", "#8DA3B8", "#C4A0A8", "#9B9EB0", "#B6B09C"];
const tagSelectRef = ref<any>(null);

// 分组选中清空搜索+关下拉
const handleGroupSelect = () => {
  if(groupSelectRef.value){
    groupSelectRef.value.query = ""
    groupSelectRef.value.visible = false
  }
}

// 标签选中事件：关闭下拉+清空搜索词
const tagChange = () => {
  if(tagSelectRef.value) tagSelectRef.value.visible = false;
  nextTick(()=>{
    if(tagSelectRef.value) tagSelectRef.value.query = "";
  });
};

// 根据id获取标签颜色
const getTagColor = (tid:number)=>{
  return availableTags.value.find(t=>t.id === tid)?.color || "#C5C9B8";
};

// 获取分组列表
const fetchGroups = async () => {
  try {
    const res = await getWatchlistGroups();
    const allGroups: WatchlistGroup[] = (res as any).data ?? [];
    availableGroups.value = allGroups.filter(g => !g.is_system && g.id != null);
  } catch (e) {
    console.error("获取分组失败：", e);
  }
};

// 获取标签列表
const fetchTags = async () => {
  try {
    const res = await getWatchlistTags();
    // 兜底标签颜色，避免无颜色导致样式异常
    availableTags.value = (res as any).data?.map((tag: WatchlistTag) => ({
      ...tag,
      color: tag.color || "#C5C9B8"
    })) ?? [];
  } catch (e) {
    console.error("获取标签失败：", e);
  }
};

// 检查资产是否已在自选
const checkAssetExists = async (symbol: string) => {
  try {
    const res = await getWatchlistItems({symbol});
    return ((res as any).data ?? []).length > 0;
  } catch {
    return false;
  }
};

// 资产搜索
const remoteSearch = async (query: string) => {
  if (!query) {
    searchResults.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    const [secRes, fundRes] = await Promise.allSettled([searchSecurities(query), searchFunds(query)]);
    const results: any[] = [];
    if (secRes.status === "fulfilled") {
      const secData = (secRes.value as any)?.data ?? [];
      results.push(...secData.map((s: any) => ({...s, searchType: "sec"})));
    }
    if (fundRes.status === "fulfilled") {
      const fundData = (fundRes.value as any)?.data ?? [];
      results.push(...fundData.map((f: any) => ({
        symbol: f.code, name: f.name, market: "CN_A", type: "fund", venue: "OTC", searchType: "fund"
      })));
    }
    searchResults.value = results;
  } catch (e) {
    ElMessage.error("搜索失败，请重试");
  } finally {
    searchLoading.value = false;
  }
};

// 选中资产后初始化状态
const onAssetSelected = async (option: any) => {
  if (!option) return;
  selectedAsset.value = option;
  pinToTop.value = false;
  selectedGroupIds.value = props.initialGroupId ? [props.initialGroupId] : [];
  selectedTagIds.value = []; // 清空已选标签
  assetAlreadyExists.value = await checkAssetExists(option.symbol);
};

// 新建标签
const addNewTag = async () => {
  if (!newTagName.value.trim()) {
    ElMessage.warning("请输入标签名称！");
    return;
  }
  try {
    const res = await createWatchlistTag({
      name: newTagName.value.trim(),
      color: newTagColor.value,
    });
    const newTag = (res as any).data;
    // 补全颜色字段
    newTag.color = newTag.color || newTagColor.value;
    // 添加到标签列表并选中
    availableTags.value.push(newTag);
    selectedTagIds.value.push(newTag.id);
    // 重置新建表单
    showNewTagForm.value = false;
    newTagName.value = "";
    newTagColor.value = "#B6B09C";
    ElMessage.success(`标签「${newTag.name}」已创建并选中`);
  } catch (e: any) {
    if (e?.response?.status === 409) {
      const existingTag = availableTags.value.find(t => t.name === newTagName.value.trim());
      if (existingTag) {
        if (!selectedTagIds.value.includes(existingTag.id)) {
          selectedTagIds.value.push(existingTag.id);
        }
        ElMessage.info(`标签「${existingTag.name}」已存在，已自动选中`);
      } else {
        ElMessage.warning(`标签「${newTagName.value.trim()}」已存在，但未找到对应数据`);
      }
    } else {
      ElMessage.error("创建标签失败：" + (e.message || "未知错误"));
    }
    // 重置新建表单
    showNewTagForm.value = false;
    newTagName.value = "";
    newTagColor.value = "#B6B09C";
  }
};

// 提交添加自选
const handleSubmit = async () => {
  if (!selectedAsset.value) {
    ElMessage.warning("请先选择要添加的资产！");
    return;
  }
  submitting.value = true;
  try {
    const itemRes = await http.request("post", "/api/watchlist/items/", {
      data: {
        symbol: selectedAsset.value.symbol,
        market: selectedAsset.value.market,
        asset_type: selectedAsset.value.type,
        venue: selectedAsset.value.venue || (selectedAsset.value.type === "fund" ? "OTC" : "EXCHANGE"),
        add_reason: addReason.value || undefined,
        is_pinned: pinToTop.value,
      },
    });
    const newItem = (itemRes as any).data;
    // 关联分组
    for (const gid of selectedGroupIds.value) {
      await addItemToGroup(newItem.id, gid);
    }
    // 关联标签
    for (const tid of selectedTagIds.value) {
      await addTagToItem(newItem.id, tid);
    }
    ElMessage.success("资产已成功添加到自选！");
    visible.value = false;
    emit("submitted");
  } catch (e: any) {
    ElMessage.error("添加失败：" + (e.response?.data?.message || e.message || "未知错误"));
  } finally {
    submitting.value = false;
  }
};

// 工具方法
const getMarketColor = (market: string): string => {
  const map: Record<string, string> = {HK: "#B5C4B1",SH: "#C4C8D0",SZ: "#D4C5C7",US: "#A3B5C7"};
  return map[market] || "#C5C9B8";
};
const getMarketLabel = (market: string): string => {
  const map: Record<string, string> = {HK: "港股",SH: "沪市",SZ: "深市",US: "美股"};
  return map[market] || market;
};
const getTypeLabel = (type: string): string => {
  const map: Record<string, string> = {stock: "股票",etf: "ETF",bond: "可转债",fund: "场外基金",index: "指数"};
  return map[type] || type;
};
const getVenueColor = (venue: string): string => {
  return venue === "OTC" ? "#E8D5C4" : "#C4C8D0";
};

// 重置表单（修复核心错误：pinToTop.value 赋值）
const resetForm = () => {
  selectedAsset.value = null;
  searchResults.value = [];
  addReason.value = "";
  pinToTop.value = false; // 正确赋值：响应式变量必须用.value
  selectedGroupIds.value = [];
  selectedTagIds.value = [];
  assetAlreadyExists.value = false;
  showNewTagForm.value = false;
  newTagName.value = "";
  newTagColor.value = "#B6B09C";
};

// 初始化加载数据
onMounted(async () => {
  // 先加载标签，确保标签选择器渲染时有数据
  await fetchTags();
  await fetchGroups();
});
</script>

<style scoped>
.asset-form {
  margin: 10px 0;
  padding: 0 5px;
}
.reason-input {
  margin-top: 10px;
}
.reason-input :deep(.el-textarea__inner) {
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 14px;
  width: 100%;
  box-sizing: border-box;
}
.reason-input :deep(.el-input__count) {
  right: 8px;
  bottom: 4px;
  color: #999;
  font-size: 12px;
}
:deep(.el-select) {
  width: 100%;
  box-sizing: border-box;
}
.add-watchlist-dialog :deep(.el-dialog__body) {
  font-size: 15px;
  padding: 20px;
}
/* 标签选中样式：浅底色+对应颜色边框 */
.tag-select :deep(.el-select__tags .el-tag) {
  border: 1px solid var(--el-tag-text-color);
  background-color: rgba(var(--el-tag-text-color-rgb), 0.1);
  color: var(--el-tag-text-color);
  margin: 2px 4px 2px 0;
  padding: 0 8px;
}
/* 颜色选择按钮样式 */
:deep(.flex gap-1 button) {
  cursor: pointer;
}
</style>
