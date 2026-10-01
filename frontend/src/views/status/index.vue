<!-- frontend/src/views/system/status.vue -->
<!--
  系统状态页（#1720 建页；#1795 命名收敛；#1799 全屏公开页；#1802 修数据读取 + 信息结构）

  信息结构参照业界 status page（GitHub / Cloudflare 等）的最小必要集：
  顶部整体状态横幅 → 组件清单（每行：名称 + 要点 + 状态）→ 法律底栏。
  刻意不写「本页面授予谁看」「供访客与维护者」这类元叙述：状态的读法由页面本身说清。

  数据来源：`GET /api/health`（**裸对象、非 {data} 信封**，见 api/health.ts 的说明）。
-->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import dayjs from "dayjs";
import { useRouter } from "vue-router";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SiteLegalBar from "@/components/SiteLegalBar/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { useAuthState } from "@/composables/useAuthState";
import { getHealth, type ComponentStatus, type HealthData } from "@/api/health";

defineOptions({
  name: "Status"
});

const router = useRouter();
const headerNavs = useMarketHeaderNavs();
const { isAuthenticated } = useAuthState();

const health = ref<HealthData | null>(null);
const loading = ref(false);
const errorMessage = ref("");
const updatedAt = ref("");

// logo 点击：登录态感知路由，与探市页一致（已登录 → 工作台；未登录 → 探市首页）
const onLogoClick = () => {
  router.push(isAuthenticated.value ? "/welcome" : "/explore");
};

type Tone = "ok" | "warn" | "error" | "muted";

const STATUS_TEXT: Record<string, string> = {
  healthy: "正常",
  ok: "正常",
  degraded: "降级",
  unhealthy: "异常",
  disabled: "未启用"
};

const statusText = (status: ComponentStatus) => STATUS_TEXT[status] ?? status;

/** 状态 → 语义色调（点色 / 文字色），只做映射，不做业务判断 */
const statusTone = (status: ComponentStatus): Tone => {
  if (status === "healthy" || status === "ok") return "ok";
  if (status === "disabled") return "muted";
  if (status === "degraded") return "warn";
  return "error";
};

interface ComponentRow {
  name: string;
  status: ComponentStatus;
  /** 常规要点（始终展示）：方言 / 最近成功运行 / 模型 */
  detail: string;
  /** 仅异常时展示的可读原因，正常时不占位（status page 的「无消息即正常」） */
  hint: string;
}

const rows = computed<ComponentRow[]>(() => {
  const c = health.value?.components;
  if (!c) return [];
  const scheduler = c.scheduler;
  const lastRun = scheduler.last_success_run
    ? scheduler.last_success_run.slice(0, 16).replace("T", " ")
    : "";
  return [
    {
      name: "数据库",
      status: c.database.status,
      detail: (c.database.dialect ?? "").toUpperCase(),
      hint: c.database.status === "healthy" ? "" : (c.database.message ?? "")
    },
    {
      name: "数据调度",
      status: scheduler.status,
      detail: !scheduler.enabled
        ? "未开启自动更新"
        : lastRun
          ? `最近成功运行 ${lastRun}`
          : "尚无成功记录",
      hint:
        scheduler.status === "healthy" || scheduler.status === "disabled"
          ? ""
          : (scheduler.message ?? "")
    },
    {
      name: "AI 识别",
      status: c.llm.status,
      detail: c.llm.configured
        ? [c.llm.provider, c.llm.model].filter(Boolean).join(" · ")
        : "未配置",
      hint:
        c.llm.status === "healthy" || c.llm.status === "disabled"
          ? ""
          : (c.llm.message ?? "")
    }
  ];
});

/** 整体横幅：一眼看出「有没有事」；异常时直接列出受影响的组件 */
const banner = computed(() => {
  if (errorMessage.value) {
    return {
      tone: "error" as Tone,
      icon: "ep:circle-close-filled",
      title: "暂时无法获取状态",
      desc: errorMessage.value
    };
  }
  if (!health.value) return null;
  const affected = rows.value.filter(
    r => statusTone(r.status) === "warn" || statusTone(r.status) === "error"
  );
  if (affected.length === 0) {
    return {
      tone: "ok" as Tone,
      icon: "ep:success-filled",
      title: "所有组件运行正常",
      desc: ""
    };
  }
  return {
    tone: "warn" as Tone,
    icon: "ep:warning-filled",
    title: "部分组件需要关注",
    desc: affected.map(r => `${r.name}：${statusText(r.status)}`).join("；")
  };
});

async function fetchHealth() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const res = await getHealth();
    // 该端点返回裸对象，无 {data} 信封；形状不符时显式报错，而不是让页面停在骨架屏
    if (!res?.components) {
      throw new Error("响应格式异常（缺少 components 字段）");
    }
    health.value = res;
  } catch (e) {
    // 失败必须落到错误态：health 保持为 null 时模板只会渲染骨架屏，
    // 用户看到的是「一直在加载」（#1793 的 /api/health 500 与 #1802 的读取错误都曾如此）
    health.value = null;
    errorMessage.value =
      (e as Error)?.message || "无法连接后端服务，请确认后端已启动";
  } finally {
    updatedAt.value = dayjs().format("HH:mm:ss");
    loading.value = false;
  }
}

onMounted(fetchHealth);
</script>

<template>
  <div class="status-page">
    <MarketHeader
      :logo="MARKET_LOGO"
      badge="系统状态"
      :navs="headerNavs"
      @logo-click="onLogoClick"
    />

    <PageHeaderBar title="系统状态" />

    <main class="status-page__body">
      <section
        v-if="banner"
        class="status-banner"
        :class="`status-banner--${banner.tone}`"
      >
        <IconifyIconOffline :icon="banner.icon" class="status-banner__icon" />
        <div class="status-banner__text">
          <p class="status-banner__title">{{ banner.title }}</p>
          <p v-if="banner.desc" class="status-banner__desc">
            {{ banner.desc }}
          </p>
          <p class="status-banner__meta">
            <template v-if="updatedAt">检查于 {{ updatedAt }}</template>
          </p>
        </div>
        <el-button
          v-if="errorMessage"
          :loading="loading"
          size="small"
          @click="fetchHealth"
        >
          重试
        </el-button>
      </section>
      <el-skeleton v-else :rows="2" animated />

      <CardBlock v-if="health">
        <SectionHeader title="组件">
          <template #action>
            <el-button :loading="loading" size="small" @click="fetchHealth">
              刷新
            </el-button>
          </template>
        </SectionHeader>
        <ul class="component-list">
          <li v-for="row in rows" :key="row.name" class="component-row">
            <span
              class="component-row__dot"
              :class="`component-row__dot--${statusTone(row.status)}`"
              aria-hidden="true"
            />
            <span class="component-row__name">{{ row.name }}</span>
            <span class="component-row__detail">{{ row.detail }}</span>
            <span
              class="component-row__status"
              :class="`component-row__status--${statusTone(row.status)}`"
            >
              {{ statusText(row.status) }}
            </span>
            <p v-if="row.hint" class="component-row__hint">{{ row.hint }}</p>
          </li>
        </ul>
      </CardBlock>
    </main>

    <footer class="status-page__footer">
      <SiteLegalBar />
    </footer>
  </div>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 全屏公开页外壳：与探市页同一套结构（页头 + 页头栏 + 内容列 + 法律底栏） */
.status-page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg-page);

  &__body {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    gap: var(--space-section);
    width: 100%;
    max-width: var(--layout-content-width);
    padding: var(--space-standard) var(--space-standard) 0;
    margin: 0 auto;

    @include bp.below("md") {
      padding: var(--space-standard) var(--space-compact) 0;
    }
  }

  &__footer {
    padding: var(--space-section) var(--space-standard) var(--space-standard);
    margin-top: var(--space-section);
    border-top: 1px solid var(--border-light);
  }
}

.status-banner {
  display: flex;
  gap: var(--space-compact);
  align-items: center;
  padding: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-left-width: 4px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);

  /* 点色直接用语义色（图形，非文字）；文字另用 *-ink 档保证对比度 */
  &--ok {
    border-left-color: var(--color-success);
  }

  &--warn {
    border-left-color: var(--color-warning);
  }

  &--error {
    border-left-color: var(--color-danger);
  }

  &__icon {
    flex: 0 0 auto;
    font-size: 28px;
  }

  &--ok &__icon {
    color: var(--color-success);
  }

  &--warn &__icon {
    color: var(--color-warning-ink);
  }

  &--error &__icon {
    color: var(--color-danger);
  }

  &__text {
    flex: 1 1 auto;
    min-width: 0;
  }

  &__title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--text-primary);
  }

  &__desc {
    margin: 4px 0 0;
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-secondary);
  }

  &__meta {
    margin: 4px 0 0;
    font-size: 12px;
    color: var(--text-tertiary-ink);
  }
}

.component-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.component-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 4px var(--space-3);
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);

  &:first-child {
    border-top: 0;
  }

  /* 窄屏：状态文字换到第三行，避免「名称 / 要点 / 状态」三列互相挤压 */
  @include bp.below("md") {
    grid-template-columns: auto minmax(0, 1fr);
  }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;

    &--ok {
      background: var(--color-success);
    }

    &--warn {
      background: var(--color-warning);
    }

    &--error {
      background: var(--color-danger);
    }

    &--muted {
      background: var(--text-disabled);
    }
  }

  &__name {
    font-size: 15px;
    color: var(--text-primary);
  }

  &__detail {
    grid-column: 3;
    font-size: 13px;
    color: var(--text-tertiary-ink);
    white-space: nowrap;

    @include bp.below("md") {
      grid-column: 2;
      white-space: normal;
    }
  }

  &__status {
    justify-self: flex-end;
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;

    &--ok {
      color: var(--color-success-ink);
    }

    &--warn {
      color: var(--color-warning-ink);
    }

    &--error {
      color: var(--color-danger-ink);
    }

    &--muted {
      color: var(--text-tertiary-ink);
    }

    @include bp.below("md") {
      justify-self: flex-start;
    }
  }

  &__hint {
    grid-column: 1 / -1;
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-secondary);
  }
}
</style>
