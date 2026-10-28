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
        caption="需逐条决策"
      />
      <MetricCard
        title="跳过"
        :value="p.result.ignored_skipped + p.result.attributed_skipped"
        :caption="`已忽略 ${p.result.ignored_skipped} 条 · 防复活跳过 ${p.result.attributed_skipped} 条`"
      />
      <MetricCard
        title="失败"
        :value="p.result.failed_rows.length"
        caption="解析或落库失败的行"
      />
    </MetricGrid>

    <!-- 有冲突：品牌色提示条（提示性信息，非危险操作）。它只陈述事实与两条决策口径
         （「归因覆盖」/「忽略」），不放按钮——唯一主入口是底部操作栏；此前提示条里的同名
         按钮与底栏按钮、页头链接三处指向同一路由，用户无从判断该点哪个。 -->
    <div v-if="p.result.conflicts > 0" class="conflict-banner" role="alert">
      <IconifyIconOffline
        icon="ep:warning-filled"
        class="conflict-banner__icon"
      />
      <p class="conflict-banner__text">
        存在 {{ p.result.conflicts }} 条冲突：渠道已有持仓但份额与
        E账户不一致，需逐条决策「归因覆盖」或「忽略」
      </p>
    </div>

    <!-- 无冲突：完成态 -->
    <div v-else-if="p.result.failed_rows.length === 0" class="done-card">
      <IconifyIconOffline icon="ep:success-filled" class="done-card__icon" />
      <p class="done-card__title">对账完成</p>
      <p class="done-card__desc">
        E账户快照已自动归因至对应销售渠道，无需人工处理
      </p>
    </div>

    <!-- 冲突明细：简要清单（symbol + 渠道 + 份额差异）。
         区块卡容器走 CardBlock（区块自身带 SectionHeader ⇒ 属页面级区块，必须复用）。 -->
    <CardBlock v-if="p.conflictList.length > 0" class="detail-block">
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
    </CardBlock>

    <!-- 失败行：原因列表（同为带 SectionHeader 的页面级区块，容器同样走 CardBlock） -->
    <CardBlock v-if="p.failedList.length > 0" class="detail-block">
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
    </CardBlock>

    <!-- 底部操作：本页唯一的主入口。
         冲突提示条只描述「有什么问题」，动作一律落在这一处：
         主按钮「前往对账中心」是全页唯一实底主按钮，左侧「重新导入」是次级动作。 -->
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
import CardBlock from "@/components/CardBlock/index.vue";
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

/* 冲突提示条：品牌色态（design.md「提示性 Banner 品牌色规范」）。
   无按钮 ⇒ 图标与文字顶端对齐，文字换行时图标仍贴着第一行。 */
.conflict-banner {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  padding: var(--space-3) var(--space-compact);
  margin-bottom: var(--space-standard);
  background: var(--brand-100);
  border-radius: var(--radius-lg);
}

.conflict-banner__text {
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.5;
  color: var(--brand-700);
}

.conflict-banner__icon {
  flex-shrink: 0;
  margin-top: 2px;
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
  font-size: var(--text-display-lg);
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

/* 明细区块（冲突 / 失败）：卡片容器由 CardBlock 提供，此处只补区块间距 */
.detail-block {
  margin-bottom: var(--space-standard);
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
  font-size: var(--text-label);
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
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.failed-list__symbol {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

/* 操作栏：一条细线把它与正文分开，读作「页脚动作」而不是又一行内容。
   主次不靠堆颜色——全页只有这一枚实底主按钮，「重新导入」是默认次按钮。 */
.result-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: flex-end;
  padding-top: var(--space-standard);
  margin-top: var(--space-loose);
  border-top: 1px solid var(--border-subtle);
}
</style>
