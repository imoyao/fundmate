<template>
  <!--
    持仓小贴士（#1017）：规则驱动的静态诊断，零 LLM、零外部调用。
    只陈述「哪条规则此刻成立」+ 触发数值，不给买卖建议。
    请求由本卡自己发起：它只有这一份数据，塞进页面数据层会让 340 行的持仓页继续变长
    （页面规模门禁 #980 只减不增）。
  -->
  <div class="rule-tips">
    <SectionHeader
      title="持仓小贴士"
      info="这些提示由固定规则在本地算出（集中度、分散度、行业敞口、单日回撤），不调用大模型、不构成操作建议。规则与阈值集中维护在 services/insight/rules.py。"
      info-label="持仓小贴士口径说明"
    />

    <CardBlock>
      <p v-if="loading" class="rule-tips__hint" role="status">小贴士计算中…</p>

      <!-- 失败态不渲染空列表：空列表会被读成「没有问题」，与「没算出来」是两件事 -->
      <div v-else-if="error" class="rule-tips__error" role="alert">
        <span class="rule-tips__error-text">小贴士加载失败</span>
        <el-button text size="small" @click="load">重试</el-button>
      </div>

      <p v-else-if="!data?.items?.length" class="rule-tips__hint">
        {{ emptyText }}
      </p>

      <ul v-else class="rule-tips__list">
        <li
          v-for="tip in data.items"
          :key="tip.code"
          class="rule-tips__item"
          :class="`rule-tips__item--${tip.severity}`"
        >
          <span class="rule-tips__dot" aria-hidden="true" />
          <div class="rule-tips__body">
            <span class="rule-tips__title">{{ tip.title }}</span>
            <span class="rule-tips__message">{{ tip.message }}</span>
          </div>
        </li>
      </ul>
    </CardBlock>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getInsightTips, type TipListData } from "@/api/insight";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";

defineOptions({ name: "RuleTipsCard" });

const data = ref<TipListData | null>(null);
const loading = ref(false);
const error = ref(false);

/**
 * 无提示时的文案必须区分两种情况：
 * - 有持仓但没触发 → 「没发现值得提醒的问题」，是结论；
 * - 没有持仓 / 没有穿透数据 → 「还算不出来」，是缺数据。
 * 混成一句「暂无提示」会让人以为已经体检过了。
 */
const emptyText = computed(() => {
  const count = data.value?.snapshot?.holding_count ?? 0;
  if (count === 0) return "还没有投资持仓，暂无可体检的对象。";
  return `已检查 ${count} 只持仓、${data.value?.snapshot?.penetration_ratio ? "行业穿透数据可用" : "行业数据覆盖不足"}，当前没有触发提醒。`;
});

const load = async () => {
  loading.value = true;
  error.value = false;
  try {
    const res = await getInsightTips();
    data.value = res.data;
  } catch (e) {
    console.error("[rule-tips] 小贴士加载失败", e);
    error.value = true;
  } finally {
    loading.value = false;
  }
};

onMounted(load);
</script>

<style scoped lang="scss">
.rule-tips {
  &__hint {
    margin: 0;
    padding: 12px 0;
    font-size: var(--text-body-sm);
    color: var(--text-tertiary-ink);
  }

  &__error {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
  }

  &__error-text {
    font-size: var(--text-body-sm);
    color: var(--text-secondary-ink);
  }

  &__list {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  &__item {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }

  &__dot {
    flex: 0 0 auto;
    width: 6px;
    height: 6px;
    margin-top: 7px;
    border-radius: var(--radius-pill);
    background: var(--text-tertiary-ink);
  }

  &__item--risk &__dot {
    background: var(--color-danger, #d64545);
  }

  &__item--warn &__dot {
    background: var(--color-warning, #d99b1f);
  }

  &__body {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  &__title {
    font-size: var(--text-body-sm);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__message {
    font-size: var(--text-body-sm);
    line-height: 1.55;
    color: var(--text-secondary-ink);
  }
}
</style>
