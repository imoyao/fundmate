<!--
  同类优选（#167 · 按指标横向筛的列表页）

  承接 CNB #167 的残留项 4：后端 `GET /api/products/fund-risk-ranking/` 与
  `GET /api/products/fund-risk-types/` 已就绪，前端零调用方——能力已经上线，
  用户却看不到。

  ## 数据范围（2026-10-17 如实化）

  快照池 = **持仓 ∪ 自选**（`fund_risk_metrics_job` 默认目标池），不是全市场——
  本页回答的是「**你持有/关注的基金**在同类里风险收益比排第几」，即持仓风险体检。
  全市场同类榜是另一个形态（探市侧 + 净值回填扩容），已另立项，不在本页语义内。

  ## 产品定位（2026-10-17 明确）

  本页**不是**独立榜单产品，而是**自选页的深度体检层**：自选页管「看哪些」，
  本页答「这些基金在同类里排第几、要不要继续拿」。因此：

  1. 榜单行带 `in_holdings` / `in_watchlist`（后端同源自快照池），持仓行高亮 +
     「持仓 / 自选」徽章——用户一眼找到「我的那只」；
  2. 命名去「榜」字（「同类风险榜」听起来像天天基金式全市场排行，与实际口径错位，
     正是「机器生成感」的来源），页面名 = **同类优选**；
  3. 与自选页共享同一批基金语义，不另立数据源、不制造割裂。

  ## 这个页面在回答什么问题

  「同类里谁的风险收益比更好」——**限定在同一类内**。风险比跨类别不可比：
  债基年化波动 2%、股基 25%，而夏普把波动当风险 ⇒ 债基系统性偏高。所以本页
  **不提供「全市场榜」**，必须先选一个基金小类（后端 `fund_type_id` 也是必填）。

  ## 三条口径纪律（页面上必须让用户看得见）

  1. **类型选择器只列有榜的类**（`fund-risk-types/` 只交出有快照行的类型）——
     否则选中一个没算过的类会是空榜，用户分不清「这个类没有基金」与「我们没算」；
  2. **被剔除的条数必须显示**（`excluded_distorted`）——「榜上只有 3 只」与
     「同类只有 3 只有数据」是两回事，不显示就等于把后者说成前者；
  3. **不给「好/差」色**——榜单是同类内的相对排序，不是买入信号（合规红线：
     不荐股不跟单不预测）。

  ## 涨跌色边界（2026-10-17 UI 优化补）

  收益列（年化收益 / 近1月 / 近3月 / 近1年）染 `--color-rise-ink` / `--color-fall-ink`：
  它们是**区间净值涨跌幅**，正负本身就是涨跌语义，与自选页「涨跌幅」列同规则
  （design.md：盈亏数字走 rise/fall，且配 +/- 符号，不把颜色当唯一信息载体）。
  风险比率列（夏普 / 卡玛 / UI / 波回比 / 最大回撤）**一律中性色**——染红绿等于
  替用户判「好坏」，越合规红线，也违反上面第 3 条纪律。

  ## 第二轮（2026-10-17 用户实测反馈）

  1. **UI 列点击即空榜**：后端 SORTABLE_METRICS 漏登记 `ulcer_index`，请求 400 →
     前端 catch 置空。已加白名单（默认升序：正数、越低越好），前端 onSort
     首击方向按列语义（dir）给——low 列首击 asc，不再一律 desc；
  2. **双层分组表头**：风险调整收益 / 风险 / 收益三组，组内同口径——回答
     「近1月是涨幅还是夏普」；「窗口」列删（每行同值），口径移脚注；
  3. **样式对齐 el-table 基线**：表头底 --bg-muted、行 hover --bg-soft、
     激活列 = 加粗 + 主色文字（去红字灰底——红字读作警告、灰底与全站基线分裂）；
  4. **删持仓行底纹**：池内持仓占多数，底纹无信号价值，唯一自选行反被读成
     bug；徽章承载「这是我的」；+/- 符号只给收益列（UI/回撤不带 +）。
-->
<template>
  <div class="fund-ranking-page min-h-full">
    <PageHeaderBar
      title="同类优选"
      subtitle="基于你的持仓与自选的基金，在同一类型内按风险收益指标排序——风险比跨类别不可比，故不做全市场榜"
    />

    <div class="ranking-shell">
      <PageSkeleton v-if="initialLoading" :cards="1" :table-rows="6" />

      <template v-else>
        <CardBlock>
          <SectionHeader :title="rankingTitle" :info="rankingInfo" />

          <!-- 表格工具栏（#1714「一层页头」原则的卡片内变体）：筛选器收进表格，
               不再单独占一张卡片——筛选与数据同卡，关联才不断裂 -->
          <div class="ranking-toolbar">
            <div class="filter-item">
              <label class="filter-item__label" for="fund-type">基金类型</label>
              <el-select
                id="fund-type"
                v-model="selectedTypeId"
                class="filter-item__control"
                placeholder="选择一个类型"
                filterable
                :loading="typesLoading"
                @change="onTypeChange"
              >
                <el-option
                  v-for="t in typeOptions"
                  :key="t.fund_type_id"
                  :value="t.fund_type_id"
                  :label="`${t.name}（共 ${t.count} 只）`"
                />
              </el-select>
            </div>

            <div class="ranking-toolbar__meta">
              <!-- 单位统一说明：表头去掉 (%) 后由这里兜底，表头更短不被截断 -->
              <span class="unit-note">
                收益 / 回撤 / UI 列单位为 %；夏普、卡玛、波回比为比率
              </span>
              <!-- 剔除提示：从整行长条降级为标题级图标气泡，纵向空间还给表格 -->
              <el-tooltip
                v-if="excludedDistorted > 0"
                placement="top"
                :content="excludedTip"
              >
                <span
                  class="excluded-tip"
                  role="img"
                  :aria-label="excludedTip"
                  tabindex="0"
                >
                  <IconifyIconOffline icon="ep:warning-filled" />
                  {{ excludedDistorted }} 只被剔除
                </span>
              </el-tooltip>
            </div>
          </div>

          <!-- 诚实降级：没有可选类型时，说明的是「没人算过」而不是「没有基金」 -->
          <p v-if="!typeOptions.length" class="empty-hint">
            暂无风险指标快照。榜单需要先跑一次
            <code>pdm run sync --job fund_risk_metrics</code> 生成同类指标。
          </p>

          <div v-else-if="rankingLoading" class="table-loading">
            <el-skeleton :rows="5" animated />
          </div>

          <div v-else-if="!rows.length" class="empty-hint">
            {{ noRowHint }}
          </div>

          <!-- 横向滚动容器：左侧「排名 + 基金」两列 sticky，滚到右侧指标时
               始终知道这行是哪只基金（design.md 冻结列规范） -->
          <div v-else class="table-scroll">
            <table class="ranking-table w-full text-sm">
              <thead>
                <!-- 双层表头（2026-10-17 第二轮）：10 个数值列平铺时，用户分不清
                     「窗口列是什么」「近1月是涨幅还是夏普」。分组行给结构——
                     组内同口径、组间不同口径；分组行不可点，hover 讲组口径。 -->
                <tr class="th-group-row">
                  <th rowspan="2" class="col-rank">#</th>
                  <th rowspan="2" class="col-fund">基金</th>
                  <th
                    v-for="g in columnGroups"
                    :key="g.label"
                    class="th-group"
                    :colspan="g.keys.length"
                    :aria-label="g.tip"
                  >
                    <el-tooltip placement="top" :content="g.tip">
                      <span class="th-group__label">{{ g.label }}</span>
                    </el-tooltip>
                  </th>
                </tr>
                <tr class="th-metric-row">
                  <!-- 指标列即排序入口（#2298）：整块可点，当前排序列加粗高亮 + 实心箭头。
                       表头 hover 弹指标说明（2026-10-17 去常驻 i 图标降噪），
                       说明里带「越高/越低越好」——术语不解释，用户读不懂数字。 -->
                  <th
                    v-for="col in tableColumns"
                    :key="col.key"
                    class="col-sortable"
                    :class="{ 'col-active': col.key === metric }"
                    :aria-sort="ariaSort(col.key)"
                    @click="onSort(col.key)"
                  >
                    <el-tooltip placement="top" :content="col.hint">
                      <span class="th-with-tip">
                        <span class="th-label">{{ col.label }}</span>
                        <span class="th-sort">
                          <IconifyIconOffline
                            v-if="col.key === metric"
                            :icon="
                              order === 'desc'
                                ? 'ep:caret-top'
                                : 'ep:caret-bottom'
                            "
                            class="th-sort__caret th-sort__caret--active"
                          />
                          <template v-else>
                            <IconifyIconOffline
                              icon="ep:caret-top"
                              class="th-sort__caret"
                            />
                            <IconifyIconOffline
                              icon="ep:caret-bottom"
                              class="th-sort__caret"
                            />
                          </template>
                        </span>
                      </span>
                    </el-tooltip>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in rows" :key="row.fund_code">
                  <td class="col-rank">{{ index + 1 }}</td>
                  <td class="col-fund">
                    <button
                      type="button"
                      class="fund-link"
                      :title="row.fund_name ? row.fund_code : undefined"
                      @click="goDetail(row.fund_code)"
                    >
                      <span class="fund-link__name">
                        {{ row.fund_name || row.fund_code }}
                        <!-- 持仓体检定位的锚点：榜上哪只是「我的」 -->
                        <span
                          v-if="row.in_holdings"
                          class="fund-tag fund-tag--holding"
                          >持仓</span
                        >
                        <span
                          v-else-if="row.in_watchlist"
                          class="fund-tag fund-tag--watch"
                          >自选</span
                        >
                      </span>
                      <!-- 名称与代码都显示：跳详情、复核数据都要代码；
                           funds 资料缺失时名称回退代码，此时不重复显示两遍 -->
                      <span v-if="row.fund_name" class="fund-link__code">{{
                        row.fund_code
                      }}</span>
                    </button>
                  </td>
                  <td
                    v-for="col in tableColumns"
                    :key="col.key"
                    :class="[
                      'col-num',
                      { 'col-active': col.key === metric },
                      col.kind === 'return' ? numClass(row, col) : ''
                    ]"
                  >
                    <span
                      v-if="col.bar"
                      class="data-bar"
                      :style="{ width: barWidth(row, col.key) }"
                      aria-hidden="true"
                    />
                    <span class="num-text">{{ formatCell(row, col) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="footnote">
            指标窗口「{{ windowLabel }}」：夏普 / 卡玛 / 波回比 / UI / 最大回撤
            / 年化收益均按该窗口计算；近1月 / 近3月 /
            近1年为区间净值涨跌幅。样本数 {{ sampleRange }} 个交易日 · 口径版本
            {{ caliberVersion ?? "—" }} · 数据截至
            {{ asOfDate }}。榜单是同类内的相对排序，**不构成投资建议**。
          </p>

          <!-- 指标说明兜底（2026-10-17）：默认态表头只有文字，深度学习需求
               由底部折叠面板承接——比满屏 i 图标安静，比底部文档卡近。 -->
          <el-collapse v-model="metricGuideOpen" class="metric-guide">
            <el-collapse-item name="guide">
              <template #title>
                <span class="metric-guide__title">指标说明与排序方向</span>
              </template>
              <dl class="metric-guide__list">
                <div
                  v-for="col in tableColumns"
                  :key="col.key"
                  class="metric-guide__row"
                >
                  <dt>
                    {{ col.label }}
                    <span class="metric-guide__dir">{{
                      dirLabel(col.dir)
                    }}</span>
                  </dt>
                  <dd>{{ col.desc }}</dd>
                </div>
              </dl>
            </el-collapse-item>
          </el-collapse>
        </CardBlock>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import {
  getFundRiskRanking,
  getFundRiskTypes,
  type FundRiskRankingRow,
  type FundRiskTypeOption
} from "@/api/products";

// 与路由 `router/modules/asset.ts` 的 name 一致，保证 keep-alive 命中
defineOptions({ name: "AssetFundRanking" });

const router = useRouter();

const DASH = "—";

/** 表格列 = 排序入口（#2298 排序进表头）：每列 key 与后端
 *  `fund_risk_ranking.SORTABLE_METRICS` 对齐（annual_return 后端亦支持，True=降序）。
 *  曾经可排、但没有列展示的「索提诺」随分段控制器一并下线——按看不见的列排序没有意义。
 *
 *  2026-10-17 UI 优化（详见文件头「涨跌色边界」）：
 *  - `label` 去掉 `(%)`：单位统一到工具栏说明，表头更短、不被横向截断；
 *  - `kind`：`return` = 区间收益列（染涨跌色，配 +/- 符号）；`ratio` / `risk` = 中性色；
 *  - `dir`：指标方向（越高 / 越低越好），进表头 tooltip 与底部指标说明；
 *  - `bar`：夏普 / 卡玛画数据条（优中选优的核心指标，长度 = 列内相对位置）；
 *  - `hint`：面向普通用户的指标解释（2026-10-17 表头 tooltip）——夏普/卡玛这类术语
 *    只摆数字不解释，多数用户读不懂「这个数高好还是低好」；
 *  - `desc`：底部折叠面板的长说明。 */
interface RankingColumn {
  key: string;
  label: string;
  /** return = 区间收益列（染涨跌色）；ratio / risk = 中性色（合规：不做好差评价） */
  kind: "ratio" | "risk" | "return";
  /** 指标方向：越高 / 越低越好（进表头 tooltip 与底部说明） */
  dir: "high" | "low";
  /** 是否画数据条（夏普 / 卡玛：优中选优的核心指标） */
  bar?: boolean;
  /** 表头 tooltip 短解释（hover 即现，无常驻图标） */
  hint: string;
  /** 底部折叠面板长说明 */
  desc: string;
}

const tableColumns: RankingColumn[] = [
  {
    key: "sharpe",
    label: "夏普",
    kind: "ratio",
    dir: "high",
    bar: true,
    hint: "每承担 1 份年化波动，获得多少超出无风险利率的回报。大于 1 尚可、大于 2 较好；越高越好，只在同类内可比",
    desc: "夏普 =（年化收益 − 无风险利率）÷ 年化波动率。衡量「每承担一份波动换来多少超额回报」，只在同一基金类型内可比。"
  },
  {
    key: "calmar",
    label: "卡玛",
    kind: "ratio",
    dir: "high",
    bar: true,
    hint: "赚的钱抵不抵得过最深的亏损——年化收益 ÷ 最大回撤，数字越大越划算",
    desc: "卡玛 = 年化收益 ÷ |最大回撤|。衡量「盈利对最深亏损的覆盖能力」，越高越好。"
  },
  {
    key: "return_drawdown_ratio",
    label: "波回比",
    kind: "ratio",
    dir: "high",
    hint: "年化收益 ÷（波动率 × 最大回撤）：平时涨跌的幅度和最深一次亏损都算进分母，数字越大越好",
    desc: "波回比 = 年化收益 ÷（年化波动率 × 最大回撤）。同时惩罚「日常颠簸」与「最深亏损」，越高越好。"
  },
  {
    key: "ulcer_index",
    label: "UI",
    kind: "risk",
    dir: "low",
    hint: "溃疡指数：回撤的深度与持续时间合成的值。数字越大，持有过程越煎熬",
    desc: "溃疡指数 UI = √(平均(每日回撤²))，可读作「长期平均回撤幅度」。UI = 18 意味着相当长时间里账户常比前高低约 18%。越低越好。"
  },
  {
    key: "max_drawdown",
    label: "最大回撤",
    kind: "risk",
    dir: "high",
    hint: "区间内从高点到低点最多亏多少。负数存储，越浅（越接近 0）越好",
    desc: "最大回撤 = 区间内从历史高点到其后最低点的最大跌幅，以负数存储（-8 优于 -25）。只反映最深那一次亏损，不计时间。"
  },
  {
    key: "annual_return",
    label: "年化收益",
    kind: "return",
    dir: "high",
    hint: "区间收益折算成的年平均值。正为盈、负为亏",
    desc: "年化收益 = 区间收益按年折算的平均值，反映该窗口内的盈利能力。"
  },
  {
    key: "ret_1m",
    label: "近1月",
    kind: "return",
    dir: "high",
    hint: "近 30 个自然日的净值涨跌幅（累计净值）；历史不足该窗口显示 —",
    desc: "近 30 个自然日的净值涨跌幅（累计净值口径）；起点取边界日当天或之后的第一个净值日，历史不足该窗口显示 —。"
  },
  {
    key: "ret_3m",
    label: "近3月",
    kind: "return",
    dir: "high",
    hint: "近 90 个自然日的净值涨跌幅（累计净值）；历史不足该窗口显示 —",
    desc: "近 90 个自然日的净值涨跌幅（累计净值口径）；起点取边界日当天或之后的第一个净值日，历史不足该窗口显示 —。"
  },
  {
    key: "ret_1y",
    label: "近1年",
    kind: "return",
    dir: "high",
    hint: "近 365 个自然日的净值涨跌幅（累计净值）；历史不足该窗口显示 —",
    desc: "近 365 个自然日的净值涨跌幅（累计净值口径）；起点取边界日当天或之后的第一个净值日，历史不足该窗口显示 —。"
  }
];

/** 表头分组（2026-10-17 第二轮）：`keys` 必须与 `tableColumns` 的键**同序全覆盖**——
 *  分组行 colspan 按 keys 长度展开，与指标行逐列对齐；少一个键表头就会错位。
 *  列顺序即按组重排（波回比从 UI 之后提前到卡玛之后），分组才连得起来。
 *  分组是纯展示层：不改排序行为、不改口径。 */
const columnGroups: { label: string; tip: string; keys: string[] }[] = [
  {
    label: "风险调整收益",
    tip: "把风险与亏损换算掉的收益效率，均按指标窗口计算；只在同类内可比，越高越好",
    keys: ["sharpe", "calmar", "return_drawdown_ratio"]
  },
  {
    label: "风险",
    tip: "持有期间的亏损深度与煎熬程度，按指标窗口计算；越低越好",
    keys: ["ulcer_index", "max_drawdown"]
  },
  {
    label: "收益",
    tip: "年化收益按指标窗口折算；近1月 / 近3月 / 近1年为对应自然日的区间净值涨跌幅",
    keys: ["annual_return", "ret_1m", "ret_3m", "ret_1y"]
  }
];

type Column = RankingColumn;

const initialLoading = ref(true);
const typesLoading = ref(false);
const rankingLoading = ref(false);
const typeOptions = ref<FundRiskTypeOption[]>([]);
const selectedTypeId = ref<number | null>(null);
const metric = ref<string>("sharpe");
const order = ref<string>("desc");
const rows = ref<FundRiskRankingRow[]>([]);
const excludedDistorted = ref(0);
const caliberVersion = ref<number | null>(null);
const metricGuideOpen = ref<string[]>([]);

const selectedTypeName = computed(
  () =>
    typeOptions.value.find(t => t.fund_type_id === selectedTypeId.value)
      ?.name ?? ""
);
// 卡片标题只写当前类型（页头已是「同类优选」）——旧版「混合型 · 同类优选」
// 与页头、筛选器三处重复同一信息。
const rankingTitle = computed(() => selectedTypeName.value || "同类优选");
const rankingInfo = computed(() => {
  const label =
    tableColumns.find(c => c.key === metric.value)?.label ?? metric.value;
  // 沿用旧分段控件的用户语言：desc = 从优到劣（最大回撤以负数存储，降序即回撤浅者前）
  return `按「${label}」${order.value === "desc" ? "从优到劣" : "从劣到优"}排序；点击表头可切换指标与方向，悬停表头看指标解释`;
});
const excludedTip = computed(
  () =>
    `另有 ${excludedDistorted.value} 只因口径可疑（净值跳变 / 样本不足）被剔除，未进入本榜——它们算出来的值可能异常突出，但那是数据问题不是业绩。`
);
const noRowHint = computed(() =>
  excludedDistorted.value > 0
    ? "该类型下所有基金的指标都因口径可疑被剔除——数据问题，不是没有基金。"
    : "该类型下暂时没有可上榜的数据。"
);
// 指标窗口 / 数据截至（2026-10-17 第二轮）：原「窗口」列每行同值（快照全是
// 近3年），是纯噪音——删列，信息移到这里随脚注讲清口径。
const windowLabel = computed(() => rows.value[0]?.window_label ?? "—");
const asOfDate = computed(
  () => (rows.value[0]?.as_of ?? "").slice(0, 10) || "—"
);
const sampleRange = computed(() => {
  if (!rows.value.length) return DASH;
  const values = rows.value.map(r => r.sample_points).filter(v => v != null);
  if (!values.length) return DASH;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return min === max ? `${min}` : `${min}~${max}`;
});

/** 数值格式化：null 一律降级「—」（诚实降级，不编造 0）。
 *  显式 +/- 只给收益列（kind=return，design.md：不用颜色作为唯一信息载体）；
 *  夏普 / 卡玛 / 波回比 / UI 是比率、最大回撤以负数存储——给它们加「+」会读成
 *  「收益为正」（UI=+18.5 尤其误导：越高越煎熬，不是利好）。 */
function formatCell(row: FundRiskRankingRow, col: Column): string {
  const v = row[col.key as keyof FundRiskRankingRow] as number | null;
  if (v == null) return DASH;
  const fixed = v.toFixed(2);
  return col.kind === "return" && v > 0 ? `+${fixed}` : fixed;
}

/** 收益列涨跌配色（红涨绿跌，A 股惯例）：文字级 -ink 令牌保 WCAG AA，
 *  与自选页「涨跌幅」列同规则；0 与非数值不染。 */
function numClass(row: FundRiskRankingRow, col: Column): string {
  const v = row[col.key as keyof FundRiskRankingRow] as number | null;
  if (v == null || v === 0) return "";
  return v > 0 ? "num--rise" : "num--fall";
}

/** 数据条（夏普 / 卡玛）：条长 = 该值在**当前榜单**内的相对位置。
 *  全列同值时统一样式（满条）——都排在同一位置，没有长短差异可言。 */
const barRanges = computed(() => {
  const out: Record<string, { min: number; max: number }> = {};
  for (const col of tableColumns) {
    if (!col.bar) continue;
    const vals = rows.value
      .map(r => r[col.key as keyof FundRiskRankingRow] as number | null)
      .filter((v): v is number => v != null);
    if (vals.length)
      out[col.key] = { min: Math.min(...vals), max: Math.max(...vals) };
  }
  return out;
});

function barWidth(row: FundRiskRankingRow, key: string): string | undefined {
  const range = barRanges.value[key];
  const v = row[key as keyof FundRiskRankingRow] as number | null;
  if (!range || v == null) return undefined;
  const span = range.max - range.min;
  const pct = span === 0 ? 100 : ((v - range.min) / span) * 100;
  return `${Math.max(4, Math.min(100, pct))}%`;
}

function dirLabel(dir: string): string {
  return dir === "high" ? "越高越好" : "越低越好";
}

async function loadTypes() {
  typesLoading.value = true;
  try {
    const res = await getFundRiskTypes();
    typeOptions.value = res?.data?.types ?? [];
    // 默认选中只数最多的那一类（typeOptions 已按 count 降序）
    if (typeOptions.value.length && selectedTypeId.value == null) {
      selectedTypeId.value = typeOptions.value[0].fund_type_id;
    }
  } catch {
    typeOptions.value = [];
  } finally {
    typesLoading.value = false;
  }
}

/** 请求序号：连续快速点击表头会并发多次请求，过期响应直接丢弃，防止旧数据覆盖新排序 */
let loadSeq = 0;

async function loadRanking() {
  if (selectedTypeId.value == null) return;
  const seq = ++loadSeq;
  rankingLoading.value = true;
  try {
    const res = await getFundRiskRanking({
      fund_type_id: selectedTypeId.value,
      metric: metric.value,
      order: order.value as "asc" | "desc"
    });
    if (seq !== loadSeq) return;
    const data = res?.data;
    rows.value = data?.rows ?? [];
    excludedDistorted.value = data?.excluded_distorted ?? 0;
    caliberVersion.value = data?.caliber_version ?? null;
  } catch {
    if (seq !== loadSeq) return;
    rows.value = [];
    excludedDistorted.value = 0;
  } finally {
    if (seq === loadSeq) rankingLoading.value = false;
  }
}

function onTypeChange() {
  loadRanking();
}

/** 表头点击排序：首次点击 = 该列「从优到劣」——方向由列语义（dir）决定：
 *  high（数值大者好；含以负数存储的最大回撤，-8 优于 -25）⇒ desc；
 *  low（UI：正数、越小越好）⇒ asc。
 *  旧版一律 desc，点 UI 列会先把「最煎熬」的排前面——从劣到优，语义错。
 *  后端 SORTABLE_METRICS 的默认方向同此规则（ulcer_index=False 升序）。 */
function onSort(key: string) {
  if (key === metric.value) {
    order.value = order.value === "desc" ? "asc" : "desc";
  } else {
    metric.value = key;
    order.value =
      tableColumns.find(c => c.key === key)?.dir === "low" ? "asc" : "desc";
  }
  loadRanking();
}

/** aria-sort：给屏幕阅读器说明当前列的排序状态（未参与排序的列 = none） */
function ariaSort(key: string): "none" | "ascending" | "descending" {
  if (key !== metric.value) return "none";
  return order.value === "desc" ? "descending" : "ascending";
}

function goDetail(code: string) {
  router.push(`/fund/${code}`);
}

onMounted(async () => {
  try {
    await loadTypes();
    await loadRanking();
  } finally {
    initialLoading.value = false;
  }
});
</script>

<style lang="scss" scoped>
.fund-ranking-page {
  background: var(--bg-page);
}

.ranking-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding-top: var(--space-4);
}

/* ── 表格工具栏：筛选器与数据同卡（2026-10-17，原独立「筛选」卡片撤销） ── */
.ranking-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: var(--space-4);

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    align-items: center;
  }
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);

  &__label {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  &__control {
    min-width: 240px;
  }
}

.unit-note {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.excluded-tip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
  white-space: nowrap;
  cursor: help;
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
}

.empty-hint {
  padding: var(--space-5) 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;

  code {
    padding: 0 4px;
    font-family: var(--font-mono, monospace);
    background: var(--bg-subtle);
    border-radius: var(--radius-xs);
  }
}

/* ── 表格（2026-10-17 重构）──────────────────────────────────────────────
   - border-collapse: separate：sticky 列在 collapse 下边框会随滚动「漂移」；
   - thead sticky top:0（滚动祖先是布局层 .el-scrollbar__wrap，#1528 同款）；
   - 左两列（排名 / 基金）sticky：横向滚到右侧指标时始终知道在看哪只；
   - 所有 th/td 不透明底色：sticky 单元格透明会透出滚动过的内容；
   - 行 hover / 持仓行底色：覆盖含 sticky 列在内的整行。 */
.table-scroll {
  overflow-x: auto;
}

.ranking-table {
  border-spacing: 0;
  border-collapse: separate;

  th,
  td {
    padding: 14px var(--space-4); /* 行高 ≈ 44px（design.md 表格行高基线） */
    text-align: right;
    white-space: nowrap;
    background: var(--bg-card);
    border-bottom: 1px solid var(--border-subtle, var(--border-light));
  }

  th {
    position: sticky;
    z-index: 2;
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-tertiary-ink);

    /* 表头底色对齐 el-table 基线（design.md Table 节：--bg-muted）——
       页面自建表头不另起炉灶；sticky 单元格必须不透明，--bg-muted 是实色 ✓ */
    background: var(--bg-muted);
  }

  /* 双层表头（2026-10-17 第二轮）：分组行吸顶 top:0，指标行下移一行高度。
     两行都 sticky——纵向滚到长列表底部时，指标名与所属组始终在场。 */
  .th-group-row th {
    top: 0;
    height: 30px;
    padding: 5px var(--space-3);
    font-size: var(--text-label);
    font-weight: 500;
  }

  .th-metric-row th {
    top: 30px; /* = 分组行高度 */
  }

  .th-group {
    text-align: center;
    cursor: help;
  }

  td {
    font-variant-numeric: tabular-nums; /* 小数点纵向绝对对齐（design.md） */
    color: var(--text-primary);
  }

  .col-rank,
  .col-fund {
    text-align: left;
  }

  .col-rank {
    position: sticky;
    left: 0;
    z-index: 1;
    width: 48px;
    color: var(--text-tertiary-ink);
  }

  .col-fund {
    position: sticky;
    left: 48px; /* = 排名列宽 */
    z-index: 1;
    min-width: 220px;
    max-width: 260px;
  }

  /* 表头左两列同时参与两个方向 sticky，z-index 需压过普通表头与左列 */
  thead .col-rank,
  thead .col-fund {
    z-index: 3;
  }

  /* 行悬停：整行（含 sticky 列）轻微底色，对齐 el-table 基线（--bg-soft） */
  tbody tr:hover td {
    background: var(--bg-soft);
  }

  /* 持仓行底纹已删（2026-10-17 第二轮）：快照池里持仓占多数，常驻底纹没有
     「找我的那只」的信号价值，唯一一只自选行反而被读成 bug（用户实测反馈）。
     「持仓 / 自选」徽章在基金名旁，已承载该信息；行视觉回归统一。 */

  /* 当前排序指标高亮（2026-10-17 第二轮，对齐 el-table 基线）：
     EP 惯例 = 加粗 + 文字提主色 + 箭头变主题色。不用红字——金融表里红字
     读作警告；不用灰底——全站表头底是 --bg-muted，另起一档灰底即语言分裂。
     排序列辨识度靠加粗 + 箭头 + 卡片标题的「按X排序」说明，三处互证。 */
  .col-active {
    font-weight: 600;
    color: var(--text-primary);
  }

  /* 收益列涨跌色（-ink 级：白底 AA 达标；符号同色，见 formatCell） */
  .num--rise {
    color: var(--color-rise-ink);
  }

  .num--fall {
    color: var(--color-fall-ink);
  }

  /* 数据条（夏普 / 卡玛）：极浅品牌色底条衬在数字背后，
     长度 = 当前榜单内相对位置；纯装饰，读屏隐藏。 */
  .col-num {
    position: relative;
  }

  .data-bar {
    position: absolute;
    top: 50%;
    right: var(--space-4);
    left: auto;
    height: 22px;
    pointer-events: none;
    background: var(--brand-100);
    border-radius: var(--radius-xs);
    transform: translateY(-50%);
  }

  .num-text {
    position: relative;
    z-index: 1;
  }
}

/* 基金列：名称主显示、代码次要小字（只显 6 位代码用户认不出产品，2026-10-17）。
   整块可点击跳详情；名称缺失时回退代码，此时不重复显示。 */
.fund-link {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-start;
  max-width: 100%;
  overflow: hidden;
  text-align: left;
  cursor: pointer;
  background: none;
  border: none;

  &:hover .fund-link__name {
    color: var(--brand-700);
    text-decoration: underline;
  }

  &__name {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-label);
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__code {
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary-ink);
  }
}

/* 持仓 / 自选徽章：软按钮档（design.md Badge），不用涨跌色——
   标记的是「这是你的」，不是盈亏语义。 */
.fund-tag {
  flex-shrink: 0;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 16px;
  border-radius: var(--radius-pill);

  &--holding {
    color: var(--brand-700);
    background: var(--brand-100);
  }

  &--watch {
    color: var(--text-secondary);
    background: var(--bg-soft);
  }
}

/* 表头（去常驻 i 图标，2026-10-17）：整块 hover 弹 tooltip 讲指标含义，
   文字下方浅虚线下划线作「有说明」暗示；箭头区与文字同组不进 tooltip 也行——
   整组包进 tooltip，悬停即讲。 */
.col-sortable {
  cursor: pointer;
  user-select: none;

  /* 当前排序列的 brand 高亮优先，hover 不改它 */
  &:not(.col-active):hover {
    color: var(--text-primary);
    background: var(--bg-hover);
  }
}

.th-with-tip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.th-label {
  border-bottom: 1px dashed var(--border-default);
}

.th-sort {
  display: inline-flex;
  flex-direction: column;
  line-height: 1;
  vertical-align: middle;

  &__caret {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
    opacity: 0.3;
    transition: opacity 0.15s ease;

    &--active {
      color: var(--brand-700);
      opacity: 1;
    }
  }
}

.col-sortable:hover .th-sort__caret:not(.th-sort__caret--active) {
  opacity: 0.75;
}

.table-loading {
  padding: var(--space-4) 0;
}

.footnote {
  margin-top: var(--space-4);
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}

/* 底部指标说明折叠面板（2026-10-17）：替代「满屏 i 图标 + 跳底部文档卡」，
   默认收起，需要时展开；口径与方向一次讲全。 */
.metric-guide {
  margin-top: var(--space-3);
  border-top: 1px solid var(--border-subtle, var(--border-light));

  &__title {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-secondary);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
  }

  &__row {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: var(--space-4);

    dt {
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-size: var(--text-label);
      font-weight: 600;
      color: var(--text-primary);
    }

    dd {
      margin: 0;
      font-size: var(--text-label);
      line-height: 1.7;
      color: var(--text-secondary);
    }
  }

  &__dir {
    font-size: var(--text-label);
    font-weight: 400;
    color: var(--text-tertiary-ink);
  }
}
</style>
