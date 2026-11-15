<!--
  持仓结构面板（#2617）：资产类别占比 + 股基分列 Top N + 集中度。

  为什么股基不合并排名：股票与基金（含 ETF）的份额与价格不可比，合成一张
  「前 5 大持仓」榜单没有经济含义，还会让基金的集中度被拆成多条。故用
  SegmentedControl 切换两组，而不是并排堆两张饼图。

  #2739：视角由**账户类型**决定，不再让用户切。
  账户级作用域（`ledger-id`）下后端返回 `view`（stock/fund）——
  证券账户只看股票、基金/银行账户只看基金，此时**不渲染切换控件**。
  组合级 / 家庭级跨类型账户混合，`view` 为 null ⇒ 保留切换。

  数据全部来自后端 `position-structure`（占比、组内集中度、跨账户合并都在
  服务端算完），前端只做展示——与全站「同一份数据只算一次」的约束一致。
-->
<template>
  <div class="position-structure">
    <SectionHeader title="持仓结构" info-label="持仓结构口径说明">
      <!-- 口径（含后端下发的 notes）收进 ⓘ：原来它是区块尾部 5 段小字，
           占 200+px 且把 Top 榜推走。原样展示、不改写，只是换了个入口。 -->
      <template #info>
        <p>{{ panelInfo }}</p>
        <p v-for="(note, i) in data?.notes ?? []" :key="i">{{ note }}</p>
        <p v-if="hasCashLike">
          另有类现金
          {{
            formatAmount(data?.cash_like_cny ?? 0)
          }}（货币基金等现金等价物）未计入上述持仓，故各类占比之和为 100%
          的持仓口径，不含这部分现金。
        </p>
      </template>
      <template #action>
        <SegmentedControl
          v-if="showSwitcher"
          v-model="activeClass"
          :options="CLASS_OPTIONS"
          size="small"
          aria-label="资产类别"
        />
      </template>
    </SectionHeader>

    <el-skeleton v-if="loading" :rows="4" animated />
    <SoftBanner v-else-if="error" variant="warning" icon="ep:warning-filled">
      {{ error }}
    </SoftBanner>

    <template v-else-if="data">
      <!-- 金额为 0 的类别不占格（2026-11-15）：证券账户恒有「基金 0.00 / 其他 0.00」
           两张空卡，把「股票 99 万」挤成三选一。 -->
      <MetricGrid>
        <MetricCard
          v-for="cls in nonEmptyClasses"
          :key="cls.key"
          :title="cls.label"
          :value="classAmount(cls.key)"
          :caption="cls.caption"
          :featured="cls.key === 'stock'"
        />
        <MetricCard
          title="前 5 集中度"
          :value="pct(data.concentration.top5_ratio_of_total)"
          :caption="`前 5 大持仓占${scopeUnit}`"
        />
      </MetricGrid>

      <CardBlock v-if="activeGroup" class="mt-4">
        <div class="group-head">
          <h4 class="group-title">
            {{ activeGroup.label }} Top {{ activeGroup.top.length }}
          </h4>
          <!-- 表头只留**一个**百分比（2026-11-15 二次收敛）：原来这里并排写
               「组内前 5 集中度 34.4% · 占组合 22.4%」，每行又各有一对
               「占组合 / 占股票」——同一张卡上四个百分比，两个同量纲数字读不出
               区别，用户实测反馈「两个百分占比让人很困惑」。现在逐行只给
               占组合（占账户 / 占全家庭），组内口径由这一句交代。
               且只在它真的与上方卡片不同时才写：单类别账户里两者逐字相同，
               并排只会让人以为看错。 -->
          <p v-if="showGroupRatio" class="group-meta">
            组内前 5 集中度 {{ pct(activeGroup.top5_ratio_of_group) }}（占{{
              activeGroup.label
            }}）
          </p>
        </div>

        <p v-if="activeGroup.count === 0" class="group-empty">
          该作用域没有{{ activeGroup.label }}持仓。
        </p>
        <!-- 与下方「持仓穿透 · 个股层 Top 5」共用 components/RankBarList：
             同一页两块榜同一套长相，条长与占比都由父级按各自口径算好传进去。 -->
        <RankBarList v-else :rows="groupRows" />
      </CardBlock>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import RankBarList from "@/components/RankBarList/index.vue";
import {
  getPositionStructure,
  type PositionStructureData
} from "@/api/summary";
import { formatAmount } from "@/utils/currency";

/**
 * 持仓结构面板（#2617）。
 *
 * 三级作用域由父页显式传：不传 = 家庭级；`portfolio-id` = 组合级；
 * `ledger-id` = 账户级（两者互斥，后端 400，父页保证）。
 *
 * #2739：账户级下视角由后端按账户类型判定（`data.view`），本组件**不提供切换**；
 * 组合/家庭级 `data.view` 为 null ⇒ 保留股基切换。
 */
const props = defineProps<{
  ledgerId?: number;
  portfolioId?: number;
}>();

const CLASS_OPTIONS = [
  { label: "股票", value: "stock" },
  { label: "基金", value: "fund" }
] as const;

type ClassKey = "stock" | "fund";

const activeClass = ref<ClassKey>("stock");
const data = ref<PositionStructureData | null>(null);
const loading = ref(false);
const error = ref("");

const scopeLabel = computed(() => {
  if (props.portfolioId != null) return "组合";
  if (props.ledgerId != null) return "账户";
  return "全家庭";
});

/**
 * 占比分母的称呼（账户页写「占组合」是错的：账户页的口径是本账户）。
 */
const scopeUnit = computed(() => {
  if (props.portfolioId != null) return "组合";
  if (props.ledgerId != null) return "账户";
  return "全家庭";
});

/**
 * 账户级固定视角（后端按 `ledger_type` 判定）：证券账户 → 股票，
 * 基金/银行账户 → 基金。为 null（组合/家庭级）时保留切换控件。
 */
const fixedView = computed<ClassKey | null>(() => data.value?.view ?? null);

/** 是否显示股基切换控件：仅组合/家庭级（跨类型账户混合，切换才有意义）。 */
const showSwitcher = computed(() => fixedView.value === null);

/** 账户级下走类现金的金额（货基等）——需如实告知，否则占比看着像丢了钱。 */
const hasCashLike = computed(() => (data.value?.cash_like_cny ?? 0) > 0);

const activeGroup = computed(
  () => data.value?.groups?.[fixedView.value ?? activeClass.value]
);

/** 类别金额（元）。0 = 该账户没有这一类持仓。 */
function classValue(key: string): number {
  return (
    data.value?.by_asset_class.find(item => item.key === key)?.value_cny ?? 0
  );
}

/**
 * 只渲染**有金额**的类别卡（2026-11-15）。
 *
 * 证券账户恒为「股票 99 万 / 基金 0.00 / 其他 0.00」——两张 0 卡把唯一有数的
 * 那张挤成三选一，读起来还像「基金一块钱都没了」。金额为 0 即整卡不渲染。
 */
const nonEmptyClasses = computed(() => {
  const meta = [
    { key: "stock", label: "股票" },
    { key: "fund", label: "基金" },
    { key: "other", label: "其他" }
  ];
  return meta
    .filter(item => classValue(item.key) > 0)
    .map(item => ({
      key: item.key,
      label: item.label,
      caption:
        item.key === "other"
          ? `占${scopeUnit.value} ${classRatio("other")}（债 / 货基 / 逆回购）`
          : `占${scopeUnit.value} ${classRatio(item.key)} · ${
              data.value?.groups?.[item.key as ClassKey]?.count ?? 0
            } 只`
    }));
});

/**
 * Top 5 的行（交给共享条列表 `RankBarList` 渲染）：
 * 名称 + 代码/合并账户副标题 + 条 + **一个**占比；市值只在悬浮提示里
 *（精确金额在页面下方的持仓明细表里，行内不再挤第二个数字）。
 *
 * 占比只给「占组合（账户 / 全家庭）」一种口径：
 * - 它跨类别可比，且与上方类别卡 caption 同分母，一眼能对上；
 * - 组内占比（占该类）由表头「组内前 5 集中度」一处交代就够——逐行再列一遍，
 *   就是两个同量纲百分比并排，实测读不出区别（2026-11-15 用户反馈）。
 *
 * 条长按**本组最大值**归一，不按「各行之和」：Top 5 之和不是 100%，按和归一
 * 会把每根条都画得比真实权重长（同 `docs/design/components.md` 的表内嵌条纪律）。
 */
const groupRows = computed(() => {
  const rows = activeGroup.value?.top ?? [];
  const maxRatio = rows.reduce(
    (max, row) => Math.max(max, row.ratio_of_total ?? 0),
    0
  );
  return rows.map(row => {
    const name = row.name || row.symbol || "—";
    const accounts = row.accounts > 1 ? `${row.accounts} 个账户合并` : "";
    const ratio = pct(row.ratio_of_total);
    return {
      key: String(row.symbol ?? name),
      name,
      sub: [row.symbol, accounts].filter(Boolean).join(" · "),
      title: `${name}（${row.symbol}）· 市值 ${formatAmount(
        row.value_cny
      )} · 占${scopeUnit.value} ${ratio}`,
      width:
        maxRatio > 0
          ? `${(((row.ratio_of_total ?? 0) / maxRatio) * 100).toFixed(2)}%`
          : "0%",
      value: ratio
    };
  });
});

/**
 * 表头的「组内前 5 集中度」是否值得写。
 *
 * 与上方「前 5 集中度」卡片同因：单类别账户里组内分母 == 账户分母，
 * 两个数字逐字相等（实测 15.7% / 15.7%）。只保留卡片那一个。
 */
const showGroupRatio = computed(() => {
  const group = activeGroup.value;
  if (!group) return false;
  return (
    Math.abs(
      (group.top5_ratio_of_group ?? 0) - (group.top5_ratio_of_total ?? 0)
    ) > 0.05
  );
});

const panelInfo = computed(() => {
  const base =
    "钱压在哪：按股票 / 基金 / 其他拆开看占比与前 5 集中度（" +
    scopeLabel.value +
    "口径）。股票与基金分开排名——份额与价格不可比，合并榜单没有意义。" +
    "榜内行尾百分比是占" +
    scopeUnit.value +
    "的比重（跨类别可比）；「组内前 5 集中度」只看该类内部，分母是该类合计。";
  if (fixedView.value === null) return base;
  return (
    base +
    "本账户是" +
    (fixedView.value === "stock" ? "证券" : "基金") +
    "账户，视角已按账户类型固定，不需切换。"
  );
});

function pct(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

function classAmount(key: string): string {
  const row = data.value?.by_asset_class.find(item => item.key === key);
  return formatAmount(row?.value_cny ?? 0);
}

function classRatio(key: string): string {
  const row = data.value?.by_asset_class.find(item => item.key === key);
  return pct(row?.ratio_of_total);
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const scope: { ledger_id?: number; portfolio_id?: number } = {};
    if (props.ledgerId != null) scope.ledger_id = props.ledgerId;
    if (props.portfolioId != null) scope.portfolio_id = props.portfolioId;
    const res = await getPositionStructure(scope);
    data.value = res?.data ?? null;
    if (!data.value) error.value = "持仓结构数据为空。";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "持仓结构加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => [props.ledgerId, props.portfolioId], load);
</script>

<style scoped>
.position-structure {
  display: flex;
  flex-direction: column;
}

.group-head {
  display: flex;
  gap: var(--space-standard);
  align-items: baseline;
  justify-content: space-between;
}

.group-title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.group-meta {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.group-empty {
  margin: var(--space-standard) 0 0;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}
</style>
