<!--
  WatchlistQuickViewDrawer · 自选行「速览」抽屉（#1285）

  设计文档「行内交互：抽屉 vs 详情页」两级模型的第一步：
  行点击 → 抽屉（速览）→ 抽屉内「查看详情」→ 完整详情页。

  本版本为**速览版**：展示当前可得的通用字段（行情 / 持有 / 信息 / 备注）。
  品种专属维度（指数估值、可转债条款、投顾持仓等）待数据底座落地后增量补充；
  详情页入口**预留且禁用**（详情页后期实现），避免与「行点击」争抢语义。

  可持有品类判定与列配置层一致：index / manager / portfolio 不展示「持有」区。
-->
<template>
  <el-drawer
    v-model="visible"
    title="速览"
    size="420px"
    direction="rtl"
    destroy-on-close
  >
    <div v-if="item" class="wqv">
      <!-- 头部：名称 / 代码 / 类型 / 组合分层信息 -->
      <div class="wqv-head">
        <div class="wqv-name" :title="item.display_name || item.symbol">
          {{ item.display_name || item.symbol }}
        </div>
        <div class="wqv-meta">
          <span v-if="!isComposite && item.symbol" class="wqv-code">
            {{ item.symbol }}
          </span>
          <span v-if="item.type_label" class="wqv-type">
            {{ item.type_label }}
          </span>
        </div>
        <div v-if="compositeMeta" class="wqv-meta">{{ compositeMeta }}</div>
      </div>

      <!-- 行情 -->
      <section class="wqv-sec">
        <h4 class="wqv-sec__title">行情</h4>
        <dl class="wqv-grid">
          <div class="wqv-cell">
            <dt class="wqv-label">最新价</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="hasPrice"
                :value="item.current_price as number"
                :precision="precision"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">涨跌幅</dt>
            <dd class="wqv-value">
              <RiseFallText
                v-if="hasChange"
                :value="item.change_pct as number"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- 持有（仅可持有品类） -->
      <section v-if="isHoldable" class="wqv-sec">
        <h4 class="wqv-sec__title">持有</h4>
        <dl class="wqv-grid">
          <div class="wqv-cell">
            <dt class="wqv-label">持有数量</dt>
            <dd class="wqv-value">
              {{ item.holding_quantity != null ? item.holding_quantity : "—" }}
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">持仓市值</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="item.position_market_value != null"
                :value="item.position_market_value"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">成本价</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="item.holding_cost_price != null"
                :value="item.holding_cost_price"
                :precision="precision"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">持仓收益</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="item.holding_pnl != null"
                :value="item.holding_pnl"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- 信息 -->
      <section class="wqv-sec">
        <h4 class="wqv-sec__title">信息</h4>
        <dl class="wqv-list">
          <div class="wqv-row">
            <dt class="wqv-label">添加自选日</dt>
            <dd class="wqv-value">
              {{ item.created_at ? formatDate(item.created_at) : "—" }}
            </dd>
          </div>
          <div class="wqv-row">
            <dt class="wqv-label">所属分组</dt>
            <dd class="wqv-value">{{ groupText }}</dd>
          </div>
          <div class="wqv-row">
            <dt class="wqv-label">标签</dt>
            <dd class="wqv-value">{{ tagText }}</dd>
          </div>
        </dl>
      </section>

      <!-- 投顾组合信息（#1468）：配置目标 / 产品类型 / 净值 / 策略简介 / 官方链接 -->
      <section v-if="isPortfolio" class="wqv-sec">
        <h4 class="wqv-sec__title">投顾信息</h4>
        <dl class="wqv-list">
          <div class="wqv-row">
            <dt class="wqv-label">配置目标</dt>
            <dd class="wqv-value">
              {{ item.advisor_allocation_label || "—" }}
            </dd>
          </div>
          <div class="wqv-row">
            <dt class="wqv-label">产品类型</dt>
            <dd class="wqv-value">{{ item.advisor_product_type || "—" }}</dd>
          </div>
          <div class="wqv-row">
            <dt class="wqv-label">组合净值</dt>
            <dd class="wqv-value">{{ navText || "—" }}</dd>
          </div>
          <div v-if="strategySummary" class="wqv-row">
            <dt class="wqv-label">策略简介</dt>
            <dd class="wqv-value wqv-value--wrap">{{ strategySummary }}</dd>
          </div>
          <div v-if="sourceUrl" class="wqv-row">
            <dt class="wqv-label">官方页面</dt>
            <dd class="wqv-value">
              <a
                class="wqv-link"
                :href="sourceUrl"
                target="_blank"
                rel="noopener noreferrer"
                >前往查看</a
              >
            </dd>
          </div>
        </dl>
      </section>

      <!-- 投顾组合成分与调仓（#1468）：抽屉打开时按需拉取，不进列表主请求 -->
      <section v-if="isPortfolio" class="wqv-sec">
        <h4 class="wqv-sec__title">成分与调仓</h4>

        <div v-if="detailLoading" class="wqv-hint">加载中…</div>
        <div v-else-if="detailError" class="wqv-empty">{{ detailError }}</div>
        <template v-else>
          <dl class="wqv-list">
            <div class="wqv-row">
              <dt class="wqv-label">成分基金</dt>
              <dd class="wqv-value">
                <span v-if="holdingsCount">{{ holdingsCount }} 只</span>
                <span v-else class="wqv-empty">—</span>
                <span v-if="missingCount" class="wqv-hint">
                  · {{ missingCount }} 只未收录本地
                </span>
              </dd>
            </div>
          </dl>

          <div v-if="adjustGroups.length" class="wqv-adjusts">
            <div
              v-for="g in adjustGroups"
              :key="g.adjust_date"
              class="wqv-adjust"
            >
              <div class="wqv-adjust__head">
                <span class="wqv-adjust__date">{{ g.adjust_date }}</span>
                <span class="wqv-hint">{{ g.items.length }} 只调整</span>
              </div>
              <ul class="wqv-adjust__list">
                <li v-for="it in g.items" :key="it.fund_code" class="wqv-li">
                  <span class="wqv-li__name" :title="it.fund_name || ''">
                    {{ it.fund_name || it.fund_code }}
                  </span>
                  <span class="wqv-li__ratio">
                    <span :class="opClass(it.op_name)">{{ it.op_name }}</span>
                    {{ ratioText(it) }}
                  </span>
                </li>
              </ul>
            </div>
          </div>
          <div v-else class="wqv-empty">
            暂无调仓记录{{
              isQieman ? "（需累积 ≥2 次持仓快照后自动推导）" : ""
            }}
          </div>
        </template>
      </section>

      <!-- 备注（可编辑） -->
      <section class="wqv-sec">
        <div class="wqv-sec__head">
          <h4 class="wqv-sec__title">备注</h4>
          <el-button text size="small" @click="emit('edit-notes', item)">
            编辑
          </el-button>
        </div>
        <p v-if="item.notes" class="wqv-notes">{{ item.notes }}</p>
        <p v-else class="wqv-empty">暂无备注</p>
      </section>

      <!-- 详情页入口（预留，详情页后期实现） -->
      <div class="wqv-footer">
        <el-button disabled>查看详情</el-button>
        <span class="wqv-hint">详情页开发中</span>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";
import {
  getAdvisorAdjusts,
  getAdvisorHoldings,
  type AdvisorAdjustGroup,
  type AdvisorAdjustItem,
  type AdvisorAdjustsResult,
  type AdvisorHoldingsResult
} from "@/api/funds";
import type { WatchlistItem } from "@/api/watchlist";

const props = defineProps<{
  modelValue: boolean;
  item: WatchlistItem | null;
  /** 全部标签（用于 tag_ids → 名称映射，与表格渲染同一份数据） */
  allTags?: { id: number; name: string; color?: string | null }[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  /** 点击「编辑」→ 由页面打开备注编辑弹窗（复用 #1285 的 NotesEditorDialog） */
  "edit-notes": [item: WatchlistItem];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

/** 非交易实体（组合 / 经理）：不展示代码、不展示「持有」区 */
const COMPOSITE_TYPES = new Set(["manager", "portfolio"]);
/** 不可持有品类：与 columnDefs.TRADABLE_TYPES 互补 */
const NON_HOLDABLE_TYPES = new Set(["index", "manager", "portfolio"]);

const assetType = computed(() => (props.item?.asset_type || "").toLowerCase());
const isComposite = computed(() => COMPOSITE_TYPES.has(assetType.value));
const isHoldable = computed(() => !NON_HOLDABLE_TYPES.has(assetType.value));
/** 投顾组合：额外展示策展元数据与策略简介（#1468） */
const isPortfolio = computed(() => assetType.value === "portfolio");

/** 策略简介完整文本（表格列里是单行省略的，抽屉里给全文） */
const strategySummary = computed(
  () => props.item?.advisor_strategy_summary || ""
);

/** 组合净值 + 净值日期，合并成「1.2345（截至 2026-09-11）」 */
const navText = computed(() => {
  const nav = props.item?.advisor_nav;
  if (nav == null) return "";
  const d = props.item?.advisor_nav_date;
  return d ? `${nav.toFixed(4)}（截至 ${d}）` : nav.toFixed(4);
});

/** 只放行 http(s)：外部站点 url 直接插 href 有注入风险 */
const sourceUrl = computed(() => {
  const raw = props.item?.advisor_source_url;
  if (!raw) return "";
  try {
    const u = new URL(raw);
    return u.protocol === "http:" || u.protocol === "https:" ? raw : "";
  } catch {
    return "";
  }
});
const precision = computed(() => pricePrecision(props.item?.asset_type ?? ""));

const hasPrice = computed(
  () => props.item?.current_price != null && props.item.current_price !== 0
);
const hasChange = computed(() => props.item?.change_pct != null);

/** 组合类标的的分层信息（平台 · 主理人 · 策略；经理为所属公司） */
const compositeMeta = computed(() => {
  const it = props.item;
  if (!it) return "";
  if (assetType.value === "portfolio") {
    return [it.advisor_platform, it.advisor_host, it.advisor_strategy_type]
      .filter(Boolean)
      .join(" · ");
  }
  if (assetType.value === "manager") {
    return it.manager_company || "";
  }
  return "";
});

const groupText = computed(() => {
  const names = props.item?.group_names ?? [];
  return names.length ? names.join("、") : "—";
});

const tagText = computed(() => {
  const ids = props.item?.tag_ids ?? [];
  const names = ids
    .map(id => props.allTags?.find(t => t.id === id)?.name)
    .filter((n): n is string => !!n);
  return names.length ? names.join("、") : "—";
});

/* ── #1468 成分与调仓：抽屉打开时按需拉取 ──
   不进列表主请求：只有点开速览的组合才需要，105 只组合全量带明细会拖慢列表。 */

const isQieman = computed(
  () => (props.item?.advisor_platform || "").toUpperCase() === "QIEMAN"
);
const detailLoading = ref(false);
const detailError = ref("");
const holdingsCount = ref(0);
const missingCount = ref(0);
const adjustGroups = ref<AdvisorAdjustGroup[]>([]);

/** http 拦截器可能已拆信封也可能没拆（仓库里两种写法并存），这里都兜住 */
function unwrap<T>(res: unknown): T | null {
  if (!res) return null;
  const r = res as { data?: unknown };
  return ((r.data ?? res) as T) ?? null;
}

async function loadDetail(symbol: string) {
  detailLoading.value = true;
  detailError.value = "";
  holdingsCount.value = 0;
  missingCount.value = 0;
  adjustGroups.value = [];
  try {
    const [hRes, aRes] = await Promise.all([
      getAdvisorHoldings(symbol),
      getAdvisorAdjusts(symbol, 3)
    ]);
    const h = unwrap<AdvisorHoldingsResult>(hRes);
    const holdings = h?.holdings ?? [];
    holdingsCount.value = holdings.length;
    missingCount.value = holdings.filter(x => !x.in_local_db).length;

    const a = unwrap<AdvisorAdjustsResult>(aRes);
    adjustGroups.value = a?.adjusts ?? [];
  } catch {
    detailError.value = "明细加载失败";
  } finally {
    detailLoading.value = false;
  }
}

watch(
  () => [props.modelValue, props.item?.symbol, isPortfolio.value] as const,
  ([open, symbol, isPf]) => {
    if (!open || !isPf || !symbol) return;
    void loadDetail(String(symbol));
  },
  { immediate: true }
);

/** 加仓/减仓用涨跌语义色，新增/持平/建仓用中性色（不是「行情」，别误导） */
function opClass(op: string | null): string {
  if (op === "加仓") return "wqv-op wqv-op--add";
  if (op === "减仓") return "wqv-op wqv-op--cut";
  return "wqv-op";
}

function ratioText(it: AdvisorAdjustItem): string {
  const pre = it.pre_ratio;
  const after = it.after_ratio;
  if (pre == null && after == null) return "";
  if (pre == null) return `${after?.toFixed(2)}%`;
  if (after == null) return `${pre.toFixed(2)}% → —`;
  return `${pre.toFixed(2)}% → ${after.toFixed(2)}%`;
}
</script>

<style scoped>
.wqv {
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 16px);
}

.wqv-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wqv-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.wqv-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

.wqv-sec {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wqv-sec__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.wqv-sec__title {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.wqv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  margin: 0;
}

.wqv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
}

.wqv-cell,
.wqv-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.wqv-row {
  justify-content: space-between;
}

.wqv-label {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.wqv-value {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  text-align: right;
}

.wqv-empty {
  color: var(--text-disabled);
}

/* #1468 策略简介可能上百字，右对齐 + 换行阅读（默认 .wqv-value 是 text-align:right） */
.wqv-value--wrap {
  max-width: 260px;
  line-height: 1.6;
  text-align: left;
  white-space: pre-wrap;
}

.wqv-link {
  color: var(--el-color-primary);
  text-decoration: none;
}

.wqv-link:hover {
  text-decoration: underline;
}

/* #1468 调仓明细：按调仓日分组的紧凑列表 */
.wqv-adjusts {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}

.wqv-adjust__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 4px;
}

.wqv-adjust__date {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.wqv-adjust__list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.wqv-li {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  padding: 2px 0;
  font-size: 12px;
}

.wqv-li__name {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-secondary);
  white-space: nowrap;
}

.wqv-li__ratio {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.wqv-op {
  margin-right: 4px;
  color: var(--text-tertiary);
}

/* 加/减仓用涨跌语义变量（不硬编码色值），其余操作保持中性色 */
.wqv-op--add {
  color: var(--color-rise);
}

.wqv-op--cut {
  color: var(--color-fall);
}

.wqv-notes {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  word-break: break-word;
  white-space: pre-wrap;
}

.wqv-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-top: var(--space-2, 8px);
  border-top: 1px solid var(--border-light);
}

.wqv-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
