<!--
  单个 MCP 服务的连接卡片（展示件）：状态与操作全部由父层持有，本组件只发事件。

  两条连接方式的差异只在这里出现一次：OAuth 点「连接」直接发事件由父层跳浏览器；
  API Key 先展开输入框、保存后清空（不回显、不落 localStorage），再交给父层入库。
  展开输入框期间隐藏「连接」主按钮 —— 保存 / 取消就是这一步的全部动作，
  两个主按钮同屏会让「下一步是哪个」无法判断（实测截图反馈）。
-->
<template>
  <article class="mcp-card" :data-provider="service.provider">
    <div class="mcp-card__head">
      <div class="mcp-card__titles">
        <h3 class="mcp-card__name">{{ service.name }}</h3>
        <span class="mcp-card__auth">{{ service.authLabel }}</span>
      </div>
      <span
        class="mcp-card__badge"
        :class="`mcp-card__badge--${state.tone}`"
        :data-state="state.tone"
      >
        {{ state.label }}
      </span>
    </div>

    <p class="mcp-card__desc">{{ service.description }}</p>
    <p v-if="expiry" class="mcp-card__hint">{{ expiry }}</p>
    <p
      v-if="connection?.last_error_kind"
      class="mcp-card__hint mcp-card__hint--warn"
    >
      上次连接异常，建议重新连接
    </p>

    <div
      v-if="showKeyInput && state.tone !== 'connected'"
      class="mcp-card__key"
    >
      <el-input
        v-model="apiKey"
        type="password"
        show-password
        clearable
        autocomplete="off"
        placeholder="粘贴 API Key"
        @keyup.enter="onSaveKey"
      />
      <div class="mcp-card__key-actions">
        <el-button type="primary" :loading="pending" @click="onSaveKey">
          保存
        </el-button>
        <el-button :disabled="pending" @click="onCancelKey">取消</el-button>
      </div>
    </div>

    <div
      v-if="state.tone === 'connected' || !showKeyInput"
      class="mcp-card__actions"
    >
      <template v-if="state.tone === 'connected'">
        <el-button
          :loading="verifyLoading"
          :disabled="pending"
          @click="emit('verify', service.provider)"
        >
          {{ verifyLabel }}
        </el-button>
        <el-button
          :loading="pending"
          @click="emit('disconnect', service.provider)"
        >
          断开连接
        </el-button>
      </template>
      <el-button v-else type="primary" :loading="pending" @click="onConnect">
        {{ state.tone === "problem" ? "重新连接" : "连接" }}
      </el-button>
    </div>

    <p
      v-if="verify"
      class="mcp-card__verify"
      :class="{ 'mcp-card__verify--fail': verify.status === 'fail' }"
    >
      {{ verify.text || "正在验证连接…" }}
    </p>

    <p class="mcp-card__tip">{{ service.connectHint }}</p>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { McpConnection } from "@/api/mcp";
import {
  connectionState,
  expiryHint,
  type McpService,
  verifyButtonLabel
} from "../mcpServices";
import type { McpVerifyState } from "../useMcpConnections";

defineOptions({ name: "McpServiceCard" });

const props = defineProps<{
  service: McpService;
  connection: McpConnection | null;
  pending: boolean;
  verify: McpVerifyState | null;
}>();

const emit = defineEmits<{
  "connect-oauth": [provider: string];
  "connect-static": [payload: { provider: string; apiKey: string }];
  disconnect: [provider: string];
  verify: [provider: string];
}>();

const apiKey = ref("");
const showKeyInput = ref(false);

const state = computed(() => connectionState(props.connection?.status));
const expiry = computed(() => expiryHint(props.connection?.expires_at));
const verifyLoading = computed(() => props.verify?.status === "loading");
const verifyLabel = computed(() => verifyButtonLabel(props.verify));

function onConnect(): void {
  if (props.service.authType === "oauth2") {
    emit("connect-oauth", props.service.provider);
    return;
  }
  showKeyInput.value = true;
}

function onSaveKey(): void {
  const key = apiKey.value.trim();
  if (!key) return;
  emit("connect-static", { provider: props.service.provider, apiKey: key });
  apiKey.value = "";
  showKeyInput.value = false;
}

function onCancelKey(): void {
  apiKey.value = "";
  showKeyInput.value = false;
}
</script>

<style scoped>
.mcp-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-standard);
  background-color: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  box-shadow: var(--shadow-raised);
}

.mcp-card__head {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  justify-content: space-between;
}

.mcp-card__titles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.mcp-card__name {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.mcp-card__auth {
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background-color: var(--bg-subtle);
  border-radius: 10px;
}

.mcp-card__badge {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: var(--text-label);
  border-radius: 10px;
}

.mcp-card__badge--connected {
  color: var(--el-color-success);
  background-color: color-mix(
    in srgb,
    var(--el-color-success) 10%,
    transparent
  );
  border: 1px solid var(--el-color-success);
}

.mcp-card__badge--problem {
  color: var(--el-color-warning);
  background-color: color-mix(
    in srgb,
    var(--el-color-warning) 10%,
    transparent
  );
  border: 1px solid var(--el-color-warning);
}

.mcp-card__badge--idle {
  color: var(--text-tertiary-ink);
  background-color: var(--bg-subtle);
  border: 1px solid var(--border-light);
}

.mcp-card__desc {
  margin: 0;
  font-size: var(--text-body);
  color: var(--text-secondary);
}

.mcp-card__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.mcp-card__hint--warn {
  color: var(--el-color-warning);
}

.mcp-card__key {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mcp-card__key-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.mcp-card__actions {
  display: flex;
  gap: var(--space-2);
}

.mcp-card__tip {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.mcp-card__verify {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-label);
  color: var(--text-secondary);
  background-color: var(--bg-subtle);
  border-radius: 10px;
  overflow-wrap: anywhere;
}

.mcp-card__verify--fail {
  color: var(--el-color-warning);
  background-color: color-mix(
    in srgb,
    var(--el-color-warning) 10%,
    transparent
  );
}
</style>
