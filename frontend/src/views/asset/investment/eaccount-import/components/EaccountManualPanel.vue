<template>
  <!-- 手动录入模式（#1788 第三分段，承接 #929 路径 1「手动表单只落持仓、不建流水」）。
       流程：选账户 → 逐行填写 → 生成预览 → 复用 EaccountParsePreview 逐行核对 →
       confirmHoldingImport 落 positions。全程不经过 e-account/reconcile。 -->
  <div class="manual-panel">
    <!-- ── 归属账户（面板级）──
         按用户口径：先选账户、再录该账户下的持仓；不做逐行账户，也不默认选中第一个账户——
         持仓归属是用户决策，替他默认等于把仓位记到错误的账本上。 -->
    <div class="manual-panel__ledger">
      <div class="manual-panel__ledger-label">
        <IconifyIconOffline
          icon="ep:wallet"
          class="manual-panel__ledger-icon"
        />
        归属账户
        <span class="manual-panel__required">*</span>
      </div>
      <el-select
        v-model="p.manualLedgerId"
        class="manual-panel__ledger-select"
        placeholder="请选择本次持仓要归入的账户"
        filterable
      >
        <el-option
          v-for="l in p.manualLedgers"
          :key="l.id"
          :label="l.name"
          :value="l.id"
        />
      </el-select>
      <p class="manual-panel__ledger-hint">本次录入的全部持仓都会归入该账户</p>
    </div>

    <div v-if="p.manualLedgers.length === 0" class="manual-panel__block">
      <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
      暂无可用账户 —— 请先到「账户」页新建账户，再回来录入持仓。
    </div>

    <template v-else>
      <!-- 行录入表格：横向可滚动，窄屏不挤压数字列 -->
      <div class="manual-panel__table-wrap">
        <table class="manual-table">
          <thead>
            <tr>
              <th class="col-symbol">代码</th>
              <th class="col-name">名称</th>
              <th class="col-type">类型</th>
              <th class="col-num">份额</th>
              <th class="col-num">成本价</th>
              <th class="col-num">市值</th>
              <th class="col-date">快照日</th>
              <th class="col-op" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in p.manualRows" :key="row.key">
              <td class="col-symbol">
                <el-input v-model="row.symbol" placeholder="如 110011" />
              </td>
              <td class="col-name">
                <el-input v-model="row.name" placeholder="如 易方达中小盘" />
              </td>
              <td class="col-type">
                <el-select v-model="row.type">
                  <el-option
                    v-for="opt in MANUAL_TYPE_OPTIONS"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </td>
              <td class="col-num">
                <el-input-number
                  v-model="row.quantity"
                  :min="0"
                  :precision="4"
                  :controls="false"
                  placeholder="0"
                />
              </td>
              <td class="col-num">
                <el-input-number
                  v-model="row.price"
                  :min="0"
                  :precision="4"
                  :controls="false"
                  placeholder="0"
                />
              </td>
              <!-- 市值是派生列：后端只有单个 price（同时当成本价与现价），份额×成本价才与落库口径一致 -->
              <td class="col-num manual-table__derived">
                {{ derivedAmount(row) }}
              </td>
              <td class="col-date">
                <el-date-picker
                  v-model="row.snapshot_date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  :clearable="false"
                  placeholder="快照日"
                />
              </td>
              <td class="col-op">
                <button
                  v-if="p.manualRows.length > 1"
                  type="button"
                  class="manual-table__del"
                  :aria-label="`删除第 ${row.key} 行`"
                  @click="removeRow(row)"
                >
                  <IconifyIconOffline icon="ep:close" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="manual-panel__toolbar">
        <el-button plain @click="p.addManualRow()">
          <IconifyIconOffline icon="ep:plus" class="mr-1" />
          添加一行
        </el-button>
        <span class="manual-panel__count">共 {{ p.manualRows.length }} 行</span>
      </div>

      <p class="manual-panel__hint">
        类型决定代码形态：基金按场外 6 位码；股票 / ETF /
        可转债落场内，代码会自动补交易所前缀。
      </p>

      <el-button
        type="primary"
        class="manual-panel__submit"
        :disabled="problem !== null"
        @click="p.generateManualPreview()"
      >
        生成预览
      </el-button>
      <p v-if="problem" class="manual-panel__problem">
        <IconifyIconOffline icon="ep:info-filled" class="mr-1" />
        {{ problem }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getTypeLabel } from "@/constants/assetType";
import type {
  ManualHoldingDraft,
  useEaccountImport
} from "../composables/useEaccountImport";

defineOptions({ name: "EaccountManualPanel" });

/** 资产类型候选：只放可交易持仓四类（AGENTS「持仓与资产」），标签取自 ASSET_TYPE_LABELS 权威映射 */
const MANUAL_TYPE_OPTIONS = ["fund", "stock", "etf", "bond"].map(v => ({
  value: v,
  label: getTypeLabel(v)
}));

const props = defineProps<{ page: ReturnType<typeof useEaccountImport> }>();

/**
 * 共享状态单体（useEaccountImport）的响应式视图：
 * reactive 解包嵌套 ref，模板内 v-model 写回同一实例（与 EaccountAiPanel 同款）。
 * 外层显隐（!parsedOk && importMode === 'manual'）由 index.vue 编排。
 */
const p = reactive(props.page);

/** 派生市值（元）：份额 × 成本价，固定两位，空值显示 -- */
function derivedAmount(row: ManualHoldingDraft): string {
  const q = Number(row.quantity) || 0;
  const price = Number(row.price) || 0;
  if (q <= 0 || price <= 0) return "--";
  return (q * price).toFixed(2);
}

/** 按 key 删除（不用索引：index 作 key 在 splice 后会让输入框内容错位） */
function removeRow(row: ManualHoldingDraft): void {
  const idx = p.manualRows.findIndex(r => r.key === row.key);
  if (idx >= 0) p.removeManualRow(idx);
}

/** 一行都没填（全默认值）时给更贴合的提示，而不是「第 1 行：请填写代码」 */
const allBlank = computed(() =>
  p.manualRows.every(
    r =>
      !r.symbol.trim() && !r.name.trim() && !(r.quantity > 0) && !(r.price > 0)
  )
);

/** 阻断「生成预览」的首个问题；null 表示可提交 */
const problem = computed<string | null>(() => {
  if (p.manualLedgerId == null) return "请先选择归属账户";
  if (allBlank.value)
    return "请先填写至少一条持仓（代码 / 名称 / 份额 / 成本价）";
  return p.validateManualRows();
});
</script>

<style scoped>
/* ===== 手动录入面板：外观基线与 AI 面板一致（同页同级卡片） ===== */
.manual-panel {
  padding: var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.manual-panel__ledger {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  padding-bottom: var(--space-standard);
  margin-bottom: var(--space-standard);
  border-bottom: 1px solid var(--border-light);
}

.manual-panel__ledger-label {
  display: flex;
  gap: 4px;
  align-items: center;
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.manual-panel__ledger-icon {
  color: var(--brand-600);
}

.manual-panel__required {
  color: var(--danger);
}

.manual-panel__ledger-select {
  width: 240px;
}

.manual-panel__ledger-hint {
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.manual-panel__block {
  font-size: var(--text-small);
  color: var(--text-secondary);
}

/* 横向滚动：7 列在窄屏不挤压数字列 */
.manual-panel__table-wrap {
  overflow-x: auto;
}

.manual-table {
  width: 100%;
  font-size: var(--text-small);
  border-collapse: collapse;
}

.manual-table th {
  padding: 0 var(--space-2) var(--space-2);
  font-weight: 600;
  color: var(--text-secondary);
  text-align: left;
  white-space: nowrap;
}

.manual-table td {
  padding: var(--space-1) var(--space-2);
  vertical-align: middle;
  border-top: 1px solid var(--border-light);
}

.manual-table .col-symbol {
  width: 120px;
}

.manual-table .col-name {
  min-width: 150px;
}

.manual-table .col-type {
  width: 110px;
}

.manual-table .col-num {
  width: 120px;
}

.manual-table .col-date {
  width: 150px;
}

.manual-table .col-op {
  width: 40px;
  text-align: center;
}

/* 派生列：数字右对齐 + 降一级视觉权重，明确「不是可编辑项」 */
.manual-table__derived {
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  text-align: right;
}

.manual-table__del {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  color: var(--text-tertiary-ink);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
}

.manual-table__del:hover {
  color: var(--danger);
  background: var(--bg-hover);
}

.manual-panel__toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-2);
}

.manual-panel__count {
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.manual-panel__hint {
  margin-top: var(--space-compact);
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.manual-panel__submit {
  display: block;
  width: 100%;
  margin-top: var(--space-standard);
}

.manual-panel__problem {
  display: flex;
  align-items: center;
  margin-top: var(--space-2);
  font-size: var(--text-small);
  color: var(--text-secondary);
}
</style>
