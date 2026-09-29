<template>
  <!-- ── 步骤二：对账结果（显隐由 index.vue 的 v-else-if 编排，此处 v-if 负责收窄 result 类型） ── -->
  <template v-if="p.result">
    <MetricGrid class="result-grid">
      <MetricCard
        title="自动归因"
        :value="p.result.auto_attributed"
        featured
        caption="已归因至对应销售渠道"
      />
      <MetricCard
        title="已核对"
        :value="p.result.verified"
        caption="与系统份额一致"
      />
      <MetricCard
        title="冲突"
        :value="p.result.conflicts"
        caption="需人工决策，前往对账中心处理"
      />
      <MetricCard
        title="跳过"
        :value="p.result.ignored_skipped + p.result.attributed_skipped"
        :caption="`已忽略 ${p.result.ignored_skipped} 条 · 防复活跳过 ${p.result.attributed_skipped} 条`"
      />
      <MetricCard
        title="失败"
        :value="p.result.failed_rows.length"
        caption="解析或落库失败，见下方明细"
      />
    </MetricGrid>

    <!-- 有冲突：品牌色提示 banner（提示性信息，非危险操作）+ 跳转对账中心 -->
    <div v-if="p.result.conflicts > 0" class="conflict-banner" role="alert">
      <div class="conflict-banner__text">
        <IconifyIconOffline
          icon="ep:warning-filled"
          class="conflict-banner__icon"
        />
        <span>
          存在 {{ p.result.conflicts }} 条冲突：渠道已有持仓但份额与
          E账户不一致， 需要逐条决策「归因覆盖」或「忽略」
        </span>
      </div>
      <el-button type="primary" @click="p.goToReconcileCenter">
        前往对账中心处理
        <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
      </el-button>
    </div>

    <!-- 无冲突：完成态 -->
    <div v-else-if="p.result.failed_rows.length === 0" class="done-card">
      <IconifyIconOffline icon="ep:success-filled" class="done-card__icon" />
      <p class="done-card__title">对账完成</p>
      <p class="done-card__desc">
        E账户快照已自动归因至对应销售渠道，无需人工处理
      </p>
    </div>

    <!-- 冲突明细：简要清单（symbol + 渠道 + 份额差异） -->
    <div v-if="p.conflictList.length > 0" class="detail-card">
      <SectionHeader
        title="冲突明细"
        :info="'共 ' + p.conflictList.length + ' 条，可在对账中心逐条决策'"
      />
      <ul class="conflict-list">
        <li
          v-for="item in p.conflictList"
          :key="item.record_id"
          class="conflict-list__item"
        >
          <span class="conflict-list__name">{{
            item.name || item.symbol
          }}</span>
          <span class="conflict-list__symbol">{{ item.symbol }}</span>
          <span class="conflict-list__detail">
            渠道「{{ item.target_ledger_name || "对应渠道" }}」{{
              formatQuantity(item.current_quantity)
            }}
            份 vs E账户 {{ formatQuantity(item.eaccount_quantity) }} 份
            <span class="conflict-list__diff"
              >差 {{ formatQuantity(item.diff_quantity) }} 份</span
            >
          </span>
        </li>
      </ul>
    </div>

    <!-- 失败行：原因列表 -->
    <div v-if="p.failedList.length > 0" class="detail-card">
      <SectionHeader
        title="失败明细"
        :info="'共 ' + p.failedList.length + ' 条，多为缺净值或成本数据'"
      />
      <ul class="failed-list">
        <li
          v-for="(item, index) in p.failedList"
          :key="index"
          class="failed-list__item"
        >
          <span class="failed-list__line">第 {{ item.line }} 行</span>
          <span class="failed-list__symbol">{{ item.symbol || "--" }}</span>
          <span class="failed-list__reason">{{ item.reason }}</span>
        </li>
      </ul>
    </div>

    <!-- 底部操作 -->
    <div class="result-actions">
      <el-button @click="p.resetFlow">
        <IconifyIconOffline icon="ep:refresh-left" class="mr-1" />
        重新导入
      </el-button>
      <el-button type="primary" @click="p.goToReconcileCenter">
        前往对账中心
      </el-button>
    </div>
  </template>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { formatQuantity } from "@/utils/format";
import type { useEaccountImport } from "../composables/useEaccountImport";

defineOptions({ name: "EaccountReconcileResult" });

const props = defineProps<{ page: ReturnType<typeof useEaccountImport> }>();

/**
 * 共享状态单体（useEaccountImport）的响应式视图（#980 P1-A 同款）。
 * 根部 `v-if="p.result"` 与拆分前 `<template v-else-if="result">` 的分支条件等价
 * （index.vue 保留步骤一 v-if / 本组件 v-else-if 的原始链条），并承担 result 的类型收窄。
 */
const p = reactive(props.page);
</script>

<style scoped>
/* ===== 结果区 ===== */
.result-grid {
  margin-bottom: var(--space-standard);
}

/* 冲突提示 banner：品牌色态（design.md「提示性 Banner 品牌色规范」） */
.conflict-banner {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-compact);
  margin-bottom: var(--space-standard);
  background: var(--brand-100);
  border-radius: var(--radius-lg);
}

.conflict-banner__text {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  min-width: 0;
  font-size: var(--text-small);
  color: var(--brand-700);
}

.conflict-banner__icon {
  flex-shrink: 0;
}

/* 无冲突完成态 */
.done-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-loose) 0;
  margin-bottom: var(--space-standard);
  text-align: center;
}

.done-card__icon {
  font-size: 40px;
  color: var(--color-success-ink);
}

.done-card__title {
  margin: 0;
  font-size: var(--text-heading);
  font-weight: 600;
  color: var(--text-primary);
}

.done-card__desc {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

/* 明细卡片：冲突 + 失败 */
.detail-card {
  padding: var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.conflict-list,
.failed-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.conflict-list__item {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-2) 0;
  font-size: var(--text-small);
  border-bottom: 1px solid var(--border-subtle);
}

.conflict-list__item:last-child {
  border-bottom: none;
}

.conflict-list__name {
  font-weight: 500;
  color: var(--text-primary);
}

.conflict-list__symbol {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.conflict-list__detail {
  flex: 1;
  color: var(--text-secondary);
  text-align: right;
}

.conflict-list__diff {
  font-weight: 500;
  color: var(--color-rise-ink);
}

/* 失败行：中性弱化，不喧宾夺主 */
.failed-list__item {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-2) 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.failed-list__item:last-child {
  border-bottom: none;
}

.failed-list__line {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.failed-list__symbol {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.result-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
