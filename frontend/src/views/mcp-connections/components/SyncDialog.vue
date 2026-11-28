<!--
  数据同步向导（#3304）：选账户类型 → 选账户 → 拉取 → 置信度判定 → 用户决定。

  交互按「导入」惯例两级级联，全部单选：先选账户类型（组），再选该组下的账户，
  然后拉取。工具名（queryStockPosition 等）由后端按组推导，前端不出现——
  那是实现细节，暴露给用户只会制造「同步内容」和「账户类型」两套概念的混乱。

  铁律不变：不信任用户的单次选择。上游返回先过置信度判定（后端），低置信时
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
      <div v-loading="loading" class="sync-steps">
        <section class="sync-section">
          <h4 class="sync-section__title">1. 选择账户类型</h4>
          <el-radio-group v-model="selectedGroup" class="sync-types">
            <el-radio
              v-for="group in groups"
              :key="group.group"
              :value="group.group"
              :disabled="!group.accounts.length"
              class="sync-type"
            >
              <span class="sync-type__name">{{ group.label }}</span>
              <span class="sync-type__count">
                {{
                  group.accounts.length
                    ? `${group.accounts.length} 个账户`
                    : "（无账户）"
                }}
              </span>
            </el-radio>
          </el-radio-group>
        </section>

        <section class="sync-section" :class="{ 'is-idle': !selectedGroup }">
          <h4 class="sync-section__title">2. 选择账户</h4>
          <p v-if="!selectedGroup" class="sync-section__hint">
            先在上面选择账户类型
          </p>
          <el-radio-group
            v-else
            v-model="selectedAccount"
            class="sync-accounts"
          >
            <el-radio
              v-for="account in selectedGroupData?.accounts ?? []"
              :key="account.id"
              :value="account.id"
              class="sync-account"
            >
              <span class="sync-account__name">
                {{ account.name || account.id }}
              </span>
              <span v-if="account.lastSyncTime" class="sync-account__synced">
                上游同步于 {{ account.lastSyncTime }}
              </span>
            </el-radio>
          </el-radio-group>
        </section>
      </div>

      <div class="sync-footer">
        <el-button @click="close">取消</el-button>
        <el-button
          type="primary"
          :disabled="!selectedAccount"
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
  type McpSyncResult
} from "@/api/mcp";

defineOptions({ name: "McpSyncDialog" });

const props = defineProps<{
  visible: boolean;
  provider: string;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  /** 用户确认导入（含强制）：父层可据此刷新提示 */
  imported: [provider: string];
}>();

const step = ref<"select" | "result">("select");
const loading = ref(false);
const syncing = ref(false);
const groups = ref<McpAccountGroup[]>([]);
const selectedGroup = ref<string>("");
const selectedAccount = ref<string>("");
const result = ref<McpSyncResult | null>(null);

/** 所选类型的组数据（含该组账户列表） */
const selectedGroupData = computed(() =>
  groups.value.find(group => group.group === selectedGroup.value)
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
    selectedGroup.value = "";
    selectedAccount.value = "";
    void loadAccounts();
  }
);

/** 换账户类型后清空已选账户：跨类型的选中项会被后端拒绝 */
watch(selectedGroup, () => {
  selectedAccount.value = "";
});

async function loadAccounts(): Promise<void> {
  loading.value = true;
  try {
    const response = await fetchMcpAccounts(props.provider);
    groups.value = response.data?.groups ?? [];
    // 只有一个类型有账户时（最常见：单券商单账户）直接预选，少一次点击
    const usable = groups.value.filter(group => group.accounts.length);
    if (usable.length === 1) selectedGroup.value = usable[0].group;
  } catch (error) {
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

async function startSync(force: boolean): Promise<void> {
  if (!selectedGroup.value || !selectedAccount.value) return;
  syncing.value = true;
  try {
    const response = await syncMcpData(props.provider, {
      accounts: [{ group: selectedGroup.value, id: selectedAccount.value }],
      force
    });
    result.value = response.data ?? null;
    step.value = "result";
    if (response.data?.imported) emit("imported", props.provider);
  } catch (error) {
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
.sync-steps {
  min-height: 160px;
}

.sync-section {
  margin-bottom: var(--space-4);
}

/* 未选类型时第二段整体压暗，视觉上表达「先做第一步」的顺序 */
.sync-section.is-idle {
  opacity: 0.55;
}

.sync-section__title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-secondary);
}

.sync-section__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.sync-types,
.sync-accounts {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  align-items: stretch;
}

.sync-type,
.sync-account {
  height: auto;
  margin-right: 0;
}

.sync-type__count {
  margin-left: var(--space-2);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.sync-account__synced {
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
