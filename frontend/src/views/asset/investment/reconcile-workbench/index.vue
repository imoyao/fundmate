<template>
  <div class="recon-workbench-page">
    <!-- 页头 -->
    <header class="workbench-head">
      <div class="workbench-head__text">
        <h1 class="workbench-head__title">对账工作台</h1>
        <p class="workbench-head__subtitle">
          统一处理 E账户对账、持仓快照一致性、对账单导入的差异与补充
        </p>
      </div>
      <div class="workbench-head__actions">
        <el-button size="small" @click="recognizerVisible = true">
          <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
          AI 识别
        </el-button>
        <el-button
          size="small"
          type="primary"
          :loading="running"
          @click="handleRun"
        >
          <IconifyIconOffline icon="ep:refresh-right" class="mr-1" />
          运行对账
        </el-button>
      </div>
    </header>

    <!-- 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗；点击切换到待处理域（#1259） -->
    <div
      v-if="hasPending"
      class="workbench-banner workbench-banner--clickable"
      role="alert"
      @click="focusFirstPendingDomain"
    >
      <IconifyIconOffline icon="ep:warning" class="workbench-banner__icon" />
      <div class="workbench-banner__text">
        有 {{ totalPending }} 项差异待处理，点击切换到对应域处理
      </div>
    </div>

    <!-- 顶部状态栏（真实数据：P1 接入 discrepancies 统计） -->
    <div class="workbench-metrics">
      <MetricGrid :cols="3">
        <MetricCard
          title="数据日期"
          :value="dataDateLabel"
          caption="最近一次对账数据日期"
        />
        <MetricCard
          title="待裁决差异"
          :value="pendingCount"
          unit="项"
          level="待处理"
          :featured="true"
        />
        <MetricCard
          title="已忽略"
          :value="ignoredCount"
          unit="项"
          caption="可撤销（P2 接入）"
        />
      </MetricGrid>
    </div>

    <!-- 三域 Tab（§6.3）：B 已接入真实对账，A/C 保持原入口 -->
    <div class="workbench-tabs">
      <el-tabs v-model="activeDomain" class="workbench-tabs__inner">
        <el-tab-pane v-for="tab in domainTabs" :key="tab.key" :name="tab.key">
          <template #label>
            <span class="domain-tab-label">
              {{ tab.label }}
              <span
                v-if="domainPending(tab.key) > 0"
                class="domain-tab-count"
                >{{ domainPending(tab.key) }}</span
              >
            </span>
          </template>
          <CardBlock :title="tab.title" :description="tab.description">
            <template #action>
              <AssetTypeBadge :type="tab.badgeType" variant="tag" />
            </template>

            <!-- 域 B：真实差异列表（P1 接入） -->
            <template v-if="tab.key === 'B'">
              <div class="domain-b-body">
                <el-empty
                  v-if="!loading && bDiscs.length === 0"
                  description="暂无待处理差异"
                  :image-size="80"
                />
                <div v-else class="disc-table-wrap">
                  <el-table
                    :data="bDiscs"
                    stripe
                    size="small"
                    class="disc-table"
                  >
                    <el-table-column label="代码" prop="symbol" width="110" />
                    <el-table-column label="类型" width="90">
                      <template #default="{ row }">
                        <span class="disc-type">{{
                          typeLabel(row.discrepancy_type)
                        }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column
                      label="理论"
                      prop="expected_value"
                      width="100"
                      align="right"
                    />
                    <el-table-column
                      label="实际"
                      prop="actual_value"
                      width="100"
                      align="right"
                    />
                    <el-table-column label="差异" width="100" align="right">
                      <template #default="{ row }">
                        <span :class="diffClass(row.diff)">{{
                          formatDiff(row.diff)
                        }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="状态" width="90">
                      <template #default="{ row }">
                        <span
                          class="disc-status"
                          :class="`disc-status--${row.status}`"
                        >
                          {{ statusLabel(row.status) }}
                        </span>
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="200">
                      <template #default="{ row }">
                        <template v-if="row.status === 'pending'">
                          <!-- 就地补充（§6.4）：工作台内直接补录，绝不跳「记一笔」 -->
                          <el-button
                            size="small"
                            text
                            type="primary"
                            @click="openSupplement(row)"
                          >
                            补充
                          </el-button>
                          <el-button
                            size="small"
                            text
                            @click="handleIgnore(row as DiscrepancyItem)"
                          >
                            忽略
                          </el-button>
                        </template>
                        <span v-else class="disc-muted">已处理</span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </div>
            </template>

            <!-- 域 A：E账户对账（P2 迁入工作台，复用既有 /api/e-account/ 链路） -->
            <template v-else-if="tab.key === 'A'">
              <!-- 识别候选（holding → 域 A，#1252）：AI 识别结果落草稿，确认后入库并刷新域 A 对账 -->
              <div
                v-if="holdingCandidates.length"
                class="recognizer-candidate-panel"
              >
                <div class="recognizer-candidate-panel__head">
                  <span class="recognizer-candidate-panel__title">
                    AI 识别候选（持仓）· {{ holdingCandidates.length }} 条
                  </span>
                  <div class="recognizer-candidate-panel__actions">
                    <el-button size="small" text @click="discardCandidates"
                      >丢弃</el-button
                    >
                    <el-button
                      size="small"
                      type="primary"
                      :loading="committing"
                      @click="commitCandidates('holding')"
                      >确认入库</el-button
                    >
                  </div>
                </div>
                <el-table
                  :data="holdingCandidates"
                  size="small"
                  stripe
                  class="disc-table"
                >
                  <el-table-column label="代码" prop="symbol" width="110" />
                  <el-table-column label="名称" prop="name" min-width="120" />
                  <el-table-column
                    label="份额"
                    prop="quantity"
                    width="110"
                    align="right"
                  />
                  <el-table-column
                    label="成本"
                    prop="price"
                    width="100"
                    align="right"
                  />
                  <el-table-column
                    label="快照日"
                    prop="snapshot_date"
                    width="120"
                  />
                </el-table>
              </div>

              <div class="domain-a-body">
                <el-empty
                  v-if="!eLoading && eItems.length === 0"
                  description="暂无 E账户对账记录"
                  :image-size="80"
                />
                <div v-else class="disc-table-wrap">
                  <el-table
                    :data="eItems"
                    stripe
                    size="small"
                    class="disc-table"
                  >
                    <el-table-column label="代码" prop="symbol" width="110" />
                    <el-table-column label="名称" prop="name" min-width="120" />
                    <el-table-column label="渠道" width="120">
                      <template #default="{ row }">
                        {{ row.source_broker || "—" }}
                      </template>
                    </el-table-column>
                    <el-table-column
                      label="E账户份额"
                      width="110"
                      align="right"
                    >
                      <template #default="{ row }">
                        {{ row.eaccount_quantity ?? "—" }}
                      </template>
                    </el-table-column>
                    <el-table-column label="系统份额" width="110" align="right">
                      <template #default="{ row }">
                        {{ row.current_quantity ?? "—" }}
                      </template>
                    </el-table-column>
                    <el-table-column label="状态" width="100">
                      <template #default="{ row }">
                        <span class="disc-status">{{
                          eStatusLabel(row.status)
                        }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="160">
                      <template #default="{ row }">
                        <template v-if="row.status === 'pending'">
                          <el-button
                            size="small"
                            text
                            type="primary"
                            @click="handleEAccountCover(row)"
                          >
                            归因覆盖
                          </el-button>
                          <el-button
                            size="small"
                            text
                            @click="handleEAccountIgnore(row)"
                          >
                            忽略
                          </el-button>
                        </template>
                        <span v-else class="disc-muted">已处理</span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </div>
            </template>

            <!-- 域 C：占位内容 -->
            <template v-else>
              <!-- 识别候选（txn → 域 C，#1251）：AI 识别结果落草稿，确认后入库并触发域 C 对账 -->
              <div
                v-if="txnCandidates.length"
                class="recognizer-candidate-panel"
              >
                <div class="recognizer-candidate-panel__head">
                  <span class="recognizer-candidate-panel__title">
                    AI 识别候选（交易）· {{ txnCandidates.length }} 条
                  </span>
                  <div class="recognizer-candidate-panel__actions">
                    <el-button size="small" text @click="discardCandidates"
                      >丢弃</el-button
                    >
                    <el-button
                      size="small"
                      type="primary"
                      :loading="committing"
                      @click="commitCandidates('txn')"
                      >确认入库</el-button
                    >
                  </div>
                </div>
                <el-table
                  :data="txnCandidates"
                  size="small"
                  stripe
                  class="disc-table"
                >
                  <el-table-column label="代码" prop="symbol" width="110" />
                  <el-table-column label="名称" prop="name" min-width="120" />
                  <el-table-column label="操作" width="90">
                    <template #default="{ row }">
                      {{ (row as any).op_type_label || row.op_type }}
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="数量"
                    prop="quantity"
                    width="100"
                    align="right"
                  />
                  <el-table-column
                    label="金额"
                    prop="amount"
                    width="110"
                    align="right"
                  />
                  <el-table-column label="日期" prop="trade_date" width="120" />
                </el-table>
              </div>

              <div class="domain-placeholder">
                <div class="domain-placeholder__status">
                  <span
                    class="domain-status-tag"
                    :class="`domain-status-tag--${tab.status}`"
                  >
                    {{ tab.statusLabel }}
                  </span>
                  <span class="domain-placeholder__hint">{{
                    tab.placeholderHint
                  }}</span>
                </div>
                <div class="domain-placeholder__body">
                  <p class="domain-placeholder__desc">{{ tab.desc }}</p>
                  <div
                    v-if="tab.links.length"
                    class="domain-placeholder__links"
                  >
                    <el-button
                      v-for="(link, i) in tab.links"
                      :key="i"
                      size="small"
                      text
                      @click="goTo(link.to)"
                    >
                      {{ link.label }}
                      <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
                    </el-button>
                  </div>
                </div>
              </div>
            </template>
          </CardBlock>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 就地补充弹窗（§6.4）：工作台内补录，绝不跳「记一笔」 -->
    <el-dialog
      v-model="supplementVisible"
      :title="`就地补充 · ${supplementTarget?.symbol || ''}`"
      width="520px"
      append-to-body
    >
      <el-form label-width="80px" size="default">
        <el-form-item label="补充方式">
          <el-radio-group v-model="supplementForm.kind">
            <el-radio-button value="increment">补一笔交易</el-radio-button>
            <el-radio-button value="set">设定持仓</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="supplementForm.kind === 'increment'">
          <el-form-item label="操作类型">
            <el-select v-model="supplementForm.op_type" style="width: 100%">
              <el-option label="买入" value="buy" />
              <el-option label="卖出" value="sell" />
              <el-option label="存入" value="deposit" />
              <el-option label="取出" value="withdraw" />
            </el-select>
          </el-form-item>
        </template>

        <el-form-item label="数量">
          <el-input-number
            v-model="supplementForm.quantity"
            :min="0"
            :precision="4"
            style="width: 100%"
            placeholder="份额/数量"
          />
        </el-form-item>
        <el-form-item label="价格">
          <el-input-number
            v-model="supplementForm.avg_price"
            :min="0"
            :precision="4"
            style="width: 100%"
            placeholder="净值/单价"
          />
        </el-form-item>
        <el-form-item
          :label="supplementForm.kind === 'increment' ? '确认日期' : '快照日期'"
        >
          <el-date-picker
            v-model="supplementForm.confirm_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
            placeholder="选择日期"
          />
        </el-form-item>
        <el-form-item label="原因">
          <el-input
            v-model="supplementForm.reason"
            type="textarea"
            :rows="2"
            placeholder="补充说明（选填）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="supplementVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="supplementing"
          @click="submitSupplement"
        >
          确认补充
        </el-button>
      </template>
    </el-dialog>

    <!-- AI 识别入口（P3 / #1250）：截图/文本识别 → 预览核对 → 确认进草稿 -->
    <RecognizerImportModal
      v-model="recognizerVisible"
      @saved="onRecognizerSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import {
  runReconciliation,
  listDiscrepancies,
  ignoreDiscrepancy,
  applyAdjustment,
  type DiscrepancyItem,
  type AdjustmentPayload
} from "@/api/reconciliation";
import {
  getEaccountReconciliation,
  attributeEaccount,
  type ReconciliationItem
} from "@/api/eaccount";
import { confirmImport, confirmHoldingImport } from "@/api/importer";
import type { OcrHoldingRow } from "@/api/ocr";
import {
  useReconDraft,
  type RecognizerCandidate
} from "@/composables/useReconDraft";
import RecognizerImportModal from "@/components/QuickEntry/RecognizerImportModal.vue";

defineOptions({ name: "ReconcileWorkbench" });

const router = useRouter();

/** 当前激活域 */
const activeDomain = ref<"A" | "B" | "C">("B");

/** 识别候选草稿（P3-1 / #1250）：AI 识别结果落 recon-draft:recognizer，由工作台加载 */
const { getRecognizerCandidates, clearRecognizerCandidates } = useReconDraft();
const recognizerCandidates = ref<RecognizerCandidate[]>([]);
const recognizerVisible = ref(false);
const committing = ref(false);

/** 差异数据 */
const discs = ref<DiscrepancyItem[]>([]);
const loading = ref(false);
const running = ref(false);

/** 域 A：E账户对账数据（P2 迁入） */
const eItems = ref<ReconciliationItem[]>([]);
const eLoading = ref(false);
const actingRecordId = ref<number | null>(null);
const actingAction = ref<"cover" | "ignore" | null>(null);

/** 域 B 差异：仅展示待处理（pending）行，使下方表格与顶部「待裁决差异」口径一致（#1259） */
const bDiscs = computed(() =>
  discs.value.filter(d => d.domain === "B" && d.status === "pending")
);

/** 就地补充弹窗（§6.4）：不跳「记一笔」 */
const supplementVisible = ref(false);
const supplementTarget = ref<DiscrepancyItem | null>(null);
const supplementForm = reactive({
  kind: "increment" as "increment" | "set",
  op_type: "buy",
  quantity: undefined as number | undefined,
  avg_price: undefined as number | undefined,
  confirm_date: "",
  reason: ""
});
const supplementing = ref(false);

/** 顶部「待裁决差异」= 当前激活域的 pending 数，与下方表格可见可操作行口径一致（#1259） */
const pendingCount = computed(() => domainPending(activeDomain.value));
/** 顶部「已忽略」= 当前激活域的 ignored 数（#1259） */
const ignoredCount = computed(() => domainIgnored(activeDomain.value));
/** 全局待处理总数，仅用于 Banner 提醒（不要求与单表对齐） */
const totalPending = computed(() => {
  const fromDiscs = discs.value.filter(d => d.status === "pending").length;
  const fromE = eItems.value.filter(i => i.status === "pending").length;
  return fromDiscs + fromE;
});
/** 数据日期：最近一次差异的 updated_at 或今日 */
const dataDateLabel = computed(() => {
  const t = discs.value
    .map(d => d.updated_at)
    .filter(Boolean)
    .sort()
    .pop();
  return t ? t.slice(0, 10) : "—";
});

/** 是否有待处理差异（Banner 显示条件，用全局总数判断） */
const hasPending = computed(() => totalPending.value > 0);

/** 三域 Tab 定义（§6.3） */
const domainTabs = [
  {
    key: "A",
    label: "E账户对账",
    title: "E账户对账（域 A）",
    description: "E账户官方快照 vs 渠道持仓",
    badgeType: "e_account",
    status: "ready",
    statusLabel: "已接入",
    placeholderHint: "复用既有对账链路",
    desc: "E账户对账已上线，P2 迁入本工作台统一入口。本期保持原入口可用。",
    links: [{ to: { name: "InvestmentReconcile" }, label: "前往原对账中心" }]
  },
  {
    key: "B",
    label: "持仓快照",
    title: "持仓快照一致性（域 B）",
    description: "流水推演理论持仓 vs 实际持仓",
    badgeType: "fund",
    status: "ready",
    statusLabel: "已接入",
    placeholderHint: "数量差异 + 孤儿检测",
    desc: "P1 已接入：理论持仓 = 流水重建净份额，比对实际持仓数量差异与孤儿。",
    links: []
  },
  {
    key: "C",
    label: "对账单导入",
    title: "对账单/交割单导入对账（域 C）",
    description: "导入的券商/基金对账单 vs 系统持仓",
    badgeType: "fund",
    status: "planned",
    statusLabel: "P1 规划",
    placeholderHint: "本期占位",
    desc: "P1 落地：导入 commit 后自动触发对账，差异进本工作台补录。",
    links: [
      { to: "/inventory/investment/import", label: "前往交易导入" },
      { to: "/investment/eaccount-import", label: "前往 E账户导入" }
    ]
  }
];

/** 各域待处理 / 已忽略计数（域 A 来自 E账户链路 eItems，域 B/C 来自 discrepancies discs），
 *  用于顶部指标与 Tab 角标，使统计口径与用户当前可见域一致（#1259） */
function domainPending(key: string): number {
  if (key === "A")
    return eItems.value.filter(i => i.status === "pending").length;
  return discs.value.filter(d => d.domain === key && d.status === "pending")
    .length;
}
function domainIgnored(key: string): number {
  if (key === "A")
    return eItems.value.filter(i => i.status === "ignored").length;
  return discs.value.filter(d => d.domain === key && d.status === "ignored")
    .length;
}

/** 差异类型中文 */
function typeLabel(t: string): string {
  const map: Record<string, string> = {
    quantity: "数量",
    cost: "成本",
    cash: "资金",
    orphan: "孤儿"
  };
  return map[t] || t;
}

/** 状态中文 */
function statusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: "待处理",
    cleared: "已清除",
    ignored: "已忽略"
  };
  return map[s] || s;
}

/** 差异值格式：份额（已由后端 Money.min_unit_to_shares 转换） */
function formatDiff(diff: number | null): string {
  if (diff === null) return "—";
  if (diff === 0) return "0";
  return Number.isInteger(diff)
    ? String(diff)
    : diff.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function diffClass(diff: number | null): string {
  if (!diff) return "disc-diff-zero";
  return diff > 0 ? "disc-diff-pos" : "disc-diff-neg";
}

/** 加载识别候选草稿（P3-1 / #1250）：AI 识别结果落 recon-draft:recognizer，跨页/刷新承接不丢 */
async function loadRecognizerCandidates(): Promise<void> {
  try {
    recognizerCandidates.value = await getRecognizerCandidates();
  } catch {
    recognizerCandidates.value = [];
  }
}

/** 域 C（txn 候选）/ 域 A（holding 候选）分别渲染 */
const txnCandidates = computed(() =>
  recognizerCandidates.value.filter(c => c.kind === "txn")
);
const holdingCandidates = computed(() =>
  recognizerCandidates.value.filter(c => c.kind === "holding")
);

/** 确认入库（#1251 / #1252）：剥离 kind → 既有导入确认端点，再触发对应域对账 */
async function commitCandidates(kind: "txn" | "holding"): Promise<void> {
  const list = recognizerCandidates.value.filter(c => c.kind === kind);
  if (list.length === 0) return;
  committing.value = true;
  try {
    // 候选行即 OCR 预览行，剥离 kind 后原样回传确认端点（txn/hodling 各自落库管线）
    const rows = list.map(c => {
      const { kind: _k, ...row } = c;
      return row;
    });
    if (kind === "txn") {
      const res = await confirmImport(rows);
      ElMessage.success(
        `已入库 ${res?.data?.imported ?? rows.length} 条交易，已触发域 C 对账`
      );
    } else {
      const res = await confirmHoldingImport(rows as OcrHoldingRow[]);
      ElMessage.success(
        `已入库 ${res?.data?.imported ?? rows.length} 条持仓，已刷新域 A 对账`
      );
    }
    await clearRecognizerCandidates(kind);
    await loadRecognizerCandidates();
    if (kind === "txn") {
      await runReconciliation("C");
    } else {
      await loadEAccount();
    }
    await loadDiscrepancies();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err.response?.data?.message || "入库失败");
  } finally {
    committing.value = false;
  }
}

/** 丢弃识别草稿 */
async function discardCandidates(): Promise<void> {
  await clearRecognizerCandidates();
  await loadRecognizerCandidates();
  ElMessage.info("已丢弃识别草稿");
}

/** 识别入口弹窗保存后刷新候选列表 */
async function onRecognizerSaved(): Promise<void> {
  await loadRecognizerCandidates();
}

/** 加载差异列表 */
async function loadDiscrepancies(): Promise<void> {
  loading.value = true;
  try {
    const res = await listDiscrepancies();
    discs.value = res.data ?? [];
  } catch {
    discs.value = [];
  } finally {
    loading.value = false;
  }
}

/** 加载 E账户对账中心数据（域 A） */
async function loadEAccount(): Promise<void> {
  eLoading.value = true;
  try {
    const res = await getEaccountReconciliation();
    const data = (res as any).data ?? {};
    eItems.value = (data.items ?? []) as ReconciliationItem[];
  } catch {
    eItems.value = [];
  } finally {
    eLoading.value = false;
  }
}

/** E账户记录状态中文（四态） */
function eStatusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: "待处理",
    attributed: "已归因",
    ignored: "已忽略",
    verified: "已核对"
  };
  return map[s] || s;
}

/** 归因覆盖（危险操作：删除渠道原记录，P2 迁入工作台） */
async function handleEAccountCover(row: any): Promise<void> {
  actingRecordId.value = row.record_id;
  actingAction.value = "cover";
  try {
    const res = await attributeEaccount([
      {
        symbol: row.symbol,
        source_broker: row.source_broker || "",
        fund_manager: row.fund_manager || "",
        action: "cover"
      }
    ]);
    const result = (res as any).data ?? {};
    if (result.failed > 0) {
      ElMessage.warning(`归因覆盖完成，但有 ${result.failed} 条未成功`);
    } else {
      ElMessage.success("已归因覆盖");
    }
    await loadEAccount();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "归因覆盖失败");
  } finally {
    actingRecordId.value = null;
    actingAction.value = null;
  }
}

/** 忽略（E账户，导入自动跳过，可重新对账恢复） */
async function handleEAccountIgnore(row: any): Promise<void> {
  actingRecordId.value = row.record_id;
  actingAction.value = "ignore";
  try {
    const res = await attributeEaccount([
      {
        symbol: row.symbol,
        source_broker: row.source_broker || "",
        fund_manager: row.fund_manager || "",
        action: "ignore"
      }
    ]);
    const result = (res as any).data ?? {};
    if (result.failed > 0) {
      ElMessage.warning(`忽略完成，但有 ${result.failed} 条未成功`);
    } else {
      ElMessage.success("已忽略");
    }
    await loadEAccount();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "忽略失败");
  } finally {
    actingRecordId.value = null;
    actingAction.value = null;
  }
}

/** 打开就地补充弹窗（§6.4） */
function openSupplement(row: any): void {
  supplementTarget.value = row;
  supplementForm.kind = "increment";
  supplementForm.op_type = "buy";
  supplementForm.quantity = undefined;
  supplementForm.avg_price = undefined;
  supplementForm.confirm_date = "";
  supplementForm.reason = "";
  supplementVisible.value = true;
}

/** 提交就地补充（调 apply_decision，不跳「记一笔」） */
async function submitSupplement(): Promise<void> {
  const target = supplementTarget.value;
  if (!target) return;
  if (!supplementForm.quantity || !supplementForm.avg_price) {
    ElMessage.warning("请填写数量与价格");
    return;
  }
  supplementing.value = true;
  try {
    const payload: AdjustmentPayload = {
      kind: supplementForm.kind,
      discrepancy_id: target.id,
      symbol: target.symbol,
      ledger_id: target.ledger_id,
      quantity: supplementForm.quantity,
      avg_price: supplementForm.avg_price,
      reason: supplementForm.reason || undefined
    };
    if (supplementForm.kind === "increment") {
      payload.op_type = supplementForm.op_type;
      payload.confirm_date = supplementForm.confirm_date || undefined;
    } else {
      payload.snapshot_date = supplementForm.confirm_date || undefined;
    }
    await applyAdjustment(payload);
    ElMessage.success("补充完成");
    supplementVisible.value = false;
    await loadDiscrepancies();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "补充失败");
  } finally {
    supplementing.value = false;
  }
}

/** 运行对账（域 B） */
async function handleRun(): Promise<void> {
  running.value = true;
  try {
    await runReconciliation("B");
    ElMessage.success("对账完成");
    await loadDiscrepancies();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "对账失败");
  } finally {
    running.value = false;
  }
}

/** 忽略一条差异（临时） */
async function handleIgnore(row: DiscrepancyItem): Promise<void> {
  try {
    await ignoreDiscrepancy(row.id, { permanent: false });
    ElMessage.success("已忽略");
    await loadDiscrepancies();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "忽略失败");
  }
}

/** 导航到既有入口（并行不破坏现状） */
function goTo(to: string | { name: string }): void {
  router.push(to);
}

/** Banner 点击：切换到第一个有待处理差异的域并定位到表格区（#1259） */
function focusFirstPendingDomain(): void {
  const order: ("A" | "B" | "C")[] = ["B", "C", "A"];
  const target = order.find(k => domainPending(k) > 0);
  if (!target) return;
  activeDomain.value = target;
  nextTick(() => {
    document
      .querySelector(".workbench-tabs")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

onMounted(() => {
  loadDiscrepancies();
  loadEAccount();
  loadRecognizerCandidates();
});
</script>

<style scoped>
.recon-workbench-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* 页头 */
.workbench-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.workbench-head__title {
  margin: 0 0 6px;
  font-size: var(--text-display);
  font-weight: 300;
  color: var(--text-primary);
}

.workbench-head__subtitle {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.workbench-head__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 柔性 Warning Banner（§6.3）：中性信息色，非红非弹窗 */
.workbench-banner {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

/* Banner 可点击：点击切换到待处理域（#1259） */
.workbench-banner--clickable {
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.workbench-banner--clickable:hover {
  background: color-mix(in srgb, var(--brand-100) 40%, var(--bg-soft));
  border-color: var(--brand-400);
}

/* Tab 标签内的各域待处理数角标（#1259） */
.domain-tab-label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.domain-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 11px;
  line-height: 1;
  color: #fff;
  background: var(--brand-600, #d98b2b);
  border-radius: 999px;
}

.workbench-banner__icon {
  font-size: 16px;
  color: var(--brand-700);
}

.workbench-banner__text {
  flex: 1;
}

/* 状态栏 */
.workbench-metrics {
  margin-bottom: 20px;
}

/* 三域 Tab */
.workbench-tabs__inner {
  padding: 4px;
}

/* 域 B 差异表 */
.domain-b-body {
  padding: 4px 0;
}

.disc-table-wrap {
  overflow-x: auto;
}

.disc-table {
  width: 100%;
}

.disc-type {
  padding: 1px 8px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: 4px;
}

.disc-diff-zero {
  color: var(--text-tertiary);
}

.disc-diff-pos {
  color: var(--tag-sage-green);
}

.disc-diff-neg {
  color: var(--color-danger-system);
}

.disc-status {
  padding: 1px 8px;
  font-size: 12px;
  border-radius: 999px;
}

.disc-status--pending {
  color: var(--tag-caramel);
  background: color-mix(in srgb, var(--tag-caramel) 12%, transparent);
}

.disc-status--cleared {
  color: var(--tag-sage-green);
  background: color-mix(in srgb, var(--tag-sage-green) 12%, transparent);
}

.disc-status--ignored {
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

.disc-muted {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 域 A/C 占位 */
.domain-placeholder {
  padding: 8px 4px;
}

.domain-placeholder__status {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}

.domain-status-tag {
  padding: 2px 10px;
  font-size: 12px;
  line-height: 1.6;
  border-radius: 999px;
}

.domain-status-tag--ready {
  color: var(--tag-sage-green);
  background: color-mix(in srgb, var(--tag-sage-green) 12%, transparent);
}

.domain-status-tag--planned {
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

.domain-placeholder__hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.domain-placeholder__desc {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.domain-placeholder__links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 识别候选面板（#1250 / P3-1）：AI 识别结果落草稿后在三域 Tab 顶部展示，确认后入库并触发对账 */
.recognizer-candidate-panel {
  padding: 12px 16px;
  margin-bottom: 16px;
  background: color-mix(in srgb, var(--brand-100) 35%, var(--bg-card));
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.recognizer-candidate-panel__head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.recognizer-candidate-panel__title {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.recognizer-candidate-panel__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
