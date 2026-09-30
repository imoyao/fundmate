<script setup lang="ts">
// 系统健康检查页（#1720）：向维护者展示后端 /api/health 的组件健康，
// 不对终端用户暴露运维故障措辞（普通探市页仅保留数据延迟提示）。
import { ref, onMounted } from "vue";
import { ElNotification } from "element-plus";
import { getHealth, type ComponentStatus, type HealthData } from "@/api/health";

const health = ref<HealthData | null>(null);
const loading = ref(false);

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
  try {
    const res = await getHealth();
    health.value = res.data;
  } catch (e) {
    ElNotification({
      title: "获取健康状态失败",
      message: (e as Error)?.message || "请检查后端服务是否运行",
      type: "error"
    });
  } finally {
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
  <div class="health-page p-4">
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="flex items-center justify-between">
          <span class="text-lg font-medium">系统健康检查</span>
          <el-button :loading="loading" size="small" @click="fetchHealth">
            刷新
          </el-button>
        </div>
      </template>
      <el-alert
        v-if="health"
        :title="`整体状态：${health.status === 'ok' ? '正常' : '需关注'}`"
        :type="health.status === 'ok' ? 'success' : 'warning'"
        :description="health.message"
        show-icon
        :closable="false"
      />
      <el-skeleton v-else :rows="4" animated />
    </el-card>

    <template v-if="health">
      <el-card shadow="never" class="mb-4">
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

      <el-card shadow="never" class="mb-4">
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

      <el-card shadow="never" class="mb-4">
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
  </div>
</template>
