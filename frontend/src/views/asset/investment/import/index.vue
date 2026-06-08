<template>
  <div class="inventory-page">
    <el-steps :active="currentStep" finish-status="success" align-center>
      <el-step v-for="(step, index) in steps" :key="index" :title="step.title" />
    </el-steps>

    <div class="step-content">
      <!-- 步骤0：选择导入账户 -->
      <div v-if="currentStep === 0">
        <div class="import-mode-group">
          <h3 class="import-group-title">选择导入账户</h3>
          <div class="account-select-area">
            <el-select
              v-model="selectedLedgerId"
              placeholder="请选择要导入的账户"
              size="large"
              class="account-select"
              @change="onAccountSelected"
            >
              <el-option-group
                v-for="group in ledgerGroups"
                :key="group.label"
                :label="group.label"
              >
                <el-option
                  v-for="ledger in group.ledgers"
                  :key="ledger.id"
                  :label="ledger.name"
                  :value="ledger.id"
                  :disabled="ledger.ledger_type === 'family'"
                >
                  <span class="ledger-option">
                    <span>{{ ledger.name }}</span>
                    <el-tag size="small" :type="ledger.ledger_type === 'family' ? 'info' : 'primary'">
                      {{ ledgerTypeMap[ledger.ledger_type] || ledger.ledger_type }}
                    </el-tag>
                  </span>
                </el-option>
              </el-option-group>
            </el-select>
            <p class="account-hint">
              选择账户后，系统将根据账户类型自动匹配导入模板。家庭账户不可用于导入交易数据。
            </p>
          </div>
        </div>

        <div class="import-mode-cards">
          <div class="mode-card" @click="goToManualEntry">
            <IconifyIconOffline icon="ep:edit" class="mode-icon" />
            <h4 class="mode-title">手动批量录入</h4>
            <p class="mode-desc">没有文件？在网页表格中逐行快速录入交易记录</p>
          </div>
          <div class="mode-card" @click="goToLiabilityForm">
            <IconifyIconOffline icon="ep:document-add" class="mode-icon" />
            <h4 class="mode-title">录入负债 / 应收款</h4>
            <p class="mode-desc">记录信用卡、房贷等非交易类资产</p>
          </div>
        </div>
      </div>

      <!-- 步骤1：文件上传 / 解析中 -->
      <div v-else-if="currentStep === 1" class="upload-step">
        <div v-show="parsing" class="parsing-status">
          <p class="text-sm text-gray-500 mb-4">
            <IconifyIconOffline icon="ep:loading" class="loading-icon" /> 正在解析文件，请稍候...
          </p>
          <p class="text-xs text-gray-400 mb-4">正在处理 {{ fileSize }}，预计需要 5-10 秒</p>
          <el-skeleton :rows="8" animated />
        </div>

        <div v-show="!parsing" class="upload-layout">
          <div class="upload-left">
            <div class="ledger-select-area">
              <div class="flex items-center gap-4">
                <span class="text-base font-medium text-gray-700">交易账户：</span>
                <el-tag size="large" type="primary">{{ selectedLedgerName }}（{{ ledgerTypeLabel }}）</el-tag>
                <el-button type="primary" link @click="currentStep = 0">更换账户</el-button>
              </div>
            </div>

            <div v-if="isStandardMode" class="template-download-section">
              <el-button type="primary" size="large" class="download-template-btn" :loading="downloading" @click="handleDownloadTemplate">
                <IconifyIconOffline icon="ep:download" class="mr-2" />
                下载{{ templateNameForAccount }}（CSV）
              </el-button>
              <p class="download-hint">
                按模板填写后上传，即可批量导入{{ accountType }}交易记录<br />
                模板包含：{{ templateFields }}
              </p>
            </div>

            <div class="import-mode-select">
              <span class="import-mode-label">导入格式：</span>
              <el-select v-model="selectedMode" size="large" style="width: 220px">
                <el-option v-for="mode in availableModes" :key="mode.value" :label="mode.label" :value="mode.value" />
              </el-select>
              <span class="import-mode-hint">选择与您的文件来源匹配的格式</span>
            </div>

            <div class="upload-area-wrapper">
              <el-upload
                ref="uploadRef"
                :accept="'.csv,.xls,.xlsx'"
                :before-upload="beforeUpload"
                :http-request="handleUpload"
                :show-file-list="false"
                drag
                :disabled="!selectedLedgerId || parsing"
                class="golden-upload"
              >
                <template #default>
                  <IconifyIconOffline icon="ep:upload-filled" class="upload-icon" :class="{ 'icon-active': isDragover }" />
                  <p class="upload-text">将文件拖到此处，或</p>
                  <el-button type="primary" size="default" class="upload-btn" :disabled="!selectedLedgerId || uploading" :loading="uploading" @click="handleUploadClick">
                    {{ uploading ? '正在上传...' : '点击上传' }}
                  </el-button>
                  <p class="upload-hint">{{ isStandardMode ? '使用标准模板格式的文件' : `直接上传${formatName}导出的文件` }}</p>
                  <p class="upload-format-info">支持 Excel、CSV 格式 ｜ 最大 5MB</p>
                </template>
              </el-upload>

              <div v-if="uploadError" class="upload-error">
                <IconifyIconOffline icon="ep:warning-filled" class="mr-1" /> {{ uploadError }}
                <div class="upload-error-detail">
                  请检查：
                  <template v-if="selectedMode === 'ths'">
                    1. 是否为同花顺客户端导出的原始文件<br />
                    2. 文件是否完整，没有被修改过<br />
                    3. 导出格式是否为"制表符分隔的文本文件"
                  </template>
                  <template v-else-if="selectedMode === 'tiantian_fund'">
                    1. 是否从天天基金网页完整复制了表格数据<br />
                    2. 确认日期、基金代码、业务类型、确认金额等关键列是否存在<br />
                    3. 文件编码是否为 UTF-8
                  </template>
                  <template v-else>
                    1. 是否为纯CSV格式（不是.xlsx直接改后缀）<br />
                    2. 表头是否与下载的模板完全一致<br />
                    3. 日期格式是否为 YYYY-MM-DD<br />
                    4. 股票代码/基金代码是否正确
                  </template>
                </div>
              </div>
            </div>
          </div>

          <div class="upload-right" v-if="formatGuides[selectedMode]">
            <div class="format-guide">
              <div class="format-guide-header">
                <IconifyIconOffline icon="ep:info-filled" class="format-guide-icon" />
                <span>{{ formatGuides[selectedMode].title }}</span>
              </div>
              <ol class="format-guide-list">
                <li v-for="(tip, index) in formatGuides[selectedMode].tips" :key="index">{{ tip }}</li>
              </ol>
            </div>
          </div>
        </div>

        <p style="text-align: center; margin-top: 24px; font-size: 13px; color: var(--text-tertiary);">
          上传后将进入预览页面，您可以修正错误后确认导入。如有问题，请参考帮助文档。
        </p>

        <el-dialog v-model="showCreateLedgerDialog" title="添加新账户" width="360px" :close-on-click-modal="false">
          <el-form label-position="top">
            <el-form-item label="账户名称" required>
              <el-input v-model="newLedgerName" placeholder="例如：华泰证券、招商银行储蓄卡" size="large" @keyup.enter="createLedger" />
            </el-form-item>
            <el-form-item label="默认配置目标">
              <el-select v-model="newLedgerAllocation" size="large">
                <el-option v-for="opt in allocationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <div class="flex justify-end gap-3">
              <el-button @click="showCreateLedgerDialog = false">取消</el-button>
              <el-button type="primary" @click="createLedger">确认添加</el-button>
            </div>
          </template>
        </el-dialog>
      </div>

      <!-- 步骤2：预览与修正 -->
      <div v-else-if="currentStep === 2" class="step3-container">
        <div class="step3-header">
          <el-button size="default" @click="currentStep = 1">返回上一步</el-button>
          <span class="header-ledger">导入账户：{{ selectedLedgerName }}</span>
          <div class="header-actions ml-auto flex items-center gap-3">
            <el-button size="default" @click="toggleAllocationPanel">
              <IconifyIconOffline icon="ep:setting" class="mr-1" />
              {{ showAllocationGroupPanel ? '收起配置' : '设置配置目标' }}
            </el-button>
          </div>
        </div>

        <div class="step3-body">
          <div class="step3-left" :class="{ collapsed: !showLeftPanel }">
            <div class="summary-panel">
              <div class="summary-cards">
                <div class="summary-card summary-card--success">
                  <div class="summary-card-header">
                    <span class="summary-card-title">
                      已校验 <el-badge :value="validRowsCount" :type="validRowsCount > 0 ? 'success' : 'info'" class="summary-badge" />
                    </span>
                  </div>
                  <div class="summary-card-body"><p>代码已匹配、字段完整、无重复，可直接导入</p></div>
                </div>
                <div v-if="duplicateCount > 0" class="summary-card summary-card--warning">
                  <div class="summary-card-header">
                    <span class="summary-card-title">重复项 <el-badge :value="duplicateCount" type="warning" class="summary-badge" /></span>
                  </div>
                </div>
                <div v-if="blockedCount > 0 || errorCount > 0" class="summary-card summary-card--danger">
                  <div class="summary-card-header">
                    <span class="summary-card-title">待确认 <el-badge :value="blockedCount + errorCount" type="danger" class="summary-badge" /></span>
                  </div>
                  <div class="summary-card-body">
                    <p v-if="errorCount > 0">· {{ errorCount }} 条解析错误</p>
                    <p>信息缺失（数量或价格为空）</p>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="(blockedCount + errorCount) > 0" class="batch-fix-bar">
              <el-button :type="showBatchFix ? '' : 'primary'" @click="toggleBatchFix" size="default">
                <IconifyIconOffline icon="ep:setting" class="mr-1" />
                {{ showBatchFix ? '收起批量修正' : '批量修正问题数据' }}
              </el-button>
              <span class="batch-fix-hint" v-if="!showBatchFix">{{ blockedCount + errorCount }} 条待处理</span>
            </div>

            <div v-if="showBatchFix && problemCategories.length > 0" class="batch-fix-panel">
              <div v-for="cat in problemCategories" :key="cat.key" class="batch-fix-group" :class="{ 'batch-fix-group--active': isCategoryActive(cat.key) }" @click="filterByCategory(cat.key)">
                <div class="batch-fix-card">
                  <div class="batch-fix-card-header">
                    <div class="batch-fix-info">
                      <span class="batch-fix-label">{{ cat.label }}</span>
                      <span class="batch-fix-desc">{{ getCategoryDesc(cat.key) }}</span>
                    </div>
                    <el-tag size="small" effect="dark" :type="getCategoryTagType(cat.key, cat.count)">{{ cat.count }} 条</el-tag>
                  </div>
                  <div class="batch-fix-actions" @click.stop>
                    <template v-if="cat.key === 'missingCode'">
                      <el-input v-model="batchCodeInput" placeholder="输入证券代码" size="small" class="batch-fix-input" />
                      <el-button type="primary" size="small" class="batch-fix-btn batch-fix-btn--primary" @click="batchFillCode(cat.rows, batchCodeInput)">应用到当前 {{ cat.count }} 条</el-button>
                    </template>
                    <template v-if="cat.key === 'mismatch'">
                      <el-tooltip content="以数量×价格为准修正金额" placement="top">
                        <el-button type="primary" size="small" class="batch-fix-btn batch-fix-btn--primary" @click="batchFixAmount(cat.rows)">修正金额</el-button>
                      </el-tooltip>
                    </template>
                    <template v-if="cat.key === 'missingQtyPrice'">
                      <el-button type="primary" size="small" class="batch-fix-btn batch-fix-btn--primary" @click="showFullTable = true; showProblemOnly = true">展开查看并手动编辑</el-button>
                    </template>
                    <el-button size="small" class="batch-fix-btn batch-fix-btn--secondary" @click="skipCategory(cat.rows)">跳过当前</el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="showAllocationGroupPanel" class="allocation-group-panel">
            <div class="allocation-group-header">
              <span class="font-weight-500">按产品类型设置配置目标</span>
              <div class="flex items-center gap-3">
                <el-button size="small" text @click="showAllocationGroupPanel = false">取消</el-button>
              </div>
            </div>
            <div class="allocation-group-item" v-if="selectedCount > 0">
              <div class="allocation-group-info">
                <span class="allocation-group-label">已选行批量设置</span>
                <el-tag size="small" type="primary">{{ selectedCount }} 条已选</el-tag>
              </div>
              <el-select model-value="" placeholder="选择配置目标" size="small" style="width: 140px" @change="(val: string) => batchSetAllocation(val)">
                <el-option v-for="opt in allocationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </div>
            <div class="allocation-group-list">
              <div v-for="group in currentAllocationGroups" :key="group.type || group.account" class="allocation-group-item">
                <div class="allocation-group-info">
                  <span class="allocation-group-label">{{ group.label }}</span>
                  <el-tag size="small" type="info">{{ group.count }} 条</el-tag>
                </div>
                <el-select :model-value="group.currentAllocation" size="small" style="width: 140px" @change="(val: string) => applyAllocationGroupSetting(group, val)">
                  <el-option v-for="opt in allocationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </div>
              <div v-if="currentAllocationGroups.length === 0" class="text-center text-gray-400 py-4">所有数据已手动设置配置目标，无需分组调整</div>
            </div>
          </div>

          <div class="step3-divider" @click="toggleLeftPanel" :title="showLeftPanel ? '收起侧边栏' : '展开数据摘要'">
            <IconifyIconOffline :icon="showLeftPanel ? 'ep:d-arrow-left' : 'ep:d-arrow-right'" class="divider-icon" />
            <span v-if="!showLeftPanel" class="divider-text">摘要</span>
          </div>

          <div class="step3-right">
            <div class="table-controls">
              <div class="flex items-center gap-4 flex-wrap">
                <el-select v-model="tableStatusFilter" placeholder="按状态筛选" size="small" style="width: 130px" clearable>
                  <el-option label="全部" value="" />
                  <el-option label="待补全" value="blocked" />
                  <el-option label="重复" value="duplicate" />
                  <el-option label="错误" value="error" />
                  <el-option label="正常" value="normal" />
                </el-select>
                <el-switch v-model="showProblemOnly" active-text="只看问题数据" inactive-text="全部数据" />
                <el-input v-model="tableFilterKeyword" placeholder="搜索代码或名称" size="small" style="width: 200px" clearable />
                <el-select v-model="tableTypeFilter" placeholder="按类型筛选" size="small" style="width: 140px" clearable multiple collapse-tags collapse-tags-tooltip>
                  <el-option v-for="(label, key) in typeLabels" :key="key" :label="label" :value="key" />
                </el-select>
              </div>
              <div class="flex items-center gap-2">
                <el-button v-if="duplicateCount > 0" size="small" :type="duplicatesHandled ? 'warning' : ''" @click="deselectAllDuplicates">
                  {{ duplicatesHandled ? '恢复查看重复行' : '取消显示重复行' }}
                </el-button>
                <el-button type="text" @click="showFullTable = !showFullTable">
                  <IconifyIconOffline :icon="showFullTable ? 'ep:arrow-up' : 'ep:arrow-down'" />
                  {{ showFullTable ? '收起列表' : '展开列表' }}
                </el-button>
              </div>
            </div>

            <div v-if="showFullTable && (duplicateCount > 0 || blockedCount > 0)" class="highlight-legend">
              <span class="legend-item"><span class="legend-color legend-color--duplicate"></span>黄色背景：已识别的重复数据，已自动跳过，可手动勾选保留</span>
              <span class="legend-item" v-if="blockedCount > 0"><span class="legend-color legend-color--blocked"></span>红色左边框：信息缺失，需补全数量或价格后可导入</span>
            </div>

            <div v-show="showFullTable" class="table-wrapper">
              <el-table :data="filteredPagedData" row-key="_rowKey" :tree-props="{ children: 'children', hasChildren: 'hasChildren' }" default-expand-all stripe size="default" :row-class-name="getRowClassName" :cell-class-name="getCellClassName" @selection-change="handleSelectionChange">
                <el-table-column width="80" fixed="left">
                  <template #header>
                    <el-checkbox v-model="isAllSelected" :indeterminate="isIndeterminate" @change="handleHeaderCheckboxChange" />
                  </template>
                  <template #default="{ row }">
                    <el-tooltip v-if="row.is_cash_transfer" content="资金划转暂不支持导入" placement="top">
                      <el-checkbox :model-value="false" disabled />
                    </el-tooltip>
                    <el-checkbox v-else :model-value="isRowSelected(row)" :disabled="row.is_duplicate || row.error || isRowBlocked(row)" @change="(val: boolean) => handleRowCheckboxChange(row, val)" />
                  </template>
                </el-table-column>
                <el-table-column v-for="col in tableColumns" :key="col.prop || col.type" v-bind="col">
                  <template v-if="col.slot === 'status'" #default="{ row }">
                    <el-tooltip v-if="row.is_duplicate" content="该交易已存在于系统中，默认跳过。如需强制导入，请手动勾选" placement="top">
                      <el-tag type="warning" size="small">重复</el-tag>
                    </el-tooltip>
                    <el-tag v-else-if="row.error" type="danger" size="small">错误</el-tag>
                    <el-tag v-else-if="isRowBlocked(row)" type="info" size="small">待补全</el-tag>
                    <el-tag v-else type="success" size="small">正常</el-tag>
                  </template>
                  <template v-else-if="col.slot === 'product'" #default="{ row }">
                    <div class="product-cell">
                      <span class="product-name">{{ row.name || row.symbol || '--' }}</span>
                      <div class="product-code-row">
                        <span class="product-code"># {{ row.symbol || '--' }}</span>
                        <el-tag v-if="row.display_type" size="small" :color="getFundTypeColor(row.display_type)" class="type-tag-inline">{{ row.display_type }}</el-tag>
                      </div>
                    </div>
                  </template>
                  <template v-else-if="col.slot === 'opType'" #default="{ row }">
                    <div class="op-type-cell">
                      <span class="op-type-label">{{ row.op_type_label || '--' }}</span>
                      <el-tag v-if="!row.is_merged && row.type !== 'fund'" :color="getTypeColor(row.type)" size="small" class="type-tag-inline">{{ typeLabels[row.type] || row.type || '未知' }}</el-tag>
                    </div>
                  </template>
                  <template v-else-if="col.slot === 'quantity'" #default="{ row }">
                    <el-popover :visible="row.isEditingQty" placement="bottom-start" :width="200" trigger="manual" :hide-after="0" :persistent="true" teleported>
                      <div class="flex flex-col gap-2" @mousedown.stop>
                        <div class="text-xs text-gray-500">{{ row.symbol }} {{ row.name }} - <span class="font-semibold">数量</span></div>
                        <el-input-number v-model="row.quantity" size="default" :precision="4" :min="0" class="w-full" controls-position="right" ref="inputRef" @vue:mounted="(el: any) => el?.input?.focus()" />
                        <div class="flex justify-end gap-2">
                          <el-button type="primary" size="small" @click.stop="finishEdit(row, 'quantity', true)">确认</el-button>
                          <el-button size="small" @click.stop="cancelEdit(row, 'quantity')">取消</el-button>
                        </div>
                      </div>
                      <template #reference>
                        <span class="cursor-pointer hover:text-blue-500 select-none" @click.stop="startEdit(row, 'quantity')" @mousedown.prevent>{{ row.quantity }}</span>
                      </template>
                    </el-popover>
                  </template>
                  <template v-else-if="col.slot === 'price'" #default="{ row }">
                    <el-popover :visible="row.isEditingPrice" placement="bottom-start" :width="200" trigger="manual" :hide-after="0" :persistent="true" teleported>
                      <div class="flex flex-col gap-2" @mousedown.stop>
                        <div class="text-xs text-gray-500">{{ row.symbol }} {{ row.name }} - <span class="font-semibold">价格</span></div>
                        <el-input-number v-model="row.price" size="default" :precision="4" :min="0" class="w-full" controls-position="right" ref="inputRef" @vue:mounted="(el: any) => el?.input?.focus()" />
                        <div class="flex justify-end gap-2">
                          <el-button type="primary" size="small" @click.stop="finishEdit(row, 'price', true)">确认</el-button>
                          <el-button size="small" @click.stop="cancelEdit(row, 'price')">取消</el-button>
                        </div>
                      </div>
                      <template #reference>
                        <span class="cursor-pointer hover:text-blue-500 select-none" @click.stop="startEdit(row, 'price')" @mousedown.prevent>{{ row.price }}</span>
                      </template>
                    </el-popover>
                  </template>
                  <template v-else-if="col.slot === 'allocation'" #default="{ row }">
                    <el-select v-model="row.allocation" size="small" :disabled="row.is_cash_transfer || row.is_duplicate || row.error" @change="onRowAllocationChange(row)">
                      <el-option v-for="opt in allocationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                    </el-select>
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
            </div>
          </div>
        </div>

        <div class="fixed-action-bar">
          <div class="action-content">
            <span class="selected-count">
              本次导入识别 {{ totalRows }} 条，已选中 <strong>{{ selectedCount }}</strong> 条有效数据
              <span v-if="(duplicateCount + blockedCount + errorCount) > 0">
                ，另有 {{ duplicateCount + blockedCount + errorCount }} 条待处理（{{ duplicateCount }}条重复 / {{ blockedCount }}条待补全
                <template v-if="errorCount > 0"> / {{ errorCount }}条错误</template>）
              </span>
            </span>
            <div class="flex gap-3">
              <el-button v-if="(duplicateCount + blockedCount + errorCount) > 0" @click="importNormalOnly" :loading="importing">仅导入校验通过的数据</el-button>
              <el-button type="primary" :disabled="selectedCount === 0" :loading="importing" @click="confirmImport" class="import-btn">确认导入 {{ selectedCount }} 条</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 步骤3：导入完成 -->
      <div v-else class="import-result">
        <template v-if="!nothingImported">
          <el-result icon="success" title="导入完成">
            <template #sub-title>
              <div class="result-summary">
                <div class="result-numbers">
                  <div class="number-item">
                    <span class="number-value" style="color: var(--color-success)">{{ importedCount }}</span>
                    <span class="number-label">笔导入成功</span>
                  </div>
                  <div class="number-divider" />
                  <div class="number-item">
                    <span class="number-value" style="color: var(--text-tertiary)">{{ skippedCount }}</span>
                    <span class="number-label">笔跳过</span>（重复 {{ duplicateCount }} 条 / 错误 {{ errorCount }} 条）
                  </div>
                </div>

                <div v-if="orphanCount > 0" class="mt-4">
                  <el-alert title="部分交易数据不完整" type="warning" :closable="false" show-icon>
                    <template #default>
                      <p>{{ orphanCount }} 笔交易因缺少对应持仓记录，已作为待处理数据保存。</p>
                      <p class="text-xs mt-1">这些交易不会影响当前资产计算，你可以在交易流水中手动关联持仓。</p>
                    </template>
                  </el-alert>
                </div>

                <div v-if="importErrors.length > 0" class="mt-4">
                  <el-alert :title="`导入过程中 ${importErrors.length} 条记录因以下原因被跳过`" type="warning" :closable="false" show-icon>
                    <template #default>
                      <div v-for="group in errorSummary" :key="group.reason" class="error-group">
                        <p class="error-reason">{{ group.reason }}（共 {{ group.count }} 条）</p>
                        <el-collapse v-if="group.items.length > 1" class="error-collapse">
                          <el-collapse-item :title="`涉及标的：${group.items.slice(0, 3).join('、')}${group.items.length > 3 ? ' 等' : ''}`">
                            <ul class="list-disc pl-4 text-xs">
                              <li v-for="item in group.items" :key="item">{{ item }}</li>
                            </ul>
                          </el-collapse-item>
                        </el-collapse>
                        <p v-else class="text-xs ml-4">{{ group.items[0] }}</p>
                      </div>
                    </template>
                  </el-alert>
                </div>

                <div v-if="showPriceUpdateTip" class="mt-4">
                  <el-alert title="建议" type="info" :closable="false" show-icon>
                    <template #default>
                      <p>你刚导入了交易记录，持仓数据已更新。</p>
                      <p class="text-xs mt-1">
                        建议现在去
                        <router-link to="/asset/investment/stocks" class="text-primary">检查持仓市价</router-link>
                        ，以确保资产计算准确。
                      </p>
                    </template>
                  </el-alert>
                </div>
              </div>
              <div class="flex gap-2 justify-center mt-6">
                <el-button type="primary" @click="goToTransactions" v-if="importedCount > 0 || orphanCount > 0">查看交易流水</el-button>
                <el-button @click="continueImport">继续导入</el-button>
              </div>
            </template>
          </el-result>
        </template>
        <template v-else>
          <el-result icon="info" title="导入处理完成">
            <template #sub-title>
              <p>本次无新增交易，共跳过 {{ skippedCount }} 条记录。</p>
              <div v-if="importErrors.length > 0" class="mt-4">
                <el-alert title="跳过原因" type="warning" :closable="false" show-icon>
                  <template #default>
                    <div v-for="group in errorSummary" :key="group.reason" class="error-group">
                      <p class="error-reason">{{ group.reason }}（共 {{ group.count }} 条）</p>
                      <el-collapse v-if="group.items.length > 1" class="error-collapse">
                        <el-collapse-item :title="`涉及标的：${group.items.slice(0, 3).join('、')}${group.items.length > 3 ? ' 等' : ''}`">
                          <ul class="list-disc pl-4 text-xs">
                            <li v-for="item in group.items" :key="item">{{ item }}</li>
                          </ul>
                        </el-collapse-item>
                      </el-collapse>
                      <p v-else class="text-xs ml-4">{{ group.items[0] }}</p>
                    </div>
                  </template>
                </el-alert>
              </div>
              <div class="flex gap-2 justify-center mt-6">
                <el-button type="primary" @click="reimport">重新导入</el-button>
                <el-button @click="goToImportGuide">查看导入规则</el-button>
              </div>
            </template>
          </el-result>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { parseFile, confirmImport as confirmImportApi } from '@/api/importer';
import type { UploadRequestOptions } from 'element-plus';
import { ref, onMounted, computed, reactive, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getLedgers, createLedger as createLedgerApi } from '@/api/ledger';
import type { LedgerItem } from '@/api/ledger';

defineOptions({ name: 'Inventory' });

const router = useRouter();

// ── 静态配置 ──
const allocationOptions = [
  { value: 'liquid', label: '活钱' },
  { value: 'stable', label: '稳健底仓' },
  { value: 'longterm', label: '长期增值' },
  { value: 'speculative', label: '高风险博弈' },
  { value: 'security', label: '保险保障' },
];

const fundTypeColorMap: Record<string, string> = {
  '股票型': 'var(--invest-stock)',
  '混合型': 'var(--invest-fund)',
  '债券型': 'var(--invest-bond)',
  '货币型': 'var(--tag-sage-green)',
  '指数型': 'var(--invest-etf)',
  'QDII': 'var(--tag-periwinkle)',
  'FOF': 'var(--tag-thistle)',
};

const typeLabels: Record<string, string> = {
  stock: '股票', fund: '基金', bond: '可转债', crypto: '虚拟货币',
  saving: '银行存款', cash: '现金', money_fund: '现金理财', reverse_repo: '逆回购', static: '其他',
};

const typeColorMap: Record<string, string> = {
  stock: 'var(--tag-muted-blue)', fund: 'var(--tag-rose-taupe)',
  bond: 'var(--tag-warm-sand)', etf: 'var(--tag-mint-green)',
  crypto: 'var(--tag-caramel)', saving: 'var(--tag-sage-green)',
  cash: 'var(--tag-periwinkle)', static: 'var(--tag-stone-gray)',
};

const ledgerTypeMap: Record<string, string> = {
  stock: '股票账户', fund: '基金账户', cash: '现金账户', general: '综合账户', family: '家庭账户',
};

const formatGuides = reactive({
  standard_stock: {
    title: '股票标准模板格式说明',
    tips: [
      '下载 CSV 模板填写数据，或直接上传同花顺等券商导出的 Excel/CSV 文件',
      '代码格式：A股 6 位数字，港股 5 位数字，美股字母代码',
      '日期格式：YYYY-MM-DD，如 2026-01-15',
      '业务类型：买入(BUY)、卖出(SELL)、现金分红(DIVIDEND_CASH)、送股(SPLIT)',
    ],
  },
  standard_fund: {
    title: '基金标准模板格式说明',
    tips: [
      '下载 CSV 模板填写数据，或直接上传基金平台导出的 CSV 文件',
      '代码为6位基金代码（如 014330）',
      '日期格式：YYYY-MM-DD，如 2023-06-01',
      '业务类型：申购(BUY)、赎回(SELL)、现金分红(DIVIDEND_CASH)、红利再投资(DIVIDEND_REINVEST)',
      '份额、净值为选填，手续费默认为0',
    ],
  },
  ths: {
    title: '同花顺交割单导出说明',
    tips: [
      '打开同花顺客户端 → 交易记录 → 历史交割单',
      '选择日期范围，点击"导出" → 选择"导出全部"',
      '导出格式选择"制表符分隔的文本文件"',
      '直接上传导出的文件即可，无需修改',
    ],
  },
  tiantian_fund: {
    title: '天天基金导入说明',
    tips: [
      '在天天基金网页版 → 我的 → 交易查询 → 对账单查询',
      '拖动选中历史交易明细表格 → Ctrl+C 复制',
      '打开基金标准模板 CSV 文件，粘贴数据覆盖示例行',
      '保存 CSV，在 ShowBuy 选择“天天基金”格式上传',
    ],
  },
});

// ── 步骤定义 ──
const steps = [
  { title: '选择导入账户' },
  { title: '上传交易文件' },
  { title: '预览与修正' },
  { title: '导入完成' },
];

// ── 核心状态 ──
const currentStep = ref(0);
const selectedMode = ref('standard');
const previewData = ref<any[]>([]);
const duplicateCount = ref(0);
const errorCount = ref(0);
const importedCount = ref(0);
const skippedCount = ref(0);
const orphanCount = ref(0);
const importing = ref(false);
const parsing = ref(false);
const uploading = ref(false);
const fileSize = ref('');
const editingRowKey = ref<string | null>(null);
const newLedgerAllocation = ref('longterm');
const showAllocationGroupPanel = ref(false);
const ledgers = ref<LedgerItem[]>([]);
const selectedLedgerId = ref<number | null>(null);
const showCreateLedgerDialog = ref(false);
const newLedgerName = ref('');
const ledgerTouched = ref(false);
const activeCategoryFilter = ref('');
const downloadLoading = ref(false);

// 分页与筛选
const currentPage = ref(1);
const pageSize = ref(50);
const totalRows = ref(0);
const selectedKeys = ref<Set<string>>(new Set());
const isAllSelected = ref(false);
const isIndeterminate = ref(false);
const showProblemOnly = ref(false);
const tableFilterKeyword = ref('');
const tableTypeFilter = ref<string[]>([]);
const tableStatusFilter = ref('');
const showFullTable = ref(true);
const showBatchFix = ref(false);
const batchCodeInput = ref('');
const showLeftPanel = ref(false);
const importErrors = ref<any[]>([]);
const duplicatesHandled = ref(false);
const uploadError = ref('');
const validRowsCount = ref(0);
const isDragover = ref(false);

// ── 计算属性 ──
const selectedLedgerName = computed(() => {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  return ledger?.name || '未选择';
});

const ledgerType = computed(() => {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  return ledger?.ledger_type || '';
});

const ledgerTypeLabel = computed(() => {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  return ledger ? (ledgerTypeMap[ledger.ledger_type] || '') : '';
});

const ledgerGroups = computed(() => {
  const groups: Record<string, { label: string; ledgers: LedgerItem[] }> = {};
  const order = ['stock', 'fund', 'cash', 'general', 'family'];
  for (const ledger of ledgers.value) {
    const type = ledger.ledger_type || 'general';
    if (!groups[type]) groups[type] = { label: ledgerTypeMap[type] || type, ledgers: [] };
    groups[type].ledgers.push(ledger);
  }
  return order.filter(o => groups[o]).map(o => groups[o]);
});

const availableModes = computed(() => {
  const allModes = [
    { label: '股票标准模板', value: 'standard_stock' },
    { label: '同花顺交割单', value: 'ths' },
    { label: '基金标准模板', value: 'standard_fund' },
    { label: '天天基金', value: 'tiantian_fund' },
  ];
  if (ledgerType.value === 'stock') return allModes.filter(m => m.value === 'standard_stock' || m.value === 'ths');
  if (ledgerType.value === 'fund' || ledgerType.value === 'cash') return allModes.filter(m => m.value === 'standard_fund' || m.value === 'tiantian_fund');
  return allModes;
});

const isStandardMode = computed(() => selectedMode.value === 'standard_stock' || selectedMode.value === 'standard_fund');

const templateNameForAccount = computed(() => selectedMode.value === 'standard_fund' ? '基金标准模板' : '股票标准模板');
const accountType = computed(() => selectedMode.value === 'standard_fund' ? '基金' : '股票');
const templateFields = computed(() => {
  if (selectedMode.value === 'standard_fund') return '确认日期、交易日期、基金代码、基金名称、业务类型、份额、金额、手续费、净值、账户名称';
  return '确认日期、交易日期、股票代码、股票名称、业务类型、数量(股)、成交均价、成交金额、手续费、账户名称';
});
const formatName = computed(() => {
  if (selectedMode.value === 'ths') return '同花顺';
  if (selectedMode.value === 'standard_fund') return '基金标准模板';
  if (selectedMode.value === 'tiantian_fund') return '天天基金';
  return '股票标准模板';
});

const isFundMode = computed(() => selectedMode.value === 'standard_fund' || selectedMode.value === 'tiantian_fund');

const tableColumns = computed(() => {
  if (isFundMode.value) {
    return [
      { prop: 'status', label: '状态', width: 70, slot: 'status', align: 'center' },
      { prop: 'product', label: '产品信息', width: 160, slot: 'product' },
      { prop: 'opType', label: '操作类型', width: 110, slot: 'opType' },
      { prop: 'trade_date', label: '日期', width: 100 },
      { prop: 'quantity', label: '份额', width: 90, align: 'right' },
      { prop: 'price', label: '净值', width: 90, align: 'right' },
      { prop: 'amount', label: '金额', width: 120, align: 'right' },
      { prop: 'fee', label: '手续费', width: 90, align: 'right' },
      { prop: 'allocation', label: '配置目标', width: 120, slot: 'allocation' },
      { prop: 'notes', label: '备注', minWidth: 120 },
    ];
  }
  return [
    { prop: 'status', label: '状态', width: 70, slot: 'status', align: 'center' },
    { prop: 'product', label: '产品信息', width: 160, slot: 'product' },
    { prop: 'opType', label: '操作类型', width: 110, slot: 'opType' },
    { prop: 'trade_date', label: '日期', width: 100 },
    { prop: 'quantity', label: '数量', width: 90, slot: 'quantity', align: 'right' },
    { prop: 'price', label: '单价', width: 90, slot: 'price', align: 'right' },
    { prop: 'amount', label: '交易金额', width: 120, align: 'right' },
    { prop: 'fee', label: '手续费', width: 90, align: 'right' },
    { prop: 'contract_id', label: '合同编号', width: 110 },
    { prop: 'net_amount', label: '发生金额', width: 120, align: 'right' },
    { prop: 'allocation', label: '配置目标', width: 120, slot: 'allocation' },
    { prop: 'notes', label: '备注', minWidth: 120 },
  ];
});

const blockedCount = computed(() => {
  return previewData.value.filter(row => isRowBlocked(row) && !row.is_duplicate && !row.error && !row.is_cash_transfer).length;
});

const selectedCount = computed(() => selectedKeys.value.size);

const nothingImported = computed(() => importedCount.value === 0 && orphanCount.value === 0 && importErrors.value.length > 0);

const showPriceUpdateTip = computed(() => {
  if (importedCount.value === 0) return false;
  return previewData.value.some(row => {
    if (!selectedKeys.value.has(row._rowKey)) return false;
    return ['stock', 'fund', 'etf', 'bond'].includes(row.type);
  });
});

const allocationGroupsByType = computed(() => {
  const groups: Record<string, { label: string; count: number; currentAllocation: string }> = {};
  previewData.value.forEach(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer || isRowBlocked(row) || row._allocationManual) return;
    const type = row.type || 'unknown';
    if (!groups[type]) groups[type] = { label: typeLabels[type] || type, count: 0, currentAllocation: row.allocation || 'longterm' };
    groups[type].count++;
  });
  return Object.entries(groups).map(([type, data]) => ({ type, ...data }));
});

const currentAllocationGroups = computed(() => allocationGroupsByType.value);

const problemCategories = computed(() => {
  const cats = [
    { key: 'missingCode', label: '代码未匹配', count: 0, rows: [] as any[] },
    { key: 'missingQtyPrice', label: '数量或价格缺失', count: 0, rows: [] as any[] },
    { key: 'mismatch', label: '数据不一致', count: 0, rows: [] as any[] },
  ];
  previewData.value.forEach(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer) return;
    const qty = Number(row.quantity), prc = Number(row.price), amt = Number(row.amount);
    if (!row.symbol || row.symbol === 'UNKNOWN') { cats[0].rows.push(row); cats[0].count++; }
    else if (isRowBlocked(row)) { cats[1].rows.push(row); cats[1].count++; }
    else if (!isNaN(qty) && qty > 0 && !isNaN(prc) && prc > 0 && !isNaN(amt) && Math.abs(qty * prc - amt) > 0.01) { cats[2].rows.push(row); cats[2].count++; }
  });
  return cats.filter(c => c.count > 0);
});

const errorSummary = computed(() => {
  const groups: Record<string, { count: number; items: string[] }> = {};
  importErrors.value.forEach(err => {
    const reason = err.error || '未知错误';
    const name = err.name || err.symbol || '--';
    if (!groups[reason]) groups[reason] = { count: 0, items: [] };
    groups[reason].count++;
    groups[reason].items.push(name);
  });
  return Object.entries(groups).map(([reason, data]) => ({ reason, ...data }));
});

const filteredPagedData = computed(() => {
  let list = previewData.value;
  if (tableStatusFilter.value === 'blocked') list = list.filter(row => isRowBlocked(row) && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  else if (tableStatusFilter.value === 'duplicate') list = list.filter(row => row.is_duplicate);
  else if (tableStatusFilter.value === 'error') list = list.filter(row => row.error);
  else if (tableStatusFilter.value === 'normal') list = list.filter(row => !row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer);

  if (activeCategoryFilter.value === 'missingCode') list = list.filter(row => (!row.symbol || row.symbol === 'UNKNOWN') && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  else if (activeCategoryFilter.value === 'mismatch') list = list.filter(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer) return false;
    const qty = Number(row.quantity), prc = Number(row.price), amt = Number(row.amount);
    return !isNaN(qty) && qty > 0 && !isNaN(prc) && prc > 0 && !isNaN(amt) && Math.abs(qty * prc - amt) > 0.01;
  });

  if (showProblemOnly.value) list = list.filter(row => {
    if (row.is_duplicate && row._duplicateHandled) return false;
    return isRowBlocked(row) || row.error || row.is_duplicate || row.isEditingQty || row.isEditingPrice;
  });
  if (tableFilterKeyword.value) {
    const kw = tableFilterKeyword.value.toLowerCase();
    list = list.filter(row => String(row.symbol).toLowerCase().includes(kw) || String(row.name).toLowerCase().includes(kw));
  }
  if (tableTypeFilter.value.length > 0) list = list.filter(row => tableTypeFilter.value.includes(row.type));

  const mergedList: any[] = [];
  const processedGroupIds = new Set<string>();
  for (const row of list) {
    const groupId = row.link_group_id;
    if (groupId && !processedGroupIds.has(groupId)) {
      const groupRows = list.filter(r => r.link_group_id === groupId);
      if (groupRows.length === 2) {
        const interestRow = groupRows.find(r => r.op_type === 'dividend') || groupRows[0];
        const taxRow = groupRows.find(r => r.op_type === 'tax') || groupRows[1];
        const netAmount = (interestRow.amount || 0) + (taxRow.amount || 0);
        const parentKey = `merged_${interestRow._rowKey}`;
        const detailRows = groupRows.map(r => ({ ...r }));
        mergedList.push({
          ...interestRow, _rowKey: parentKey, amount: netAmount, net_amount: netAmount,
          is_merged: true, children: detailRows,
          notes: `税前${interestRow.amount?.toFixed(2)}元，扣税${Math.abs(taxRow.amount || 0).toFixed(2)}元，实收${netAmount.toFixed(2)}元`,
          op_type_label: '利息收入',
        });
        processedGroupIds.add(groupId);
      } else {
        groupRows.forEach(r => mergedList.push(r));
        processedGroupIds.add(groupId);
      }
    } else if (!groupId) mergedList.push(row);
  }
  const start = (currentPage.value - 1) * pageSize.value;
  return mergedList.slice(start, start + pageSize.value);
});

const filteredTotal = computed(() => {
  let list = previewData.value;
  if (tableStatusFilter.value === 'blocked') list = list.filter(row => isRowBlocked(row) && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  else if (tableStatusFilter.value === 'duplicate') list = list.filter(row => row.is_duplicate);
  else if (tableStatusFilter.value === 'error') list = list.filter(row => row.error);
  else if (tableStatusFilter.value === 'normal') list = list.filter(row => !row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer);

  if (activeCategoryFilter.value === 'missingCode') list = list.filter(row => (!row.symbol || row.symbol === 'UNKNOWN') && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  else if (activeCategoryFilter.value === 'mismatch') list = list.filter(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer) return false;
    const qty = Number(row.quantity), prc = Number(row.price), amt = Number(row.amount);
    return !isNaN(qty) && qty > 0 && !isNaN(prc) && prc > 0 && !isNaN(amt) && Math.abs(qty * prc - amt) > 0.01;
  });
  if (showProblemOnly.value) list = list.filter(row => {
    if (row.is_duplicate && row._duplicateHandled) return false;
    return isRowBlocked(row) || row.error || row.is_duplicate || row.isEditingQty || row.isEditingPrice;
  });
  if (tableFilterKeyword.value) {
    const kw = tableFilterKeyword.value.toLowerCase();
    list = list.filter(row => String(row.symbol).toLowerCase().includes(kw) || String(row.name).toLowerCase().includes(kw));
  }
  if (tableTypeFilter.value.length > 0) list = list.filter(row => tableTypeFilter.value.includes(row.type));

  const mergedList: any[] = [];
  const processedGroupIds = new Set<string>();
  for (const row of list) {
    const groupId = row.link_group_id;
    if (groupId && !processedGroupIds.has(groupId)) {
      const groupRows = list.filter(r => r.link_group_id === groupId);
      if (groupRows.length === 2) { mergedList.push(groupRows[0]); processedGroupIds.add(groupId); }
      else { groupRows.forEach(r => mergedList.push(r)); processedGroupIds.add(groupId); }
    } else if (!groupId) mergedList.push(row);
  }
  return mergedList.length;
});

// ── 辅助函数 ──
function getTemplateKeyForLedger(ledger: LedgerItem | null): string {
  if (!ledger) return '';
  switch (ledger.ledger_type) {
    case 'stock': return 'standard_stock';
    case 'fund': case 'cash': return 'standard_fund';
    default: return '';
  }
}

const lockedTemplateKey = computed(() => getTemplateKeyForLedger(ledgers.value.find(l => l.id === selectedLedgerId.value) || null));

function isRowBlocked(row: any): boolean {
  if (row.is_cash_transfer || row.error || row.is_duplicate) return false;
  if (row.op_type === 'tax' || row.op_type === 'dividend' || row.op_type === 'dividend_cash' || row.op_type === 'dividend_reinvest' || row.op_type === 'split') return false;
  if (row.type === 'money_fund' || row.type === 'reverse_repo') return false;
  const qty = Number(row.quantity), prc = Number(row.price);
  return (isNaN(qty) || qty <= 0) || (isNaN(prc) || prc <= 0);
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function getFundTypeColor(typeName: string): string {
  return fundTypeColorMap[typeName] || 'var(--tag-stone-gray)';
}

function getTypeColor(type: string): string {
  return typeColorMap[type] || 'var(--tag-stone-gray)';
}

function addRowKeys(data: any[]) {
  return data.map((item, idx) => ({ ...item, _rowKey: `row_${idx}` }));
}

function isRowSelected(row: any): boolean {
  return selectedKeys.value.has(row._rowKey);
}

function recalcValidRowsCount() {
  validRowsCount.value = previewData.value.filter(row => !row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer).length;
}

function updateSelectAllState() {
  const totalValid = validRowsCount.value;
  const current = selectedKeys.value.size;
  if (current === 0) { isAllSelected.value = false; isIndeterminate.value = false; }
  else if (current >= totalValid) { isAllSelected.value = true; isIndeterminate.value = false; }
  else { isAllSelected.value = false; isIndeterminate.value = true; }
}

function clearImportState() {
  previewData.value = [];
  selectedKeys.value = new Set();
  duplicateCount.value = 0;
  errorCount.value = 0;
  orphanCount.value = 0;
  isAllSelected.value = false;
  isIndeterminate.value = false;
  importErrors.value = [];
  validRowsCount.value = 0;
  showFullTable.value = true;
  showBatchFix.value = false;
  tableFilterKeyword.value = '';
  tableTypeFilter.value = [];
  tableStatusFilter.value = '';
  duplicatesHandled.value = false;
  uploadError.value = '';
  parsing.value = false;
}

// ── 流程控制 ──
function onAccountSelected(ledgerId: number) {
  const ledger = ledgers.value.find(l => l.id === ledgerId);
  if (!ledger) return;
  const templateKey = getTemplateKeyForLedger(ledger);
  selectedMode.value = templateKey || 'standard_fund';
  currentStep.value = 1;
}

function handleDownloadTemplate() {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  if (!ledger) return;
  const key = getTemplateKeyForLedger(ledger);
  const urlMap: Record<string, string> = { standard_fund: '/api/importers/template/fund', standard_stock: '/api/importers/template/stock' };
  const url = urlMap[key] || '/api/importers/template/standard';
  downloadLoading.value = true;
  window.open(url);
  setTimeout(() => downloadLoading.value = false, 1500);
}

function handleUploadClick() {
  if (!selectedLedgerId.value) {
    ElMessage.warning('请先选择交易所属账户');
    const el = document.querySelector('.ledger-select-area .el-select');
    if (el) {
      el.classList.add('ledger-select-flash');
      setTimeout(() => el.classList.remove('ledger-select-flash'), 600);
    }
    ledgerTouched.value = true;
  }
}

function beforeUpload(file: File) {
  if (!selectedLedgerId.value) {
    ElMessage.warning('请先选择交易所属账户');
    return false;
  }
  const allowedExtensions = ['.csv', '.xls', '.xlsx'];
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (!allowedExtensions.includes(ext)) { ElMessage.error('仅支持 CSV、Excel 文件'); return false; }
  if (file.size > 5 * 1024 * 1024) { ElMessage.error('文件大小不能超过5MB'); return false; }
  fileSize.value = formatFileSize(file.size);
  uploadError.value = '';
  return true;
}

async function handleUpload(options: UploadRequestOptions) {
  const file = options.file as File;
  if (!selectedLedgerId.value) return ElMessage.warning('请先选择一个账户');

  parsing.value = true;
  uploadError.value = '';
  await new Promise(resolve => setTimeout(resolve, 50));

  try {
    const res = await parseFile(file, selectedMode.value, selectedLedgerId.value);
    const rawData = (res as any).data ?? [];
    previewData.value = addRowKeys(rawData);
    totalRows.value = previewData.value.length;
    duplicateCount.value = (res as any).duplicate_count ?? 0;
    errorCount.value = (res as any).error_count ?? 0;

    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    const defaultAlloc = ledger?.default_allocation || 'longterm';
    previewData.value.forEach(row => {
      row.account_name = row.account_name && row.account_name !== '默认证券账户' ? row.account_name : (ledger?.name || '');
      if (row.allocation == null) row.allocation = defaultAlloc;
      if (!isRowBlocked(row) && !row.is_cash_transfer && !row.error && !row.is_duplicate) {
        const qty = parseFloat(row.quantity), prc = parseFloat(row.price), amt = parseFloat(row.amount);
        if (!isNaN(qty) && qty > 0 && (isNaN(prc) || prc <= 0) && !isNaN(amt)) {
          row.price = parseFloat((amt / qty).toFixed(4));
          row.smartFilled = true;
        }
      }
    });

    previewData.value = [...previewData.value];
    recalcValidRowsCount();
    selectAllValid();
    showFullTable.value = true;

    const warning = (res as any).compatibility_warning;
    if (warning) {
      await ElMessageBox.confirm(warning, '文件格式提醒', { confirmButtonText: '继续导入', cancelButtonText: '返回重选', type: 'warning' })
        .then(() => currentStep.value = 2)
        .catch(() => { parsing.value = false; return; });
    } else {
      ElMessage.success(`解析完成，共识别 ${totalRows.value} 条记录`);
      currentStep.value = 2;
    }
    options.onSuccess(res);
  } catch (e: any) {
    uploadError.value = e?.response?.data?.message || '文件解析失败';
    options.onError(e);
  } finally {
    parsing.value = false;
  }
}

async function confirmImport() {
  if (!selectedLedgerId.value) return ElMessage.warning('请先在第二步选择导入账户');

  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  if (!ledger) return ElMessage.error('所选账户无效，请重新选择');

  saveAllEditingRows();

  previewData.value.forEach(row => {
    if (!row._allocationManual) row.allocation = row.allocation || ledger.default_allocation || 'longterm';
    row.account_name = ledger.name;
  });

  const rowsToImport = previewData.value.filter(row =>
    selectedKeys.value.has(row._rowKey) && !row.is_duplicate && !row.error && !row.is_cash_transfer && !isRowBlocked(row)
  );
  if (rowsToImport.length === 0) return ElMessage.warning('没有可导入的有效记录');

  importing.value = true;
  try {
    const res = await confirmImportApi(rowsToImport);
    const result = (res as any).data ?? {};
    importedCount.value = result.imported ?? 0;
    skippedCount.value = result.skipped ?? 0;
    orphanCount.value = result.orphan_count ?? 0;
    importErrors.value = result.errors ?? [];
    currentStep.value = 3;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '导入失败');
  } finally {
    importing.value = false;
  }
}

async function importNormalOnly() {
  clearAllSelection();
  selectAllValid();
  await confirmImport();
}

function resetImport() {
  const savedLedgerId = selectedLedgerId.value;
  const savedMode = selectedMode.value;
  clearImportState();
  selectedLedgerId.value = savedLedgerId;
  selectedMode.value = savedMode;
  currentStep.value = 0;
}

function continueImport() {
  const savedLedgerId = selectedLedgerId.value;
  const savedMode = selectedMode.value;
  clearImportState();
  selectedLedgerId.value = savedLedgerId;
  selectedMode.value = savedMode;
  currentStep.value = 1;
}

function reimport() { resetImport(); }

// ── 选择与勾选 ──
function handleHeaderCheckboxChange(checked: boolean) { checked ? selectAllValid() : clearAllSelection(); }

function selectAllValid() {
  const newKeys = new Set<string>();
  previewData.value.forEach(row => {
    if (!row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer) newKeys.add(row._rowKey);
  });
  selectedKeys.value = newKeys;
  isAllSelected.value = true; isIndeterminate.value = false;
}

function clearAllSelection() { selectedKeys.value = new Set(); isAllSelected.value = false; isIndeterminate.value = false; }

function handleRowCheckboxChange(row: any, checked: boolean) {
  if (checked) selectedKeys.value.add(row._rowKey); else selectedKeys.value.delete(row._rowKey);
  selectedKeys.value = new Set(selectedKeys.value);
  updateSelectAllState();
}

// ── 批量修正 ──
async function batchFillCode(rows: any[], code: string) {
  if (!code.trim()) return ElMessage.warning('请输入有效的证券代码');
  rows.forEach(r => r.symbol = code.trim());
  recalcValidRowsCount(); updateSelectAllState();
  await nextTick(); previewData.value = [...previewData.value];
  ElMessage.success(`已为 ${rows.length} 条记录设置代码「${code}」`);
}

async function batchFixAmount(rows: any[]) {
  rows.forEach(r => { const qty = Number(r.quantity), prc = Number(r.price); if (!isNaN(qty) && !isNaN(prc)) r.amount = parseFloat((qty * prc).toFixed(2)); });
  recalcValidRowsCount(); updateSelectAllState();
  await nextTick(); previewData.value = [...previewData.value];
  ElMessage.success(`已修正 ${rows.length} 条记录的金额`);
}

async function skipCategory(rows: any[]) {
  rows.forEach(row => selectedKeys.value.delete(row._rowKey));
  selectedKeys.value = new Set(selectedKeys.value);
  updateSelectAllState();
  await nextTick(); previewData.value = [...previewData.value];
  ElMessage.success(`已跳过 ${rows.length} 条记录`);
}

function deselectAllDuplicates() {
  if (duplicatesHandled.value) {
    // 恢复全部重复行
    previewData.value.forEach(row => { if (row.is_duplicate) row._duplicateHandled = false; });
    duplicatesHandled.value = false;
  } else {
    // 取消显示重复行
    previewData.value.forEach(row => {
      if (row.is_duplicate) {
        row._duplicateHandled = true;
        selectedKeys.value.delete(row._rowKey);
      }
    });
    selectedKeys.value = new Set(selectedKeys.value);
    duplicatesHandled.value = true;
  }
  // 关键：触发 previewData 的响应式更新
  previewData.value = [...previewData.value];
  recalcValidRowsCount();
  updateSelectAllState();
  ElMessage.success(duplicatesHandled.value ? `已取消 ${duplicateCount.value} 条重复数据的展示` : '已恢复全部重复数据');
}

function filterByCategory(key: string) {
  showFullTable.value = true; showProblemOnly.value = false; tableStatusFilter.value = '';
  if (key === 'missingCode') activeCategoryFilter.value = 'missingCode';
  else if (key === 'missingQtyPrice') tableStatusFilter.value = 'blocked';
  else if (key === 'mismatch') activeCategoryFilter.value = 'mismatch';
}

function batchSetAllocation(target: string) {
  let applied = 0;
  previewData.value.forEach(row => {
    if (selectedKeys.value.has(row._rowKey) && !row.is_cash_transfer && !row.is_duplicate && !row.error) {
      row.allocation = target; row._allocationManual = true; applied++;
    }
  });
  previewData.value = [...previewData.value];
  ElMessage.success(applied > 0 ? `已将 ${applied} 条已选数据的配置目标设为「${allocationOptions.find(o => o.value === target)?.label}」` : '没有可设置的数据');
}

function applyAllocationGroupSetting(group: any, allocation: string) {
  previewData.value.forEach(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer || isRowBlocked(row)) return;
    if (row.type === group.type) { row.allocation = allocation; row._allocationManual = true; }
  });
  previewData.value = [...previewData.value];
  ElMessage.success(`已将「${group.label}」的配置目标设为「${allocationOptions.find(o => o.value === allocation)?.label}」`);
}

function onRowAllocationChange(row: any) { row._allocationManual = true; }

function toggleAllocationPanel() {
  showAllocationGroupPanel.value = !showAllocationGroupPanel.value;
  showBatchFix.value = false;
  showLeftPanel.value = true;
}

function toggleBatchFix() {
  showBatchFix.value = !showBatchFix.value;
  showAllocationGroupPanel.value = false;
  showLeftPanel.value = true;
}

function toggleLeftPanel() {
  showLeftPanel.value = !showLeftPanel.value;
  showBatchFix.value = false;
}

// ── 行编辑 ──
function startEdit(row: any, field: string) {
  if (editingRowKey.value && editingRowKey.value !== row._rowKey) {
    saveAllEditingRows();
    closeAllEditing();
  }
  row._oldValue = row[field];
  if (field === 'quantity') { row.isEditingQty = true; row.isEditingPrice = false; }
  else if (field === 'price') { row.isEditingPrice = true; row.isEditingQty = false; }
  editingRowKey.value = row._rowKey;
  previewData.value = [...previewData.value];  // 新增
}

function finishEdit(row: any, field: string, save: boolean = true) {
  const wasBlocked = isRowBlocked(row);
  if (!save) row[field] = row._oldValue; else smartFill(row, field);
  delete row._oldValue;
  if (field === 'quantity') row.isEditingQty = false; else row.isEditingPrice = false;
  editingRowKey.value = null;

  const nowBlocked = isRowBlocked(row);
  if (wasBlocked && !nowBlocked) {
    selectedKeys.value.add(row._rowKey); selectedKeys.value = new Set(selectedKeys.value);
    if (showProblemOnly.value) { showProblemOnly.value = false; ElMessage.success('数据已修正，已自动切换为全部数据视图'); }
    else ElMessage.success('数据已自动勾选');
  } else if (!wasBlocked && nowBlocked) { selectedKeys.value.delete(row._rowKey); selectedKeys.value = new Set(selectedKeys.value); }
  previewData.value = [...previewData.value];
  recalcValidRowsCount();
  updateSelectAllState();
}

function cancelEdit(row: any, field: string) { finishEdit(row, field, false); }

function smartFill(row: any, field: string) {
  const qty = parseFloat(row.quantity), prc = parseFloat(row.price), amt = parseFloat(row.amount);
  if (field === 'quantity' && isNaN(qty) && !isNaN(prc) && !isNaN(amt)) { row.quantity = parseFloat((amt / prc).toFixed(4)); row.smartFilled = true; }
  else if (field === 'price' && isNaN(prc) && !isNaN(qty) && !isNaN(amt)) { row.price = parseFloat((amt / qty).toFixed(4)); row.smartFilled = true; }
}

function saveAllEditingRows() {
  previewData.value.forEach(row => {
    if (row.isEditingQty) finishEdit(row, 'quantity', true);
    if (row.isEditingPrice) finishEdit(row, 'price', true);
  });
}

function closeAllEditing() {
  previewData.value.forEach(row => {
    if (row.isEditingQty) { row.isEditingQty = false; delete row._oldValue; }
    if (row.isEditingPrice) { row.isEditingPrice = false; delete row._oldValue; }
  });
  editingRowKey.value = null;
  previewData.value = [...previewData.value];  // 新增
}

function getRowClassName({ row }: { row: any }) {
  if (row.is_duplicate) return 'row-duplicate';
  if (row.error || isRowBlocked(row)) return 'row-blocked';
  return '';
}

function getCellClassName({ row, column }: { row: any; column: any }) {
  const prop = column.property;
  if (prop === 'quantity' && isRowBlocked(row) && !row.is_duplicate && !row.error) return 'cell-blocked';
  if (prop === 'price' && isRowBlocked(row) && !row.is_duplicate && !row.error) return 'cell-blocked';
  if (prop === 'fee' && (isNaN(parseFloat(row.fee)) || row.fee === null || row.fee === undefined)) return 'cell-missing';
  return '';
}

function getCategoryDesc(key: string): string {
  const map: Record<string, string> = { missingCode: '系统无法识别以下证券代码', missingQtyPrice: '数量或价格缺失', mismatch: '金额与数量×价格不符' };
  return map[key] || '';
}

function getCategoryTagType(key: string, count: number): 'danger' | 'warning' | 'success' | 'info' {
  if (count > 200) return 'danger'; if (count > 50) return 'warning'; if (count > 10) return 'info'; return 'success';
}

function isCategoryActive(key: string): boolean {
  if (key === 'missingCode') return activeCategoryFilter.value === 'missingCode';
  if (key === 'missingQtyPrice') return tableStatusFilter.value === 'blocked';
  if (key === 'mismatch') return activeCategoryFilter.value === 'mismatch';
  return false;
}

// ── 导航 ──
function goToTransactions() { router.push('/transactions'); }
function goToManualEntry() { router.push('/asset/inventory/investment/manual'); }
function goToLiabilityForm() { router.push('/asset/asset-entry'); }
function goToImportGuide() { ElMessage.info('当前支持买入、卖出、分红操作类型。其他类型暂不支持。'); }

// ── 数据获取 ──
async function fetchLedgers() {
  try { const res = await getLedgers(); ledgers.value = (res as any).data ?? []; } catch (e) { console.error(e); }
}

async function createLedger() {
  const name = newLedgerName.value.trim();
  if (!name) return;
  try {
    const res = await createLedgerApi({ name, default_allocation: newLedgerAllocation.value });
    await fetchLedgers();
    const newId = (res as any).data?.id;
    if (newId) selectedLedgerId.value = newId;
    showCreateLedgerDialog.value = false;
    newLedgerName.value = '';
    newLedgerAllocation.value = 'longterm';
    ElMessage.success(`已添加账户「${name}」`);
  } catch (e: any) { ElMessage.error(e?.response?.data?.message || '添加失败'); }
}

function handleSizeChange(val: number) { pageSize.value = val; currentPage.value = 1; }
function handlePageChange(val: number) { currentPage.value = val; }
function handleSelectionChange() {}

onMounted(async () => { await fetchLedgers(); });
</script>

<style scoped>
.el-button--large {
  height: 40px;
}

.download-template-btn,
.upload-btn {
  height: 40px;
}

.el-message--error {
  --el-message-text-color: var(--color-danger);
}

.text-error {
  color: var(--color-danger);
}

:deep(.el-step__head.is-finish) {
  cursor: pointer;
}

:deep(.el-step__title.is-finish) {
  cursor: pointer;
}

/* 步骤0 - 账户选择 */
.account-select-area {
  max-width: 520px;
  margin: 0 auto;
  padding: 24px 0;
  text-align: center;
}
.account-select {
  width: 100%;
}
.ledger-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.account-hint {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.import-mode-group {
  margin-bottom: 32px;
}

.import-group-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 16px;
  padding-left: 4px;
  border-left: 3px solid var(--color-primary);
}

.mode-card {
  width: 240px;
  cursor: pointer;
  text-align: center;
  padding: 32px 24px;
  border-radius: 16px;
  border: 2px solid var(--border-default);
  background: var(--bg-card);
  transition: all 0.3s ease;
}

.mode-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
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
  color: var(--text-primary);
}

.mode-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.5;
}

.import-mode-cards {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-top: 32px;
}

/* 步骤1 - 上传页面 */
.upload-step {
  padding: 0;
  min-height: 380px;
}

.upload-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  max-width: 1100px;
  margin: 0 auto;
}

.upload-left {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.upload-right {
  width: 340px;
  flex-shrink: 0;
  margin-top: 120px;
}

.ledger-select-area {
  margin-bottom: 16px;
}

.ledger-select-area :deep(.el-form-item__content) {
  display: block !important;
}

.template-download-section {
  margin: 0 0 16px 0;
  text-align: left;
}

.download-template-btn,
.upload-btn {
  height: 40px;
  border-radius: 8px;
  font-size: 14px;
  padding: 0 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.download-hint {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  text-align: left;
  max-width: 700px;
}

.import-mode-select {
  margin: 0 0 20px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.import-mode-label {
  font-size: 14px;
  color: var(--text-secondary);
}
.import-mode-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.upload-area-wrapper {
  flex: 1;
}

.golden-upload {
  width: 100%;
  height: 300px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  border: 2px dashed #888;
  border-radius: 14px;
  background: #f5f7fa;
  transition: all 0.3s;
  padding: 32px;
}
.golden-upload:hover {
  border-color: var(--color-primary);
}
.golden-upload.is-dragover {
  border: 2px solid var(--color-primary) !important;
  background: var(--color-primary-10) !important;
}
.golden-upload.is-dragover .upload-icon {
  transform: scale(1.1);
  color: var(--color-primary);
}

.upload-icon {
  font-size: 64px;
  color: var(--color-primary);
  margin-bottom: 16px;
  transition: color 0.2s, transform 0.2s;
}
.upload-text {
  font-size: 16px;
  color: var(--text-primary);
  margin: 0 0 16px;
  font-weight: 500;
}
.upload-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 12px 0 0 0;
}
.upload-format-info {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 6px;
}
.upload-btn:hover {
  opacity: 0.9;
}
.upload-btn:active {
  transform: scale(0.98);
}

.upload-error {
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger-30);
  border-radius: 6px;
  color: var(--color-danger);
  font-size: 14px;
  text-align: center;
}
.upload-error-detail {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  text-align: left;
}

.parsing-status {
  text-align: center;
  max-width: 680px;
  width: 100%;
  margin: 0 auto;
}

.loading-icon {
  font-size: 16px;
  margin-right: 4px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.format-guide {
  margin-top: 0;
  padding: 16px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid var(--border-default);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}
.format-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
  margin-bottom: 12px;
}
.format-guide-icon {
  color: var(--color-primary);
  font-size: 18px;
}
.format-guide-list {
  list-style: none;
  padding-left: 0;
  margin: 0;
  counter-reset: step-counter;
}
.format-guide-list li {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 8px;
  display: flex;
  align-items: baseline;
  counter-increment: step-counter;
}
.format-guide-list li::before {
  content: counter(step-counter) ".";
  color: var(--color-primary);
  font-weight: 600;
  margin-right: 8px;
  min-width: 18px;
  flex-shrink: 0;
}

/* 步骤2 - 预览修正 */
.step3-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 160px);
  overflow: hidden;
  margin-top: 16px;
}
.step3-header {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.header-ledger {
  margin-left: 16px;
  font-weight: 500;
  color: var(--text-secondary);
}
.step3-body {
  flex: 1;
  display: flex;
  gap: 0;
  overflow: hidden;
  min-height: 0;
}
.step3-left {
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
  padding-right: 12px;
  border-right: 1px solid var(--border-default);
  transition: width 0.25s ease;
}
.step3-left.collapsed {
  width: 0;
  padding-right: 0;
  border-right: none;
  overflow: hidden;
}
.step3-divider {
  width: 32px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  background: var(--bg-muted);
  border-radius: 4px;
  margin: 0 4px;
  transition: background 0.2s;
}
.step3-divider:hover {
  background: var(--color-primary-20);
}
.divider-icon {
  font-size: 16px;
  color: var(--text-tertiary);
  transition: color 0.2s;
}
.step3-divider:hover .divider-icon {
  color: var(--color-primary);
}
.divider-text {
  font-size: 11px;
  color: var(--text-tertiary);
  transition: color 0.2s;
}
.step3-divider:hover .divider-text {
  color: var(--color-primary);
}
.step3-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  padding-left: 12px;
}

.summary-panel {
  flex-shrink: 0;
  margin-bottom: 16px;
}
.summary-cards {
  display: flex;
  gap: 16px;
}
.summary-card {
  flex: 1;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border-default);
  background: var(--bg-card);
}
.summary-card--success {
  border-left: 4px solid var(--color-success);
}
.summary-card--warning {
  border-left: 4px solid var(--color-warning);
}
.summary-card--danger {
  border-left: 4px solid var(--color-danger);
}
.summary-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.summary-card-title {
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
}
.summary-card-body p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}
.summary-badge {
  margin-left: 8px;
  vertical-align: middle;
}

.batch-fix-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
  padding: 8px 0;
  flex-shrink: 0;
}
.batch-fix-hint {
  font-size: 13px;
  color: var(--text-tertiary);
}
.batch-fix-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 16px;
}
.batch-fix-group {
  cursor: pointer;
  transition: transform 0.15s;
}
.batch-fix-group:hover {
  transform: translateX(2px);
}
.batch-fix-card {
  padding: 16px;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.batch-fix-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.batch-fix-group--active .batch-fix-card {
  border-left: 4px solid var(--color-primary);
  background: var(--color-primary-20);
  border-color: var(--color-primary);
  box-shadow: 0 2px 12px rgba(122, 127, 168, 0.15);
}
.batch-fix-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.batch-fix-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}
.batch-fix-label {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}
.batch-fix-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.4;
}
.batch-fix-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.batch-fix-input {
  width: 160px;
}
.batch-fix-input :deep(.el-input__wrapper) {
  background-color: var(--bg-muted);
  border-color: var(--border-default);
  box-shadow: none;
}
.batch-fix-input :deep(.el-input__wrapper:hover) {
  border-color: var(--color-primary);
}
.batch-fix-input :deep(.el-input__wrapper.is-focus) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary-20);
}
.batch-fix-btn {
  min-width: 140px;
  text-align: center;
  font-size: 13px;
  border-radius: 6px;
  transition: all 0.2s;
}

.allocation-group-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}
.allocation-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-default);
}
.allocation-group-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.allocation-group-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-muted);
  border-radius: 8px;
  transition: background 0.15s;
}
.allocation-group-item:hover {
  background: var(--bg-hover);
}
.allocation-group-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.allocation-group-label {
  font-weight: 500;
  font-size: 14px;
  color: var(--text-primary);
}

.table-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
}
.table-controls > div:last-child {
  display: flex;
  align-items: center;
  gap: 8px;
}
.table-wrapper {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.highlight-legend {
  display: flex;
  gap: 24px;
  padding: 8px 0;
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.legend-color {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  flex-shrink: 0;
}
.legend-color--duplicate {
  background-color: var(--color-warning-20);
  border: 1px solid var(--border-default);
}
.legend-color--blocked {
  background-color: var(--bg-card);
  border-left: 3px solid var(--color-danger);
}

:deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
:deep(.el-table__header-wrapper) {
  position: sticky;
  top: 0;
  z-index: 3;
  background: var(--bg-card);
}
:deep(.row-duplicate) {
  background-color: var(--color-warning-20) !important;
}
:deep(.row-blocked) {
  border-left: 3px solid var(--color-danger) !important;
  background-color: var(--color-danger-20) !important;
}
:deep(.cell-blocked) {
  background-color: var(--color-danger-20) !important;
}
:deep(.cell-missing) {
  background-color: var(--bg-muted) !important;
  border-bottom: 1px dashed var(--border-default);
}
:deep(.el-table__row--level-1) {
  background-color: var(--bg-muted);
}

.product-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.3;
}
.product-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.product-code-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
}

.op-type-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.op-type-label {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}
.type-tag-inline {
  font-size: 11px;
  padding: 0 6px;
  height: 20px;
  line-height: 20px;
  border: none;
  color: #fff;
}

.pagination-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.fixed-action-bar {
  flex-shrink: 0;
  position: sticky;
  bottom: 0;
  background: var(--bg-card);
  border-top: 1px solid var(--border-default);
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06);
  z-index: 10;
  margin-top: 12px;
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
  color: var(--text-secondary);
  font-size: 14px;
}
.import-btn {
  min-width: 160px;
  font-weight: 500;
}

/* 步骤3 - 导入完成 */
.import-result {
  margin-top: 64px;
  text-align: center;
}
.result-summary {
  margin-top: 16px;
}
.result-numbers {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 24px;
}
.number-item {
  text-align: center;
}
.number-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}
.number-label {
  display: block;
  font-size: 14px;
  color: var(--text-tertiary);
}
.number-divider {
  width: 1px;
  height: 40px;
  background: var(--border-default);
}

.error-group {
  margin-bottom: 12px;
}
.error-reason {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.error-collapse {
  margin-top: 4px;
  border: none;
}

/* 全局 */
.step-content {
  margin-top: 20px;
  min-height: 380px;
  height: auto;
  overflow: visible;
}

@keyframes ledgerFlash {
  0%, 100% { box-shadow: 0 0 0 0 rgba(122, 127, 168, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(122, 127, 168, 0.15); }
}
.ledger-select-flash :deep(.el-input__wrapper) {
  animation: ledgerFlash 0.6s ease-in-out 2;
  border-color: var(--color-primary) !important;
}
</style>
