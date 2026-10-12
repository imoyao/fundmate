<script setup lang="ts">
import { computed } from "vue";
import AssetAllocationBars from "@/components/Charts/AssetAllocationBars.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type {
  FundHoldingsDetailResult,
  FundIndustryBucket
} from "@/api/products";

/**
 * 详情页「行业配置」区块（#2029 卡 C · 设计卡 §4.1 #4）。
 *
 * **横向条形图**（`AssetAllocationBars`）+ 表格，数据来自
 * `GET /api/products/fund-holdings-detail/`。
 *
 * 为什么不用环形图（#2097 改）：后端按 `DEFAULT_INDUSTRY_TOP_N = 12` 截断行业，
 * 加上「其他」**最多 13 个扇区**——远超饼图的舒适区（6~7 类）。扇区太细时角度
 * 不可比（读者分不出「电子 8%」与「医药 7%」），底部图例也会挤到换行。
 * 横向条形按长度排序，一眼看出重仓谁。少分类场景仍用 `AssetAllocationDonut`。
 *
 * 口径与降级（设计卡 §4.2④ · penetration 硬口径 2）：
 * - **csrc / gics 禁止跨体系相加** —— 图只画主口径（证监会门类），
 *   GICS 板块只作参考单列并明确标注「与证监会门类不可相加」。把两套体系混进
 *   一张图会得出「制造业与非必需消费品同级并列」的荒谬结论。
 * - 无数据显空态，**绝不 mock 顶替**（G1 教训）。
 */

const props = defineProps<{
  /** 整个详情响应（本卡只读其中行业部分） */
  detail: FundHoldingsDetailResult | null;
  /** 来源站点名 */
  source: string;
}>();

/** 主口径分区（后端已保证排在第一位且 is_primary=true） */
const primary = computed<FundIndustryBucket | null>(() => {
  const list = props.detail?.industries ?? [];
  return list.find(b => b.is_primary) ?? list[0] ?? null;
});

/** 非主口径分区（GICS 等），单列展示并标注不可相加 */
const secondary = computed<FundIndustryBucket[]>(() =>
  (props.detail?.industries ?? []).filter(b => !b.is_primary)
);

/** 环形图数据：只取主口径、且占比为正的行 */
const chartData = computed(() => props.detail?.industry_chart ?? []);

const hasData = computed(() => (props.detail?.industries?.length ?? 0) > 0);
</script>

<template>
  <CardBlock class="industry-section">
    <SectionHeader title="行业配置" />

    <p v-if="!hasData" class="industry-section__hint">暂无行业配置数据</p>

    <template v-else>
      <!-- 条形图 + 表格并排：窄屏纵向堆叠 -->
      <div class="industry-section__layout">
        <div class="industry-section__chart">
          <!-- 条右侧标签直接给「占净值比」，不传 formatValue。
               旧环形图传的是 `${value}%（占净值 ${pct}%）`，而那个 `pct` 是
               **占图表各项之和**的比例（各行业占净值比之和未必等于 100，未披露
               部分被摊掉了）——标成「占净值」会让人误以为是占净值比。
               条形长度本身就是 value，再叠一次换算只会多一个口径。 -->
          <AssetAllocationBars :data="chartData" empty-text="暂无行业配置" />
        </div>

        <div class="industry-section__table-wrap">
          <div class="industry-section__table-title">
            {{ primary?.scheme_label }}
            <span
              v-if="primary?.report_period"
              class="industry-section__period"
              >{{ primary.report_period }}</span
            >
          </div>
          <table class="industry-section__table">
            <thead>
              <tr>
                <th scope="col">行业</th>
                <th scope="col" class="industry-section__num">占净值比</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="it in primary?.items ?? []"
                :key="it.industry_code || it.industry_name"
              >
                <td>{{ it.industry_name }}</td>
                <td class="industry-section__num">
                  {{ it.ratio != null ? it.ratio.toFixed(2) + "%" : "—" }}
                </td>
              </tr>
              <tr v-if="!primary?.items?.length">
                <td class="industry-section__empty" colspan="2">
                  该报告期无行业配置记录
                </td>
              </tr>
            </tbody>
            <tfoot v-if="primary?.total_ratio != null">
              <tr>
                <th scope="row">合计</th>
                <td class="industry-section__num">
                  {{ primary.total_ratio.toFixed(2) }}%
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <!-- 非主口径：单列并显式警告不可相加（硬口径 2） -->
      <details
        v-for="b in secondary"
        :key="b.scheme"
        class="industry-section__other"
      >
        <summary class="industry-section__other-title">
          {{ b.scheme_label }}（参考）
        </summary>
        <p class="industry-section__other-note">
          该分类体系与上方{{ primary?.scheme_label }}不可相加，仅作参考
        </p>
        <dl class="industry-section__other-list">
          <div
            v-for="it in b.items"
            :key="it.industry_code || it.industry_name"
            class="industry-section__other-item"
          >
            <dt>{{ it.industry_name }}</dt>
            <dd>
              {{ it.ratio != null ? it.ratio.toFixed(2) + "%" : "—" }}
            </dd>
          </div>
        </dl>
      </details>

      <p class="industry-section__footnote">
        数据来源：{{ source }} · 行业配置为报告期快照（非日期序列）
        <template v-if="primary?.report_period">
          · 报告期 {{ primary.report_period }}
        </template>
      </p>
    </template>
  </CardBlock>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;

.industry-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.industry-section__hint,
.industry-section__footnote,
.industry-section__other-note {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.industry-section__layout {
  display: grid;

  /* 严禁 `minmax(0, 1fr)`：会让轨道塌成 0（#1969 P0 实测，标签逐字竖排）。
     图表列从 320px 放宽到 420px（#2097 改环形图 → 条形图）：横向条形图靠
     **长度**传达比例，320px 里扣掉左侧行业名（约 96px）只剩 200px 画条，
     13 行里「8% vs 7%」的条长差不足 15px，读不出来。表格只有两列，
     收到 200px 仍然宽裕。 */
  grid-template-columns: minmax(320px, 420px) minmax(200px, 1fr);

  /* 注意：不能用 `--space-4` —— 它在全仓被引用但**从未定义**（探针实测），
     写了会整条 gap 静默失效。定义齐全的是 1/2/3/5/6。 */
  gap: var(--space-3) var(--space-5);
  align-items: start;
}

@include bp.below("lg") {
  .industry-section__layout {
    grid-template-columns: 1fr;
  }
}

/* 高度交给 `AssetAllocationBars` 按条目数算：行业少时不该留一大片空白，
   行业多时也不该把 13 行压成看不出差别的细线。 */

.industry-section__table-wrap {
  min-width: 0;
}

.industry-section__table-title {
  margin-bottom: var(--space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.industry-section__period {
  margin-left: var(--space-2);
  font-size: 12px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.industry-section__table {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
}

.industry-section__table th,
.industry-section__table td {
  padding: var(--space-2) var(--space-1);
  text-align: left;
  border-bottom: 1px solid var(--border-light);
}

.industry-section__table thead th {
  font-weight: 500;
  color: var(--text-tertiary);
}

.industry-section__num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.industry-section__empty {
  color: var(--text-tertiary);
  text-align: center;
}

.industry-section__other {
  padding: var(--space-2) 0;
  border-top: 1px solid var(--border-light);
}

.industry-section__other-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
}

.industry-section__other-note {
  margin: var(--space-2) 0;
}

.industry-section__other-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-2) var(--space-5);
  margin: 0;
}

.industry-section__other-item {
  display: flex;
  gap: var(--space-2);
  justify-content: space-between;
  font-size: 13px;
}

.industry-section__other-item dt {
  color: var(--text-primary);
}

.industry-section__other-item dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}
</style>
