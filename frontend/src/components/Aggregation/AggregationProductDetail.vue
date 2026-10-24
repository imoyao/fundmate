<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElDrawer, ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { AggregationProductGroup } from "@/api/ledger";
import { resolveDetailPath } from "@/utils/productDetailNav";
import AggregationAmountAnchor from "./aggregationProductDetail/AggregationAmountAnchor.vue";
import AggregationHoldingsSection from "./aggregationProductDetail/AggregationHoldingsSection.vue";

/**
 * 产品详情抽屉（#1133，对齐参考截图3/4）。
 *
 * 点击产品卡片后展开的完整详情：
 * - 红色头部：基金名 + 代码
 * - 大数字锚点：资产情况（元）+ tooltip（含改总价分摊 #1176）
 * - 四格信息：持有份额 / 份额日期 / 参考净值 / 净值日期
 * - 基金管理人（可点击查看联系方式）
 * - 分渠道持仓详情：每条来源展示渠道名 + 分红方式 + 份额 + 市值
 * - 扩展字段（截图4）：基金账户 / 交易账户 / 销售机构 / 分红方式
 * - 免责声明
 *
 * #980 拆分：换算与文案进 `aggregationProductDetail/aggregationDetailModel.ts`，
 * 大数字锚点（含分摊编辑态与资金进出提示）与持仓信息区各成一个组件，
 * 本文件只留抽屉外壳、头部与「查看详情」跳转。
 */
defineOptions({ name: "AggregationProductDetail" });

const props = withDefaults(
  defineProps<{
    /** 是否展示 */
    modelValue?: boolean;
    /** 产品聚合数据 */
    group?: AggregationProductGroup | null;
  }>(),
  {
    modelValue: false,
    group: null
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  /** 总价分摊保存成功；调用方需刷新聚合数据（#1176） */
  (e: "saved"): void;
}>();

const router = useRouter();
const detailLoading = ref(false);

/**
 * 跳详情页（#1965）。
 *
 * 聚合分组**只有 symbol**——没有 asset_type / market / venue，故一律回后端取权威品类
 * （设计 §3.3：前端不推断）。按既有范式「先关抽屉再跳」，否则抽屉会盖住详情页。
 */
async function goDetail() {
  const g = props.group;
  if (!g?.symbol || detailLoading.value) return;
  detailLoading.value = true;
  try {
    const path = await resolveDetailPath({ symbol: g.symbol });
    if (!path) {
      ElMessage.warning("该品类详情页暂未开放");
      return;
    }
    emit("update:modelValue", false);
    await router.push(path);
  } catch {
    ElMessage.warning("未找到该产品，可能已下架或代码有误");
  } finally {
    detailLoading.value = false;
  }
}

function close() {
  emit("update:modelValue", false);
}

/** 分摊保存成功：向上转发，调用方据此刷新聚合数据 */
function handleSaved() {
  emit("saved");
}
</script>

<template>
  <ElDrawer
    :model-value="modelValue"
    direction="rtl"
    size="420px"
    :show-close="true"
    class="product-detail-drawer"
    @close="close"
  >
    <!-- 红色头部 -->
    <template #header>
      <div class="detail-header">
        <p class="detail-name" :title="group?.name">
          {{ group?.name || "--" }}
        </p>
        <p class="detail-code">{{ group?.symbol }}</p>
        <!-- #1965：聚合分组只有 symbol（无 asset_type / market / venue），
             点击时回后端问权威品类（前端不推断、不剥前缀） -->
        <el-button text size="small" :loading="detailLoading" @click="goDetail">
          查看详情
        </el-button>
      </div>
    </template>

    <div v-if="group" class="detail-body">
      <AggregationAmountAnchor
        :group="group"
        :visible="modelValue"
        @saved="handleSaved"
      />

      <AggregationHoldingsSection :group="group" />

      <!-- 免责声明 -->
      <p class="disclaimer">
        <IconifyIconOffline icon="ep:warning-filled" class="warn-icon" />
        基金有风险，投资需谨慎。以上数据仅供参考，不构成投资建议。
        净值数据可能存在延迟，请以基金公司官方披露为准。
      </p>
    </div>
  </ElDrawer>
</template>

<style scoped>
/* ── 头部 ── */
.detail-header {
  padding: 0;
}

.detail-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.detail-code {
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* ── 免责声明 ── */
.disclaimer {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: var(--space-3, 12px);
  margin-top: var(--space-6);
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.warn-icon {
  flex: none;
  margin-top: 2px;
  font-size: var(--text-label);
  opacity: 0.5;
}
</style>
