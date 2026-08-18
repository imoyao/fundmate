<template>
  <div class="eaccount-import-page">
    <!-- 页头 -->
    <header class="import-head">
      <div class="import-head__text">
        <h1 class="import-head__title">导入 E账户快照</h1>
        <p class="import-head__subtitle">
          上传 E账户（中国结算）导出的持仓文件，解析后自动与各销售渠道对账归因
        </p>
      </div>
      <el-button
        v-if="currentStep === 1"
        text
        :style="{ color: 'var(--text-secondary)' }"
        @click="goToReconcileCenter"
      >
        <IconifyIconOffline icon="ep:files" class="mr-1" />
        前往对账中心
      </el-button>
    </header>

    <!-- 两步流程指示（与交易导入向导同语言） -->
    <el-steps
      :active="currentStep"
      finish-status="success"
      align-center
      class="import-steps"
    >
      <el-step
        v-for="(step, index) in STEPS"
        :key="index"
        :title="step.title"
      />
    </el-steps>

    <!-- ── 步骤一：上传与预览 ── -->
    <template v-if="currentStep === 0">
      <!-- 大上传卡片：解析成功后折叠让位（el-upload 保留在 DOM，http-request 与 accept 校验不变） -->
      <div
        class="upload-collapse"
        :class="{ 'is-folded': parsedOk }"
        :inert="parsedOk"
      >
        <div class="upload-collapse__inner">
          <div class="upload-card">
            <el-upload
              accept=".csv,.xls,.xlsx"
              :before-upload="beforeUpload"
              :http-request="handleUpload"
              :show-file-list="false"
              drag
              :disabled="parsing"
              class="eaccount-upload"
            >
              <template #default>
                <IconifyIconOffline
                  icon="lucide:cloud-upload"
                  class="upload-icon"
                />
                <p class="upload-text">将文件拖到此处，或</p>
                <el-button plain class="upload-btn" :loading="parsing">
                  {{ parsing ? "正在解析..." : "点击上传" }}
                </el-button>
                <p class="upload-hint">E账户导出文件（基金持仓快照）</p>
                <p class="upload-format-info">
                  支持 Excel、CSV 格式 ｜ 最大 5MB
                </p>
              </template>
            </el-upload>

            <div v-if="uploadError" class="upload-error">
              <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
              {{ uploadError }}
              <div class="upload-error-detail">
                请检查：1. 是否为 E账户（中国结算）导出的原始文件；2.
                文件是否完整， 没有被修改过；3. 文件编码是否为 UTF-8
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 解析完成状态条：折叠后的一行反馈 + 重新上传 -->
      <transition name="done-bar">
        <div v-if="parsedOk" class="parse-done-bar">
          <IconifyIconOffline
            icon="ep:success-filled"
            class="parse-done-bar__icon"
          />
          <span class="parse-done-bar__file" :title="fileName">
            {{ fileName }}
          </span>
          <span class="parse-done-bar__summary">
            已解析
            <b class="parse-done-bar__count">{{ parseMeta.total }}</b>
            条记录<template v-if="errorCount > 0"
              >，其中 {{ errorCount }} 条解析失败</template
            >
          </span>
          <el-button text class="parse-done-bar__reset" @click="resetUpload">
            <IconifyIconOffline icon="ep:refresh-left" class="mr-1" />
            重新上传
          </el-button>
        </div>
      </transition>

      <!-- 解析预览：只读展示，error 行标红禁提交 -->
      <div v-if="previewRows.length > 0" class="preview-card">
        <SectionHeader
          title="解析预览"
          :info="
            '共识别 ' +
            parseMeta.total +
            ' 条记录' +
            (errorCount > 0 ? '，其中 ' + errorCount + ' 条解析失败' : '')
          "
        >
          <template #action>
            <el-button
              type="primary"
              :disabled="errorCount > 0 || previewRows.length === 0"
              :loading="reconciling"
              @click="handleReconcile"
            >
              <IconifyIconOffline icon="ep:connection" class="mr-1" />
              开始对账
            </el-button>
          </template>
        </SectionHeader>

        <div v-if="errorCount > 0" class="parse-warning">
          <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
          存在 {{ errorCount }} 条解析失败记录（红底行），请更换文件后重试，
          有误数据不会参与对账
        </div>

        <!-- 表格视觉基线走 src/style/el-table.css（row-blocked 为基线内置类） -->
        <el-table
          :data="pagedPreviewRows"
          stripe
          :row-class-name="getRowClassName"
          max-height="480"
        >
          <el-table-column label="基金" min-width="180">
            <template #default="{ row }">
              <div class="fund-cell">
                <span class="fund-cell__name">{{ row.name || "--" }}</span>
                <span class="fund-cell__symbol">{{ row.symbol || "--" }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="份额" width="110" align="right">
            <template #default="{ row }">
              <span class="num-cell">{{
                toNumber(row.quantity) != null
                  ? formatQuantity(toNumber(row.quantity))
                  : "--"
              }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" width="100" align="right">
            <template #default="{ row }">
              <span class="num-cell">{{
                toNumber(row.price) != null
                  ? Number(row.price).toFixed(4)
                  : "--"
              }}</span>
            </template>
          </el-table-column>
          <el-table-column label="快照日期" width="110" align="right">
            <template #default="{ row }">
              <span class="num-cell">{{ formatDate(row.snapshot_date) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="销售机构" min-width="170">
            <template #default="{ row }">
              <span class="ellipsis-text" :title="row.source_broker || ''">
                {{ row.source_broker || "--" }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="基金管理人" min-width="170">
            <template #default="{ row }">
              <span class="ellipsis-text" :title="row.fund_manager || ''">
                {{ row.fund_manager || "--" }}
              </span>
            </template>
          </el-table-column>
          <template #empty>
            <div class="preview-empty">暂无预览数据</div>
          </template>
        </el-table>

        <!-- 客户端分页：在全量解析行上切片，统计口径保持全量 -->
        <el-pagination
          v-model:current-page="previewPage"
          v-model:page-size="previewPageSize"
          :total="previewRows.length"
          :page-sizes="[50, 100, 200]"
          layout="total, prev, pager, next, sizes"
          class="table-pagination"
        />

        <div class="preview-footer">
          <span class="preview-footer__count">
            共 {{ parseMeta.total }} 条，可对账
            {{ previewRows.length - errorCount }} 条
          </span>
        </div>
      </div>
    </template>

    <!-- ── 步骤二：对账结果 ── -->
    <template v-else-if="result">
      <MetricGrid class="result-grid">
        <MetricCard
          title="自动归因"
          :value="result.auto_attributed"
          featured
          caption="已归因至对应销售渠道"
        />
        <MetricCard
          title="已核对"
          :value="result.verified"
          caption="与系统份额一致"
        />
        <MetricCard
          title="冲突"
          :value="result.conflicts"
          caption="需人工决策，前往对账中心处理"
        />
        <MetricCard
          title="跳过"
          :value="result.ignored_skipped + result.attributed_skipped"
          :caption="`已忽略 ${result.ignored_skipped} 条 · 防复活跳过 ${result.attributed_skipped} 条`"
        />
        <MetricCard
          title="失败"
          :value="result.failed_rows.length"
          caption="解析或落库失败，见下方明细"
        />
      </MetricGrid>

      <!-- 有冲突：品牌色提示 banner（提示性信息，非危险操作）+ 跳转对账中心 -->
      <div v-if="result.conflicts > 0" class="conflict-banner" role="alert">
        <div class="conflict-banner__text">
          <IconifyIconOffline
            icon="ep:warning-filled"
            class="conflict-banner__icon"
          />
          <span>
            存在 {{ result.conflicts }} 条冲突：渠道已有持仓但份额与
            E账户不一致， 需要逐条决策「归因覆盖」或「忽略」
          </span>
        </div>
        <el-button type="primary" @click="goToReconcileCenter">
          前往对账中心处理
          <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
        </el-button>
      </div>

      <!-- 无冲突：完成态 -->
      <div v-else-if="result.failed_rows.length === 0" class="done-card">
        <IconifyIconOffline icon="ep:success-filled" class="done-card__icon" />
        <p class="done-card__title">对账完成</p>
        <p class="done-card__desc">
          E账户快照已自动归因至对应销售渠道，无需人工处理
        </p>
      </div>

      <!-- 冲突明细：简要清单（symbol + 渠道 + 份额差异） -->
      <div v-if="conflictList.length > 0" class="detail-card">
        <SectionHeader
          title="冲突明细"
          :info="'共 ' + conflictList.length + ' 条，可在对账中心逐条决策'"
        />
        <ul class="conflict-list">
          <li
            v-for="item in conflictList"
            :key="item.record_id"
            class="conflict-list__item"
          >
            <span class="conflict-list__name">{{
              item.name || item.symbol
            }}</span>
            <span class="conflict-list__symbol">{{ item.symbol }}</span>
            <span class="conflict-list__detail">
              渠道「{{ item.target_ledger_name || "对应渠道" }}」{{
                formatQuantity(item.current_quantity)
              }}
              份 vs E账户 {{ formatQuantity(item.eaccount_quantity) }} 份
              <span class="conflict-list__diff"
                >差 {{ formatQuantity(item.diff_quantity) }} 份</span
              >
            </span>
          </li>
        </ul>
      </div>

      <!-- 失败行：原因列表 -->
      <div v-if="failedList.length > 0" class="detail-card">
        <SectionHeader
          title="失败明细"
          :info="'共 ' + failedList.length + ' 条，多为缺净值或成本数据'"
        />
        <ul class="failed-list">
          <li
            v-for="(item, index) in failedList"
            :key="index"
            class="failed-list__item"
          >
            <span class="failed-list__line">第 {{ item.line }} 行</span>
            <span class="failed-list__symbol">{{ item.symbol || "--" }}</span>
            <span class="failed-list__reason">{{ item.reason }}</span>
          </li>
        </ul>
      </div>

      <!-- 底部操作 -->
      <div class="result-actions">
        <el-button @click="resetFlow">
          <IconifyIconOffline icon="ep:refresh-left" class="mr-1" />
          重新导入
        </el-button>
        <el-button type="primary" @click="goToReconcileCenter">
          前往对账中心
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { UploadRequestOptions } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  parseHoldings,
  reconcileEaccount,
  type HoldingParseRow,
  type ReconcileResult,
  type ConflictItem
} from "@/api/eaccount";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { formatDate } from "@/utils/date";
import { formatQuantity } from "@/utils/format";

defineOptions({ name: "InvestmentEaccountImport" });

/** 兼容「信封 {data}」与「直接返回」两种响应形态（并行 lane 契约以直接返回为准） */
function unwrap<T>(res: unknown): T {
  const r = res as { data?: T } | null;
  if (r && typeof r === "object" && "data" in r && r.data != null)
    return r.data;
  return res as T;
}

function errMsg(e: unknown, fallback: string): string {
  const err = e as {
    response?: { data?: { message?: string } };
    message?: string;
  };
  return err?.response?.data?.message || err?.message || fallback;
}

const router = useRouter();

const STEPS = [{ title: "上传与预览" }, { title: "对账结果" }];

const currentStep = ref(0);
const parsing = ref(false);
const reconciling = ref(false);
const uploadError = ref("");
const previewRows = ref<HoldingParseRow[]>([]);
const parseMeta = ref({ total: 0, error_count: 0 });
const result = ref<ReconcileResult | null>(null);
const fileName = ref("");
/** 预览表格客户端分页：当前页码 + 每页条数（默认 50） */
const previewPage = ref(1);
const previewPageSize = ref(50);

const errorCount = computed(
  () => previewRows.value.filter(row => !!row.error).length
);

/** 解析成功（有行数据且无错误）→ 上传卡片折叠为一行状态条 */
const parsedOk = computed(
  () => previewRows.value.length > 0 && !uploadError.value
);

/** 预览表格分页切片：在全量解析行上切片（errorCount / 状态条 / SectionHeader 统计均保持全量口径） */
const pagedPreviewRows = computed(() => {
  const start = (previewPage.value - 1) * previewPageSize.value;
  return previewRows.value.slice(start, start + previewPageSize.value);
});

const conflictList = computed(() => result.value?.conflict_list ?? []);
const failedList = computed(() => result.value?.failed_rows ?? []);

/** 解析行数值可能为字符串（CSV），统一转 number，无效返回 null */
function toNumber(value: number | string | undefined): number | null {
  if (value === undefined || value === null || value === "") return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function beforeUpload(file: File): boolean {
  const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
  if (![".csv", ".xls", ".xlsx"].includes(ext)) {
    ElMessage.error("仅支持 CSV、Excel 文件");
    return false;
  }
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error("文件大小不能超过 5MB");
    return false;
  }
  return true;
}

/** 上传入口：el-upload 的 http-request 模式（与交易导入 UploadArea 同构） */
async function handleUpload(options: UploadRequestOptions) {
  const file = options.file as File;
  parsing.value = true;
  uploadError.value = "";
  try {
    const res = await parseHoldings(file);
    // 后端 /holdings/parse 返回信封：data 即行数组，total/error_count 在顶层
    const rows = Array.isArray(res.data) ? res.data : [];
    previewRows.value = rows;
    parseMeta.value = {
      total: res.total ?? rows.length,
      error_count: res.error_count ?? 0
    };
    fileName.value = file.name;
    options.onSuccess(res);
  } catch (e) {
    uploadError.value = errMsg(e, "文件解析失败");
    options.onError(e);
  } finally {
    parsing.value = false;
  }
}

/** 有 error 的行标红（row-blocked 为 el-table.css 基线内置类） */
function getRowClassName({ row }: { row: HoldingParseRow }): string {
  return row.error ? "row-blocked" : "";
}

/** 开始对账：error 行禁提交（有失败行直接阻止整个提交） */
async function handleReconcile() {
  if (errorCount.value > 0) {
    ElMessage.warning(
      `存在 ${errorCount.value} 条解析失败记录，请更换文件后重试`
    );
    return;
  }
  if (previewRows.value.length === 0) {
    ElMessage.warning("没有可对账的记录，请先上传文件");
    return;
  }
  reconciling.value = true;
  try {
    const res = await reconcileEaccount(previewRows.value);
    result.value = unwrap<ReconcileResult>(res);
    currentStep.value = 1;
  } catch (e) {
    ElMessage.error(errMsg(e, "对账失败"));
  } finally {
    reconciling.value = false;
  }
}

function goToReconcileCenter() {
  router.push({ name: "InvestmentReconcile" });
}

function resetFlow() {
  currentStep.value = 0;
  previewRows.value = [];
  parseMeta.value = { total: 0, error_count: 0 };
  result.value = null;
  uploadError.value = "";
  fileName.value = "";
  previewPage.value = 1;
}

/** 重新上传：清空解析结果，恢复大上传卡片 */
function resetUpload() {
  uploadError.value = "";
  previewRows.value = [];
  parseMeta.value = { total: 0, error_count: 0 };
  fileName.value = "";
  previewPage.value = 1;
}
</script>

<style scoped>
/* 页面根容器：字体继承全局 token + 全页数字等宽（design.md「数字等宽对齐落地规范」） */
.eaccount-import-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* ===== 页头 ===== */
.import-head {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-standard);
}

.import-head__title {
  margin: 0;
  font-size: var(--text-display);
  font-weight: 300;
  line-height: 1.3;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.import-head__subtitle {
  margin: 6px 0 0;
  font-size: var(--text-small);
  line-height: 1.5;
  color: var(--text-secondary);
}

.import-steps {
  margin-bottom: var(--space-loose);
}

/* ===== 上传区（复用交易导入 UploadArea 的 golden-upload 语言） ===== */
.upload-card {
  padding: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.eaccount-upload :deep(.el-upload-dragger) {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 280px;
  padding: 40px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transition:
    border-color 0.25s ease,
    background-color 0.25s ease;
}

.eaccount-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--brand-400);
}

.eaccount-upload :deep(.el-upload-dragger.is-dragover) {
  background: var(--brand-100);
  border-color: var(--brand-400);
}

.upload-icon {
  margin-bottom: 16px;
  font-size: 56px;
  color: var(--brand-700);
}

.upload-text {
  margin: 0 0 16px;
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text-primary);
}

.upload-btn {
  height: 40px;
  padding: 0 24px;
  font-size: var(--text-small);
  color: var(--brand-700);
  background: transparent;
  border: 1px solid var(--brand-400);
  border-radius: var(--radius-sm);
  transition:
    background-color 150ms ease,
    border-color 150ms ease;
}

.upload-btn:hover:not(:disabled) {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-600);
}

.upload-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.upload-format-info {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.upload-error {
  padding: 12px 16px;
  margin-top: var(--space-compact);
  font-size: var(--text-small);
  color: var(--color-danger-system);
  text-align: center;
  background: var(--color-danger-20);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
}

.upload-error-detail {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  text-align: left;
}

/* ===== 上传卡片折叠（解析成功后让位给预览表格） ===== */

/* 外层 grid 行高 1fr→0fr 平滑收缩 + 淡出；el-upload 始终留在 DOM，仅视觉折叠 */
.upload-collapse {
  display: grid;
  grid-template-rows: 1fr;
  transition:
    grid-template-rows 0.35s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.3s ease;
}

.upload-collapse.is-folded {
  grid-template-rows: 0fr;
  opacity: 0;
}

.upload-collapse__inner {
  min-height: 0;
  overflow: hidden;
}

/* ===== 解析完成状态条 ===== */
.parse-done-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  align-items: center;
  padding: var(--space-3) var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.parse-done-bar__icon {
  flex-shrink: 0;
  font-size: 18px;
  color: var(--color-success);
}

.parse-done-bar__file {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.parse-done-bar__summary {
  font-size: var(--text-small);
  color: var(--text-secondary);
  white-space: nowrap;
}

.parse-done-bar__count {
  font-weight: 600;
  color: var(--color-success);
}

.parse-done-bar__reset {
  flex-shrink: 0;
  margin-left: auto;
  color: var(--text-secondary);
}

/* 状态条出现：淡入 + 轻微下落（与折叠收缩同步） */
.done-bar-enter-active {
  transition:
    opacity 0.3s ease,
    transform 0.3s ease;
}

.done-bar-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}

.done-bar-leave-active {
  transition: opacity 0.2s ease;
}

.done-bar-leave-to {
  opacity: 0;
}

/* ===== 预览区 ===== */
.preview-card {
  padding: var(--space-standard);
  margin-top: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

/* 有解析失败行时提示（提示性信息用品牌色，危险色只留给破坏性操作） */
.parse-warning {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-3) var(--space-compact);
  margin-bottom: var(--space-compact);
  font-size: var(--text-small);
  color: var(--brand-700);
  background: var(--brand-100);
  border-radius: var(--radius-md);
}

.fund-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.fund-cell__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.fund-cell__symbol {
  font-size: 12px;
  color: var(--text-tertiary);
}

.ellipsis-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.num-cell {
  font-family: var(--font-mono);
  font-size: var(--text-small);
  color: var(--text-primary);
}

.preview-empty {
  padding: 24px 0;
  color: var(--text-tertiary);
  text-align: center;
}

/* 分页条：表格底部右对齐，Element Plus 默认视觉 */
.table-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-compact);
}

.preview-footer {
  padding-top: var(--space-compact);
  margin-top: var(--space-compact);
  border-top: 1px solid var(--border-subtle);
}

.preview-footer__count {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* ===== 结果区 ===== */
.result-grid {
  margin-bottom: var(--space-standard);
}

/* 冲突提示 banner：品牌色态（design.md「提示性 Banner 品牌色规范」） */
.conflict-banner {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-compact);
  margin-bottom: var(--space-standard);
  background: var(--brand-100);
  border-radius: var(--radius-lg);
}

.conflict-banner__text {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  min-width: 0;
  font-size: var(--text-small);
  color: var(--brand-700);
}

.conflict-banner__icon {
  flex-shrink: 0;
}

/* 无冲突完成态 */
.done-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-loose) 0;
  margin-bottom: var(--space-standard);
  text-align: center;
}

.done-card__icon {
  font-size: 40px;
  color: var(--color-success);
}

.done-card__title {
  margin: 0;
  font-size: var(--text-heading);
  font-weight: 600;
  color: var(--text-primary);
}

.done-card__desc {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

/* 明细卡片：冲突 + 失败 */
.detail-card {
  padding: var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.conflict-list,
.failed-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.conflict-list__item {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-2) 0;
  font-size: var(--text-small);
  border-bottom: 1px solid var(--border-subtle);
}

.conflict-list__item:last-child {
  border-bottom: none;
}

.conflict-list__name {
  font-weight: 500;
  color: var(--text-primary);
}

.conflict-list__symbol {
  font-size: 12px;
  color: var(--text-tertiary);
}

.conflict-list__detail {
  flex: 1;
  color: var(--text-secondary);
  text-align: right;
}

.conflict-list__diff {
  font-weight: 500;
  color: var(--color-rise);
}

/* 失败行：中性弱化，不喧宾夺主 */
.failed-list__item {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-2) 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.failed-list__item:last-child {
  border-bottom: none;
}

.failed-list__line {
  font-size: 12px;
  color: var(--text-tertiary);
}

.failed-list__symbol {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.result-actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}
</style>
