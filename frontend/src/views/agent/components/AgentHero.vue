<!--
  空态：能力目录（功能型空态，不是营销落地页）。

  2026-11 改版要点（原版是「两行大标题 + 品牌渐变词 + 3 个示例块」）：
  - 去掉口号式文案：这页是工作台，第一屏该回答「我能查什么」，不是讲品牌故事；
  - 3 个示例 → 能力目录：与后端工具注册表对齐（见 agentQuickActions.ts），
    空态成为一次性的能力导航，用后即消失（有对话就不占地方）；
  - 每项都是 button（点一下直接发问、键盘可达、有焦点环），不是装饰文案；
  - 不再用 `min-height: calc(100vh - 260px)` 猜视口高——那个魔法数字在 375px 高
    屏上把内容顶到输入区下面（实测第三条示例被 dock 压住）。改自然流 + 上下留白。

  2026-11-26 分层（用户反馈「10 个入口权重完全平等」）：
  10 项平铺 2 列，读起来是一张没有主次的菜单，且「单只基金」与「整个账户」并列。
  现在三段：
  - **主入口**一张整行大卡（资产总览：唯一的汇总口径，其余 9 项都是它的下钻方向）；
  - **常用** 3 列（默认收益/持仓/市场，点过之后按最近使用排——见 useRecentCapabilities）；
  - **更多能力**默认折叠，展开后按粒度分组（账户与市场 / 单只基金）。
  折叠不会藏掉可发现性：能力清单就在「更多能力（N 项）」这一行上写着。

  本文件只负责**编排**（分几段、怎么分、展开与否）；单张卡长什么样在
  AgentCapabilityCard.vue，卡片结构与样式不在两处维护。
-->
<template>
  <div class="chat-hero" data-region="agent-capabilities">
    <div class="chat-hero__intro">
      <h2 class="chat-hero__title">问一句，我把账户里的事实查给你</h2>
      <p class="chat-hero__desc">
        只读查询，不改任何数据；不预测涨跌，不给买卖建议。
      </p>
    </div>

    <!-- 主入口：独占一行，视觉权重最高 -->
    <AgentCapabilityCard v-if="primary" :cap="primary" primary @ask="ask" />

    <!-- 常用 3 项：一屏可见、固定槽数（不随使用次数长成第二份全量清单） -->
    <div class="chat-hero__grid chat-hero__grid--pinned">
      <AgentCapabilityCard
        v-for="cap in pinned"
        :key="cap.key"
        :cap="cap"
        @ask="ask"
      />
    </div>

    <!-- 更多能力：默认折叠。v-show 而非 v-if——展开/收起时内部按钮不销毁，
         键盘焦点不会因为折叠再展开而掉回页面顶部。 -->
    <div v-if="restGroups.length > 0" class="chat-hero__more">
      <button
        type="button"
        class="chat-hero__toggle"
        :aria-expanded="moreOpen ? 'true' : 'false'"
        aria-controls="agent-capability-more"
        @click="moreOpen = !moreOpen"
      >
        <span>更多能力（{{ restCount }} 项）</span>
        <el-icon
          class="chat-hero__toggle-icon"
          :class="{ 'is-open': moreOpen }"
          aria-hidden="true"
        >
          <ArrowDown />
        </el-icon>
      </button>

      <div
        v-show="moreOpen"
        id="agent-capability-more"
        class="chat-hero__more-body"
      >
        <section
          v-for="g in restGroups"
          :key="g.group"
          class="chat-hero__group"
        >
          <h3 class="chat-hero__group-title">{{ g.label }}</h3>
          <div class="chat-hero__grid">
            <AgentCapabilityCard
              v-for="cap in g.items"
              :key="cap.key"
              :cap="cap"
              @ask="ask"
            />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowDown } from "@element-plus/icons-vue";
import AgentCapabilityCard from "./AgentCapabilityCard.vue";
import {
  CAPABILITY_GROUP_LABELS,
  DEFAULT_PINNED_KEYS,
  PRIMARY_CAPABILITY_KEY
} from "../agentQuickActions";
import type {
  AgentCapability,
  AgentCapabilityGroup
} from "../agentQuickActions";
import { useRecentCapabilities } from "../useRecentCapabilities";

defineOptions({ name: "AgentCapabilityGrid" });

const props = defineProps<{
  /** 能力目录（唯一来源见 agentQuickActions.ts 的 AGENT_CAPABILITIES） */
  capabilities: readonly AgentCapability[];
}>();

const emit = defineEmits<{
  (e: "ask", question: string): void;
}>();

/** 主入口（整行大卡）；目录里没有该项时整段不渲染，不至于空出一个大白块 */
const primary = computed<AgentCapability | null>(
  () => props.capabilities.find(c => c.key === PRIMARY_CAPABILITY_KEY) ?? null
);

const { pinned: pinnedKeys, record } =
  useRecentCapabilities(DEFAULT_PINNED_KEYS);

/** 常用位：key → 能力对象。目录里已下线的 key 会被过滤掉（不渲染空按钮） */
const pinned = computed<AgentCapability[]>(() =>
  pinnedKeys.value
    .map(key => props.capabilities.find(c => c.key === key))
    .filter((c): c is AgentCapability => Boolean(c))
);

/** 除主入口与常用位之外的全部（保持目录原顺序，组内顺序才稳定） */
const rest = computed<AgentCapability[]>(() => {
  const used = new Set(pinned.value.map(c => c.key));
  return props.capabilities.filter(
    c => c.key !== PRIMARY_CAPABILITY_KEY && !used.has(c.key)
  );
});

const restCount = computed(() => rest.value.length);

/**
 * 按粒度分组。组的顺序跟目录里首次出现的顺序一致
 * （AGENT_CAPABILITIES 先 account 后 fund），不另外维护一份组序常量。
 */
const restGroups = computed<
  { group: AgentCapabilityGroup; label: string; items: AgentCapability[] }[]
>(() => {
  const groups: {
    group: AgentCapabilityGroup;
    label: string;
    items: AgentCapability[];
  }[] = [];
  for (const cap of rest.value) {
    let bucket = groups.find(g => g.group === cap.group);
    if (!bucket) {
      bucket = {
        group: cap.group,
        label: CAPABILITY_GROUP_LABELS[cap.group],
        items: []
      };
      groups.push(bucket);
    }
    bucket.items.push(cap);
  }
  return groups;
});

/** 「更多能力」展开态。不持久化：它是「这一眼想看看还有什么」，不是长期偏好 */
const moreOpen = ref(false);

/**
 * 点击能力：主入口不记（它永远在大卡上，记进常用位只是和自己重复），
 * 其余点击记一次，下次进来常用位就是按最近使用排的。
 */
function ask(cap: AgentCapability): void {
  if (cap.key !== PRIMARY_CAPABILITY_KEY) record(cap.key);
  emit("ask", cap.ask);
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.chat-hero {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding: clamp(8px, 3vh, 32px) 0 var(--space-standard);
}

.chat-hero__intro {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chat-hero__title {
  margin: 0;
  font-size: var(--text-heading);
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-primary);
}

.chat-hero__desc {
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.6;
  color: var(--text-secondary);
}

/* 目录：≥sm 两列（一行两项，扫读快、不做成「设置菜单」），窄屏一列。
   ⚠️ 列间距 > 行间距（16 / 8）：两者相等时 10 张卡读成「一片均匀的方格」，
   分不清是 2 组×5 还是 5 组×2。列宽拉开后，同列的两项才被读成一对。 */
.chat-hero__grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-2) var(--space-4);

  @include bp.above("sm") {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* 常用位固定 3 槽：宽屏一行三项，与上方主卡合成「1 + 3」的层级 */
.chat-hero__grid--pinned {
  @include bp.above("lg") {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

/* 与上方常用区多留 8px：两者都是「一行卡片」的高度，
   间距相等时折叠开关会被读成第四行卡（它是次要入口，要靠留白降权）。 */
.chat-hero__more {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-2);
}

/* 折叠开关：视觉上是一行文字，不是按钮——它旁边就是真按钮，
   自己再有边框就会变成「第 N+1 张卡」。负 margin 让文字与卡片左边缘对齐 */
.chat-hero__toggle {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
  align-self: flex-start;
  padding: var(--space-1) var(--space-2);
  margin-left: calc(var(--space-2) * -1);
  font-family: inherit;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  transition:
    color 0.15s ease,
    background-color 0.15s ease;

  &:hover {
    color: var(--text-primary);
    background-color: var(--bg-soft);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

.chat-hero__toggle-icon {
  transition: transform 0.15s ease;

  &.is-open {
    transform: rotate(180deg);
  }
}

.chat-hero__more-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.chat-hero__group-title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-tertiary-ink);
}

@include bp.below("md") {
  .chat-hero__title {
    font-size: var(--text-body);
  }
}
</style>
