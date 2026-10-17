<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  fetchProStatus,
  type ProductResolveResult,
  type ProStatusResult
} from "@/api/products";

/**
 * 详情页「高级洞察 Pro」占位区块（#2272 · #994 Phase 1）。
 *
 * 定位：#994 的 Tab 2 在通篇详情页里的落点——建设期只放**占位 + 付费墙壳**，
 * 模块内容随 Phase 2-4（里程碑 #19）逐个上线，届时仅后端翻转可用性位，
 * 本组件按位渲染，前端无感。
 *
 * 品类门控（自门控，与 ProductExternalLinksSection 同一模式）：四模块都是
 * **基金向**分析（绩效归因 / 风险 / 配置 / 穿透），故只对 fund / etf 渲染；
 * 其余品类（stock / bond / index / manager / portfolio）接入是 Phase 2+
 * 的品类扩展决策，届时改 PRO_ASSET_TYPES 一处白名单，不动挂载点。
 *
 * 两条已拍板约束（#994 评论，2026-10-08）：
 * 1. **付费墙是纯前端 feature flag**：env `VITE_PRO_PAYWALL_ENABLED` 控制遮罩，
 *    未配置时默认开启（"Pro 只作后期功能墙"）；后端接口一期全开无权益校验，
 *    权益判定后期抽 `GET /api/me/entitlements`，与本组件解耦；
 * 2. **不用 mock / 演示数据占位**：徽标（Phase N 建设中）来自后端状态位，
 *    取不到就不显示徽标，绝不编造"已上线"。
 *
 * 锚点：根节点 attribute fallthrough 把 `id="nav-pro"` 挂到 CardBlock 上，
 * 页内导航（useProductPageNav）扫 DOM 时自动收录（NAV_LABELS 已登记）。
 */

const props = defineProps<{
  /** 详情页 resolve 结果（与 ProductIdentityCard 同传参模式；取 symbol / asset_type） */
  product: ProductResolveResult;
}>();

/** 一期只对基金家族开放（模块全是基金向分析）；扩品类改这里，勿改挂载点 */
const PRO_ASSET_TYPES = ["fund", "etf"];

const enabled = computed(() =>
  PRO_ASSET_TYPES.includes(props.product.asset_type)
);

/** 四模块展示元数据——纯呈现层；可用性 / 落地 Phase 以后端状态位为唯一真相 */
const MODULE_META = [
  {
    key: "performance",
    title: "深度绩效与归因",
    desc: "权益分拆 XIRR、交易行为画像、持有期回撤——全部基于你自己的真实持仓与流水（账户级口径）。"
  },
  {
    key: "risk",
    title: "偏离与风险控制",
    desc: "净值乖离率、波动率、VaR——你的持仓成本与基金风险指标并示，偏离过高时克制提示。"
  },
  {
    key: "allocation",
    title: "资产配置与相关性",
    desc: "大类资产画像、持仓穿透、相关性矩阵——识别「看起来分散、实则同涨同跌」的组合。"
  },
  {
    key: "report",
    title: "智能报告与自动化",
    desc: "投资报告导出与异动提醒——把一页分析变成可留存、可回顾的结论。"
  }
] as const;

/** 付费墙遮罩开关（未配置默认开启；显式传 "false" 关闭） */
const paywallEnabled = import.meta.env.VITE_PRO_PAYWALL_ENABLED !== "false";

const status = ref<ProStatusResult | null>(null);

onMounted(async () => {
  if (!enabled.value) return;
  try {
    const { data } = await fetchProStatus(
      props.product.symbol,
      props.product.asset_type
    );
    status.value = data;
  } catch {
    // 状态位取不到不阻断区块：占位卡照常渲染，仅少了徽标（宁缺勿假）
    status.value = null;
  }
});

/** 模块徽标文案；状态位未就绪时返回 null（不渲染徽标，不编造） */
function badgeText(key: string): string | null {
  const module = status.value?.modules[key as keyof ProStatusResult["modules"]];
  if (!module) return null;
  return module.available ? "已上线" : `Phase ${module.phase} 建设中`;
}
</script>

<template>
  <CardBlock v-if="enabled" class="pro-section">
    <SectionHeader
      title="高级洞察 Pro"
      info="深度分析与归因的付费能力位。当前为建设期：四个模块按 Phase 2-4 逐个上线。上线后，基金级指标来自第三方数据源并标注「非账户级」口径；你的账户级指标（XIRR、行为画像）始终基于自己的流水计算。"
      info-label="关于高级洞察 Pro"
    />
    <div class="pro-section__body">
      <div class="pro-section__grid">
        <article v-for="meta in MODULE_META" :key="meta.key" class="pro-module">
          <header class="pro-module__head">
            <h3 class="pro-module__title">{{ meta.title }}</h3>
            <span v-if="badgeText(meta.key)" class="pro-module__badge">{{
              badgeText(meta.key)
            }}</span>
          </header>
          <p class="pro-module__desc">{{ meta.desc }}</p>
        </article>
      </div>

      <!-- 付费墙遮罩（VITE_PRO_PAYWALL_ENABLED 控制）：只遮内容区不遮标题，
           且不阻断详情页其他区块——「克制不打扰」（#994 付费墙交互）。 -->
      <div v-if="paywallEnabled" class="pro-paywall">
        <p class="pro-paywall__title">解锁高级风险指标与交易行为分析</p>
        <p class="pro-paywall__desc">
          升级至 Pro 版，持续获得归因、风险与配置洞察。
        </p>
        <button
          class="pro-paywall__cta"
          type="button"
          disabled
          title="升级通道随付费体系建设后开放"
        >
          升级 Pro
        </button>
      </div>
    </div>
  </CardBlock>
</template>

<style scoped>
.pro-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pro-section__body {
  position: relative;
}

.pro-section__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
}

.pro-module {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-module__head {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
}

.pro-module__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.pro-module__badge {
  flex-shrink: 0;
  padding: 0 var(--space-1);
  font-size: 11px;
  color: var(--brand-ink);
  background: color-mix(in srgb, var(--brand-700) 10%, transparent);
  border-radius: 4px;
}

.pro-module__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

/* 付费墙遮罩：贴住内容区（不遮 SectionHeader），translucent 卡片底 + 轻模糊 */
.pro-paywall {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-card) 86%, transparent);
  border-radius: var(--radius-md);
  backdrop-filter: blur(2px);
}

.pro-paywall__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.pro-paywall__desc {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.pro-paywall__cta {
  padding: var(--space-1) var(--space-4);
  font-size: 13px;
  color: var(--text-inverse);
  cursor: not-allowed;
  background: var(--brand-700);
  border: none;
  border-radius: 4px;
  opacity: 0.6;
}
</style>
