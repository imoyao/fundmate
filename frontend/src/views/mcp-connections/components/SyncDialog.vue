<!--
  数据同步向导（#3304）：选账户 → 拉取 → 置信度判定 → 用户决定。

  铁律：不信任用户的单次选择。上游返回先过置信度判定（后端），低置信时
  本弹窗只展示差异摘要、默认不导入；「仍要导入」必须二次确认，审计在后端留痕。
  账户清单由后端 promptAccountSelection 下发（组名 / 中文标签 / 参数名都来自后端），
  前端不维护一份账户类型映射，避免两处真相漂移。
-->
<template>
  <el-dialog
    :model-value="visible"
    title="同步数据"
    width="600px"
    @update:model-value="onVisibleChange"
  >
    <template v-if="step === 'select'">
      <p class="sync-hint">
        同步前先选择要使用的账户。所选账户类型必须与同步内容匹配，选错会被校验拦下。
      </p>

      <div class="sync-tool">
        <span class="sync-tool__label">同步内容</span>
        <el-radio-group v-model="tool" @change="onToolChange">
          <el-radio-button value="queryStockPosition">证券持仓</el-radio-button>
          <el-radio-button value="queryFundAccount">基金账户</el-radio-button>
        </el-radio-group>
      </div>

      <div v-loading="loading" class="sync-groups">
        <div
          v-for="group in allowedGroups"
          :key="group.group"
          class="sync-group"
        >
          <h4 class="sync-group__title">{{ group.label }}</h4>
          <p v-if="!group.accounts.length" class="sync-group__empty">
            无此类型账户
          </p>
          <el-checkbox-group v-else v-model="selected" class="sync-group__list">
            <el-checkbox
              v-for="account in group.accounts"
              :key="account.id"
              :value="`${group.group}:${account.id}`"
            >
              <span class="sync-group__name">
                {{ account.name || account.id }}
              </span>
              <span v-if="account.lastSyncTime" class="sync-group__synced">
                上游同步于 {{ account.lastSyncTime }}
              </span>
            </el-checkbox>
          </el-checkbox-group>
        </div>
      </div>

      <div class="sync-footer">
        <el-button @click="close">取消</el-button>
        <el-button
          type="primary"
          :disabled="!selected.length"
          :loading="syncing"
          @click="startSync(false)"
        >
          拉取数据
        </el-button>
      </div>
    </template>

    <template v-else-if="result">
      <el-alert
        v-if="result.confidence === 'high'"
        type="success"
        :title="healthyText"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else
        type="warning"
        title="检测到数据与所选账户可能不匹配，默认不导入"
        :closable="false"
        show-icon
      />

      <ul v-if="result.reasons.length" class="sync-reasons">
        <li v-for="reason in result.reasons" :key="reason">{{ reason }}</li>
      </ul>

      <div v-if="result.items.length" class="sync-preview">
        <div class="sync-preview__head">
          <span>数据预览（前 {{ result.items.length }} 笔）</span>
          <span v-if="totalAssetText">{{ totalAssetText }}</span>
        </div>
        <ul class="sync-preview__list">
          <li
            v-for="(item, index) in result.items"
            :key="`${item.code ?? 'unknown'}-${index}`"
          >
            <span class="sync-preview__name">
              {{ item.name || item.code || "（未识别条目）" }}
            </span>
            <span v-if="item.marketValue" class="sync-preview__value">
              ¥{{ item.marketValue }}
            </span>
          </li>
        </ul>
      </div>

      <div class="sync-footer">
        <el-button @click="backToSelect">换账户重试</el-button>
        <el-button
          v-if="result.confidence === 'low' && !result.imported"
          type="warning"
          :loading="syncing"
          @click="forceImport"
        >
          仍要导入
        </el-button>
        <el-button v-if="result.imported" type="primary" @click="close">
          完成
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  fetchMcpAccounts,
  syncMcpData,
  type McpAccountGroup,
  type McpSyncAccount,
  type McpSyncResult
} from "@/api/mcp";
import { isMcpAuthError } from "../mcpServices";

defineOptions({ name: "McpSyncDialog" });

const props = defineProps<{
  visible: boolean;
  provider: string;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  /** 用户确认导入（含强制）：父层可据此刷新提示 */
  imported: [provider: string];
  /** McpAuthError：父层把该卡片翻到「重新授权」态（#3303） */
  "auth-error": [provider: string];
}>();

const ALLOWED_GROUPS: Record<string, string[]> = {
  queryStockPosition: ["fund_key", "rzrq_fund_key", "manual_id"],
  queryFundAccount: ["fund_id", "cust_id"]
};

const step = ref<"select" | "result">("select");
const loading = ref(false);
const syncing = ref(false);
const tool = ref("queryStockPosition");
const groups = ref<McpAccountGroup[]>([]);
const selected = ref<string[]>([]);
const result = ref<McpSyncResult | null>(null);

const allowedGroups = computed(() =>
  groups.value.filter(group =>
    (ALLOWED_GROUPS[tool.value] ?? []).includes(group.group)
  )
);

const totalAssetText = computed(() => {
  const value = result.value?.summary?.totalAsset;
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return `总资产 ¥${value.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`;
});

const healthyText = computed(() => {
  const summary = result.value?.summary;
  if (!summary) return "校验通过";
  return `校验通过：${summary.count} 笔数据，与本地持仓重合 ${summary.overlap} 笔`;
});

/** 每次打开都重新拉账户清单：上游账户可能刚同步过，缓存不新鲜 */
watch(
  () => props.visible,
  visible => {
    if (!visible) return;
    step.value = "select";
    result.value = null;
    selected.value = [];
    void loadAccounts();
  }
);

async function loadAccounts(): Promise<void> {
  loading.value = true;
  try {
    const response = await fetchMcpAccounts(props.provider);
    groups.value = response.data?.groups ?? [];
  } catch (error) {
    if (isMcpAuthError(error)) emit("auth-error", props.provider);
    ElMessage.error(errorMessage(error, "账户清单获取失败，请稍后重试"));
    close();
  } finally {
    loading.value = false;
  }
}

function onVisibleChange(value: boolean): void {
  if (!value) close();
}

function close(): void {
  emit("update:visible", false);
}

/** 换同步内容后清空已选：跨类型的选中项会被后端 422 拒绝，前端先拦住 */
function onToolChange(): void {
  selected.value = [];
}

function selectedAccounts(): McpSyncAccount[] {
  return selected.value.map(entry => {
    const [group, ...rest] = entry.split(":");
    return { group, id: rest.join(":") };
  });
}

async function startSync(force: boolean): Promise<void> {
  syncing.value = true;
  try {
    const response = await syncMcpData(props.provider, {
      tool: tool.value,
      accounts: selectedAccounts(),
      force
    });
    result.value = response.data ?? null;
    step.value = "result";
    if (response.data?.imported) emit("imported", props.provider);
  } catch (error) {
    if (isMcpAuthError(error)) emit("auth-error", props.provider);
    ElMessage.error(errorMessage(error, "同步失败，请稍后重试"));
  } finally {
    syncing.value = false;
  }
}

/** 仍要导入：二次确认后带 force 重发（后端审计记强制标志） */
async function forceImport(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "校验未通过的数据可能与所选账户不匹配，导入后会留在同步记录里供追溯。确定仍要导入吗？",
      "强制导入确认",
      {
        type: "warning",
        confirmButtonText: "仍要导入",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return; // 用户取消
  }
  await startSync(true);
}

function backToSelect(): void {
  step.value = "select";
  result.value = null;
}

function errorMessage(error: unknown, fallback: string): string {
  const backend = (
    error as { response?: { data?: { message?: string } } } | undefined
  )?.response?.data?.message;
  return backend || fallback;
}
</script>

<style scoped>
.sync-hint {
  margin: 0 0 var(--space-3);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.sync-tool {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-3);
}

.sync-tool__label {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.sync-groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-height: 80px;
}

.sync-group__title {
  margin: 0 0 var(--space-1);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-secondary);
}

.sync-group__empty {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.sync-group__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.sync-group__name {
  color: var(--text-primary);
}

.sync-group__synced {
  margin-left: var(--space-2);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.sync-reasons {
  padding-left: var(--space-5);
  margin: var(--space-3) 0 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.sync-preview {
  margin-top: var(--space-3);
  overflow: hidden;
  background-color: var(--bg-subtle);
  border-radius: 10px;
}

.sync-preview__head {
  display: flex;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.sync-preview__list {
  max-height: 220px;
  padding: 0 var(--space-3) var(--space-2);
  margin: 0;
  overflow-y: auto;
  list-style: none;
}

.sync-preview__list li {
  display: flex;
  justify-content: space-between;
  padding: var(--space-1) 0;
  font-size: var(--text-label);
  color: var(--text-primary);
}

.sync-preview__value {
  color: var(--text-secondary);
}

.sync-footer {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  margin-top: var(--space-4);
}
</style>
