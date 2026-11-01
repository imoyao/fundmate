<template>
  <ProductDrawer
    :model-value="visible"
    :name="positionData?.name"
    :symbol="positionData?.symbol"
    :asset-type="positionData?.asset_type"
    :type-label="positionData?.type_label"
    :detail-available="detailAvailable"
    :detail-hint="
      detailAvailable ? '查看完整资料、持仓与历史记录' : '该品类暂无详情页'
    "
    :detail-loading="detailLoading"
    :disclaimer="PRODUCT_DISCLAIMER"
    @update:model-value="emit('update:visible', $event)"
    @detail="goDetail"
  >
    <!-- 锚点：持仓市值（24/600），副行是持仓盈亏 + 盈亏率（同一件事的绝对值与比率） -->
    <template #anchor>
      <MoneyDisplay
        :value="anchor.value"
        size="lg"
        :show-sign="false"
        :auto-color="false"
      />
      <div v-if="anchor.hasSub" class="pd-anchor__sub">
        <template v-if="anchor.pnl != null || anchor.pnlRate != null">
          <span>持仓盈亏</span>
          <MoneyDisplay
            v-if="anchor.pnl != null"
            :value="anchor.pnl"
            size="sm"
          />
          <RiseFallText
            v-if="anchor.pnlRate != null"
            :value="anchor.pnlRate"
            size="sm"
          />
        </template>
        <template v-else-if="anchor.xirrLoading">
          <span>年化收益率 计算中…</span>
        </template>
        <template v-else>
          <span>年化收益率</span>
          <span :style="{ color: xirrColor(anchor.xirr) }">
            {{ formatXirr(anchor.xirr) }}
          </span>
        </template>
      </div>
    </template>

    <!-- 键值网格：份额 / 成本 / 净值 / 时长 / 年化（市值与盈亏已升到锚点） -->
    <DrawerSection title="持仓概况">
      <PositionSummaryGrid
        :position-data="positionData"
        :xirr="xirr"
        :loading-xirr="loadingXirr"
      />
    </DrawerSection>

    <!-- 交易明细（抽屉 destroy-on-close：打开即取数，关闭即重置） -->
    <PositionTransactionsList
      :position-id="positionData?.id"
      :asset-type="positionData?.asset_type"
      :symbol="positionData?.symbol"
      :is-fund="isFund"
    />
  </ProductDrawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { getPositionXirr } from "@/api/performance";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDrawer from "@/components/ProductDrawer/index.vue";
import DrawerSection from "@/components/ProductDrawer/DrawerSection.vue";
import { PRODUCT_DISCLAIMER } from "@/components/ProductDrawer/disclaimer";
import { resolveDetailPath } from "@/utils/productDetailNav";
import { isDetailAssetType } from "@/utils/productIdentity";
import PositionSummaryGrid from "./PositionSummaryGrid.vue";
import PositionTransactionsList from "./PositionTransactionsList.vue";
import {
  buildAnchor,
  formatXirr,
  isFundPosition,
  xirrColor,
  type PositionLike
} from "./positionSummaryModel";

/**
 * 持仓明细抽屉（#980 拆分）。
 *
 * 骨架（宽度 / 两条线 / 区块标题 / 唯一出口）全部由 `ProductDrawer` 承担；
 * 头部原先由 `PositionDrawerHeader.vue` 自绘，职责已并入外壳，该文件已删除。
 * 本文件只剩：跳详情的路由副作用、XIRR 取数、锚点与区块的编排。
 *
 * 已删除（设计 §6.1）：「历史价格与成本曲线（数据依赖 P1-20 定时任务同步）」
 * 空壳块——它把内部工单号写进界面，读起来像「图坏了」。
 */
const props = defineProps<{
  visible: boolean;
  positionData: PositionLike | null;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
}>();

const router = useRouter();
const detailLoading = ref(false);

/** 品类白名单单点判定：没有详情页就不渲染按钮，只留原因（§5） */
const detailAvailable = computed(() =>
  isDetailAssetType(props.positionData?.asset_type)
);

/**
 * 跳详情页（#1965）。
 *
 * 持仓行带 `asset_type` 但**没有 venue**（持仓表不存交易场所），故不传——
 * 由后端 resolve 按品类兜底（fund → OTC），不在前端编造场所。
 */
async function goDetail() {
  const pos = props.positionData;
  if (!pos?.symbol || detailLoading.value) return;
  detailLoading.value = true;
  try {
    const path = await resolveDetailPath({
      symbol: pos.symbol,
      assetType: pos.asset_type,
      market: pos.market
    });
    if (!path) {
      ElMessage.warning("该品类详情页暂未开放");
      return;
    }
    // 先关抽屉再跳（沿用 TransactionDrawer 的既有范式）
    emit("update:visible", false);
    await router.push(path);
  } catch {
    ElMessage.warning("未找到该产品，可能已下架或代码有误");
  } finally {
    detailLoading.value = false;
  }
}

/** 基金类型判断（基金/货币基金） */
const isFund = computed(() => isFundPosition(props.positionData?.asset_type));

// 年化收益率（XIRR，#862 / #796）：单持仓维度，开抽屉时拉取
const loadingXirr = ref(false);
const xirr = ref<number | null>(null);

/** 锚点模型：主数值 + 副行（盈亏 / 盈亏率 / 年化兜底） */
const anchor = computed(() =>
  buildAnchor(props.positionData, xirr.value, loadingXirr.value)
);

async function fetchXirr() {
  const id = props.positionData?.id;
  if (!id) {
    xirr.value = null;
    return;
  }
  loadingXirr.value = true;
  try {
    const res = await getPositionXirr(id as number);
    const data = res?.data;
    // xirr 为小数（0.1234=12.34%）；无现金流/无法计算时后端可能不返回该字段
    xirr.value = typeof data?.xirr === "number" ? data.xirr : null;
  } catch {
    xirr.value = null;
  } finally {
    loadingXirr.value = false;
  }
}

// 监听抽屉打开事件，触发年化收益率加载（交易明细由子组件自取）
watch(
  () => props.visible,
  newVal => {
    if (newVal) {
      fetchXirr();
    }
  }
);
</script>
