<template>
  <!--
    策略诊断卡（#2224 / #2225）：规则触发的客观状态 + 行为反推画像。
    纯展示，请求由页面数据层 `useStrategyInsight` 承担。
  -->
  <div class="diagnosis-card">
    <SectionHeader
      title="策略诊断"
      info="诊断由既定的规则对已有行情自动跑出，描述的是「哪条规则此刻成立」，不是操作建议。行为画像只统计你自己的历史交易。"
      info-label="策略诊断口径说明"
    />

    <CardBlock>
      <!-- 加载中 -->
      <p v-if="loading" class="diagnosis-card__hint" role="status">
        诊断信号加载中…
      </p>

      <!-- 失败态：不显示 0 / 空列表，避免被读成「没有信号」 -->
      <div v-else-if="error" class="diagnosis-card__error" role="alert">
        <span class="diagnosis-card__error-text">诊断信号加载失败</span>
        <el-button text size="small" @click="emit('retry')">重试</el-button>
      </div>

      <p v-else-if="!diagnosis?.items?.length" class="diagnosis-card__hint">
        还没有持仓，暂无可诊断的标的。
      </p>

      <!-- 行为总览 + 逐标的信号（见 DiagnosisSignalList） -->
      <DiagnosisSignalList
        v-else
        :diagnosis="diagnosis"
        :behavior="behavior"
        :strategies="strategies"
      />
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
/**
 * 策略诊断卡（#2224 / #2225）。
 *
 * 合规红线：后端 `contracts.py` 与 `allocation.py` 明确禁止「建议买入 / 建议卖出」措辞。
 * 本组件只做三件事——把 `strategy_code` 翻成策略名、把 `action` 翻成**状态词**
 * （买入区间 / 减仓区间 等，描述的是规则落在哪个区间，不是让人去做什么）、
 * 原样展示后端 `reason`。前端不补任何倾向性动词。
 *
 * `early_exit_cost` 可能为负（提前卖出反而躲过下跌），负数如实显示，
 * 绝不取绝对值或隐藏——那是用户行为里最有信息量的一半。
 *
 * #980 拆分：总览横条与逐标的列表 → `DiagnosisSignalList`，翻译与格式化口径 →
 * `diagnosisModel.ts`。本文件只保留区块外壳与三态分派。
 */
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type {
  BehaviorData,
  DiagnosisData,
  EngineStrategyMeta
} from "@/api/strategyEngine";
import DiagnosisSignalList from "./DiagnosisSignalList.vue";

defineOptions({ name: "StrategyDiagnosisCard" });

defineProps<{
  diagnosis: DiagnosisData | null;
  behavior: BehaviorData | null;
  /** `GET /api/strategy/engine/strategies/` 的列表，用于把 code 翻成策略名 */
  strategies?: EngineStrategyMeta[];
  loading?: boolean;
  error?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();
</script>

<style lang="scss" scoped>
.diagnosis-card {
  display: flex;
  flex-direction: column;

  &__hint {
    margin: 0;
    font-size: var(--text-label);
    line-height: 1.6;
    color: var(--text-tertiary-ink);
  }

  &__error {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }

  &__error-text {
    font-size: var(--text-label);
    color: var(--text-secondary);
  }

  /* 窄屏适配已并入 `DiagnosisSignalList` 的 .diagnosis-card__overview / __signal 内部
     （媒体查询必须贴着它覆盖的规则放：同特异性下源序即优先级，
     见 stylelint.config.js 的 order/order 注释） */
}
</style>
