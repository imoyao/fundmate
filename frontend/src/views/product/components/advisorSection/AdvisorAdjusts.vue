<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  getAdvisorAdjusts,
  type AdvisorAdjustGroup,
  type AdvisorAdjustsResult
} from "@/api/funds";
import AdvisorAdjustList from "./AdvisorAdjustList.vue";
import {
  ADJUST_LIMIT,
  adjustEmptyHint,
  derivedFromSnapshots
} from "./advisorAdjustModel";

/**
 * 详情页「主理人调仓」（区块内的子块）。
 *
 * ## 这块回答什么、不回答什么
 *
 * 回答：**这个组合的主理人最近动过什么**。
 * 不回答：我自己在这只组合上买卖了什么——详情页没有「我的交易」语境，
 * 交易记录只在持仓页 / 交易记录里。
 *
 * ## 为什么调仓记录此前不显示
 *
 * 不是没人做，是**刻意没做**：早先的注释写着「调仓明细待速览抽屉的渲染提取成共用
 * 组件后再复用」。那句注释一直没被兑现，用户看到的就是「调仓历史拿不到」。现在
 * 渲染已提取为 `AdvisorAdjustList`（与持仓页同一份），本组件只负责取数与口径说明。
 *
 * ## 口径必须写在脸上（且慢）
 *
 * 且慢现在有官方调仓接口（`/alfa/v1/graphql` 的 `Adjustment`，2026-11-03 接入），
 * 但**不是所有代码都在它的命名空间里**——计划型组合（`LONG_WIN` / `LONG_WIN_S`）返回空，
 * 仍由我们的持仓快照序列推导。两种来源靠 `source` 区分（`qieman_official` / `qieman`），
 * 只要列表里混进推导行，下方就必须声明「由持仓快照推导」——不写就等于冒充官方数据。
 * 判断逻辑在 `advisorAdjustModel`（纯函数，有单测），本组件只渲染它的结论。
 *
 * ## 已知边界
 *
 * 推导噪声（阈值 0.5pp 偏粗、连续同向未合并、占比漂移被当事件）属已知技术债，
 * 不在本组件治理——这里只改「有没有显示」，不改「怎么算出来的」。官方行没有这个问题。
 */
const props = defineProps<{
  /** 平台组合码（`advisor_portfolios.code`，如 ZH012926） */
  code: string;
  /** 平台码（`advisor_portfolios.platform`），用于空态解释「为什么没有调仓记录」 */
  platform: string;
}>();

const loading = ref(false);
const failed = ref(false);
const groups = ref<AdvisorAdjustGroup[]>([]);

const derived = computed(() => derivedFromSnapshots(groups.value));
const emptyHint = computed(() => adjustEmptyHint(props.platform));

async function load() {
  if (!props.code) return;
  loading.value = true;
  failed.value = false;
  groups.value = [];
  try {
    const res = await getAdvisorAdjusts(props.code, ADJUST_LIMIT);
    const data: AdvisorAdjustsResult | undefined = res.data;
    // 后端已按调仓日倒序；这里**不重排**，避免两处各排一次后不一致
    groups.value = data?.adjusts ?? [];
  } catch {
    // 调仓取不到只影响这一块，上面的档案 / 指标 / 成分照常展示
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.code, load, { immediate: true });
</script>

<template>
  <div class="advisor-adjusts-block advisor-section__block">
    <h4 class="advisor-section__metrics-title">
      主理人调仓
      <span v-if="groups.length" class="advisor-section__sub">
        最近 {{ groups.length }} 次
      </span>
    </h4>

    <p v-if="loading" class="advisor-adjusts-block__hint">
      正在读取主理人调仓…
    </p>
    <p v-else-if="failed" class="advisor-adjusts-block__hint">
      主理人调仓暂时取不到，稍后再看。
    </p>
    <p v-else-if="!groups.length" class="advisor-adjusts-block__hint">
      {{ emptyHint }}
    </p>
    <template v-else>
      <AdvisorAdjustList :groups="groups" />
      <p v-if="derived" class="advisor-adjusts-block__caveat">
        以上标记为推导的记录由我们的持仓快照序列算出（该组合不在且慢官方调仓接口的覆盖范围内），
        时点与幅度可能与实际调仓存在差异。
      </p>
    </template>
  </div>
</template>

<style lang="scss" scoped>
@use "./advisor-base";

.advisor-section__block {
  margin-top: var(--space-3);
}

.advisor-adjusts-block__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 口径声明：与正文脚注同族（更弱色阶），但它挂在列表下方，需要自带上间距 */
.advisor-adjusts-block__caveat {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
