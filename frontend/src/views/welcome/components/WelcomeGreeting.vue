<template>
  <!-- 顶部欢迎语（规范：docs/design/welcome-greeting-spec.md v1.3） -->
  <div class="flex justify-between items-center mb-6" aria-live="polite">
    <div class="flex flex-col gap-2">
      <!-- 状态三：未读站内信提示条（叠加在顶部，可选迭代功能） -->
      <div
        v-if="hasUnread"
        class="flex items-center gap-2 text-sm"
        :style="{ color: 'var(--color-warning-ink)' }"
      >
        <span>📬 你有 {{ unreadCount }} 条未读消息</span>
        <button
          type="button"
          class="underline underline-offset-2 hover:opacity-80"
          @click="openNotice"
        >
          查看
        </button>
      </div>

      <!-- 主数据行：加载中仅展示品牌定调语；数据态展示问候+天数 -->
      <div class="flex items-center gap-2">
        <template v-if="welcomeState === 'data'">
          <span
            class="font-medium"
            :style="{
              color: 'var(--text-primary)',
              fontSize: '24px',
              fontWeight: 500
            }"
          >
            <span class="welcome-nickname">{{ userTitle }}</span>
            👋 {{ greetingText }},你已记账
            <span
              class="font-bold"
              :style="{
                color: 'var(--color-rise-ink)',
                fontVariantNumeric: 'tabular-nums'
              }"
              >{{ recordDays }}</span
            >
            天
          </span>
        </template>
        <span
          v-else
          class="font-medium"
          :style="{ color: 'var(--text-secondary)', fontSize: '14px' }"
        >
          把涨跌交给市场，用复利丈量自己 🌊
        </span>
      </div>

      <!-- 首页消息播报：真实数据派生，轮动展示 -->
      <Transition name="ticker-fade" mode="out-in">
        <p
          :key="tickerIndex"
          class="flex items-center gap-2 text-sm"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          <span
            class="shrink-0 font-medium"
            :style="{ color: 'var(--brand-700)' }"
            >播报</span
          >
          <span>{{ currentHomeMessage }}</span>
        </p>
      </Transition>
    </div>

    <!-- 右侧按钮：仅空状态（含未读）显示「导入持仓，看清每日涨跌」。
         #936：原指向 `/asset/entry` 是死链（全仓无此路由，点击无反应），且「先记账」与
         「先有持仓才能算涨跌」的真实上手顺序相反。改为直达持仓快照导入（holding-import）——
         默认的文件 / AI 两档跳过选账户步骤、由后端按文件自动归因，是零持仓用户门槛最低的
         第一步（#1788 新增的「手动录入」分段才需要先选归属账户）。
         用 name 而非字面 path：名称写错时 vue-router 会直接告警，不会像死链那样静默存活
         （静态兜底见 scripts/check_router_links.mjs）。 -->
    <router-link
      v-if="welcomeState === 'empty'"
      :to="{ name: 'InvestmentHoldingImport' }"
      class="btn-welcome-cta"
      aria-label="导入持仓，看清每日涨跌"
    >
      导入持仓，看清每日涨跌
    </router-link>
  </div>
</template>

<script setup lang="ts">
import type { WelcomeState } from "../composables/useWelcomeData";

defineOptions({ name: "WelcomeGreeting" });

defineProps<{
  welcomeState: WelcomeState;
  hasUnread: boolean;
  unreadCount: number;
  userTitle: string;
  greetingText: string;
  recordDays: number;
  tickerIndex: number;
  currentHomeMessage: string;
}>();

const openNotice = () => {
  // TODO: 待 lay-notice 真实站内信路由接入后替换；当前无真实跳转目标
  console.debug("[welcome] 打开站内信：待 lay-notice 路由接入");
};
</script>
