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
import ProductProPerformance from "./ProductProPerformance.vue";
import ProductProAllocation from "./ProductProAllocation.vue";
import ProductProRisk from "./ProductProRisk.vue";
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

const status = ref<ProStatusResult | null>(null);

/**
 * 付费墙开关（四层，优先级从高到低，URL 层 #2527）：URL `?pro_paywall=0|1` >
 * env `VITE_PRO_PAYWALL_ENABLED` > 后端 `paywall_required`。URL 与 env 都是
 * **显式覆盖**——只管遮罩显不显示，不改权益事实（介绍卡两态只认后端，
 * 见 entitled 的注释）。判定逻辑与单测见 `proEntitlement.ts`。
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

/** 模块是否已上线（决定徽章档位与卡片是否降权）；状态位未就绪按未上线处理（#2303） */
function moduleAvailable(key: string): boolean {
  return (
    status.value?.modules[key as keyof ProStatusResult["modules"]]
      ?.available === true
  );
}

/** 模块一内容是否可渲染（后端状态位翻真后挂载 ProductProPerformance，#994 Phase 2） */
const performanceAvailable = computed(
  () => status.value?.modules.performance?.available === true
);

/** 模块三内容是否可渲染（后端状态位翻真后挂载 ProductProAllocation，#994 Phase 2） */
const allocationAvailable = computed(
  () => status.value?.modules.allocation?.available === true
);

/** 模块二内容是否可渲染（后端状态位翻真后挂载 ProductProRisk，#994 Phase 2） */
const riskAvailable = computed(
  () => status.value?.modules.risk?.available === true
);

/**
 * 介绍卡两态（#2523）：**只有未开通家庭看得到这四张卡**。
 *
 * 用户反馈（#2400 评审）：「下面的 4 个 Pro 介绍卡应仅在无权限时显示
 * （引导开通，功能未实现），已开通则不需或换更好方式」。
 *
 * 判据取**后端权益事实** `paywall_required`（#2324：家庭一份权益都没开通 ⇒
 * true；未登录同样按未开通），**不取 env 覆盖**——env 只决定遮罩显不显示
 * （e2e / 本地预览用），不改变「这个家庭有没有权益」这个事实。两者混用会出
 * 现「e2e 关了遮罩，介绍卡也跟着消失」的串味。
 *
 * 状态位取不到（null，请求失败 / 未挂载完）时按**未开通**处理：介绍卡是区块
 * 的兜底内容，「问不出来」时不能把区块掏空（宁缺勿假的反面是宁空勿假，这里
 * 空区块比多四张卡更糟）。
 *
 * 已开通态整组隐藏：已上线模块的内容就在上方，把「Phase N 建设中」这种内部
 * 排期语言留给已付费用户是噪声——介绍卡是获客件，不是路线图。未上线模块的
 * 预告由运营侧统一给，不占详情页版面。
 */
const entitled = computed(() => status.value?.paywall_required === false);

/** 介绍卡组（含组名）是否渲染 */
const showIntroGrid = computed(() => !entitled.value);

/** 已上线模块数（已开通态进度行） */
const liveModuleCount = computed(
  () => MODULE_META.filter(m => moduleAvailable(m.key)).length
);

/**
 * 首个未上线模块（按 MODULE_META 顺序；全上线为 null）。
 *
 * 已开通态用「模块进度」一行代替四张介绍卡（#2523）：介绍卡是获客件，付费用户
 * 看进度不看推销；但「哪个模块在建」这个状态位信号不能丢——它来自后端
 * `modules[*].phase`，与徽标同源。
 */
const nextPendingModule = computed(() => {
  const meta = MODULE_META.find(m => !moduleAvailable(m.key));
  if (!meta) return null;
  const mod =
    status.value?.modules[meta.key as keyof ProStatusResult["modules"]];
  return mod ? { title: meta.title, phase: mod.phase } : null;
});

/**
 * 模块进度行文案（**整串在 computed 里拼，不在模板里跨行插值**——Vue 的
 * condense 模式会吃掉跨行文本节点里的换行+缩进，「Phase\n4」会渲染成
 * 「Phase4」；单插值从根上没这个歧义，e2e 也能逐字断言）。
 */
const progressText = computed(() => {
  const base = `已上线 ${liveModuleCount.value}/${MODULE_META.length}`;
  const pending = nextPendingModule.value;
  return pending
    ? `${base} · ${pending.title} Phase ${pending.phase} 建设中`
    : base;
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
           模块内容就在上方，介绍卡是获客件不是路线图。判据与理由见 showIntroGrid。 -->
      <div v-if="showIntroGrid" class="pro-section__intro">
        <!-- 卡片组名（用户反馈：「4 张卡片是不是应该带个名字」）：与页内导航锚点名
             （NAV_LABELS「高级洞察 Pro」）同名同序——无名浮块读不出归属，现在
             组名 / 锚点 / 标题+徽标三处一个名。overline 样式与标题行分层，不重复感。 -->
        <div class="pro-section__intro-head">
          <span class="pro-section__intro-name">高级洞察 Pro</span>
          <span class="pro-section__intro-hint">开通后陆续解锁四大模块</span>
        </div>

        <div class="pro-section__grid">
          <article
            v-for="meta in MODULE_META"
            :key="meta.key"
            class="pro-module"
            :class="{ 'pro-module--pending': !moduleAvailable(meta.key) }"
          >
            <header class="pro-module__head">
              <h3 class="pro-module__title">{{ meta.title }}</h3>
              <span
                v-if="badgeText(meta.key)"
                class="pro-module__badge"
                :class="
                  moduleAvailable(meta.key)
                    ? 'pro-module__badge--live'
                    : 'pro-module__badge--wip'
                "
                >{{ badgeText(meta.key) }}</span
              >
            </header>
            <p class="pro-module__desc">{{ meta.desc }}</p>
          </article>
        </div>
      </div>

      <!-- 已开通态（#2523）：四张介绍卡换成一「模块进度」行——获客件不对付费用户
           展示，但「哪些上线 / 哪个在建」的状态位信号不丢（与徽标同源，来自
           后端 modules[*].phase）。全上线时只有计数，不硬凑「建设中」。 -->
      <div v-else class="pro-section__progress">
        <span class="pro-section__progress-label">模块进度</span>
        <span class="pro-section__progress-text">{{ progressText }}</span>
      </div>

      <!-- 付费墙遮罩（三态：env 显式覆盖 / 后端 paywall_required）：只遮内容区不遮标题，
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

.pro-section__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
}

/* 介绍卡组（#2523）：组名行 + 卡片网格。组名与页内导航锚点同名（「高级洞察 Pro」）——
   无名浮块读不出归属。overline 样式（小号 + 品牌色 + 字距）与 SectionHeader 的
   标题行分层：同屏两个「高级洞察 Pro」一个是区块名一个是组名，形态不同不犯复读感。 */
.pro-section__intro {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.pro-section__intro-head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.pro-section__intro-name {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--brand-ink);
  letter-spacing: 0.02em;
}

.pro-section__intro-hint {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 已开通态模块进度行（#2523）：一行代替四张介绍卡。标签用品牌文字级、
   数值用主文字级——「模块进度」是语境不是数据，数据是后面的计数与 Phase。 */
.pro-section__progress {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-3);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-section__progress-label {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--brand-ink);
}

.pro-section__progress-text {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
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
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

/* 阶段徽章：中性三档语言（#2044 / #2303）——红绿是涨跌语义专用，阶段状态禁用 */
.pro-module__badge {
  flex-shrink: 0;
  padding: 0 var(--space-2);
  font-size: var(--text-label);
  line-height: 18px;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
}

/* 已上线：中档（--bg-soft 底 + 主文字 600），尘埃落定的安静态 */
.pro-module__badge--live {
  font-weight: 600;
  color: var(--text-primary);
  background: var(--bg-soft);
}

/* Phase N 建设中：低档（透明底 + 弱描边），规划中内容不与已上线内容争权重 */
.pro-module__badge--wip {
  font-weight: 400;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

.pro-module__desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

/* 未上线模块整体降权：描述文字降到辅助级，让已上线模块承担视觉主体（#2303） */
.pro-module--pending .pro-module__desc {
  color: var(--text-tertiary);
}

/* 付费墙遮罩：贴住内容区（不遮 SectionHeader），高不透明度实底
   （#2319）去掉 backdrop-filter：design.md 红线是「Glass 毛玻璃仅限全局浮窗」，
   全站唯一合法用法在 style/index.scss 的全局浮窗层；付费墙是贴住卡片内容区的
   绝对定位遮罩，不是浮窗，用毛玻璃即违规。原 blur(2px) 叠在 86% 实底之上肉眼
   几乎不可感知——既没拿到质感，又留下一个每次严格审计都会命中的违规点。
   去掉后把不透明度提到 92% 补偿失去的模糊分离感，保证被遮内容不干扰遮罩文字可读性。 */
.pro-paywall {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-card) 92%, transparent);
  border-radius: var(--radius-md);
}

.pro-paywall__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.pro-paywall__desc {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.pro-paywall__cta {
  padding: var(--space-1) var(--space-4);
  font-size: var(--text-label);
  color: var(--text-inverse);
  cursor: not-allowed;

  /* #1600 实底阶梯：--brand-700 白字 3.86:1 不达 AA，实底一律走 --brand-solid（800） */
  background: var(--brand-solid);
  border: none;
  border-radius: var(--radius-sm);
  opacity: 0.6;
}
</style>
