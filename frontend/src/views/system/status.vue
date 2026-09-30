<!-- frontend/src/views/system/status.vue -->
<!--
  系统状态页（#1720 建页；#1795 命名收敛；#1799 改为全屏公开页）

  定位：与探市（/explore）同族的**全屏公开页**，不经 Layout（无侧边栏）。
  出口页脚带「系统状态」入口，探市/主站页脚点进来若落到带侧边栏的后台布局，
  对匿名访客是观感割裂的跳变，故状态页自带 —— 共用 MarketHeader / PageHeaderBar /
  SiteLegalBar，与探市页保持同一套品牌外壳。

  命名口径：页面叫 status（业界 status page 惯例），后端接口仍是 /api/health
  （运维探活端点，探活工具普遍按 /health 调用，且属 conventions.md 尾斜杠规范例外 D28）。
-->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import dayjs from "dayjs";
import { useRouter } from "vue-router";
import { ElNotification } from "element-plus";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SiteLegalBar from "@/components/SiteLegalBar/index.vue";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { useAuthState } from "@/composables/useAuthState";
import { getHealth, type ComponentStatus, type HealthData } from "@/api/health";

defineOptions({
  name: "SystemStatus"
});

const router = useRouter();
const headerNavs = useMarketHeaderNavs();
const { isAuthenticated } = useAuthState();

const health = ref<HealthData | null>(null);
const loading = ref(false);
// 失败原因：非空即代表本次拉取失败，页面必须退出骨架屏（见 fetchHealth 注释）
const errorMessage = ref("");
// 本次查询时刻（页头胶囊）：状态页没有「业务数据更新时间」概念，展示查询时刻最诚实
const queriedAt = ref("");
const headerUpdatedAt = computed(() =>
  queriedAt.value ? `${queriedAt.value} 查询` : ""
);

// logo 点击：登录态感知路由，与探市页一致（已登录 → 工作台；未登录 → 探市首页）
const onLogoClick = () => {
  router.push(isAuthenticated.value ? "/welcome" : "/explore");
};

function statusTagType(
  status: ComponentStatus
): "success" | "warning" | "danger" | "info" | "primary" {
  switch (status) {
    case "healthy":
    case "ok":
      return "success";
    case "disabled":
      return "info";
    case "degraded":
    case "unhealthy":
      return "danger";
    default:
      return "warning";
  }
}

function statusText(status: ComponentStatus): string {
  const map: Record<string, string> = {
    healthy: "正常",
    ok: "正常",
    disabled: "未启用",
    degraded: "降级",
    unhealthy: "异常"
  };
  return map[status] ?? status;
}

async function fetchHealth() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const res = await getHealth();
    health.value = res.data;
  } catch (e) {
    // 关键：失败必须落到错误态，而不是让 health 保持 null → 骨架屏一直转
    // （#1793 现象：/api/health 500 时本页看起来「一直在加载」，实际是接口挂了）
    health.value = null;
    errorMessage.value =
      (e as Error)?.message || "无法连接后端服务，请确认后端已启动";
    ElNotification({
      title: "获取系统状态失败",
      message: errorMessage.value,
      type: "error"
    });
  } finally {
    queriedAt.value = dayjs().format("HH:mm:ss");
    loading.value = false;
  }
}

// 首次启动一次性提示（#1720）：默认关闭数据调度，部署后首次进入状态页显式引导一次。
function showFirstLaunchTip() {
  const KEY = "fm_first_launch_tip";
  if (localStorage.getItem(KEY)) return;
  localStorage.setItem(KEY, "1");
  ElNotification({
    title: "欢迎使用多多贝 · 数据调度说明",
    message:
      "数据自动更新（每日净值 / 温度计）默认关闭。如需自动更新，请在 .env 设置 SCHEDULER_ENABLED=1 并常驻调度进程；本页可随时查看调度与数据库 / LLM 状态。",
    type: "info",
    duration: 10000,
    offset: 60
  });
}

onMounted(() => {
  fetchHealth();
  showFirstLaunchTip();
});
</script>

<template>
  <div class="status-page">
    <MarketHeader
      :logo="MARKET_LOGO"
      badge="系统状态"
      :navs="headerNavs"
      @logo-click="onLogoClick"
    />

    <PageHeaderBar
      title="系统状态"
      subtitle="展示服务进程、数据库、数据调度与 AI 识别的运行状况，供访客与维护者查看（本页免登录）"
      :updated-at="headerUpdatedAt"
    >
      <template #action>
        <el-button :loading="loading" size="small" @click="fetchHealth">
          刷新
        </el-button>
      </template>
    </PageHeaderBar>

    <main class="status-page__body">
      <el-card shadow="never">
        <template #header>整体状态</template>
        <el-alert
          v-if="health"
          :title="`整体状态：${health.status === 'ok' ? '正常' : '需关注'}`"
          :type="health.status === 'ok' ? 'success' : 'warning'"
          :description="health.message"
          show-icon
          :closable="false"
        />
        <template v-else-if="errorMessage">
          <el-alert
            title="暂时拿不到系统状态"
            type="error"
            :description="errorMessage"
            show-icon
            :closable="false"
          />
          <el-button class="mt-3" size="small" @click="fetchHealth">
            重试
          </el-button>
        </template>
        <el-skeleton v-else :rows="4" animated />
      </el-card>

      <template v-if="health">
        <el-card shadow="never">
          <template #header>数据库</template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="状态">
              <el-tag
                :type="statusTagType(health.components.database.status)"
                size="small"
              >
                {{ statusText(health.components.database.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="方言">
              {{ health.components.database.dialect ?? "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="说明">
              {{ health.components.database.message }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never">
          <template #header>数据调度</template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="状态">
              <el-tag
                :type="statusTagType(health.components.scheduler.status)"
                size="small"
              >
                {{ statusText(health.components.scheduler.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="是否开启">
              {{ health.components.scheduler.enabled ? "已开启" : "未开启" }}
            </el-descriptions-item>
            <el-descriptions-item label="最近成功运行">
              {{ health.components.scheduler.last_success_run ?? "无记录" }}
            </el-descriptions-item>
            <el-descriptions-item label="说明">
              {{ health.components.scheduler.message }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never">
          <template #header>AI 识别（LLM）</template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="状态">
              <el-tag
                :type="statusTagType(health.components.llm.status)"
                size="small"
              >
                {{ statusText(health.components.llm.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="是否已配置">
              {{ health.components.llm.configured ? "已配置" : "未配置" }}
            </el-descriptions-item>
            <el-descriptions-item label="提供商">
              {{ health.components.llm.provider ?? "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="模型">
              {{ health.components.llm.model ?? "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="端点">
              {{ health.components.llm.endpoint ?? "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="说明">
              {{ health.components.llm.message }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </template>
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
