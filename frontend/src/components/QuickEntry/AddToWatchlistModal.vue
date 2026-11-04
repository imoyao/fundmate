<template>
  <el-dialog
    v-model="visible"
    class="add-watchlist-dialog"
    title="添加自选资产"
    width="520px"
    destroy-on-close
    :close-on-click-modal="false"
    :before-close="onBeforeClose"
    @closed="resetForm"
  >
    <!-- 搜索框。结果项统一为「名称(主) · 次要锚点(灰) · 类型(最右配色)」一行三列：
         带编码品种（股票/基金/ETF/指数/可转债/加密）：名称 | 编码 | 类型；
         组合类（投顾组合/基金经理）：名称 | 平台·主理人 | 类型。
         组合类平台原生码（且慢 ZHxxxx / 天天基金 tgCode）对用户无意义，整段不展示，
         由名称 + 平台/主理人承担（见 @/constants/advisorPlatform）。 -->
    <el-form label-width="0px" class="asset-form">
      <el-form-item>
        <!-- #2214：不加 clearable——清除图标会把输入一并抹掉，与「关键字应保留」相悖。 -->
        <AddToWatchlistSearch
          ref="searchRef"
          v-model="selectedAsset"
          @change="onAssetSelected"
        />
      </el-form-item>

      <!-- 已选择资产信息：主行与搜索项同结构（名称主视觉 · 次要锚点灰 · 类型配色最右）。
           组合类标的（投顾组合 / 基金经理）不展示平台原生码——见上方搜索框注释。 -->
      <div v-if="selectedAsset" class="selected-asset-card rounded-xl mb-4">
        <!-- 卡片内部按「识别 / 编排」两职责拆开（#980）：
             识别区仍是多根片段，DOM 与拆分前完全一致，不会有额外包裹层影响排版。 -->
        <AddToWatchlistAssetIdentity
          :asset="selectedAsset"
          :already-exists="assetAlreadyExists"
        />
        <AddToWatchlistOrganizeFields
          v-model:pin-to-top="pinToTop"
          v-model:group-ids="selectedGroupIds"
          v-model:tag-ids="selectedTagIds"
          :show-pin="!assetAlreadyExists"
          :groups="availableGroups"
          :tags="availableTags"
          @create-group="groupFormVisible = true"
          @create-tag="tagFormVisible = true"
        />
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
    </el-form>

    <template #footer>
      <el-button @click="requestClose">取消</el-button>
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
// 添加自选弹窗的「装配层」：#980 拆分后这里只留编排——搜索、资产识别、归组编排、
// 分组标签目录各自独立（见同目录 AddToWatchlistSearch / ...AssetIdentity /
// ...OrganizeFields / composables/useWatchlistAddCatalog）。
//
// 本文件仍是唯一知道「提交长什么样」的地方：查重、创建、关联分组标签、脏检查、
// 未保存离开保护都在这里，因为它们是同一个事务的不同阶段，拆开只会让时序更难追。
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  useFormDirty,
  useUnsavedChangesGuard
} from "@/composables/useUnsavedChangesGuard";
import {
  addItemToGroup,
  addTagToItem,
  createWatchlistItem,
  getWatchlistItems
} from "@/api/watchlist";
import type { WatchlistItem } from "@/api/watchlist";
import TagFormDialog from "@/components/Watchlist/TagFormDialog.vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";
import type { SearchAssetOption } from "./assetOptionColumns";
import AddToWatchlistSearch from "./AddToWatchlistSearch.vue";
import AddToWatchlistAssetIdentity from "./AddToWatchlistAssetIdentity.vue";
import AddToWatchlistOrganizeFields from "./AddToWatchlistOrganizeFields.vue";
import { useWatchlistAddCatalog } from "./composables/useWatchlistAddCatalog";

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

const selectedAsset = ref<SearchAssetOption | null>(null);
/** 搜索子组件的内部残留（结果列表 / 关键字副本）随弹窗关闭一并清掉 */
const searchRef = ref<{ reset: () => void } | null>(null);
const addReason = ref("");
const pinToTop = ref(false);
const submitting = ref(false);
const assetAlreadyExists = ref(false);

// 复用全局「新建标签 / 新建分组」弹窗，统一入口体验
const tagFormVisible = ref(false);
const groupFormVisible = ref(false);

const {
  availableGroups,
  availableTags,
  selectedGroupIds,
  selectedTagIds,
  tagFormUsedColors,
  groupFormUsedColors,
  onTagFormCreated,
  onTagFormSaved,
  onGroupFormCreated,
  onGroupFormSaved,
  applyInitialSelection
} = useWatchlistAddCatalog({
  initialGroupId: computed(() => props.initialGroupId),
  onCatalogChanged: () => emit("catalog-changed")
});

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

const onAssetSelected = async (option: SearchAssetOption | null) => {
  if (!option) return;
  selectedAsset.value = option;
  pinToTop.value = false;
  // 默认勾上来源分组、清空标签（与 resetForm 的「一律清空」不同，见 composable 注释）
  applyInitialSelection();
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
      // 名称快照（#1508）：搜索结果本就带 name，随创建落库，避免后端读时反查出错名
      name: selectedAsset.value.name,
      market: selectedAsset.value.market,
      asset_type: selectedAsset.value.type,
      // venue 用 ?? 兜底：无市场实体（经理/组合）后端返回空串，须原样透传而非转 EXCHANGE
      venue:
        selectedAsset.value.venue ??
        (selectedAsset.value.type === "fund" ? "OTC" : "EXCHANGE"),
      add_reason: addReason.value || undefined,
      is_pinned: pinToTop.value
    });
    const newItem: WatchlistItem = itemRes.data;

    // 关联端点成功仅返回 { message }，无 data，故收集为 Promise<unknown>
    const promises: Promise<unknown>[] = [];
    for (const gid of selectedGroupIds.value) {
      promises.push(addItemToGroup(newItem.id, gid));
    }
    for (const tid of selectedTagIds.value) {
      promises.push(addTagToItem(newItem.id, tid));
    }
    await Promise.all(promises);

    ElMessage.success("资产已成功添加到自选！");
    // 先清脏再关：提交成功后表单仍是脏的，而关闭走的是 v-model setter，
    // 不先清就会弹「确定放弃吗？」（与 TransactionDrawer.onSubmitSuccess 同源）。
    markClean();
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

// ── 未保存离开保护（#1835）──
// 关闭按钮 / ESC 走 el-dialog 的 before-close；底部「取消」是程序化 close，走不到它，
// 必须各自接一道，否则那条路仍然静默丢数据（选了资产 + 填了备注 + 勾了标签/分组，
// 一路 Esc 关掉，用户什么都不知道）。路由离开由 useUnsavedChangesGuard 内部注册。
//
// 脏基线只取「用户真正填过的字段」：搜索过程（searchResults）不算改动，
// 否则搜了两下没选中也弹「确定放弃吗」，那是纯粹的噪音。
const { isDirty, markClean } = useFormDirty(() => ({
  asset: selectedAsset.value?.symbol ?? null,
  reason: addReason.value,
  pinToTop: pinToTop.value,
  groupIds: [...selectedGroupIds.value].sort(),
  tagIds: [...selectedTagIds.value].sort()
}));

const { onBeforeClose, requestClose: confirmThenClose } =
  useUnsavedChangesGuard(() => isDirty.value, {
    message: "已填写自选信息，确定放弃吗？"
  });

/** 底部「取消」：程序化 close 走不到 before-close，必须自己问一遍 */
async function requestClose() {
  await confirmThenClose(() => (visible.value = false));
}

// 打开时记基线。放在 watch 而不是 @open：@open 只在动画结束后触发，
// 期间的 watch 会被判成「已修改」（与 #1845 同源的坑）。
watch(
  () => props.modelValue,
  open => {
    if (open) markClean();
  },
  { immediate: true }
);

const resetForm = () => {
  selectedAsset.value = null;
  // 搜索子组件自行清理结果列表与关键字副本：否则下次打开弹窗，
  // 失焦回填会把上一轮的关键字塞回空输入框（#2214）
  searchRef.value?.reset();
  markClean();
  addReason.value = "";
  pinToTop.value = false;
  selectedGroupIds.value = [];
  selectedTagIds.value = [];
  assetAlreadyExists.value = false;
};
</script>

<style scoped>
.selected-asset-card {
  padding: var(--space-compact);
  background-color: var(--bg-warm);
}

/* 表单元素通用 */
.asset-form {
  padding: 0 5px;
  margin: 10px 0;
}

.reason-input {
  /* 比基线默认（5px 11px）更松的文本域内边距：只覆盖令牌，不再 :deep（#1772） */
  --input-textarea-padding: 8px 12px;

  margin-top: 10px;
}

.reason-input :deep(.el-input__count) {
  right: 8px;
  bottom: 4px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

:deep(.el-select) {
  box-sizing: border-box;
  width: 100%;
}

.add-watchlist-dialog :deep(.el-dialog__body) {
  padding: 20px;
  font-size: var(--text-body);
}

/* 全局焦点环（确保所有可交互元素有键盘反馈）。
   输入框 / 下拉不在此列：它们的焦点环由 #1772 输入基线统一画，
   再叠一层就成双环了。 */
:deep(.el-button:focus-visible),
:deep(.el-switch:focus-visible .el-switch__core) {
  box-shadow: var(--focus-ring) !important;
}
</style>
