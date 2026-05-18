<template>
  <div class="inventory-page">
    <el-steps :active="currentStep" finish-status="success" align-center>
      <el-step title="选择导入模式" />
      <el-step title="上传文件" />
      <el-step title="预览与修正" />
      <el-step title="导入完成" />
    </el-steps>

    <div class="step-content">
      <!-- 步骤1：选择导入模式 -->
      <div v-if="currentStep === 0" class="import-mode-cards">
        <div
          v-for="mode in importModes"
          :key="mode.key"
          class="mode-card"
          :class="{ active: selectedMode === mode.key }"
          @click="selectMode(mode.key)"
        >
          <IconifyIconOffline :icon="mode.icon" class="mode-icon" />
          <h4 class="mode-title">{{ mode.title }}</h4>
          <p class="mode-desc">{{ mode.description }}</p>
        </div>
      </div>

      <!-- 步骤2：文件上传 / 解析中 -->
      <div v-else-if="currentStep === 1" class="upload-step">
        <!-- 解析中骨架屏（标准 el-skeleton） -->
        <div v-show="parsing" class="parsing-status">
          <p class="text-sm text-gray-500 mb-4">
            <el-icon class="is-loading mr-1"><Loading /></el-icon>
            正在解析文件，请稍候...
          </p>
          <p class="text-xs text-gray-400 mb-4">
            正在处理 {{ fileSize }}，预计需要 5-10 秒
          </p>
          <el-skeleton :rows="8" animated />
        </div>

        <!-- 上传区域 -->
        <div v-show="!parsing" class="upload-area">
          <el-upload
            ref="uploadRef"
            :accept="'.csv,.xls,.xlsx'"
            :before-upload="beforeUpload"
            :http-request="handleUpload"
            :show-file-list="false"
            drag
            class="golden-upload"
          >
            <IconifyIconOffline icon="ep:upload-filled" class="upload-icon" />
            <p class="upload-text">将 CSV/Excel 文件拖到此处，或<span class="upload-link">点击上传</span></p>
            <p class="upload-hint">
              {{ selectedMode === 'ths' ? '同花顺历史交割单导出文件' : '使用标准模板格式的文件' }}
            </p>
          </el-upload>
        </div>
      </div>

      <!-- 步骤3：预览与修正 -->
      <div v-else-if="currentStep === 2" class="preview-table">
        <el-alert
          v-if="duplicateCount > 0"
          :title="`发现 ${duplicateCount} 条疑似重复记录，已自动取消勾选`"
          type="warning"
          show-icon
          closable
          class="mb-4"
        />
        <el-alert
          v-if="errorCount > 0"
          :title="`发现 ${errorCount} 条解析错误，请修正或取消勾选`"
          type="error"
          show-icon
          closable
          class="mb-4"
        />

        <div class="top-action-bar">
          <el-button size="default" @click="currentStep = 1">返回上一步</el-button>
          <el-button size="default" :loading="isTogglingAll" @click="debouncedToggleAllSelection">
            {{ isAllSelected ? '取消全选' : '全选有效' }}
          </el-button>
          <el-switch
            v-model="showProblemOnly"
            active-text="只显示问题数据"
            inactive-text="全部数据"
            class="ml-4"
          />
        </div>

        <!-- 表格：去掉固定高度，使用前端分页保证性能 -->
        <el-table
          :data="filteredPagedData"
          row-key="_rowKey"
          ref="previewTableRef"
          stripe
          size="default"
          class="preview-table-content"
          @selection-change="handleSelectionChange"
        >
          <!-- 自定义全选列 -->
          <el-table-column width="55" fixed="left">
            <template #header>
              <el-checkbox
                v-model="isAllSelected"
                :indeterminate="isIndeterminate"
                @change="handleHeaderCheckboxChange"
              />
            </template>
            <template #default="{ row }">
              <!-- 资金划转：禁用并提示 -->
              <el-tooltip
                v-if="row.is_cash_transfer"
                content="资金划转暂不支持导入"
                placement="top"
              >
                <el-checkbox :model-value="false" :disabled="true" />
              </el-tooltip>
              <!-- 正常行：可勾选 -->
              <el-checkbox
                v-else
                :model-value="isRowSelected(row)"
                :disabled="row.is_duplicate || row.error || isRowBlocked(row)"
                @change="(val) => handleRowCheckboxChange(row, val)"
              />
            </template>
          </el-table-column>
          <!-- 数据列 -->
          <el-table-column prop="symbol" label="代码" width="110" />
          <el-table-column prop="name" label="名称" width="100" />
          <el-table-column prop="op_type_label" label="操作" width="60" />
          <!-- 可编辑列：数量 -->
          <el-table-column prop="quantity" label="数量" width="80" align="right">
            <template #default="{ row }">
              <el-popover
                :visible="row.isEditingQty"
                placement="bottom-start"
                :width="200"
                trigger="manual"
                :hide-after="0"
                :persistent="true"
                teleported
              >
                <div class="flex flex-col gap-2" @mousedown.stop>
                  <div class="text-xs text-gray-500">
                    {{ row.symbol }} {{ row.name }} - <span class="font-semibold text-gray-700">数量</span>
                  </div>
                  <el-input-number
                    v-model="row.quantity"
                    size="default"
                    :precision="4"
                    :min="0"
                    class="w-full"
                    controls-position="right"
                    ref="inputRef"
                    @vue:mounted="(el) => el?.input?.focus()"
                  />
                  <div class="flex justify-end gap-2">
                    <el-button type="primary" size="small" @click.stop="finishEdit(row, 'quantity', true)">确认</el-button>
                    <el-button size="small" @click.stop="cancelEdit(row, 'quantity')">取消</el-button>
                  </div>
                </div>
                <template #reference>
                  <span
                    class="cursor-pointer hover:text-blue-500 select-none"
                    @click.stop="startEdit(row, 'quantity')"
                    @mousedown.prevent
                  >{{ row.quantity }}</span>
                </template>
              </el-popover>
            </template>
          </el-table-column>
          <!-- 可编辑列：价格 -->
          <el-table-column prop="price" label="价格" width="90" align="right">
            <template #default="{ row }">
              <el-popover
                :visible="row.isEditingPrice"
                placement="bottom-start"
                :width="200"
                trigger="manual"
                :hide-after="0"
                :persistent="true"
                teleported
              >
                <div class="flex flex-col gap-2" @mousedown.stop>
                  <div class="text-xs text-gray-500">
                    {{ row.symbol }} {{ row.name }} - <span class="font-semibold text-gray-700">价格</span>
                  </div>
                  <el-input-number
                    v-model="row.price"
                    size="default"
                    :precision="4"
                    :min="0"
                    class="w-full"
                    controls-position="right"
                    ref="inputRef"
                    @vue:mounted="(el) => el?.input?.focus()"
                  />
                  <div class="flex justify-end gap-2">
                    <el-button type="primary" size="small" @click.stop="finishEdit(row, 'price', true)">确认</el-button>
                    <el-button size="small" @click.stop="cancelEdit(row, 'price')">取消</el-button>
                  </div>
                </div>
                <template #reference>
                  <span
                    class="cursor-pointer hover:text-blue-500 select-none"
                    @click.stop="startEdit(row, 'price')"
                    @mousedown.prevent
                  >{{ row.price }}</span>
                </template>
              </el-popover>
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="交易金额" width="120" align="right" />
          <el-table-column prop="fee" label="手续费" width="90" align="right" />
          <el-table-column prop="trade_date" label="交收日期" width="110" />
          <el-table-column prop="contract_id" label="合同编号" width="110" />
          <el-table-column prop="net_amount" label="发生金额" width="120" align="right" />
          <el-table-column prop="notes" label="备注" min-width="120" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_duplicate" type="warning" size="small">重复</el-tag>
              <el-tag v-else-if="row.error" type="danger" size="small">错误</el-tag>
              <el-tag v-else-if="isRowBlocked(row)" type="info" size="small">待补全</el-tag>
              <el-tag v-else type="success" size="small">正常</el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-bar">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="filteredTotal"
            :page-sizes="[20, 50, 100, 200]"
            layout="prev, pager, next, sizes, jumper"
            small
            background
            @size-change="handleSizeChange"
            @current-change="handlePageChange"
          />
        </div>

        <!-- 底部固定操作栏 -->
        <div class="fixed-action-bar">
          <div class="action-content">
            <span class="selected-count">
              已选择 <strong>{{ selectedCount }}</strong> / {{ validRowsCount }} 条有效记录（共 {{ totalRows }} 条）
            </span>
            <el-button
              type="primary"
              size="default"
              :disabled="selectedCount === 0"
              :loading="importing"
              @click="confirmImport"
              class="import-btn"
            >
              确认导入 {{ selectedCount }} 条
            </el-button>
          </div>
        </div>
      </div>

      <!-- 步骤4：导入完成 -->
      <div v-else class="import-result">
        <el-result icon="success" title="导入完成">
          <template #sub-title>
            <p>成功导入 {{ importedCount }} 笔交易，跳过 {{ skippedCount }} 笔。</p>
            <div v-if="importErrors.length > 0" class="mt-4 text-left">
              <el-alert
                title="以下记录未导入"
                type="warning"
                :closable="false"
              >
                <ul class="list-disc pl-4 text-xs">
                  <li v-for="(err, idx) in importErrors" :key="idx">
                    {{ err.name || err.symbol }}: {{ err.error }}
                  </li>
                </ul>
              </el-alert>
            </div>
            <div class="flex gap-2 justify-center mt-4">
              <el-button type="primary" @click="goToTransactions">查看交易流水</el-button>
              <el-button @click="resetImport">继续导入</el-button>
            </div>
          </template>
        </el-result>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { parseFile, confirmImport as confirmImportApi } from '@/api/importer';
import type { UploadRequestOptions } from 'element-plus';
import { ref, watch, onUnmounted, nextTick, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';

defineOptions({ name: 'Inventory' });

const router = useRouter();

// ---------- 基础状态 ----------
const currentStep = ref(0);
const selectedMode = ref('standard');
const previewData = ref<any[]>([]);
const duplicateCount = ref(0);
const errorCount = ref(0);
const importedCount = ref(0);
const skippedCount = ref(0);
const importing = ref(false);
const parsing = ref(false);
const fileSize = ref('');
const isTogglingAll = ref(false);
const editingRowKey = ref<string | null>(null);

// ---------- 分页 ----------
const currentPage = ref(1);
const pageSize = ref(50);
const totalRows = ref(0);
const previewTableRef = ref<any>(null);

// ---------- 自定义选择 ----------
const selectedKeys = ref<Set<string>>(new Set());
const isAllSelected = ref(false);
const isIndeterminate = ref(false);
const showProblemOnly = ref(false);

// ---------- 导入错误反馈 ----------
const importErrors = ref<any[]>([]);

// ---------- 骨架屏（现在只用 CSS 动画，无需 JS 定时器） ----------
const importModes = [
  { key: 'standard', icon: 'ep:document', title: '标准模板', description: '使用 ShowBuy 通用模板导入交易记录' },
  { key: 'ths', icon: 'ep:bank-card', title: '同花顺交割单', description: '直接上传同花顺导出的历史交割单' },
];

// ---------- 工具函数 ----------
function addRowKeys(data: any[]) {
  return data.map((item, idx) => ({ ...item, _rowKey: `row_${idx}` }));
}

// 判断行是否因数量/价格为0且非资金划转而不能导入
function isRowBlocked(row: any): boolean {
  if (row.is_cash_transfer || row.error || row.is_duplicate) return false;
  const qty = Number(row.quantity);
  const prc = Number(row.price);
  return (isNaN(qty) || qty <= 0) || (isNaN(prc) || prc <= 0);
}

// ---------- 有效行计数（手动管理，保证更新） ----------
const validRowsCount = ref(0);

function recalcValidRowsCount() {
  validRowsCount.value = previewData.value.filter(
    row => !row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer
  ).length;
}

// ---------- 分页过滤数据 ----------
const filteredPagedData = computed(() => {
  let list = previewData.value;
  if (showProblemOnly.value) {
    // 编辑中的行即使不再是问题数据，也要保留在视图中，避免弹窗消失
    list = list.filter(row => isRowBlocked(row) || row.error || row.isEditingQty || row.isEditingPrice);
  }
  const start = (currentPage.value - 1) * pageSize.value;
  return list.slice(start, start + pageSize.value);
});

const filteredTotal = computed(() => {
  let list = previewData.value;
  if (showProblemOnly.value) {
    list = list.filter(row => isRowBlocked(row) || row.error || row.isEditingQty || row.isEditingPrice);
  }
  return list.length;
});

// 已选行数
const selectedCount = computed(() => selectedKeys.value.size);

// 行是否被选中
function isRowSelected(row: any): boolean {
  return selectedKeys.value.has(row._rowKey);
}

// 单行选中切换
function handleRowCheckboxChange(row: any, checked: boolean) {
  if (checked) {
    selectedKeys.value.add(row._rowKey);
  } else {
    selectedKeys.value.delete(row._rowKey);
  }
  selectedKeys.value = new Set(selectedKeys.value);
  updateSelectAllState();
}

// 表头全选
function handleHeaderCheckboxChange(checked: boolean) {
  if (checked) {
    selectAllValid();
  } else {
    clearAllSelection();
  }
}

function selectAllValid() {
  const newKeys = new Set<string>();
  previewData.value.forEach(row => {
    if (!row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer) {
      newKeys.add(row._rowKey);
    }
  });
  selectedKeys.value = newKeys;
  isAllSelected.value = true;
  isIndeterminate.value = false;
}

function clearAllSelection() {
  selectedKeys.value = new Set();
  isAllSelected.value = false;
  isIndeterminate.value = false;
}

function updateSelectAllState() {
  const totalValid = validRowsCount.value;
  const currentSelected = selectedKeys.value.size;
  if (currentSelected === 0) {
    isAllSelected.value = false;
    isIndeterminate.value = false;
  } else if (currentSelected >= totalValid) {
    isAllSelected.value = true;
    isIndeterminate.value = false;
  } else {
    isAllSelected.value = false;
    isIndeterminate.value = true;
  }
}

// 防抖全选按钮
function debouncedToggleAllSelection() {
  isTogglingAll.value = true;
  setTimeout(() => {
    if (isAllSelected.value) {
      clearAllSelection();
    } else {
      selectAllValid();
    }
    isTogglingAll.value = false;
  }, 150);
}

// ---------- 行内编辑 ----------
function startEdit(row: any, field: string) {
  if (editingRowKey.value && editingRowKey.value !== row._rowKey) {
    saveAllEditingRows();
    closeAllEditing();
  }
  row._oldValue = row[field];
  if (field === 'quantity') {
    row.isEditingQty = true;
    row.isEditingPrice = false;
  } else if (field === 'price') {
    row.isEditingPrice = true;
    row.isEditingQty = false;
  }
  editingRowKey.value = row._rowKey;
}

function finishEdit(row: any, field: string, save: boolean = true) {
  const wasBlocked = isRowBlocked(row);   // 编辑前是否阻塞
  if (!save) {
    row[field] = row._oldValue;
  } else {
    smartFill(row, field);
  }
  delete row._oldValue;
  if (field === 'quantity') row.isEditingQty = false;
  else if (field === 'price') row.isEditingPrice = false;

  editingRowKey.value = null;

  // 行状态变化处理
  const nowBlocked = isRowBlocked(row);
  if (wasBlocked && !nowBlocked) {
    // 从阻塞变为有效 → 自动勾选、切换回全部视图
    selectedKeys.value.add(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
    if (showProblemOnly.value) {
      showProblemOnly.value = false;
      ElMessage.success('数据已修正，已自动切换为全部数据视图');
    } else {
      ElMessage.success('数据已自动勾选');
    }
  } else if (!wasBlocked && nowBlocked) {
    // 从有效变为阻塞 → 取消勾选
    selectedKeys.value.delete(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
  }

  recalcValidRowsCount();
  updateSelectAllState();
}

function closeAllEditing() {
  previewData.value.forEach(row => {
    if (row.isEditingQty) {
      row.isEditingQty = false;
      delete row._oldValue;
    }
    if (row.isEditingPrice) {
      row.isEditingPrice = false;
      delete row._oldValue;
    }
  });
  editingRowKey.value = null;
}

function cancelEdit(row: any, field: string) {
  finishEdit(row, field, false);
}

function syncRowState(row: any) {
  if (!isRowBlocked(row)) {
    if (isAllSelected.value) {
      selectedKeys.value.add(row._rowKey);
      selectedKeys.value = new Set(selectedKeys.value);
    }
  } else {
    selectedKeys.value.delete(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
  }
}

// ---------- 步骤控制 ----------
function selectMode(mode: string) {
  selectedMode.value = mode;
  currentStep.value = 1;
}

function beforeUpload(file: File) {
  const allowedExtensions = ['.csv', '.xls', '.xlsx'];
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (!allowedExtensions.includes(ext)) {
    ElMessage.error('仅支持 CSV 或 Excel 文件');
    return false;
  }
  return true;
}

// ---------- 上传解析 ----------
async function handleUpload(options: UploadRequestOptions) {
  const file = options.file as File;
  parsing.value = true;
  await new Promise(resolve => setTimeout(resolve, 50));

  try {
    const res = await parseFile(file, selectedMode.value);
    const rawData = (res as any).data ?? [];
    previewData.value = addRowKeys(rawData);
    totalRows.value = previewData.value.length;
    duplicateCount.value = (res as any).duplicate_count ?? 0;
    errorCount.value = (res as any).error_count ?? 0;

    // 初始智能填充：对价格缺失但数量和金额都有的行计算参考价格
    previewData.value.forEach(row => {
      if (!isRowBlocked(row) && !row.is_cash_transfer && !row.error && !row.is_duplicate) {
        const qty = parseFloat(row.quantity);
        const prc = parseFloat(row.price);
        const amt = parseFloat(row.amount);
        if (!isNaN(qty) && qty > 0 && (isNaN(prc) || prc <= 0) && !isNaN(amt)) {
          row.price = parseFloat((amt / qty).toFixed(4));
          row.smartFilled = true;
        }
      }
    });

    recalcValidRowsCount();
    selectAllValid();

    currentStep.value = 2;
    options.onSuccess(res);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '文件解析失败');
    options.onError(e);
  } finally {
    parsing.value = false;
  }
}

function smartFill(row: any, field: string) {
  const qty = parseFloat(row.quantity);
  const prc = parseFloat(row.price);
  const amt = parseFloat(row.amount);
  if (field === 'quantity' && isNaN(qty) && !isNaN(prc) && !isNaN(amt)) {
    row.quantity = parseFloat((amt / prc).toFixed(4));
    row.smartFilled = true;
  } else if (field === 'price' && isNaN(prc) && !isNaN(qty) && !isNaN(amt)) {
    row.price = parseFloat((amt / qty).toFixed(4));
    row.smartFilled = true;
  }
}

function saveAllEditingRows() {
  previewData.value.forEach(row => {
    if (row.isEditingQty) finishEdit(row, 'quantity', true);
    if (row.isEditingPrice) finishEdit(row, 'price', true);
  });
}

// ---------- 确认导入 ----------
async function confirmImport() {
  saveAllEditingRows();
  const rowsToImport = previewData.value.filter(row => {
    if (!selectedKeys.value.has(row._rowKey)) return false;
    if (row.is_duplicate || row.error) return false;
    if (row.is_cash_transfer) return false;
    if (isRowBlocked(row)) return false;
    return true;
  });

  if (rowsToImport.length === 0) {
    ElMessage.warning('没有可导入的有效记录');
    return;
  }

  importing.value = true;
  try {
    const res = await confirmImportApi(rowsToImport);
    importedCount.value = (res as any).data?.imported ?? 0;
    skippedCount.value = (res as any).data?.skipped ?? 0;
    importErrors.value = (res as any).data?.errors ?? [];
    currentStep.value = 3;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '导入失败');
  } finally {
    importing.value = false;
  }
}

// ---------- 其他操作 ----------
function goToTransactions() {
  router.push('/account/transactions');
}

function resetImport() {
  currentStep.value = 0;
  selectedMode.value = 'standard';
  previewData.value = [];
  selectedKeys.value = new Set();
  duplicateCount.value = 0;
  errorCount.value = 0;
  isAllSelected.value = false;
  isIndeterminate.value = false;
  importErrors.value = [];
  validRowsCount.value = 0;
}

function handleSizeChange(val: number) {
  pageSize.value = val;
  currentPage.value = 1;
}

function handlePageChange(val: number) {
  currentPage.value = val;
}

// 空函数，避免模板报错
function handleSelectionChange() {}

// ---------- 骨架屏动画（已改用纯 CSS，无需 JS 定时器） ----------
onUnmounted(() => {});
</script>

<style scoped>
/* 模式选择卡片 */
.mode-card {
  width: 240px;
  cursor: pointer;
  text-align: center;
  padding: 32px 24px;
  border-radius: 16px;
  border: 2px solid #eee;
  background: #fff;
  transition: all 0.3s ease;
}
.mode-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
}
.mode-card.active {
  border-color: var(--color-primary);
  background-color: var(--bg-hover);
}
.mode-icon {
  font-size: 36px;
  color: var(--color-primary);
  margin-bottom: 12px;
}
.mode-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}
.mode-desc {
  font-size: 12px;
  color: #999;
  line-height: 1.5;
}

/* 黄金比例上传区域（宽屏版） */
.upload-step {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 420px;
  padding: 24px 0;
}
.upload-area {
  width: 100%;
  display: flex;
  justify-content: center;
}
.golden-upload {
  width: 680px;
  height: 420px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  border: 2px dashed #d9d9d9;
  border-radius: 16px;
  background: #fafafa;
  transition: all 0.3s;
}
.golden-upload:hover {
  border-color: var(--color-primary);
  background: #f8f8ff;
}
.golden-upload :deep(.el-upload-dragger) {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}
.upload-icon {
  font-size: 56px;
  color: var(--color-primary);
  margin-bottom: 16px;
}
.upload-text {
  font-size: 16px;
  color: #333;
  margin: 0 0 12px;
}
.upload-link {
  color: var(--color-primary);
  font-weight: 500;
  cursor: pointer;
}
.upload-hint {
  font-size: 12px;
  color: #999;
  margin: 0;
}

.parsing-status {
  text-align: center;
  max-width: 680px;
  width: 100%;
}

/* ---------- 骨架屏呼吸动画 ---------- */
.skeleton-animate {
  background: linear-gradient(90deg, #f0f2f5 25%, #f5f7fa 50%, #f0f2f5 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 2.8s linear infinite forwards;
  border-radius: 4px;
}

@keyframes skeleton-loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.custom-skeleton {
  width: 100%;
  margin-top: 24px;
}

.skeleton-header,
.skeleton-row {
  border-radius: 4px;
  background-size: 200% 100%;
}

.skeleton-header {
  height: 54px;
  margin-bottom: 8px;
}

.skeleton-row {
  height: 48px;
  margin-bottom: 8px;
}

.preview-table {
  padding-bottom: 80px;
}

.top-action-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.preview-table-content {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.fixed-action-bar {
  position: sticky;
  bottom: 0;
  background: #fff;
  border-top: 1px solid #e5e7eb;
  box-shadow: 0 -2px 8px rgba(0,0,0,0.06);
  z-index: 10;
  margin-top: 16px;
}

.action-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.selected-count {
  color: #666666;
  font-size: 14px;
}

.import-btn {
  min-width: 160px;
  font-weight: 500;
}

:deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.import-mode-cards {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-top: 32px;
}

.step-content {
  margin-top: 32px;
  min-height: 400px;
}

.import-result {
  margin-top: 64px;
  text-align: center;
}
</style>
