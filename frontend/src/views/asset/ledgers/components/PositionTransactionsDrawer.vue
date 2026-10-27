<template>
  <el-drawer
    v-model="drawerVisible"
    size="680px"
    direction="rtl"
    destroy-on-close
    title="持仓明细"
  >
    <!-- 1. 顶部：持仓名称与信息 -->
    <PositionDrawerHeader
      :position-data="positionData"
      :detail-loading="detailLoading"
      @detail="goDetail"
    />

    <!-- 2. 核心摘要卡片 -->
    <PositionSummaryGrid
      :position-data="positionData"
      :xirr="xirr"
      :loading-xirr="loadingXirr"
    />

    <!-- 3. 走势图区 -->
    <div
      class="mb-5 p-4 bg-gray-50 rounded-lg border border-dashed flex items-center justify-center"
      :style="{ borderColor: 'var(--border-default)' }"
    >
      <div
        class="text-xs text-center leading-relaxed"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        <IconifyIconOffline
          icon="ep:trend-charts"
          class="text-lg block mx-auto mb-1"
        />
        历史价格与成本曲线<br />
        <span class="text-[10px]">(数据依赖 P1-20 定时任务同步)</span>
      </div>
    </div>

    <!-- 4. 交易明细列表（抽屉 destroy-on-close：打开即取数，关闭即重置） -->
    <PositionTransactionsList
      :position-id="positionData?.id"
      :asset-type="positionData?.asset_type"
      :symbol="positionData?.symbol"
      :is-fund="isFund"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getPositionXirr } from "@/api/performance";
import { resolveDetailPath } from "@/utils/productDetailNav";
import PositionDrawerHeader from "./PositionDrawerHeader.vue";
import PositionSummaryGrid from "./PositionSummaryGrid.vue";
import PositionTransactionsList from "./PositionTransactionsList.vue";
import { isFundPosition, type PositionLike } from "./positionSummaryModel";

/**
 * 持仓明细抽屉（#980 拆分）。
 *
 * 原 494 行里约 300 行是模板：头部、8 张摘要卡、走势图占位、交易明细各段
 * 结构互不相干。现在按段拆为三个子件：
 * - `PositionDrawerHeader.vue`：名称 / 代码 / 品类 + 查看详情入口；
 * - `PositionSummaryGrid.vue`：8 张卡片（数据由 `positionSummaryModel.ts` 产出）；
 * - `PositionTransactionsList.vue`：交易明细与行内编辑弹窗（自管取数与重置）。
 * 本文件只保留抽屉外壳、跳详情的路由副作用与 XIRR 取数。
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
      market: (pos as any).market
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

// 抽屉双向绑定
const drawerVisible = computed({
  get: () => props.visible,
  set: val => emit("update:visible", val)
});

// 年化收益率（XIRR，#862 / #796）：单持仓维度，开抽屉时拉取
const loadingXirr = ref(false);
const xirr = ref<number | null>(null);

async function fetchXirr() {
  const id = props.positionData?.id;
  if (!id) {
    xirr.value = null;
    return;
  }
  loadingXirr.value = true;
  try {
    const res = await getPositionXirr(id as number);
    const data = (res as any)?.data;
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
