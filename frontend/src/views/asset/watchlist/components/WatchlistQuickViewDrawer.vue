<!--
  WatchlistQuickViewDrawer · 自选行「速览」抽屉（#1285）

  两级模型的第一步：行点击 → 抽屉（速览）→ footer「查看详情」→ 完整详情页。
  骨架、两条线、宽度与出口位置一律由 `ProductDrawer` 承担（设计
  `docs/design/product-detail-drawer.md`），本文件只决定「里面放什么」。

  内容顺序（§6）：锚点（最新价 / 组合净值）→ ①持有 → ②投顾信息 → ③成分与调仓 → ④备注。
  原先独立的「行情」区块并进锚点（同一个问题不答两遍），「信息」区块（添加自选日 /
  分组 / 标签）降为备注区末行 13px 元信息——标签与分组是管理元数据，不是决策信息。

  各区块在 `quickView/`，纯函数在 `quickView/quickViewModel.ts`，按需拉取在
  `quickView/useQuickViewDetail.ts`。
-->
<template>
  <ProductDrawer
    :model-value="modelValue"
    :name="item?.display_name || item?.symbol"
    :symbol="item?.symbol"
    :asset-type="item?.asset_type"
    :type-label="item?.type_label"
    :meta="metaParts"
    :detail-available="detailOpenable"
    :detail-hint="
      detailOpenable ? '查看完整业绩、持仓与历史记录' : '该品类暂无详情页'
    "
    :disclaimer="PRODUCT_DISCLAIMER"
    @update:model-value="emit('update:modelValue', $event)"
    @detail="goDetail"
  >
    <!-- 锚点：有价格给最新价 + 涨跌幅副行，组合给组合净值；两者都不可得则不传 anchor -->
    <template v-if="anchorKind" #anchor>
      <template v-if="anchorKind === 'price'">
        <MoneyDisplay
          :value="item?.current_price"
          :precision="precision"
          size="lg"
          :show-sign="false"
          :auto-color="false"
        />
        <div class="pd-anchor__sub">
          <RiseFallText
            v-if="hasChange"
            :value="item?.change_pct as number"
            size="sm"
          />
          <span v-else>暂无涨跌数据</span>
        </div>
      </template>
      <template v-else>
        <MoneyDisplay
          :value="item?.advisor_nav"
          size="lg"
          :precision="4"
          :show-sign="false"
          :show-currency="false"
          :auto-color="false"
        />
        <div class="pd-anchor__sub">
          <span>组合净值</span>
          <span v-if="item?.advisor_nav_date"
            >截至 {{ item?.advisor_nav_date }}</span
          >
        </div>
      </template>
    </template>

    <QuickViewHoldingSection
      v-if="isHoldable"
      :item="item"
      :precision="precision"
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

    <!-- 提醒放在备注之前：它是可执行项，备注是查阅项 -->
    <QuickViewAlertSection :item="item" />

    <QuickViewNotesSection
      :item="item"
      :meta-text="notesMeta"
      @edit-notes="emit('edit-notes', $event)"
    />
  </ProductDrawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { WatchlistItem } from "@/api/watchlist";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDrawer from "@/components/ProductDrawer/index.vue";
import { PRODUCT_DISCLAIMER } from "@/components/ProductDrawer/disclaimer";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";
import { resolveDetailPath } from "@/utils/productDetailNav";
import { isDetailAssetType } from "@/utils/productIdentity";
import {
  compositeMetaParts,
  groupNamesText,
  hasChangeOf,
  hasPriceOf,
  isHoldableType,
  isPortfolioType,
  isQiemanPlatform,
  normalizeAssetType,
  tagNamesText
} from "./quickView/quickViewModel";
import { useQuickViewDetail } from "./quickView/useQuickViewDetail";
import QuickViewHoldingSection from "./quickView/QuickViewHoldingSection.vue";
import QuickViewAdvisorSection from "./quickView/QuickViewAdvisorSection.vue";
import QuickViewAdjustSection from "./quickView/QuickViewAdjustSection.vue";
import QuickViewAlertSection from "./quickView/QuickViewAlertSection.vue";
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

const router = useRouter();

/** 有详情页的品类由 `productIdentity` 白名单单点判定（设计 §3.1） */
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
    emit("update:modelValue", false);
    await router.push(path);
  } catch {
    ElMessage.warning("未找到该产品，可能已下架或代码有误");
  }
}

const assetType = computed(() => normalizeAssetType(props.item?.asset_type));
const isHoldable = computed(() => isHoldableType(assetType.value));
const isPortfolio = computed(() => isPortfolioType(assetType.value));
const isQieman = computed(() => isQiemanPlatform(props.item?.advisor_platform));

const precision = computed(() => pricePrecision(props.item?.asset_type ?? ""));

const hasChange = computed(() => hasChangeOf(props.item));

/**
 * 锚点取值：有价格 → 最新价；组合 → 组合净值；都没有 → 不渲染锚点（§4 每抽屉恰好一个）。
 *
 * 价格这一档**按数据可得判定**而不是按「可持有品类」：原「行情」区块对所有品类都展示
 * 最新价，并进锚点后若只对可持有品类开放，指数 / 可转债行会凭空丢掉主数值。
 */
const anchorKind = computed<"price" | "nav" | null>(() => {
  if (hasPriceOf(props.item)) return "price";
  if (isPortfolio.value && props.item?.advisor_nav != null) return "nav";
  return null;
});

/** 识别信息行：平台 · 主理人 · 策略（组合）/ 所属公司（经理） */
const metaParts = computed(() =>
  compositeMetaParts(props.item, assetType.value)
);

/** 备注区末行的元信息：缺项整段跳过，用 `·` 连接（不写「—」占位） */
const notesMeta = computed(() => {
  const it = props.item;
  const parts: string[] = [];
  if (it?.created_at) parts.push(`已添加 ${formatDate(it.created_at)}`);
  const group = groupNamesText(it?.group_names);
  if (group) parts.push(`所属分组 ${group}`);
  const tags = tagNamesText(it?.tag_ids, props.allTags);
  if (tags) parts.push(`标签 ${tags}`);
  return parts.join(" · ");
});

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
