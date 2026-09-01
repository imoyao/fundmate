<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElDrawer, ElMessage } from "element-plus";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatQuantity } from "@/utils/format";
import type { AggregationProductGroup, AggregationSource } from "@/api/ledger";
import { allocateValue } from "@/api/positions";

/**
 * 产品详情抽屉（#1133，对齐参考截图3/4）。
 *
 * 点击产品卡片后展开的完整详情：
 * - 红色头部：基金名 + 代码
 * - 大数字锚点：资产情况（元）+ tooltip
 * - 四格信息：持有份额 / 份额日期 / 参考净值 / 净值日期
 * - 基金管理人（可点击查看联系方式）
 * - 分渠道持仓详情：每条来源展示渠道名 + 分红方式 + 份额 + 市值
 * - 扩展字段（截图4）：基金账户 / 交易账户 / 销售机构 / 分红方式
 * - 免责声明
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

/** 汇总份额 */
const totalShares = computed(() => (props.group?.quantity || 0) / 10000);
/** 汇总市值（元） */
const totalYuan = computed(() => (props.group?.market_value_cents || 0) / 100);
/** 参考净值 */
const nav = computed(() => props.group?.nav_yuan ?? null);
/** 快照日期（= 份额日期） */
const snapshotDate = computed(() => props.group?.snapshot_date ?? null);
/** 净值日期（与快照日期一致，均为导入对账日期） */
const navDate = computed(() => props.group?.snapshot_date ?? null);
/** 管理人 */
const manager = computed(() => props.group?.fund_manager ?? null);
/** 分红方式 */
const dividendPref = computed(() => props.group?.dividend_preference ?? null);
/** 来源列表（分渠道持仓明细的数据源） */
const sources = computed<AggregationSource[]>(() => props.group?.sources ?? []);
/** 是否多渠道持有 */
const multiChannel = computed(() => sources.value.length > 1);

// ── 产品维度改总价 + 按占比分摊（#1176）──
/** 是否处于编辑态 */
const editing = ref(false);
/** 编辑中的产品总价（元） */
const inputTotal = ref<number | null>(null);
/** 保存中 */
const saving = ref(false);
/** 资金进出提示（#1217）：有资金进出时引导用户在下一个开盘日更新其他存量持仓 */
const cashFlowHint = ref<string | null>(null);

/** 有来源持仓才允许改总价（后端按各来源既有市值占比分摊） */
const canEdit = computed(() => sources.value.length > 0);
/** 各账户既有市值合计（分），即分摊分母 */
const totalWeightCents = computed(() =>
  sources.value.reduce((sum, s) => sum + (s.market_value_cents || 0), 0)
);

/**
 * 分摊预览：与后端 value_allocation_service **同一算法**
 * （按既有市值占比 → 整数分四舍五入 → 尾差归占比最大一笔），
 * 保证预览值之和严格等于输入总价，与保存后的真实落库结果一致。
 */
const previewRows = computed(() => {
  const total = Number(inputTotal.value);
  const weight = totalWeightCents.value;
  if (!weight || !Number.isFinite(total) || total <= 0) return [];

  const totalCents = Math.round(total * 100);
  const weights = sources.value.map(s => s.market_value_cents || 0);
  const allocs = weights.map(w => Math.round((w * totalCents) / weight));

  const diff = totalCents - allocs.reduce((a, b) => a + b, 0);
  if (diff !== 0) {
    allocs[weights.indexOf(Math.max(...weights))] += diff;
  }

  return sources.value.map((s, i) => ({
    key: `${s.ledger_id}-${i}`,
    name: s.ledger_name || s.institution_name || "未关联账户",
    ratioText: `${((allocs[i] / totalCents) * 100).toFixed(1)}%`,
    allocatedYuan: allocs[i] / 100
  }));
});

/** 预览合计（元），恒等于输入总价（尾差已归集） */
const previewSumYuan = computed(() =>
  previewRows.value.reduce((sum, r) => sum + r.allocatedYuan, 0)
);

// 抽屉关闭时复位编辑态，避免下次打开残留上次的输入
watch(
  () => props.modelValue,
  visible => {
    if (!visible) {
      editing.value = false;
      inputTotal.value = null;
      cashFlowHint.value = null;
    }
  }
);

function startEdit() {
  inputTotal.value = Number(totalYuan.value.toFixed(2));
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  inputTotal.value = null;
  cashFlowHint.value = null;
}

async function save() {
  const total = Number(inputTotal.value);
  if (!props.group?.symbol) return;
  if (!Number.isFinite(total) || total <= 0) {
    ElMessage.warning("请输入大于 0 的产品总价");
    return;
  }
  if (totalWeightCents.value <= 0) {
    ElMessage.warning("当前各账户市值均为 0，无法按比例分摊，请先录入市值");
    return;
  }

  saving.value = true;
  try {
    const res = await allocateValue({
      symbol: props.group.symbol,
      total_value: total
    });
    const data = res?.data;
    // #1217：上次录入市值之后若发生过资金进出，「按既有市值占比」这一分摊基数
    // 已不能反映实际持有，提示用户在下一个开盘日更新其他存量持仓的总价
    cashFlowHint.value =
      data?.cash_flow_detected && data?.next_trading_day
        ? `本次分摊前该账户有资金进出记录，建议在下一个开盘日（${data.next_trading_day}）更新其他存量持仓的总价。`
        : null;
    ElMessage.success("总价已按占比分摊到各账户");
    editing.value = false;
    emit("saved");
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || "分摊失败，请稍后重试");
  } finally {
    saving.value = false;
  }
}

function close() {
  emit("update:modelValue", false);
}

/** YYYY-MM-DD → MM-DD 格式 */
function fmtShort(d: string | null): string {
  if (!d) return "--";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[2]}-${m[3]}` : d;
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
      </div>
    </template>

    <div v-if="group" class="detail-body">
      <!-- 大数字锚点（#1176：可就地改产品总价并按占比分摊） -->
      <div class="amount-anchor">
        <div class="amount-head">
          <el-tooltip
            placement="top-start"
            content="资产情况为当前持有份额 × 最新参考净值"
          >
            <div class="amount-label">资产情况(元)</div>
          </el-tooltip>
          <el-button
            v-if="!editing && canEdit"
            link
            type="primary"
            class="edit-btn"
            @click="startEdit"
          >
            更新总价
          </el-button>
        </div>

        <!-- 只读态 -->
        <MoneyDisplay
          v-if="!editing"
          :value="totalYuan"
          size="xl"
          :show-sign="false"
          :auto-color="false"
        />

        <!-- 编辑态：改总价 → 按各账户既有市值占比实时预览 → 保存落库 -->
        <template v-else>
          <el-input-number
            v-model="inputTotal"
            class="total-input"
            :min="0.01"
            :precision="2"
            :step="100"
            :controls="false"
            placeholder="请输入产品总价"
          />
          <p class="edit-hint">
            修改后将按各账户<strong>当前市值占比</strong>自动分摊（整数分，尾差归占比最大的一笔）
          </p>

          <div v-if="previewRows.length" class="preview-block">
            <div class="preview-head">
              <span class="preview-title">分摊预览</span>
              <span class="preview-sum">
                合计
                <MoneyDisplay
                  :value="previewSumYuan"
                  size="sm"
                  :show-sign="false"
                  :auto-color="false"
                />
              </span>
            </div>
            <div v-for="row in previewRows" :key="row.key" class="preview-row">
              <span class="preview-name" :title="row.name">{{ row.name }}</span>
              <span class="preview-ratio">{{ row.ratioText }}</span>
              <MoneyDisplay
                :value="row.allocatedYuan"
                size="sm"
                :show-sign="false"
                :auto-color="false"
              />
            </div>
          </div>

          <div class="edit-actions">
            <el-button type="primary" :loading="saving" @click="save">
              保存
            </el-button>
            <el-button :disabled="saving" @click="cancelEdit">取消</el-button>
          </div>
        </template>
      </div>

      <!-- 资金进出提示（#1217）：来自后端的「下一开盘日」建议 -->
      <div v-if="cashFlowHint" class="cash-flow-hint">
        <IconifyIconOffline icon="ep:warning-filled" class="hint-icon" />
        <span class="hint-text">{{ cashFlowHint }}</span>
      </div>

      <!-- 四格信息 -->
      <div class="info-grid">
        <div class="info-cell">
          <span class="cell-label">持有份额</span>
          <span class="cell-value">{{ formatQuantity(totalShares) }}</span>
        </div>
        <div class="info-cell">
          <span class="cell-label">份额日期</span>
          <span class="cell-value">{{ fmtShort(snapshotDate) }}</span>
        </div>
        <div class="info-cell">
          <span class="cell-label">参考净值</span>
          <span class="cell-value">{{
            nav != null ? nav.toFixed(4) : "--"
          }}</span>
        </div>
        <div class="info-cell">
          <span class="cell-label">净值日期</span>
          <span class="cell-value">{{ fmtShort(navDate) }}</span>
        </div>
      </div>

      <!-- 基金管理人 -->
      <div v-if="manager" class="meta-line">
        <span class="meta-label">基金管理人：</span>
        <span class="meta-value meta-link"
          >{{ manager }}
          <IconifyIconOffline icon="ep:arrow-right" class="link-icon" />
        </span>
      </div>

      <!-- 分渠道持仓详情（核心区块，对齐截图3） -->
      <section v-if="multiChannel" class="channel-section">
        <h4 class="section-title">分渠道持仓详情</h4>
        <div class="channel-list">
          <div
            v-for="(src, idx) in sources"
            :key="`${src.ledger_id}-${idx}`"
            class="channel-row"
          >
            <div class="channel-head">
              <IconifyIconOffline icon="ep:wallet" class="channel-icon" />
              <div class="channel-title">
                <!-- 销售机构：AMAC 权威全称（真实完整）；别名为辅助提示 -->
                <span class="channel-name" :title="src.institution_name || ''">
                  {{ src.institution_name || "未关联机构" }}
                </span>
                <!-- 对应账本名称 -->
                <span v-if="src.ledger_name" class="channel-ledger">
                  <IconifyIconOffline icon="ep:wallet" class="ledger-icon" />
                  {{ src.ledger_name }}
                </span>
              </div>
              <span v-if="src.fund_manager" class="channel-dividend">
                {{ src.dividend_preference || src.fund_manager }}
              </span>
            </div>
            <div class="channel-metrics">
              <span class="ch-shares">{{
                formatQuantity((src.quantity || 0) / 10000)
              }}</span>
              <MoneyDisplay
                :value="(src.market_value_cents || 0) / 100"
                size="sm"
                :show-sign="false"
                :auto-color="false"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- 单渠道时展示该渠道的详细信息（对齐截图4的扩展字段） -->
      <section v-else-if="sources.length === 1" class="single-channel-info">
        <div class="meta-line">
          <IconifyIconOffline icon="ep:wallet" class="meta-icon" />
          <span class="meta-label">销售机构：</span>
          <span class="meta-value">
            {{ sources[0].institution_name || "未关联机构" }}
            <span v-if="sources[0].institution_alias" class="meta-alias">
              ({{ sources[0].institution_alias }})
            </span>
          </span>
        </div>
        <div v-if="sources[0].ledger_name" class="meta-line">
          <IconifyIconOffline icon="ep:wallet" class="meta-icon" />
          <span class="meta-label">账本名称：</span>
          <span class="meta-value">{{ sources[0].ledger_name }}</span>
        </div>
        <div v-if="dividendPref" class="meta-line">
          <span class="meta-label">分红方式：</span>
          <span class="meta-value">{{ dividendPref }}</span>
        </div>
        <div v-if="sources[0].fund_account" class="meta-line">
          <span class="meta-label">基金账户：</span>
          <span class="meta-value mono">{{ sources[0].fund_account }}</span>
        </div>
        <div v-if="sources[0].trade_account" class="meta-line">
          <span class="meta-label">交易账户：</span>
          <span class="meta-value mono">{{ sources[0].trade_account }}</span>
        </div>
      </section>

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
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.detail-code {
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-tertiary);
}

/* ── 大数字锚点 ── */
.amount-anchor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: var(--space-5, 24px);
  border-bottom: 1px solid var(--border-light);
}

/* 标签与「更新总价」入口同一行，右侧对齐 */
.amount-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.amount-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.edit-btn {
  flex: none;
  padding: 0;
  font-size: 13px;
}

/* ── 编辑态：改总价 + 分摊预览（#1176）── */
.total-input {
  width: 100%;
  margin-top: 4px;
}

.edit-hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-tertiary);
}

.preview-block {
  padding: var(--space-3, 12px);
  margin-top: var(--space-3, 12px);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.preview-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.preview-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.preview-sum {
  display: inline-flex;
  gap: 4px;
  align-items: baseline;
  font-size: 12px;
  color: var(--text-secondary);
}

.preview-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
}

.preview-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
  white-space: nowrap;
}

.preview-ratio {
  flex: none;
  font-family: var(--font-mono);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: var(--space-4, 16px);
}

/* ── 资金进出提示（#1217）── */
.cash-flow-hint {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: var(--space-3, 12px);
  margin-top: var(--space-4, 16px);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-tertiary);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.hint-icon {
  flex: none;
  margin-top: 2px;
  font-size: 13px;
  color: var(--brand-500, #f69988);
}

.hint-text {
  min-width: 0;
  word-break: break-word;
}

/* ── 四格信息 ── */
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4, 16px);
  padding: var(--space-5, 24px) 0;
  border-bottom: 1px solid var(--border-light);
}

.info-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cell-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.cell-value {
  font-family: var(--font-mono);
  font-size: 17px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* ── 元信息行 ── */
.meta-line {
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding: var(--space-3, 12px) 0;
  font-size: 14px;
}

.meta-icon {
  flex: none;
  font-size: 14px;
  color: var(--brand-500, #f69988);

  /* 与文字基线对齐（图标为 inline-block，需手动微调） */
  transform: translateY(1px);
}

.meta-label {
  flex: none;
  color: var(--text-secondary);
}

.meta-value {
  min-width: 0;
  color: var(--text-primary);
  word-break: break-word;
}

/* 机构别名：辅助提示，弱化显示 */
.meta-alias {
  font-size: 12px;
  color: var(--text-tertiary);
}

.meta-link {
  color: var(--brand-600, #f06b57);
  cursor: pointer;
}

.link-icon {
  font-size: 12px;
  vertical-align: middle;
}

.mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

/* ── 分渠道持仓详情 ── */
.channel-section {
  margin-top: var(--space-4, 16px);
}

.section-title {
  margin-bottom: var(--space-3, 12px);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.channel-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
}

.channel-row {
  padding: var(--space-3, 12px);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.channel-head {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.channel-icon {
  flex: none;
  margin-top: 1px;
  font-size: 14px;
  color: var(--brand-500, #f69988);
}

/* 机构全称 + 账本名 竖排 */
.channel-title {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.channel-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-word;
}

.channel-ledger {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
}

.ledger-icon {
  flex: none;
  font-size: 12px;
  opacity: 0.65;
}

.channel-dividend {
  flex: none;
  padding: 2px 8px;
  margin-left: auto;
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-card);
  border-radius: var(--radius-sm);
}

.channel-metrics {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-left: 22px; /* 与图标对齐 */
}

.ch-shares {
  font-family: var(--font-mono);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

/* ── 单渠道扩展信息 ── */
.single-channel-info {
  /* 不再加 border-top：上方 .info-grid 已有 border-bottom，
     重复加会呈现「两条分割线」的观感 */
  padding-top: var(--space-2, 8px);
  margin-top: var(--space-4, 16px);
}

/* ── 免责声明 ── */
.disclaimer {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: var(--space-3, 12px);
  margin-top: var(--space-6, 28px);
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-tertiary);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.warn-icon {
  flex: none;
  margin-top: 2px;
  font-size: 13px;
  opacity: 0.5;
}
</style>
