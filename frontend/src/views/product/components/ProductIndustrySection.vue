<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type {
  FundHoldingsDetailResult,
  FundIndustryBucket
} from "@/api/products";

/**
 * 详情页「行业配置」区块（#2029 卡 C · 设计卡 §4.1 #4）。
 *
 * 单一区域：**表内嵌条**——行内比例条 + 精确值 + 完整行业名 + 合计行。
 *
 * 为什么不再是「图表 + 表格」并排（#2097 item 4 的后续收尾）：
 * - 后端 `industry_chart` 就是 `industries[0].items` 的投影（同一份截断后的
 *   items、同一顺序，只过滤 `ratio > 0`）——两个区域渲染的是**同一批数字**，
 *   不是互补信息。#2097 把环形图换成条形图、且条形图自带精确数值标签之后，
 *   表格原有的「给精度」职责就被图表自己接管了，而表没删。
 * - 图表 y 轴标签写死 96px（≈8 个汉字），证监会门类名最长 15 字必被截断
 *   （「电力、热力、燃气及水生产和供应业」→「电力、热力、燃…」），
 *   **唯一能读全名的地方是表格**。合并后名称列拿到剩余全部宽度，不再截断。
 * - 条长（图表的唯一独有贡献）降级为表格里的一列，纯 CSS 画：为一个静态
 *   十来行的列表起一个 echarts 实例不划算，表格语义对读屏与复制也更友好。
 *
 * 口径与降级（设计卡 §4.2④ · penetration 硬口径 2）：
 * - **csrc / gics 禁止跨体系相加** —— 只列主口径（证监会门类），
 *   GICS 板块只作参考单列并明确标注「与证监会门类不可相加」。
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

const hasData = computed(() => (props.detail?.industries?.length ?? 0) > 0);

/**
 * 条长按本区最大值归一。
 *
 * 用最大值而不是「各行之和」：占比之和未必等于 100（未披露的行业不在这个
 * 列表里），按和归一会把 47.94% 画成半条，读起来像「占了一半」。
 */
const maxRatio = computed(() => {
  const vals = (primary.value?.items ?? [])
    .map(it => it.ratio)
    .filter((r): r is number => r != null && r > 0);
  return vals.length ? Math.max(...vals) : 0;
});

/** 有占比才画条：占比缺失的行整条不画，只留「—」，避免被读成 0 */
function hasBar(ratio: number | null): boolean {
  return ratio != null && ratio > 0 && maxRatio.value > 0;
}

function barWidth(ratio: number): string {
  return `${((ratio / maxRatio.value) * 100).toFixed(2)}%`;
}

/**
 * 沿用原条形图的 `--chart-01~08` 循环：不引入新色，也不让颜色承担分类职责
 * （分类名就在同一行，颜色只是延续既有观感）。
 */
const CHART_PALETTE_VARS = [
  "--chart-01",
  "--chart-02",
  "--chart-03",
  "--chart-04",
  "--chart-05",
  "--chart-06",
  "--chart-07",
  "--chart-08"
];

function barColor(index: number): string {
  return `var(${CHART_PALETTE_VARS[index % CHART_PALETTE_VARS.length]})`;
}
</script>

<template>
  <CardBlock class="industry-section">
    <SectionHeader title="行业配置">
      <!-- 体系名 + 报告期只在这里出现一次：此前表格标题与脚注各写一遍 -->
      <template #action>
        <span v-if="primary?.scheme_label" class="industry-section__scheme">
          {{ primary.scheme_label }}
        </span>
        <span v-if="primary?.report_period" class="industry-section__period">
          报告期 {{ primary.report_period }}
        </span>
      </template>
    </SectionHeader>

    <p v-if="!hasData" class="section-footnote">暂无行业配置数据</p>

    <template v-else>
      <!-- 表口径见 `_detail-table.scss`（#553）。名称列是行标题（<th scope="row">），
           故用 `__product`（允许折行）；比例列是「条 + 数值」复合单元格，
           条宽由本组件的 bp 断点控制，只借共享类的右对齐与等宽数字。 -->
      <table class="detail-table industry-section__table">
        <thead>
          <tr>
            <th scope="col">行业</th>
            <th scope="col" class="detail-table__num">占净值比</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(it, i) in primary?.items ?? []"
            :key="it.industry_code || it.industry_name"
          >
            <th
              scope="row"
              class="detail-table__product industry-section__name"
            >
              {{ it.industry_name }}
            </th>
            <td class="detail-table__num industry-section__ratio">
              <span
                v-if="hasBar(it.ratio)"
                class="industry-section__track"
                aria-hidden="true"
              >
                <span
                  class="industry-section__fill"
                  :style="{
                    width: barWidth(it.ratio ?? 0),
                    background: barColor(i)
                  }"
                />
              </span>
              <span class="industry-section__value">
                {{ it.ratio != null ? it.ratio.toFixed(2) + "%" : "—" }}
              </span>
            </td>
          </tr>
          <tr v-if="!primary?.items?.length">
            <td class="detail-table__empty" colspan="2">
              该报告期无行业配置记录
            </td>
          </tr>
        </tbody>
        <tfoot v-if="primary?.total_ratio != null">
          <tr>
            <th scope="row" class="detail-table__product">合计</th>
            <td class="detail-table__num industry-section__ratio">
              <span class="industry-section__value">
                {{ primary.total_ratio.toFixed(2) }}%
              </span>
            </td>
          </tr>
        </tfoot>
      </table>

      <!-- 非主口径：单列并显式警告不可相加（硬口径 2）。
           ⚠️ 这条警告必须在 <details> **外面**：跨体系（csrc / gics）相加会得出
           荒谬结论，藏进折叠区就不再是「用户第一眼就要看到」的硬口径了。 -->
      <div
        v-for="b in secondary"
        :key="b.scheme"
        class="industry-section__other"
      >
        <p class="industry-section__other-note">
          该分类体系与上方{{ primary?.scheme_label }}不可相加，仅作参考
        </p>
        <details class="industry-section__other-details">
          <summary class="industry-section__other-title">
            {{ b.scheme_label }}（参考）
          </summary>
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
      </div>

      <p class="section-footnote">
        数据来源：{{ source }} · 行业配置为报告期快照（非日期序列）
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

/* 脚注与空态提示已迁至共享类 .section-footnote（#2320）；本区块容器带
   `gap: var(--space-3)`，故只用基础类、不加 --spaced。迁移前此处用图形级
   --text-tertiary 作前景文字（不足 4.5:1），已随共享类修正为 -ink。 */

/* 「不可相加」是**跨体系硬口径**，不是普通脚注：csrc / gics 加总得出的是荒谬结论。
   沿用持仓明细 caveat 的同一套警告视觉，避免两处硬口径长得不一样。
   （此前它躺在 <details> 里且是 tertiary 淡色，等于没有警告。） */
.industry-section__other-note {
  padding: var(--space-2) var(--space-3);
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--bg-subtle, var(--bg-card));
  border-left: 3px solid var(--color-warning, var(--brand-700));
  border-radius: 0 var(--radius-sm, 4px) var(--radius-sm, 4px) 0;
}

.industry-section__scheme {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.industry-section__period {
  margin-left: var(--space-2);
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* 表格的宽度 / 字号 / padding / 分隔线 / 表头 / 表尾 / 数字列全部来自
   `.detail-table`（#553）。本组件只留列宽与「条」的几何——那些是这张表独有的。 */

/* 名称列不设宽度：剩余空间全给它，长行业名换行而不是截断
   （旧图表 y 轴 96px 会把「电力、热力、燃气及水生产…」切掉） */
.industry-section__name {
  font-weight: 400;
  color: var(--text-primary);
}

/* 比例列定宽：条长左端对齐、数值右端对齐，条与条之间才可比（长度是本区块唯一的比例通道） */
.industry-section__ratio {
  width: 190px;
  white-space: nowrap;
}

.industry-section__track {
  display: inline-block;
  width: 96px;
  height: 8px;
  margin-right: var(--space-2);
  overflow: hidden;
  vertical-align: middle;
  background: var(--bg-muted);
  border-radius: 4px;
}

/* 极小占比（0.67% 在 47.94% 的最大值下只有 1.4% 宽）给 3px 兜底，
   否则屏上是一条看不见的线；0 / 缺失的行根本不画条（见 hasBar） */
.industry-section__fill {
  display: block;
  min-width: 3px;
  height: 100%;
  border-radius: 4px;
}

.industry-section__value {
  display: inline-block;
  min-width: 52px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  text-align: right;
}

@include bp.below("sm") {
  /* 窄屏先让出名称空间：条缩到 48px，仍可比，只是分辨率下降 */
  .industry-section__ratio {
    width: 132px;
  }

  .industry-section__track {
    width: 48px;
  }
}

.industry-section__other {
  padding: var(--space-2) 0;
  border-top: 1px solid var(--border-light);
}

.industry-section__other-title {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
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
  font-size: var(--text-label);
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
