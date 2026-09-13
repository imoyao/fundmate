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
    <!-- 搜索框。结果项统一为「名称(主) · 次要锚点(灰) · 类型(最右配色)」一行三列：
         带编码品种（股票/基金/ETF/指数/可转债/加密）：名称 | 编码 | 类型；
         组合类（投顾组合/基金经理）：名称 | 平台·主理人 | 类型。
         组合类平台原生码（且慢 ZHxxxx / 天天基金 tgCode）对用户无意义，整段不展示，
         由名称 + 平台/主理人承担（见 @/constants/advisorPlatform）。 -->
    <el-form label-width="0px" class="asset-form">
      <el-form-item>
        <el-select
          v-model="selectedAsset"
          value-key="symbol"
          remote
          filterable
          reserve-keyword
          placeholder="输入名称搜索，如「远足」「沪深300」"
          :remote-method="remoteSearch"
          :loading="searchLoading"
          clearable
          class="w-full asset-search"
          popper-class="add-asset-option-popper"
          @change="onAssetSelected"
        >
          <el-option
            v-for="item in searchResults"
            :key="item.symbol"
            :label="item.name"
            :value="item"
          >
            <div class="asset-option">
              <span class="asset-option__name" :title="rowColumns(item).name">{{
                rowColumns(item).name
              }}</span>
              <span
                v-if="rowColumns(item).sub"
                class="asset-option__sub"
                :title="rowColumns(item).sub"
                >{{ rowColumns(item).sub }}</span
              >
              <span
                class="asset-option__type"
                :class="`asset-option__type--${rowColumns(item).typeKey}`"
                >{{ rowColumns(item).type }}</span
              >
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <!-- 已选择资产信息：主行与搜索项同结构（名称主视觉 · 次要锚点灰 · 类型配色最右）。
           组合类标的（投顾组合 / 基金经理）不展示平台原生码——见上方搜索框注释。 -->
      <div v-if="selectedAsset" class="selected-asset-card rounded-xl mb-4">
        <div class="selected-asset-card__head">
          <span
            class="selected-asset-card__name"
            :title="rowColumns(selectedAsset).name"
            >{{ rowColumns(selectedAsset).name }}</span
          >
          <span
            v-if="rowColumns(selectedAsset).sub"
            class="selected-asset-card__sub"
            :title="rowColumns(selectedAsset).sub"
            >{{ rowColumns(selectedAsset).sub }}</span
          >
          <span
            class="selected-asset-card__type"
            :class="`selected-asset-card__type--${rowColumns(selectedAsset).typeKey}`"
            >{{ rowColumns(selectedAsset).type }}</span
          >
          <el-tag v-if="assetAlreadyExists" type="warning" size="small">
            已在自选
          </el-tag>
          <el-tag
            v-else-if="venueLabelOf(selectedAsset)"
            size="small"
            class="venue-tag"
            :class="selectedAsset.venue === 'OTC' ? 'tag-otc' : 'tag-exchange'"
          >
            {{ venueLabelOf(selectedAsset) }}
          </el-tag>
        </div>

        <dl v-if="selectedMetaRows.length" class="selected-asset-card__meta">
          <div
            v-for="row in selectedMetaRows"
            :key="row.label"
            class="selected-asset-card__meta-item"
          >
            <dt>{{ row.label }}</dt>
            <dd :title="row.value">{{ row.value }}</dd>
          </div>
        </dl>

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
import {
  getAdvisorPlatformLabel,
  isCompositeAssetType
} from "@/constants/advisorPlatform";
import { getTypeLabel } from "@/constants/assetType";
import { getMarketLabel, getVenueLabel } from "@/constants/market";
import type { AssetSearchExtra } from "@/api/search";
import TagFormDialog from "@/components/Watchlist/TagFormDialog.vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";

interface SearchAssetOption {
  symbol: string;
  name: string;
  market: string;
  type?: string;
  venue: string;
  /** 品种差异化展示字段（#1285）：组合类的 platform/host、经理的 company 等。
      原先在 remoteSearch 映射时被丢弃，导致弹窗无法按「平台」而非「编码」展示。 */
  extra?: AssetSearchExtra;
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
      // extra 必须整段透传：平台（投顾组合）、主理人、所属公司（经理）都靠它展示
      extra: item.extra,
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

// ── 展示派生（组合类标的不展示平台原生码，见 @/constants/advisorPlatform）──

/** 品类中文标签（后端 asset_type → 中文，如 portfolio → 投顾组合） */
const typeLabelOf = (item: SearchAssetOption): string =>
  getTypeLabel(item.type || "");

/** 交易场所标签（EXCHANGE 场内 / OTC 场外；空串＝无市场实体，不展示） */
const venueLabelOf = (item: SearchAssetOption): string =>
  item.venue ? getVenueLabel(item.venue) : "";

/**
 * 搜索结果 / 已选信息卡主行：方案 A——名称统一为主视觉，次要锚点(灰)置右，类型配色最右。
 * 所有品种行内结构完全一致，混合列表不再「各是各的」：
 * - 带编码品种（股票/基金/ETF/指数/可转债/加密等）：名称 | 编码 | 类型
 * - 组合类（基金经理/投顾）：名称 | 平台·主理人/公司 | 类型
 *   平台原生码（且慢 ZHxxxx / 天天基金 tgCode）对用户无意义，整段不展示，
 *   由名称 + 平台/主理人承担（见 @/constants/advisorPlatform）。
 */
interface RowColumns {
  /** 主视觉：资产名称。所有品种统一加粗主色、左对齐占满、超长省略 */
  name: string;
  /** 次要锚点：编码 / 平台·主理人 / 市场。灰色小字，无则不展示 */
  sub?: string;
  /** 类型中文标签（最右 pill 文本） */
  type: string;
  /** 原始 asset_type，用于类型 pill 按品种配色 */
  typeKey: string;
}
const rowColumns = (item: SearchAssetOption): RowColumns => {
  const extra = item.extra ?? {};
  const type = typeLabelOf(item);
  const typeKey = item.type || "";
  if (isCompositeAssetType(item.type)) {
    if (item.type === "manager") {
      return {
        name: item.name,
        sub: extra.company || undefined,
        type,
        typeKey
      };
    }
    const sub = [getAdvisorPlatformLabel(extra.platform), extra.host]
      .filter((v): v is string => Boolean(v))
      .join(" · ");
    return { name: item.name, sub: sub || undefined, type, typeKey };
  }
  return { name: item.name, sub: item.symbol || undefined, type, typeKey };
};

/**
 * 已选资产的关键信息行（信息卡内两列栅格）。
 * 组合类标的不出现「代码」行；缺失值直接过滤，避免整片「—」噪音。
 */
const selectedMetaRows = computed<{ label: string; value: string }[]>(() => {
  const item = selectedAsset.value;
  if (!item) return [];
  // 主行（rowColumns）已覆盖 名称/编码/类型（或 名称/平台/类型），
  // 此处仅补主行未承载的次要信息，避免与头部重复堆叠。
  if (isCompositeAssetType(item.type)) return [];
  const market = item.market ? getMarketLabel(item.market) : "";
  return market ? [{ label: "市场", value: market }] : [];
});

const resetForm = () => {
  selectedAsset.value = null;
  searchResults.value = [];
  addReason.value = "";
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
/* ── 搜索结果项：主行三列（名称主视觉 | 次要锚点灰 | 类型配色最右），全部一行平铺。
   注意：下拉浮层被 teleport 到 body，这里只负责「行内结构」，浮层容器样式
   （高度、行高、hover）在文件末尾的非 scoped 块中按 popper-class 限定。 */
.asset-option {
  display: flex;
  gap: 10px;
  align-items: center;
  width: 100%;
  min-width: 0;
}

/* 名称：所有品种统一主视觉（加粗、主色、占满左列、超长省略）。
   方案 A：名称恒为主视觉，次要锚点（代码/平台/主理人）落到右侧灰字，
   类型 pill 固定最右——混合列表里每行结构完全一致。 */
.asset-option__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
  color: var(--text-primary);
  white-space: nowrap;
}

/* 次要锚点：编码 / 平台·主理人 / 市场；灰色小字、不占空间、无则不渲染 */
.asset-option__sub {
  flex: 0 0 auto;
  font-size: 12px;
  line-height: 20px;
  color: var(--text-tertiary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.asset-option__type {
  flex-shrink: 0;
  padding: 0 6px;
  font-size: 11px;
  line-height: 18px;
  color: var(--text-secondary);
  background-color: var(--bg-soft);
  border-radius: var(--radius-pill);
}

/* 类型 pill 按品种配色：色值来自 colors.css / dark.scss 的 --asset-type-* 专属
   token（深莫兰迪文字色 + 低透明同 hue 底，10 品种互不撞色，暗色同名覆盖）；
   未知品种走默认灰。 */
.asset-option__type--fund {
  color: var(--asset-type-fund);
  background-color: var(--asset-type-fund-bg);
}
.asset-option__type--stock {
  color: var(--asset-type-stock);
  background-color: var(--asset-type-stock-bg);
}
.asset-option__type--etf {
  color: var(--asset-type-etf);
  background-color: var(--asset-type-etf-bg);
}
.asset-option__type--index {
  color: var(--asset-type-index);
  background-color: var(--asset-type-index-bg);
}
.asset-option__type--bond {
  color: var(--asset-type-bond);
  background-color: var(--asset-type-bond-bg);
}
.asset-option__type--crypto {
  color: var(--asset-type-crypto);
  background-color: var(--asset-type-crypto-bg);
}
.asset-option__type--portfolio {
  color: var(--asset-type-portfolio);
  background-color: var(--asset-type-portfolio-bg);
}
.asset-option__type--manager {
  color: var(--asset-type-manager);
  background-color: var(--asset-type-manager-bg);
}
.asset-option__type--money_fund {
  color: var(--asset-type-money_fund);
  background-color: var(--asset-type-money_fund-bg);
}
.asset-option__type--reverse_repo {
  color: var(--asset-type-reverse_repo);
  background-color: var(--asset-type-reverse_repo-bg);
}

/* ── 已选资产信息卡 ── */
.selected-asset-card {
  padding: var(--space-compact);
  background-color: var(--bg-warm);
}

.selected-asset-card__head {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.selected-asset-card__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 15px;
  font-weight: 600;
  line-height: 22px;
  color: var(--text-primary);
  white-space: nowrap;
}

.selected-asset-card__sub {
  flex: 0 0 auto;
  font-size: 12px;
  line-height: 22px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.selected-asset-card__type {
  flex-shrink: 0;
  padding: 0 6px;
  font-size: 11px;
  line-height: 18px;
  color: var(--text-secondary);
  background-color: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.selected-asset-card__type--fund {
  color: var(--asset-type-fund);
  background-color: var(--asset-type-fund-bg);
}
.selected-asset-card__type--stock {
  color: var(--asset-type-stock);
  background-color: var(--asset-type-stock-bg);
}
.selected-asset-card__type--etf {
  color: var(--asset-type-etf);
  background-color: var(--asset-type-etf-bg);
}
.selected-asset-card__type--index {
  color: var(--asset-type-index);
  background-color: var(--asset-type-index-bg);
}
.selected-asset-card__type--bond {
  color: var(--asset-type-bond);
  background-color: var(--asset-type-bond-bg);
}
.selected-asset-card__type--crypto {
  color: var(--asset-type-crypto);
  background-color: var(--asset-type-crypto-bg);
}
.selected-asset-card__type--portfolio {
  color: var(--asset-type-portfolio);
  background-color: var(--asset-type-portfolio-bg);
}
.selected-asset-card__type--manager {
  color: var(--asset-type-manager);
  background-color: var(--asset-type-manager-bg);
}
.selected-asset-card__type--money_fund {
  color: var(--asset-type-money_fund);
  background-color: var(--asset-type-money_fund-bg);
}
.selected-asset-card__type--reverse_repo {
  color: var(--asset-type-reverse_repo);
  background-color: var(--asset-type-reverse_repo-bg);
}

/* 关键信息两列栅格：label 弱化、value 单行省略（长公司名不撑破卡片） */
.selected-asset-card__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 16px;
  margin-top: 10px;
}

.selected-asset-card__meta-item {
  display: flex;
  gap: 6px;
  align-items: baseline;
  min-width: 0;
  font-size: 12px;
  line-height: 18px;
}

.selected-asset-card__meta-item dt {
  flex-shrink: 0;
  color: var(--text-tertiary);
}

.selected-asset-card__meta-item dd {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-secondary);
  white-space: nowrap;
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

<!-- 下拉浮层样式必须放在**非 scoped** 块：el-select 的 dropdown 被 teleport 到 body，
     scoped 属性与 :deep() 都命中不到浮层 DOM。此处以 popper-class 限定作用域，
     只影响本弹窗的搜索下拉，不污染其它 el-select。 -->
<style>
/* EP 默认 .el-select-dropdown__item 是 height / line-height: 34px 的「单行」容器，
   自绘的两行内容会贴顶，视觉上就是「文字没有上下居中」（用户实测反馈）。
   这里把高度交给内容（height: auto + 上下 padding）并重置 line-height: normal，
   同时显式 flex + align-items: center 保证行内内容垂直居中；
   min-height 从 48px 降到 36px，单行选项不再显得过于高挑。 */
.add-asset-option-popper .el-select-dropdown__item {
  display: flex;
  align-items: center;
  height: auto;
  min-height: 36px;
  padding: 8px 12px;
  line-height: normal;
  white-space: normal;
}

.add-asset-option-popper .el-select-dropdown__item:not(.is-disabled):hover {
  background-color: var(--bg-hover);
}

/* 选中态回到品牌软底（与全站「软按钮」语言一致），不用 EP 默认的实心主色文字 */
.add-asset-option-popper .el-select-dropdown__item.is-selected {
  font-weight: 400;
  color: var(--text-primary);
  background-color: var(--brand-100);
}
</style>
