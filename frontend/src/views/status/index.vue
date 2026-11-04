<!-- frontend/src/views/system/status.vue -->
<!--
  系统状态页（#1720 建页；#1795 命名收敛；#1799 全屏公开页；#1802 修数据读取 + 信息结构）

  信息结构参照业界 status page（GitHub / Cloudflare 等）的最小必要集：
  顶部整体状态横幅 → 组件清单（每行：名称 + 要点 + 状态）→ 法律底栏。
  刻意不写「本页面授予谁看」「供访客与维护者」这类元叙述：状态的读法由页面本身说清。

  数据来源：`GET /api/health`（**裸对象、非 {data} 信封**，见 api/health.ts 的说明）。

  #980 批 B9 拆分后本文件只剩「取数 + 外壳」：
  - 状态→文案/色调、组件行、整体横幅 → `components/statusModel.ts`（纯函数）
  - 顶部横幅（含骨架屏）→ `components/StatusBanner.vue`
  - 组件清单 → `components/StatusComponentList.vue`
-->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import dayjs from "dayjs";
import { useRouter } from "vue-router";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SiteLegalBar from "@/components/SiteLegalBar/index.vue";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { useAuthState } from "@/composables/useAuthState";
import { getHealth, type HealthData } from "@/api/health";
import StatusBanner from "./components/StatusBanner.vue";
import StatusComponentList from "./components/StatusComponentList.vue";
import { buildBanner, buildComponentRows } from "./components/statusModel";

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

const rows = computed(() => buildComponentRows(health.value));

/** 整体横幅：一眼看出「有没有事」；异常时直接列出受影响的组件 */
const banner = computed(() =>
  buildBanner({
    errorMessage: errorMessage.value,
    hasHealth: !!health.value,
    rows: rows.value
  })
);

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
      <StatusBanner
        :banner="banner"
        :loading="loading"
        :error-message="errorMessage"
        :updated-at="updatedAt"
        @retry="fetchHealth"
      />

      <StatusComponentList
        v-if="health"
        :rows="rows"
        :loading="loading"
        @refresh="fetchHealth"
      />
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
</style>
