<!--
  WatchlistQuickViewDrawer · 自选行「速览」抽屉（#1285）

  设计文档「行内交互：抽屉 vs 详情页」两级模型的第一步：
  行点击 → 抽屉（速览）→ 抽屉内「查看详情」→ 完整详情页。

  本版本为**速览版**：展示当前可得的通用字段（行情 / 持有 / 信息 / 备注）。
  品种专属维度（指数估值、可转债条款、投顾持仓等）待数据底座落地后增量补充；
  详情页入口已于 #1965 启用（跳 ProductDetail）；一期仅 fund / stock / manager 可跳，
  其余品类按钮禁用并说明「暂未开放」，不静默失败。

  可持有品类判定与列配置层一致：index / manager / portfolio 不展示「持有」区。

  各区块已拆到 `quickView/`（头部 / 行情 / 持有 / 信息 / 投顾 / 成分与调仓 / 备注），
  纯函数在 `quickView/quickViewModel.ts`，按需拉取在 `quickView/useQuickViewDetail.ts`。
-->
<template>
  <el-drawer
    v-model="visible"
    title="速览"
    size="420px"
    direction="rtl"
    destroy-on-close
  >
    <div v-if="item" class="wqv">
      <QuickViewHead
        :item="item"
        :is-composite="isComposite"
        :composite-meta="compositeMeta"
      />

      <QuickViewQuoteSection :item="item" :precision="precision" />

      <QuickViewHoldingSection
        v-if="isHoldable"
        :item="item"
        :precision="precision"
      />

      <QuickViewInfoSection
        :item="item"
        :group-text="groupText"
        :tag-text="tagText"
      />

      <QuickViewAdvisorSection v-if="isPortfolio" :item="item" />

      <QuickViewAdjustSection
        v-if="isPortfolio"
        :loading="detailLoading"
        :error="detailError"
        :holdings-count="holdingsCount"
        :missing-count="missingCount"
        :adjust-groups="adjustGroups"
        :is-qieman="isQieman"
      />

      <QuickViewNotesSection
        :item="item"
        @edit-notes="emit('edit-notes', $event)"
      />

      <!-- 详情页入口（#1965 启用）：一期只开放 fund / stock / manager（设计 §3.1），
           其余品类按钮禁用并说明原因，不静默失败 -->
      <div class="wqv-footer">
        <el-button :disabled="!detailOpenable" @click="goDetail"
          >查看详情</el-button
        >
        <span class="wqv-hint">{{
          detailOpenable ? "查看完整资料与持仓" : "该品类详情页暂未开放"
        }}</span>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { WatchlistItem } from "@/api/watchlist";
import { pricePrecision } from "@/utils/pricePrecision";
import { resolveDetailPath } from "@/utils/productDetailNav";
import { isDetailAssetType } from "@/utils/productIdentity";
import {
  compositeMetaOf,
  groupTextOf,
  isCompositeType,
  isHoldableType,
  isPortfolioType,
  isQiemanPlatform,
  normalizeAssetType,
  tagTextOf
} from "./quickView/quickViewModel";
import { useQuickViewDetail } from "./quickView/useQuickViewDetail";
import QuickViewHead from "./quickView/QuickViewHead.vue";
import QuickViewQuoteSection from "./quickView/QuickViewQuoteSection.vue";
import QuickViewHoldingSection from "./quickView/QuickViewHoldingSection.vue";
import QuickViewInfoSection from "./quickView/QuickViewInfoSection.vue";
import QuickViewAdvisorSection from "./quickView/QuickViewAdvisorSection.vue";
import QuickViewAdjustSection from "./quickView/QuickViewAdjustSection.vue";
import QuickViewNotesSection from "./quickView/QuickViewNotesSection.vue";

const props = defineProps<{
  modelValue: boolean;
  item: WatchlistItem | null;
  /** 全部标签（用于 tag_ids → 名称映射，与表格渲染同一份数据） */
  allTags?: { id: number; name: string; color?: string | null }[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  /** 点击「编辑」→ 由页面打开备注编辑弹窗（复用 #1285 的 NotesEditorDialog） */
  "edit-notes": [item: WatchlistItem];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const router = useRouter();

/** 有详情页的品类由 `productIdentity` 白名单单点判定（设计 §3.1）。
 *  已开放：fund / stock / manager / portfolio（#1975）/ etf（#1974）；
 *  未开放品类（如 bond、index）在此禁用并说明原因，不在这里另写一份名单。 */
const detailOpenable = computed(() =>
  isDetailAssetType(props.item?.asset_type)
);

async function goDetail() {
  const it = props.item;
  if (!it) return;
  try {
    // 字段齐全时内部直接拼路径；缺失则回后端问权威品类（前端不推断）
    const path = await resolveDetailPath({
      symbol: it.symbol,
      assetType: it.asset_type,
      market: it.market,
      venue: it.venue
    });
    if (!path) {
      ElMessage.warning("该品类详情页暂未开放");
      return;
    }
    // 先关抽屉再跳：否则抽屉会盖住刚打开的详情页
    visible.value = false;
    await router.push(path);
  } catch {
    ElMessage.warning("未找到该产品，可能已下架或代码有误");
  }
}

const assetType = computed(() => normalizeAssetType(props.item?.asset_type));
const isComposite = computed(() => isCompositeType(assetType.value));
const isHoldable = computed(() => isHoldableType(assetType.value));
const isPortfolio = computed(() => isPortfolioType(assetType.value));
const isQieman = computed(() => isQiemanPlatform(props.item?.advisor_platform));

const precision = computed(() => pricePrecision(props.item?.asset_type ?? ""));

const compositeMeta = computed(() =>
  compositeMetaOf(props.item, assetType.value)
);
const groupText = computed(() => groupTextOf(props.item?.group_names));
const tagText = computed(() => tagTextOf(props.item?.tag_ids, props.allTags));

const {
  detailLoading,
  detailError,
  holdingsCount,
  missingCount,
  adjustGroups
} = useQuickViewDetail({
  open: () => props.modelValue,
  symbol: () => props.item?.symbol ?? undefined,
  isPortfolio: () => isPortfolio.value
});
</script>

<style scoped>
/* 抽屉容器：各区块自带 `quickView/_wqv-base.scss` 里的共用骨架（scoped 只作用于
   本组件的元素，子组件内部拿不到这里的类名） */
.wqv {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
}

.wqv-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-top: var(--space-2, 8px);
  border-top: 1px solid var(--border-light);
}

.wqv-hint {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
