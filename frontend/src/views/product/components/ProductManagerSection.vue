<script setup lang="ts">
import { ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  getManagerHoldings,
  getManagerProfile,
  type ManagerHoldingsResult,
  type ManagerProfileResult
} from "@/api/products";
import ManagerFundList from "./mgrSection/ManagerFundList.vue";
import ManagerHoldings from "./mgrSection/ManagerHoldings.vue";
import ManagerIdentity from "./mgrSection/ManagerIdentity.vue";

/**
 * 详情页「基金经理」区块（#1970 · 设计 §6 品类矩阵，#1970 扩展改版）。
 *
 * 取数：**两个端点并发**，互不阻塞
 * - `GET /api/products/manager-profile/` —— 经理档案 + 任职基金列表
 * - `GET /api/products/manager-holdings/` —— 代表作前十大重仓
 *
 * 拆成两个端点而不是塞在一起：重仓要按 fund_code 查最新报告期，是独立重查询，
 * 而首屏并非总需要它。分开后档案可以先渲染，重仓慢也不拖累整个区块。
 *
 * 入参是 **mgr_code 而非姓名**：库内实测 119 组重名（最多「吴昊」6 位），
 * 姓名不是唯一键。这里把路由 symbol **原样**发出去，不要在前端猜形态——
 * 自选/搜索里点进来的是 `MGR_<mgr_code>`（#1286 命名空间），而详情页路由的 symbol
 * 还会被 `resolve_product_identity` 大写化；**归一收口在后端**
 * （`services/manager_code.py`），前端若自己剥前缀，就会出现「两个地方各剥一半」。
 *
 * **换算全部交给后端**（#1970 扩展 · `services/tenure_display.py`）：
 * 本组件直接用后端给的 `*_display` 文本，**不做任何÷365 / toFixed 换算**。
 * 后端存的是为计算而存的原值（从业天数 5125、规模 307.94），展示口径收口在
 * 服务层单点——前端再写一次换算正是要消灭的那种重复，口径迟早会漂移。
 *
 * 不展示 12 位哈希（设计 §6）：经理类靠「姓名 + 公司」识别，展示哈希对用户无意义。
 *
 * ## 结构（#980 拆分）
 *
 * 主文件只留取数与三态；三块内容各自成件：
 * - `mgrSection/ManagerIdentity.vue` —— 身份行 + 指标卡 + 最佳回报 + 无任期说明
 * - `mgrSection/ManagerFundList.vue` —— 任职基金列表（含在任 / 代表作徽章）
 * - `mgrSection/ManagerHoldings.vue` —— 重仓明细（含风格标签与报表口径）
 * - `mgrSection/mgrModel.ts` —— 涨跌档位、口径文案、截断判定（纯函数，可单测）
 */
const props = defineProps<{
  /** 经理编码 mgr_code（12 位哈希），非姓名 */
  mgrCode: string;
}>();

const loading = ref(false);
const profile = ref<ManagerProfileResult | null>(null);
const failed = ref(false);

const holdings = ref<ManagerHoldingsResult | null>(null);
const holdingsFailed = ref(false);

async function load() {
  if (!props.mgrCode) return;
  loading.value = true;
  failed.value = false;
  holdingsFailed.value = false;
  // 两个端点并发：档案失败不牵连重仓，反之亦然
  const [profileRes, holdingsRes] = await Promise.allSettled([
    getManagerProfile({ mgr_code: props.mgrCode }),
    getManagerHoldings({ mgr_code: props.mgrCode })
  ]);

  if (profileRes.status === "fulfilled") {
    profile.value = profileRes.value.data;
  } else {
    // 非经理编码 / 未收录 / 网络异常：统一降级为空态，不影响详情页其余区块
    profile.value = null;
    failed.value = true;
  }

  if (holdingsRes.status === "fulfilled") {
    holdings.value = holdingsRes.value.data;
  } else {
    holdings.value = null;
    holdingsFailed.value = true;
  }

  loading.value = false;
}

watch(() => props.mgrCode, load, { immediate: true });
</script>

<template>
  <CardBlock class="mgr-section">
    <SectionHeader title="基金经理" />

    <p v-if="loading" class="mgr-section__hint">正在读取基金经理资料…</p>

    <p v-else-if="failed || !profile" class="mgr-section__hint">
      暂无可展示的基金经理资料
    </p>

    <template v-else>
      <ManagerIdentity :profile="profile" />
      <ManagerFundList :profile="profile" />
      <ManagerHoldings :holdings="holdings" :failed="holdingsFailed" />
    </template>
  </CardBlock>
</template>

<style lang="scss" scoped>
/*
 * 只留「加载 / 空态提示」这一条：其余 .mgr-section__* 都渲染在子组件里，
 * 由各子件 @use "./mgrSection/mgr-base" 承接（一份源，三处生效）。
 * 这里不整体 @use，避免把整份底座再编译一遍。
 */
.mgr-section__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}
</style>
