<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import {
  getManagerHoldings,
  getManagerProfile,
  type ManagerHoldingsResult,
  type ManagerProfileResult
} from "@/api/products";
import { productRoute } from "@/utils/productIdentity";

/**
 * 详情页「基金经理」区块（#1970 · 设计 §6 品类矩阵，#1970 扩展改版）。
 *
 * 取数：**两个端点并发**，互不阻塞
 * - `GET /api/products/manager-profile/` —— 经理档案 + 任职基金列表
 * - `GET /api/products/manager-holdings/` —— 代表作前十大重仓
 *
 * 拆成两个端点而不是塞在一起：重仓要按 fund_code 查最新报告期，是独立重查询，
 * 而首屏并非总需要它。分开后档案可以先渲染，重仓慢也不拖累整个区块。
 *
 * 入参是 **mgr_code 而非姓名**：库内实测 119 组重名（最多「吴昊」6 位），
 * 姓名不是唯一键。这里把路由 symbol **原样**发出去，不要在前端猜形态——
 * 自选/搜索里点进来的是 `MGR_<mgr_code>`（#1286 命名空间），而详情页路由的 symbol
 * 还会被 `resolve_product_identity` 大写化；**归一收口在后端**
 * （`services/manager_code.py`），前端若自己剥前缀，就会出现「两个地方各剥一半」。
 *
 * **换算全部交给后端**（#1970 扩展 · `services/tenure_display.py`）：
 * 本组件直接用后端给的 `*_display` 文本，**不做任何÷365 / toFixed 换算**。
 * 后端存的是为计算而存的原值（从业天数 5125、规模 307.94），展示口径收口在
 * 服务层单点——前端再写一次换算正是要消灭的那种重复，口径迟早会漂移。
 *
 * 不展示 12 位哈希（设计 §6）：经理类靠「姓名 + 公司」识别，展示哈希对用户无意义。
 */
const props = defineProps<{
  /** 经理编码 mgr_code（12 位哈希），非姓名 */
  mgrCode: string;
}>();

const loading = ref(false);
const profile = ref<ManagerProfileResult | null>(null);
const failed = ref(false);

const holdings = ref<ManagerHoldingsResult | null>(null);
const holdingsFailed = ref(false);

const DASH = "—";

/** 档案是否有可展示的任期类数据（决定是否还要给「尚未同步」说明） */
const hasTenureData = computed(() => {
  const p = profile.value;
  if (!p) return false;
  return (
    p.appointment_date != null ||
    p.tenure_display != null ||
    p.sum_scale != null ||
    p.funds.some(f => f.start_date != null)
  );
});

/** 任职基金是否被 fund_limit 截断（后端上限 20，实测最多 42 只） */
const fundsTruncated = computed(() => {
  const p = profile.value;
  return !!p && p.fund_count > p.funds.length;
});

/**
 * 最佳回报的涨跌色class。
 *
 * **必须由前端按符号决定**：转换层刻意不返回颜色（服务层给颜色会导致色板分裂成
 * 两套），涨跌语义属于 design.md 的视觉层。涨红跌绿用 --color-rise / --color-fall。
 */
const bestReturnClass = computed(() => {
  const v = profile.value?.best_return;
  if (v == null) return "";
  return v >= 0 ? "is-rise" : "is-fall";
});

/** 从业年限副文案：点明口径，避免把「日历跨度」误读成「累计在任年数」 */
const tenureCaption = computed(() => {
  const t = profile.value?.tenure_display;
  if (!t) return undefined;
  return t.basis === "em_days_derived" ? "自首次任职起算" : "按任职起始日推算";
});

/**
 * 风格标签 key 后缀 → 三档视觉档位（#2044）。
 *
 * 档位是**强度阶梯不是评价**（集中度高≠坏、中性≠好），故只用墨色/填充权重递进，
 * 不用红绿——那是涨跌语义专用（见 design.md「Badge / Tag」）。size 维度的
 * small/balanced/large 映射到同一阶梯；未知后缀落 mid（中性默认，前向兼容）。
 */
function styleTierClass(key: string): string {
  const suffix = key.split("_").pop() ?? "";
  if (suffix === "low" || suffix === "small") return "is-low";
  if (suffix === "high" || suffix === "large") return "is-high";
  return "is-mid";
}

/**
 * 代表作风格标签（#2044）。
 *
 * 数据不足的维度由后端**缺席**（不给该 dim，而非 null 占位）；列表为空则整行
 * 不渲染——不显示空容器、不渲染占位徽章。
 */
const styleBadges = computed(() =>
  (holdings.value?.style_labels ?? []).map(lb => ({
    ...lb,
    tierClass: styleTierClass(lb.key)
  }))
);

async function load() {
  if (!props.mgrCode) return;
  loading.value = true;
  failed.value = false;
  holdingsFailed.value = false;
  // 两个端点并发：档案失败不牵连重仓，反之亦然
  const [profileRes, holdingsRes] = await Promise.allSettled([
    getManagerProfile({ mgr_code: props.mgrCode }),
    getManagerHoldings({ mgr_code: props.mgrCode })
  ]);

  if (profileRes.status === "fulfilled") {
    profile.value = profileRes.value.data;
  } else {
    // 非经理编码 / 未收录 / 网络异常：统一降级为空态，不影响详情页其余区块
    profile.value = null;
    failed.value = true;
  }

  if (holdingsRes.status === "fulfilled") {
    holdings.value = holdingsRes.value.data;
  } else {
    holdings.value = null;
    holdingsFailed.value = true;
  }

  loading.value = false;
}

watch(() => props.mgrCode, load, { immediate: true });
</script>

<template>
  <CardBlock class="mgr-section">
    <SectionHeader title="基金经理" />

    <p v-if="loading" class="mgr-section__hint">正在读取基金经理资料…</p>

    <p v-else-if="failed || !profile" class="mgr-section__hint">
      暂无可展示的基金经理资料
    </p>

    <template v-else>
      <!-- 身份行：姓名 + 公司（重名靠公司消歧，库内 119 组重名） -->
      <div class="mgr-section__identity">
        <span class="mgr-section__name">{{ profile.name || DASH }}</span>
        <span class="mgr-section__company">{{ profile.company || DASH }}</span>
      </div>

      <!-- 指标卡：数值直接用后端换算结果，不在前端做二次换算 -->
      <MetricGrid class="mgr-section__metrics">
        <MetricCard
          title="从业年限"
          :value="profile.tenure_display?.text ?? DASH"
          :caption="tenureCaption"
        />
        <MetricCard
          title="管理规模"
          :value="profile.scale_display?.value ?? DASH"
          :unit="profile.scale_display ? profile.scale_display.unit : undefined"
          caption="现任基金合计"
        />
        <MetricCard
          title="最佳回报"
          :value="profile.best_return_display?.text ?? DASH"
          caption="现任基金中最高"
        />
        <MetricCard
          title="任职基金"
          :value="profile.fund_count"
          :unit="profile.fund_count ? '只' : undefined"
          :caption="
            profile.active_fund_count
              ? `在任 ${profile.active_fund_count} 只`
              : undefined
          "
        />
      </MetricGrid>

      <!-- 最佳回报涨跌色：视觉语义在前端，数据不带色 -->
      <p
        v-if="profile.best_return_display"
        class="mgr-section__best-return"
        :class="bestReturnClass"
      >
        {{ profile.name }} 的现任基金最佳回报
        {{ profile.best_return_display.text }}
      </p>

      <!-- 任期类字段整片为空时给出定调说明，避免用户以为加载失败 -->
      <p v-if="!hasTenureData" class="mgr-section__note">
        从业年限与任期起止尚未同步，当前仅展示任职基金名单。
      </p>

      <!-- 任职基金列表：在任 / 已卸任分明，点条目跳该基金详情页 -->
      <div v-if="profile.funds.length" class="mgr-section__funds">
        <h4 class="mgr-section__subtitle">任职基金</h4>
        <ul class="mgr-section__fund-list">
          <li
            v-for="f in profile.funds"
            :key="f.fund_code"
            class="mgr-section__fund-item"
          >
            <RouterLink
              class="mgr-section__fund-link"
              :to="productRoute({ assetType: 'fund', symbol: f.fund_code })"
            >
              {{ f.name }}
            </RouterLink>
            <span class="mgr-section__fund-meta">
              <!-- 任期跨度：起始 ~ 结束（在任则到今天）。空值不渲染，不显示「— ~ —」 -->
              <span v-if="f.start_date" class="mgr-section__fund-tenure">
                {{ f.start_date.slice(0, 7) }} ~
                {{ f.end_date ? f.end_date.slice(0, 7) : "至今" }}
              </span>
              <span
                v-if="f.tenure_display"
                class="mgr-section__fund-tenure-length"
              >
                {{ f.tenure_display.text }}
              </span>
              <!-- 在任标记以 F10 任期为准：东财全量表把已卸任者仍列为现任 -->
              <span
                v-if="!f.is_active"
                class="mgr-section__badge mgr-section__badge--muted"
              >
                已卸任
              </span>
              <span v-else-if="f.is_classic" class="mgr-section__badge"
                >代表作</span
              >
            </span>
          </li>
        </ul>
        <p v-if="fundsTruncated" class="mgr-section__note">
          共 {{ profile.fund_count }} 只，当前仅显示前
          {{ profile.funds.length }} 只。
        </p>
      </div>
      <p v-else class="mgr-section__hint">暂无关联的任职基金</p>

      <!-- 代表作前十大重仓（#1970 扩展）。口径标签必须展示：
           否则「只披露 10 只」会被误读成「只买了 10 只」 -->
      <div
        v-if="holdings && holdings.rows.length"
        class="mgr-section__holdings"
      >
        <div class="mgr-section__holdings-head">
          <h4 class="mgr-section__subtitle">重仓明细</h4>
          <span v-if="holdings.fund_name" class="mgr-section__holdings-fund">
            {{ holdings.fund_name }}
          </span>
        </div>
        <!-- 风格标签（#2044）：徽章文字直接用后端 label；依据 basis 走 tooltip；
             维度缺席即该徽章不出现，为空整行不渲染 -->
        <div v-if="styleBadges.length" class="mgr-section__styles">
          <span class="mgr-section__styles-label">风格</span>
          <ul class="mgr-section__styles-list" aria-label="风格标签">
            <li
              v-for="lb in styleBadges"
              :key="lb.key"
              class="mgr-section__style-item"
            >
              <el-tooltip :content="lb.basis" placement="top">
                <span
                  class="mgr-section__style-badge"
                  :class="lb.tierClass"
                  tabindex="0"
                >
                  {{ lb.label }}
                </span>
              </el-tooltip>
            </li>
          </ul>
        </div>
        <el-table :data="holdings.rows" size="small" class="mgr-section__table">
          <el-table-column label="#" width="48">
            <template #default="{ row }">{{ row.rank }}</template>
          </el-table-column>
          <el-table-column label="股票" min-width="140">
            <template #default="{ row }">
              <span class="mgr-section__stock">{{
                row.stock_name || row.stock_code
              }}</span>
            </template>
          </el-table-column>
          <el-table-column label="占净值比" align="right" width="110">
            <template #default="{ row }">
              <span class="mgr-section__ratio">
                {{ row.ratio == null ? DASH : row.ratio.toFixed(2) + "%" }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <p class="mgr-section__note">
          报告期 {{ holdings.report_period }}（{{ holdings.basis_label }}）
          <template v-if="holdings.total_ratio != null">
            ，前 {{ holdings.rows.length }} 大合计占净值
            {{ holdings.total_ratio.toFixed(2) }}%
          </template>
        </p>
      </div>
      <p v-else-if="holdingsFailed" class="mgr-section__hint">
        重仓明细读取失败
      </p>
      <p v-else-if="holdings?.empty_reason" class="mgr-section__hint">
        {{ holdings.empty_reason }}
      </p>
    </template>
  </CardBlock>
</template>

<style lang="scss" scoped>
.mgr-section {
  &__identity {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-6);
    align-items: baseline;
    margin-bottom: var(--space-6);
  }

  &__name {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__company {
    font-size: 13px;
    color: var(--text-tertiary-ink);
  }

  &__metrics {
    margin-bottom: var(--space-3);
  }

  /* 涨跌语义：数据不带色，视觉在前端决定（涨红跌绿，见 design.md） */
  &__best-return {
    margin: 0 0 var(--space-3);
    font-size: 13px;
    color: var(--text-secondary);

    &.is-rise {
      color: var(--color-rise-ink);
    }

    &.is-fall {
      color: var(--color-fall-ink);
    }
  }

  &__hint {
    margin: 0;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  &__note {
    padding: var(--space-2) var(--space-3);
    margin: var(--space-3) 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-secondary);
    background: var(--bg-soft);
    border-radius: var(--radius-sm);
  }

  &__funds,
  &__holdings {
    margin-top: var(--space-5);
  }

  &__subtitle {
    margin: 0 0 var(--space-2);
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__fund-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__fund-item {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-3);
    align-items: center;
    justify-content: space-between;
  }

  &__fund-link {
    font-size: 13px;
    color: var(--text-primary);
    text-decoration: none;

    &:hover {
      color: var(--brand-700);
    }

    /* 键盘焦点必须可见（#1838 可访问性） */
    &:focus-visible {
      outline: 2px solid var(--brand-700);
      outline-offset: 2px;
    }
  }

  &__fund-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
    font-size: 12px;

    /* 数字用等宽，避免日期/百分比在列内跳动 */
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  &__fund-tenure-length {
    color: var(--text-secondary);
  }

  &__badge {
    padding: 0 4px;
    font-size: 11px;
    color: var(--brand-700);
    background: var(--brand-100);
    border-radius: var(--radius-sm);

    &--muted {
      color: var(--text-tertiary);
      background: var(--bg-muted);
    }
  }

  &__holdings-head {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-3);
    align-items: baseline;
    justify-content: space-between;
  }

  &__styles {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
    margin-top: var(--space-2);
  }

  &__styles-label {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  &__styles-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    padding: 0;
    margin: 0;
    list-style: none;
  }

  /* 档位阶梯：描边（低）→ 软底（中）→ 软底+重墨（高）。
     中性强度递进，刻意不用红绿——涨跌语义专用（design.md「Badge / Tag」）；
     配色由 key 档位在本层映射，后端不返回颜色 */
  &__style-badge {
    display: inline-flex;
    align-items: center;
    padding: 1px 8px;
    font-size: 11px;
    line-height: 1.6;
    color: var(--text-secondary);
    cursor: help;
    border: 1px solid transparent;
    border-radius: var(--radius-pill);

    &.is-low {
      border-color: var(--border-subtle);
    }

    &.is-mid {
      background: var(--bg-soft);
    }

    &.is-high {
      font-weight: 600;
      color: var(--text-primary);
      background: var(--bg-soft);
    }

    /* 依据（basis）经 tooltip 展示，键盘 focus 也必须可见（#1838 可访问性） */
    &:focus-visible {
      outline: 2px solid var(--brand-700);
      outline-offset: 2px;
    }
  }

  &__holdings-fund {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  &__stock {
    color: var(--text-primary);
  }

  &__ratio {
    /* 表格数字必须等宽（design.md 表格规范） */
    font-variant-numeric: tabular-nums;
  }
}
</style>
