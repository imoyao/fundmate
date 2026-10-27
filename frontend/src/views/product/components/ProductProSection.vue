<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  fetchProStatus,
  type ProductResolveResult,
  type ProStatusResult
} from "@/api/products";
import ProductProAllocation from "./ProductProAllocation.vue";
import ProductProPerformance from "./ProductProPerformance.vue";
import ProductProRisk from "./ProductProRisk.vue";
import ProModuleGrid from "./proSection/ProModuleGrid.vue";
import ProPaywall from "./proSection/ProPaywall.vue";
import ProProgressRow from "./proSection/ProProgressRow.vue";
import {
  isEntitled,
  isProEnabled,
  moduleAvailable
} from "./proSection/proModel";
import { resolvePaywallEnabled } from "./proEntitlement";

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
 * 两条已拍板约束（#994 评论 2026-10-08；第 1 条已随 #2324 权益落地改写）：
 * 1. **付费墙由后端权益驱动，env / URL 只是显式覆盖**：`GET /api/products/pro/` 的
 *    `paywall_required` 已按家庭权益算（`backend/app/services/product_pro_status.py`），
 *    未配置 `VITE_PRO_PAYWALL_ENABLED` 时以它为准；env 传 "true" / "false" 可强制开 / 关
 *    （e2e 与本地预览用，见 `playwright.config.ts` 的 webServer env），URL
 *    `?pro_paywall=0|1` 同义且优先级更高（免重建dev server 的运行时放行口）。
 *    状态位取不到（null）时**不显示遮罩**——「还没问出来」不等于「未开通」。四态实现见
 *    `proEntitlement.ts` 的 `resolvePaywallEnabled`；三个内容端点在未开通时回
 *    `403 + error_code=1007`，各内容块自行渲染权益未开通态（块级自治，互不阻塞）；
 *    **env / URL 只决定遮罩显隐，不改权益事实**——介绍卡两态（#2523）只认后端；
 * 2. **不用 mock / 演示数据占位**：徽标（Phase N 建设中）来自后端状态位，
 *    取不到就不显示徽标，绝不编造"已上线"。
 *
 * ## 介绍卡两态（#2523，用户 #2400 评审反馈）
 *
 * 四张模块介绍卡**只有未开通家庭看得到**（引导开通）；已开通态换成一行
 * 「模块进度」（已上线计数 + 下一个未上线模块的 Phase）——介绍卡是获客件，
 * 把「Phase N 建设中」的排期语言留给付费用户是噪声，但状态位信号不丢。
 * 判据取后端 `paywall_required`（不取 env 覆盖：env 只管遮罩显不显示，
 * 不改权益事实）；取不到按未开通（兜底内容不能掏空区块）。介绍卡组带组名
 * 「高级洞察 Pro」，与页内导航锚点同名同序。
 *
 * 锚点：根节点 attribute fallthrough 把 `id="nav-pro"` 挂到 CardBlock 上，
 * 页内导航（useProductPageNav）扫 DOM 时自动收录（NAV_LABELS 已登记）。
 *
 * ## 结构（#980 拆分）
 *
 * - `proSection/proModel.ts` —— 门控 / 徽标文案 / 两态判定 / 进度文案（纯函数）
 * - `proSection/ProModuleGrid.vue` —— 未开通态的四张介绍卡（含组名行）
 * - `proSection/ProProgressRow.vue` —— 已开通态的「模块进度」一行
 * - `proSection/ProPaywall.vue` —— 付费墙遮罩
 */
const props = defineProps<{
  /** 详情页 resolve 结果（与 ProductIdentityCard 同传参模式；取 symbol / asset_type） */
  product: ProductResolveResult;
}>();

const enabled = computed(() => isProEnabled(props.product.asset_type));

const status = ref<ProStatusResult | null>(null);

/**
 * 付费墙开关（四层，优先级从高到低，URL 层 #2527）：URL `?pro_paywall=0|1` >
 * env `VITE_PRO_PAYWALL_ENABLED` > 后端 `paywall_required`。URL 与 env 都是
 * **显式覆盖**——只管遮罩显不显示，不改权益事实（介绍卡两态只认后端，
 * 见 `proModel.isEntitled` 的注释）。判定逻辑与单测见 `proEntitlement.ts`。
 *
 * URL 读取形态（hash 路由）：`/#/fund/<symbol>?pro_paywall=1`——查询串在
 * hash 里由 vue-router 解析。重复参数（`?pro_paywall=1&pro_paywall=0`）会
 * 解析成数组，按「不猜」处理：非字符串一律当没给，逐层往下落。
 */
const route = useRoute();

const paywallUrlFlag = computed(() => {
  const raw = route.query.pro_paywall;
  return typeof raw === "string" ? raw : null;
});

const PAYWALL_ENV_FLAG = import.meta.env.VITE_PRO_PAYWALL_ENABLED;

const paywallEnabled = computed(() =>
  resolvePaywallEnabled(
    paywallUrlFlag.value,
    PAYWALL_ENV_FLAG,
    status.value?.paywall_required
  )
);

/** 已开通家庭：介绍卡整组隐藏，换「模块进度」一行（判据见 proModel.isEntitled） */
const entitled = computed(() => isEntitled(status.value));

/** 模块一内容是否可渲染（后端状态位翻真后挂载 ProductProPerformance，#994 Phase 2） */
const performanceAvailable = computed(() =>
  moduleAvailable(status.value, "performance")
);

/** 模块三内容是否可渲染（后端状态位翻真后挂载 ProductProAllocation，#994 Phase 2） */
const allocationAvailable = computed(() =>
  moduleAvailable(status.value, "allocation")
);

/** 模块二内容是否可渲染（后端状态位翻真后挂载 ProductProRisk，#994 Phase 2） */
const riskAvailable = computed(() => moduleAvailable(status.value, "risk"));

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
</script>

<template>
  <CardBlock v-if="enabled" class="pro-section">
    <SectionHeader
      title="高级洞察"
      info="深度绩效归因、风险控制、资产配置与智能报告——四大高级分析模块陆续上线中。与你账户相关的指标（如真实收益率、交易行为画像）始终基于你自己的持仓与流水计算。"
      info-label="关于高级洞察 Pro"
    >
      <!-- Pro 档位胶囊：Badge「品牌」档（#2303）。文字用 --brand-ink（品牌文字级，
           #1599 batch 3）而非 --brand-700——后者作文字白底仅 3.73:1 不达 AA。 -->
      <template #badge>
        <span class="pro-section__pro-badge">Pro</span>
      </template>
    </SectionHeader>
    <div class="pro-section__body">
      <!-- 模块一内容区（#994 Phase 2）：状态位翻真才挂载取数；无账户数据时
           组件内部渲染引导文案——「可用」≠「有数据」由组件自行分化 -->
      <ProductProPerformance
        v-if="performanceAvailable"
        class="pro-section__performance"
        :symbol="product.symbol"
        :asset-type="product.asset_type"
      />

      <!-- 模块三内容区（#994 Phase 2）：当前标的 vs 家庭其余持仓的相关性。
           没有足够持仓时会自行渲染引导文案（「可用」≠「有数据」由组件分化） -->
      <ProductProAllocation
        v-if="allocationAvailable"
        class="pro-section__alloc"
        :symbol="product.symbol"
        :asset-type="product.asset_type"
      />

      <!-- 模块二内容区（#994 Phase 2）：BIAS + 波动率 + VaR；块级自治，
           基金级指标不依赖账户数据，无持仓时账户级块自行降级 -->
      <ProductProRisk
        v-if="riskAvailable"
        class="pro-section__risk"
        :symbol="product.symbol"
        :asset-type="product.asset_type"
      />

      <!-- 介绍卡组（#2523 两态）：**仅未开通家庭可见**（引导开通）。已开通整组隐藏——
           模块内容就在上方，介绍卡是获客件不是路线图。判据与理由见 proModel.isEntitled。 -->
      <ProModuleGrid v-if="!entitled" :status="status" />
      <ProProgressRow v-else :status="status" />

      <!-- 付费墙遮罩（三态：env 显式覆盖 / 后端 paywall_required）：只遮内容区不遮标题，
           且不阻断详情页其他区块——「克制不打扰」（#994 付费墙交互）。 -->
      <ProPaywall v-if="paywallEnabled" />
    </div>
  </CardBlock>
</template>

<style scoped>
/* 顶部品牌渐变光带（#2303）：Pro 区块的唯一表现力信号。
   渐变取单一来源令牌 --pro-accent-gradient（colors.css 亮 / dark.scss 暗），
   禁止手写同款渐变。光带 3px 贴卡片顶缘，overflow:hidden 负责把两端裁进圆角。 */
.pro-section {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow: hidden;
}

.pro-section::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  content: "";
  background: var(--pro-accent-gradient);
}

/* Pro 档位胶囊：Badge「品牌」档（--brand-200 底），文字用品牌文字级 --brand-ink */
.pro-section__pro-badge {
  flex-shrink: 0;
  padding: 0 var(--space-2);
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 20px;
  color: var(--brand-ink);
  background: var(--brand-200);
  border-radius: var(--radius-pill);
}

/* 内容区：付费墙遮罩的定位上下文（.pro-paywall 是 absolute inset:0） */
.pro-section__body {
  position: relative;
}

.pro-section__performance {
  margin-bottom: var(--space-3);
}

.pro-section__alloc {
  margin-bottom: var(--space-3);
}

.pro-section__risk {
  margin-bottom: var(--space-3);
}
</style>
