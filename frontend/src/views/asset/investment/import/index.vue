<template>
  <div class="inventory-page">
    <el-steps :active="currentStep" finish-status="success" align-center>
      <el-step
        v-for="(step, index) in steps"
        :key="index"
        :title="step.title"
      />
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
                    <el-tag
                      size="small"
                      :type="
                        ledger.ledger_type === 'family' ? 'info' : 'primary'
                      "
                    >
                      {{
                        ledgerTypeMap[ledger.ledger_type] || ledger.ledger_type
                      }}
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
          <div class="mode-card" @click="openAiImport">
            <IconifyIconOffline icon="ep:magic-stick" class="mode-icon" />
            <h4 class="mode-title">AI 截图/文本识别</h4>
            <p class="mode-desc">
              上传持仓/交易截图或粘贴文本，AI 识别后逐行核对入账
            </p>
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
            <IconifyIconOffline icon="ep:loading" class="loading-icon" />
            正在解析文件，请稍候...
          </p>
          <p class="text-xs text-gray-400 mb-4">
            正在处理 {{ fileSize }}，预计需要 5-10 秒
          </p>
          <el-skeleton :rows="8" animated />
        </div>

        <div v-show="!parsing" class="upload-layout">
          <div class="upload-left">
            <div class="ledger-select-area">
              <div class="flex items-center gap-4">
                <span class="text-base font-medium text-gray-700"
                  >交易账户：</span
                >
                <el-tag size="large" type="primary"
                  >{{ selectedLedgerName }}（{{ ledgerTypeLabel }}）</el-tag
                >
                <el-button type="primary" link @click="currentStep = 0"
                  >更换账户</el-button
                >
              </div>
            </div>

            <div v-if="isStandardMode" class="template-download-section">
              <el-button
                type="primary"
                size="large"
                class="download-template-btn"
                :loading="downloadLoading"
                @click="handleDownloadTemplate"
              >
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
              <el-select
                v-model="selectedMode"
                size="large"
                style="width: 220px"
              >
                <el-option
                  v-for="mode in availableModes"
                  :key="mode.value"
                  :label="mode.label"
                  :value="mode.value"
                />
              </el-select>
              <span class="import-mode-hint">选择与您的文件来源匹配的格式</span>
            </div>

            <div class="source-logos">
              <span class="source-logos-label">支持来源</span>
              <div class="source-logo-pills">
                <button
                  v-for="mode in availableModes"
                  :key="mode.value"
                  type="button"
                  class="source-logo-pill"
                  :class="{ 'is-active': selectedMode === mode.value }"
                  @click="selectedMode = mode.value"
                >
                  <Superellipse
                    v-if="mode.logo && !logoBrokenMap[mode.value]"
                    :power="3"
                    class="source-logo-frame"
                  >
                    <img
                      :src="mode.logo"
                      :alt="mode.label"
                      class="source-logo-img"
                      @error="onLogoError(mode.value)"
                    />
                  </Superellipse>
                  <span v-else class="source-logo-fallback">
                    <IconifyIconOffline icon="ep:document" />
                  </span>
                  <span class="source-logo-name">{{ mode.label }}</span>
                </button>
              </div>
            </div>

            <div class="upload-area-wrapper">
              <el-upload
                ref="uploadRef"
                :accept="uploadAccept"
                :before-upload="beforeUpload"
                :http-request="handleUpload"
                :show-file-list="false"
                drag
                :disabled="!selectedLedgerId || parsing"
                class="golden-upload"
              >
                <template #default>
                  <IconifyIconOffline
                    icon="ep:upload-filled"
                    class="upload-icon"
                    :class="{ 'icon-active': isDragover }"
                  />
                  <p class="upload-text">将文件拖到此处，或</p>
                  <el-button
                    type="primary"
                    size="default"
                    class="upload-btn"
                    :disabled="!selectedLedgerId || uploading"
                    :loading="uploading"
                    @click="handleUploadClick"
                  >
                    {{ uploading ? "正在上传..." : "点击上传" }}
                  </el-button>
                  <p class="upload-hint">
                    {{
                      isStandardMode
                        ? "使用标准模板格式的文件"
                        : `直接上传${formatName}导出的文件`
                    }}
                  </p>
                  <p class="upload-format-info">
                    支持 Excel、CSV 格式 ｜ 最大 5MB
                  </p>
                </template>
              </el-upload>

              <div v-if="uploadError" class="upload-error">
                <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
                {{ uploadError }}
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

          <div v-if="formatGuides[selectedMode]" class="upload-right">
            <div class="format-guide">
              <div class="format-guide-header">
                <IconifyIconOffline
                  icon="ep:info-filled"
                  class="format-guide-icon"
                />
                <span>{{ formatGuides[selectedMode].title }}</span>
              </div>
              <ol class="format-guide-list">
                <li
                  v-for="(tip, index) in formatGuides[selectedMode].tips"
                  :key="index"
                >
                  {{ tip }}
                </li>
              </ol>
            </div>
          </div>
        </div>

        <p
          style="
            margin-top: 24px;
            font-size: 13px;
            color: var(--text-tertiary);
            text-align: center;
          "
        >
          上传后将进入预览页面，您可以修正错误后确认导入。如有问题，请参考帮助文档。
        </p>

        <el-dialog
          v-model="showCreateLedgerDialog"
          title="添加新账户"
          width="360px"
          :close-on-click-modal="false"
        >
          <el-form label-position="top">
            <el-form-item label="账户名称" required>
              <el-input
                v-model="newLedgerName"
                placeholder="例如：华泰证券、招商银行储蓄卡"
                size="large"
                @keyup.enter="createLedger"
              />
            </el-form-item>
            <el-form-item label="默认配置目标">
              <el-select v-model="newLedgerAllocation" size="large">
                <el-option
                  v-for="opt in ALLOCATION_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <div class="flex justify-end gap-3">
              <el-button @click="showCreateLedgerDialog = false"
                >取消</el-button
              >
              <el-button type="primary" @click="createLedger"
                >确认添加</el-button
              >
            </div>
          </template>
        </el-dialog>
      </div>

      <!-- 步骤2：预览与修正 -->
      <div v-else-if="currentStep === 2" class="step3-container">
        <div class="step3-header">
          <el-button size="default" @click="currentStep = 1"
            >返回上一步</el-button
          >
          <span class="header-ledger">导入账户：{{ selectedLedgerName }}</span>
          <div class="header-actions ml-auto flex items-center gap-3">
            <el-button size="default" @click="toggleAllocationPanel">
              <IconifyIconOffline icon="ep:setting" class="mr-1" />
              {{ showAllocationGroupPanel ? "收起配置" : "设置配置目标" }}
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
                      已校验
                      <el-badge
                        :value="validRowsCount"
                        :type="validRowsCount > 0 ? 'success' : 'info'"
                        class="summary-badge"
                      />
                    </span>
                  </div>
                  <div class="summary-card-body">
                    <p>代码已匹配、字段完整、无重复，可直接导入</p>
                  </div>
                </div>
                <div
                  v-if="duplicateCount > 0"
                  class="summary-card summary-card--warning"
                >
                  <div class="summary-card-header">
                    <span class="summary-card-title"
                      >重复项
                      <el-badge
                        :value="duplicateCount"
                        type="warning"
                        class="summary-badge"
                    /></span>
                  </div>
                </div>
                <div
                  v-if="blockedCount > 0 || errorCount > 0"
                  class="summary-card summary-card--danger"
                >
                  <div class="summary-card-header">
                    <span class="summary-card-title"
                      >待确认
                      <el-badge
                        :value="blockedCount + errorCount"
                        type="danger"
                        class="summary-badge"
                    /></span>
                  </div>
                  <div class="summary-card-body">
                    <p v-if="errorCount > 0">· {{ errorCount }} 条解析错误</p>
                    <p>信息缺失（数量或价格为空）</p>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="blockedCount + errorCount > 0" class="batch-fix-bar">
              <el-button
                :type="showBatchFix ? '' : 'primary'"
                size="default"
                @click="toggleBatchFix"
              >
                <IconifyIconOffline icon="ep:setting" class="mr-1" />
                {{ showBatchFix ? "收起批量修正" : "批量修正问题数据" }}
              </el-button>
              <span v-if="!showBatchFix" class="batch-fix-hint"
                >{{ blockedCount + errorCount }} 条待处理</span
              >
              <el-button
                v-if="hasFundRecordsForNav"
                type="primary"
                size="default"
                :loading="enrichingNav"
                @click="fetchAndFillFundNav"
              >
                获取净值和份额（{{ fundRecordsCount }}只）
              </el-button>
              <el-button
                v-if="calculatedCount > 0"
                type="warning"
                size="default"
                @click="confirmAllCalculated"
              >
                确认所有推算数据（{{ calculatedCount }} 条）
              </el-button>
            </div>

            <div
              v-if="showBatchFix && problemCategories.length > 0"
              class="batch-fix-panel"
            >
              <div
                v-for="cat in problemCategories"
                :key="cat.key"
                class="batch-fix-group"
                :class="{
                  'batch-fix-group--active': isCategoryActive(cat.key)
                }"
                @click="filterByCategory(cat.key)"
              >
                <div class="batch-fix-card">
                  <div class="batch-fix-card-header">
                    <div class="batch-fix-info">
                      <span class="batch-fix-label">{{ cat.label }}</span>
                      <span class="batch-fix-desc">{{
                        getCategoryDesc(cat.key)
                      }}</span>
                    </div>
                    <el-tag
                      size="small"
                      effect="dark"
                      :type="getCategoryTagType(cat.key, cat.count)"
                      >{{ cat.count }}
                      条
                    </el-tag>
                  </div>
                  <div class="batch-fix-actions" @click.stop>
                    <template v-if="cat.key === 'missingCode'">
                      <!-- 分别处理基金和股票 -->
                      <template
                        v-for="assetType in ['fund', 'stock']"
                        :key="assetType"
                      >
                        <template
                          v-if="
                            getMissingRowsByType(cat.rows, assetType).length > 0
                          "
                        >
                          <!-- 基金：单条显示输入框，多条显示抽屉按钮 -->
                          <template v-if="assetType === 'fund'">
                            <template
                              v-if="
                                getMissingRowsByType(cat.rows, 'fund')
                                  .length === 1
                              "
                            >
                              <el-input
                                v-model="batchCodeInput"
                                placeholder="输入基金代码"
                                size="small"
                                class="batch-fix-input"
                              />
                              <el-button
                                type="primary"
                                size="small"
                                class="batch-fix-btn batch-fix-btn--primary"
                                @click="
                                  batchFillCode(
                                    getMissingRowsByType(cat.rows, 'fund'),
                                    batchCodeInput
                                  )
                                "
                              >
                                应用到当前 1 条
                              </el-button>
                            </template>
                            <template v-else>
                              <el-button
                                type="primary"
                                size="small"
                                @click="showMatchDrawer = true"
                              >
                                匹配基金代码（{{
                                  getMissingRowsByType(cat.rows, "fund").length
                                }}只）
                              </el-button>
                            </template>
                          </template>

                          <!-- 股票：暂不支持批量匹配，使用输入框 -->
                          <template v-if="assetType === 'stock'">
                            <el-input
                              v-model="batchCodeInput"
                              placeholder="输入股票代码"
                              size="small"
                              class="batch-fix-input"
                            />
                            <el-button
                              type="primary"
                              size="small"
                              class="batch-fix-btn batch-fix-btn--primary"
                              @click="
                                batchFillCode(
                                  getMissingRowsByType(cat.rows, 'stock'),
                                  batchCodeInput
                                )
                              "
                            >
                              应用到当前
                              {{
                                getMissingRowsByType(cat.rows, "stock").length
                              }}
                              条
                            </el-button>
                          </template>
                        </template>
                      </template>
                    </template>
                    <template v-if="cat.key === 'mismatch'">
                      <el-tooltip
                        content="以数量×价格为准修正金额"
                        placement="top"
                      >
                        <el-button
                          type="primary"
                          size="small"
                          class="batch-fix-btn batch-fix-btn--primary"
                          @click="batchFixAmount(cat.rows)"
                          >修正金额
                        </el-button>
                      </el-tooltip>
                    </template>
                    <template v-if="cat.key === 'missingQtyPrice'">
                      <el-button
                        type="primary"
                        size="small"
                        class="batch-fix-btn batch-fix-btn--primary"
                        @click="
                          showFullTable = true;
                          showProblemOnly = true;
                        "
                        >展开查看并手动编辑
                      </el-button>
                    </template>
                    <el-button
                      size="small"
                      class="batch-fix-btn batch-fix-btn--secondary"
                      @click="skipCategory(cat.rows)"
                      >跳过当前
                    </el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="showAllocationGroupPanel" class="allocation-group-panel">
            <div class="allocation-group-header">
              <span class="font-weight-500">按产品类型设置配置目标</span>
              <div class="flex items-center gap-3">
                <el-button
                  size="small"
                  text
                  @click="showAllocationGroupPanel = false"
                  >取消</el-button
                >
              </div>
            </div>
            <div v-if="selectedCount > 0" class="allocation-group-item">
              <div class="allocation-group-info">
                <span class="allocation-group-label">已选行批量设置</span>
                <el-tag size="small" type="primary"
                  >{{ selectedCount }} 条已选</el-tag
                >
              </div>
              <el-select
                model-value=""
                placeholder="选择配置目标"
                size="small"
                style="width: 140px"
                @change="(val: string) => batchSetAllocation(val)"
              >
                <el-option
                  v-for="opt in ALLOCATION_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </div>
            <div class="allocation-group-list">
              <div
                v-for="(group, key) in currentAllocationGroups"
                :key="key"
                class="allocation-group-item"
              >
                <div class="allocation-group-info">
                  <span class="allocation-group-label">{{ group.label }}</span>
                  <el-tag size="small" type="info">{{ group.count }} 条</el-tag>
                </div>
                <el-select
                  :model-value="group.currentAllocation"
                  size="small"
                  style="width: 140px"
                  @change="
                    (val: string) => applyAllocationGroupSetting(group, val)
                  "
                >
                  <el-option
                    v-for="opt in ALLOCATION_OPTIONS"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </div>
              <div
                v-if="Object.keys(currentAllocationGroups).length === 0"
                class="text-center text-gray-400 py-4"
              >
                所有数据已手动设置配置目标，无需分组调整
              </div>
            </div>
          </div>

          <div
            class="step3-divider"
            :title="showLeftPanel ? '收起侧边栏' : '展开数据摘要'"
            @click="toggleLeftPanel"
          >
            <IconifyIconOffline
              :icon="showLeftPanel ? 'ep:d-arrow-left' : 'ep:d-arrow-right'"
              class="divider-icon"
            />
            <span v-if="!showLeftPanel" class="divider-text">摘要</span>
          </div>

          <div class="step3-right">
            <div class="table-controls">
              <div class="flex items-center gap-4 flex-wrap">
                <el-select
                  v-model="tableStatusFilter"
                  placeholder="按状态筛选"
                  size="small"
                  style="width: 130px"
                  clearable
                >
                  <el-option label="全部" value="" />
                  <el-option label="待补全" value="blocked" />
                  <el-option label="重复" value="duplicate" />
                  <el-option label="错误" value="error" />
                  <el-option label="正常" value="normal" />
                </el-select>
                <el-switch
                  v-model="showProblemOnly"
                  active-text="只看问题数据"
                  inactive-text="全部数据"
                />
                <el-input
                  v-model="tableFilterKeyword"
                  placeholder="搜索代码或名称"
                  size="small"
                  style="width: 200px"
                  clearable
                />
                <el-select
                  v-model="tableTypeFilter"
                  placeholder="按类型筛选"
                  size="small"
                  style="width: 140px"
                  clearable
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                >
                  <el-option
                    v-for="(label, key) in typeLabels"
                    :key="key"
                    :label="label"
                    :value="key"
                  />
                </el-select>
              </div>
              <div class="flex items-center gap-2">
                <el-tooltip
                  content="请切换到“只看问题数据”视图后使用"
                  :disabled="showProblemOnly"
                >
                  <span>
                    <el-button
                      v-if="duplicateCount > 0"
                      size="small"
                      :type="duplicatesHandled ? 'warning' : ''"
                      :disabled="!showProblemOnly"
                      @click="deselectAllDuplicates"
                    >
                      {{
                        duplicatesHandled ? "恢复查看重复行" : "取消显示重复行"
                      }}
                    </el-button>
                  </span>
                </el-tooltip>
                <el-button link @click="toggleFullTable">
                  <IconifyIconOffline
                    :icon="showFullTable ? 'ep:arrow-up' : 'ep:arrow-down'"
                  />
                  {{ showFullTable ? "收起列表" : "展开列表" }}
                </el-button>
              </div>
            </div>

            <div
              v-if="showFullTable && (duplicateCount > 0 || blockedCount > 0)"
              class="highlight-legend"
            >
              <span class="legend-item"
                ><span
                  class="legend-color legend-color--duplicate"
                />黄色背景：已识别的重复数据，已自动跳过，可手动勾选保留</span
              >
              <span v-if="blockedCount > 0" class="legend-item"
                ><span
                  class="legend-color legend-color--blocked"
                />红色左边框：信息缺失，需补全数量或价格后可导入</span
              >
            </div>

            <div v-show="showFullTable" class="table-wrapper">
              <el-table
                :data="filteredPagedData"
                row-key="_rowKey"
                :tree-props="{
                  children: 'children',
                  hasChildren: 'hasChildren'
                }"
                default-expand-all
                stripe
                size="default"
                :row-class-name="getRowClassName"
                :cell-class-name="getCellClassName"
                @selection-change="handleSelectionChange"
              >
                <el-table-column width="80" fixed="left">
                  <template #header>
                    <el-checkbox
                      v-model="isAllSelected"
                      :indeterminate="isIndeterminate"
                      @change="handleHeaderCheckboxChange"
                    />
                  </template>
                  <template #default="{ row }">
                    <el-tooltip
                      v-if="row.is_cash_transfer"
                      content="资金划转暂不支持导入"
                      placement="top"
                    >
                      <el-checkbox :model-value="false" disabled />
                    </el-tooltip>
                    <el-checkbox
                      v-else
                      :model-value="isRowSelected(row)"
                      :disabled="
                        row.is_duplicate || row.error || isRowBlocked(row)
                      "
                      @change="
                        (val: boolean) => handleRowCheckboxChange(row, val)
                      "
                    />

                    <el-tag
                      v-if="row.is_calculated"
                      size="small"
                      type="warning"
                      class="ml-1"
                      >待确认</el-tag
                    >
                  </template>
                </el-table-column>
                <el-table-column
                  v-for="col in tableColumns"
                  :key="col.prop"
                  v-bind="col"
                >
                  <template v-if="col.slot === 'status'" #default="{ row }">
                    <el-tooltip
                      v-if="row.is_duplicate"
                      content="该交易已存在于系统中，默认跳过。如需强制导入，请手动勾选"
                      placement="top"
                    >
                      <el-tag type="warning" size="small">重复</el-tag>
                    </el-tooltip>
                    <el-tag v-else-if="row.error" type="danger" size="small"
                      >错误</el-tag
                    >
                    <el-tag
                      v-else-if="isRowBlocked(row)"
                      type="info"
                      size="small"
                      >待补全</el-tag
                    >
                    <el-tag v-else type="success" size="small">正常</el-tag>
                  </template>
                  <template
                    v-else-if="col.slot === 'product'"
                    #default="{ row }"
                  >
                    <div class="product-cell">
                      <span class="product-name">{{
                        row.name || row.symbol || "--"
                      }}</span>
                      <div class="product-code-row">
                        <span class="product-code"
                          ># {{ row.symbol || "--" }}</span
                        >
                        <el-tag
                          v-if="row.display_type"
                          size="small"
                          :color="getFundTypeColor(row.display_type)"
                          class="type-tag-inline"
                          >{{ row.display_type }}
                        </el-tag>
                      </div>
                    </div>
                  </template>
                  <template
                    v-else-if="col.slot === 'opType'"
                    #default="{ row }"
                  >
                    <div class="op-type-cell">
                      <span class="op-type-label">{{
                        row.op_type_label || "--"
                      }}</span>
                      <el-tag
                        v-if="!row.is_merged && row.type !== 'fund'"
                        :color="getTypeColor(row.type)"
                        size="small"
                        class="type-tag-inline"
                        >{{ typeLabels[row.type] || row.type || "未知" }}
                      </el-tag>
                    </div>
                  </template>
                  <template
                    v-else-if="col.slot === 'quantity'"
                    #default="{ row }"
                  >
                    <el-popover
                      :visible="row.isEditingQty"
                      placement="bottom-start"
                      :width="200"
                      :trigger="'manual' as any"
                      :hide-after="0"
                      :persistent="true"
                      teleported
                    >
                      <div class="flex flex-col gap-2" @mousedown.stop>
                        <div class="text-xs text-gray-500">
                          {{ row.symbol }} {{ row.name }} -
                          <span class="font-semibold">数量</span>
                        </div>
                        <el-input-number
                          ref="inputRef"
                          v-model="row.quantity"
                          size="default"
                          :precision="4"
                          :min="0"
                          class="w-full"
                          controls-position="right"
                          @vue:mounted="(el: any) => el?.input?.focus()"
                        />
                        <div class="flex justify-end gap-2">
                          <el-button
                            type="primary"
                            size="small"
                            @click.stop="finishEdit(row, 'quantity', true)"
                            >确认
                          </el-button>
                          <el-button
                            size="small"
                            @click.stop="cancelEdit(row, 'quantity')"
                            >取消</el-button
                          >
                        </div>
                      </div>
                      <template #reference>
                        <span
                          class="cursor-pointer hover:text-blue-500 select-none"
                          @click.stop="startEdit(row, 'quantity')"
                          @mousedown.prevent
                        >
                          {{ row.quantity }}
                          <el-tag
                            v-if="row.is_calculated"
                            size="small"
                            type="warning"
                            class="ml-1"
                            >待确认</el-tag
                          >
                        </span>
                      </template>
                    </el-popover>
                  </template>
                  <template v-else-if="col.slot === 'price'" #default="{ row }">
                    <el-popover
                      :visible="row.isEditingPrice"
                      placement="bottom-start"
                      :width="200"
                      :trigger="'manual' as any"
                      :hide-after="0"
                      :persistent="true"
                      teleported
                    >
                      <div class="flex flex-col gap-2" @mousedown.stop>
                        <div class="text-xs text-gray-500">
                          {{ row.symbol }} {{ row.name }} -
                          <span class="font-semibold">价格</span>
                        </div>
                        <el-input-number
                          ref="inputRef"
                          v-model="row.price"
                          size="default"
                          :precision="4"
                          :min="0"
                          class="w-full"
                          controls-position="right"
                          @vue:mounted="(el: any) => el?.input?.focus()"
                        />
                        <div class="flex justify-end gap-2">
                          <el-button
                            type="primary"
                            size="small"
                            @click.stop="finishEdit(row, 'price', true)"
                            >确认
                          </el-button>
                          <el-button
                            size="small"
                            @click.stop="cancelEdit(row, 'price')"
                            >取消</el-button
                          >
                        </div>
                      </div>
                      <template #reference>
                        <span
                          class="cursor-pointer hover:text-blue-500 select-none"
                          @click.stop="startEdit(row, 'price')"
                          @mousedown.prevent
                        >
                          {{ row.price }}
                          <el-tag
                            v-if="row.is_calculated"
                            size="small"
                            type="warning"
                            class="ml-1"
                            >待确认</el-tag
                          >
                        </span>
                      </template>
                    </el-popover>
                  </template>
                  <template
                    v-else-if="col.slot === 'allocation'"
                    #default="{ row }"
                  >
                    <el-select
                      v-model="row.allocation"
                      size="small"
                      :disabled="
                        row.is_cash_transfer || row.is_duplicate || row.error
                      "
                      @change="onRowAllocationChange(row)"
                    >
                      <el-option
                        v-for="opt in ALLOCATION_OPTIONS"
                        :key="opt.value"
                        :label="opt.label"
                        :value="opt.value"
                      />
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
              本次导入识别 {{ totalRows }} 条，已选中
              <strong>{{ selectedCount }}</strong> 条有效数据
              <span v-if="duplicateCount + blockedCount + errorCount > 0">
                ，另有
                {{ duplicateCount + blockedCount + errorCount }} 条待处理（{{
                  duplicateCount
                }}条重复 / {{ blockedCount }}条待补全
                <template v-if="errorCount > 0">
                  / {{ errorCount }}条错误</template
                >）
              </span>
            </span>
            <div class="flex gap-3">
              <el-button
                v-if="duplicateCount + blockedCount + errorCount > 0"
                :loading="importing"
                @click="importNormalOnly"
                >仅导入校验通过的数据
              </el-button>
              <el-button
                type="primary"
                :disabled="selectedCount === 0"
                :loading="importing"
                class="import-btn"
                @click="confirmImport"
                >确认导入 {{ selectedCount }} 条
              </el-button>
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
                    <span
                      class="number-value"
                      style="color: var(--color-success)"
                      >{{ importedCount }}</span
                    >
                    <span class="number-label">笔导入成功</span>
                  </div>
                  <div class="number-divider" />
                  <div class="number-item">
                    <span
                      class="number-value"
                      style="color: var(--text-tertiary)"
                      >{{ skippedCount }}</span
                    >
                    <span class="number-label">笔跳过</span>（重复
                    {{ duplicateCount }} 条 / 错误 {{ errorCount }} 条）
                  </div>
                </div>

                <div v-if="orphanCount > 0" class="mt-4">
                  <el-alert
                    title="部分交易数据不完整"
                    type="warning"
                    :closable="false"
                    show-icon
                  >
                    <template #default>
                      <p>
                        {{ orphanCount }}
                        笔交易因缺少对应持仓记录，已作为待处理数据保存。
                      </p>
                      <p class="text-xs mt-1">
                        这些交易不会影响当前资产计算，你可以在交易流水中手动关联持仓。
                      </p>
                    </template>
                  </el-alert>
                </div>

                <div v-if="importErrors.length > 0" class="mt-4">
                  <el-alert
                    :title="`导入过程中 ${importErrors.length} 条记录因以下原因被跳过`"
                    type="warning"
                    :closable="false"
                    show-icon
                  >
                    <template #default>
                      <div
                        v-for="group in errorSummary"
                        :key="group.reason"
                        class="error-group"
                      >
                        <p class="error-reason">
                          {{ group.reason }}（共 {{ group.count }} 条）
                        </p>
                        <el-collapse
                          v-if="group.items.length > 1"
                          class="error-collapse"
                        >
                          <el-collapse-item
                            :title="`涉及标的：${group.items.slice(0, 3).join('、')}${group.items.length > 3 ? ' 等' : ''}`"
                          >
                            <ul class="list-disc pl-4 text-xs">
                              <li v-for="item in group.items" :key="item">
                                {{ item }}
                              </li>
                            </ul>
                          </el-collapse-item>
                        </el-collapse>
                        <p v-else class="text-xs ml-4">{{ group.items[0] }}</p>
                      </div>
                    </template>
                  </el-alert>
                </div>

                <div v-if="showPriceUpdateTip" class="mt-4">
                  <el-alert
                    title="建议"
                    type="info"
                    :closable="false"
                    show-icon
                  >
                    <template #default>
                      <p>你刚导入了交易记录，持仓数据已更新。</p>
                      <p class="text-xs mt-1">
                        建议现在去
                        <router-link
                          to="/asset/investment/stocks"
                          class="text-primary"
                          >检查持仓市价</router-link
                        >
                        ，以确保资产计算准确。
                      </p>
                    </template>
                  </el-alert>
                </div>
              </div>
              <div class="flex gap-2 justify-center mt-6">
                <el-button
                  v-if="importedCount > 0 || orphanCount > 0"
                  type="primary"
                  @click="goToTransactions"
                >
                  查看交易流水
                </el-button>
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
                <el-alert
                  title="跳过原因"
                  type="warning"
                  :closable="false"
                  show-icon
                >
                  <template #default>
                    <div
                      v-for="group in errorSummary"
                      :key="group.reason"
                      class="error-group"
                    >
                      <p class="error-reason">
                        {{ group.reason }}（共 {{ group.count }} 条）
                      </p>
                      <el-collapse
                        v-if="group.items.length > 1"
                        class="error-collapse"
                      >
                        <el-collapse-item
                          :title="`涉及标的：${group.items.slice(0, 3).join('、')}${group.items.length > 3 ? ' 等' : ''}`"
                        >
                          <ul class="list-disc pl-4 text-xs">
                            <li v-for="item in group.items" :key="item">
                              {{ item }}
                            </li>
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

    <FundMatchDrawer
      :visible="showMatchDrawer"
      :missing-fund-names="missingFundNames"
      :preview-data="previewData"
      @match-complete="onMatchComplete"
    />
    <AiImportModal
      v-model="showAiModal"
      :ledger-id="selectedLedgerId"
      @rows-found="onAiRowsFound"
    />
  </div>
</template>

<script setup lang="ts">
import { useImportWizard } from "./composables/useImportWizard";
import FundMatchDrawer from "./components/FundMatchDrawer.vue";
import AiImportModal from "./components/AiImportModal.vue";
import Superellipse from "@/components/Superellipse/index.vue";
import { ALLOCATION_OPTIONS } from "@/constants";

defineOptions({ name: "Inventory" });

const {
  router,
  showMatchDrawer,
  showAiModal,
  formatGuides,
  steps,
  currentStep,
  selectedMode,
  previewData,
  duplicateCount,
  errorCount,
  importedCount,
  skippedCount,
  orphanCount,
  importing,
  parsing,
  uploading,
  fileSize,
  newLedgerAllocation,
  showAllocationGroupPanel,
  selectedLedgerId,
  showCreateLedgerDialog,
  newLedgerName,
  downloadLoading,
  currentPage,
  pageSize,
  totalRows,
  isAllSelected,
  isIndeterminate,
  showProblemOnly,
  tableFilterKeyword,
  tableTypeFilter,
  tableStatusFilter,
  showFullTable,
  showBatchFix,
  batchCodeInput,
  showLeftPanel,
  importErrors,
  duplicatesHandled,
  uploadError,
  validRowsCount,
  isDragover,
  selectedLedgerName,
  ledgerTypeLabel,
  ledgerGroups,
  logoBrokenMap,
  onLogoError,
  availableModes,
  isStandardMode,
  templateNameForAccount,
  accountType,
  templateFields,
  formatName,
  tableColumns,
  blockedCount,
  selectedCount,
  nothingImported,
  showPriceUpdateTip,
  currentAllocationGroups,
  problemCategories,
  errorSummary,
  filteredPagedData,
  calculatedCount,
  enrichingNav,
  hasFundRecordsForNav,
  fundRecordsCount,
  filteredTotal,
  uploadAccept,
  missingFundNames,
  openAiImport,
  onAiRowsFound,
  fetchAndFillFundNav,
  confirmAllCalculated,
  isRowBlocked,
  getFundTypeColor,
  getTypeColor,
  isRowSelected,
  onAccountSelected,
  handleDownloadTemplate,
  handleUploadClick,
  toggleFullTable,
  beforeUpload,
  handleUpload,
  confirmImport,
  importNormalOnly,
  continueImport,
  reimport,
  handleHeaderCheckboxChange,
  handleRowCheckboxChange,
  batchFillCode,
  batchFixAmount,
  skipCategory,
  deselectAllDuplicates,
  filterByCategory,
  onMatchComplete,
  batchSetAllocation,
  applyAllocationGroupSetting,
  onRowAllocationChange,
  toggleAllocationPanel,
  toggleBatchFix,
  toggleLeftPanel,
  startEdit,
  finishEdit,
  cancelEdit,
  getRowClassName,
  getCellClassName,
  getCategoryDesc,
  getCategoryTagType,
  isCategoryActive,
  goToTransactions,
  goToManualEntry,
  goToLiabilityForm,
  goToImportGuide,
  getMissingRowsByType,
  createLedger,
  handleSizeChange,
  handlePageChange,
  handleSelectionChange,
  ledgerTypeMap,
  typeLabels,
} = useImportWizard();
</script>

<style scoped>
@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@keyframes ledger-flash {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgb(122 127 168 / 40%);
  }

  50% {
    box-shadow: 0 0 0 4px rgb(122 127 168 / 15%);
  }
}

.el-button--large {
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
  padding: 24px 0;
  margin: 0 auto;
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
  padding-left: 4px;
  margin-bottom: 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  border-left: 3px solid var(--color-primary);
}

.mode-card {
  width: 240px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  background: var(--bg-card);
  border: 2px solid var(--border-default);
  border-radius: 16px;
  transition: all 0.3s ease;
}

.mode-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 8px 24px rgb(0 0 0 / 6%);
  transform: translateY(-2px);
}

.mode-icon {
  margin-bottom: 12px;
  font-size: 36px;
  color: var(--color-primary);
}

.mode-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.mode-desc {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}

.import-mode-cards {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-top: 32px;
}

/* 步骤1 - 上传页面 */
.upload-step {
  min-height: 380px;
  padding: 0;
}

.upload-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  max-width: 1100px;
  margin: 0 auto;
}

.upload-left {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.upload-right {
  flex-shrink: 0;
  width: 340px;
  margin-top: 120px;
}

.ledger-select-area {
  margin-bottom: 16px;
}

.ledger-select-area :deep(.el-form-item__content) {
  display: block !important;
}

.template-download-section {
  margin: 0 0 16px;
  text-align: left;
}

/* 下载模板 / 上传两个按钮统一为「凸起胶囊」样式（高度、内边距、圆角一致）。
   原本上方另有一处仅设 height:40px 的 .download-template-btn,.upload-btn
   重复块，因其属性已被本块完全覆盖，已删除合并至此，避免 no-duplicate-selectors
   误报。 */
.download-template-btn,
.upload-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 0 20px;
  font-size: 14px;
  border-radius: 8px;
}

.download-hint {
  max-width: 700px;
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  text-align: left;
}

.import-mode-select {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0 0 20px;
}

.import-mode-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.import-mode-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 支持来源平台 logo 胶囊条 —— 对齐 design.md 设计令牌 */
.source-logos {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 0 0 20px;
}

.source-logos-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.source-logo-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.source-logo-pill {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  padding: 8px 14px;
  font-size: 13px;
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    background-color 0.3s ease,
    border-color 0.3s ease,
    box-shadow 0.3s ease,
    transform 0.3s ease;
}

.source-logo-pill:hover {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-200);
  box-shadow: 0 4px 14px rgb(227 79 56 / 8%);
  transform: translateY(-2px);
}

.source-logo-pill.is-active {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-400);
  box-shadow: 0 0 0 2px rgb(227 79 56 / 12%);
}

.source-logo-frame {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  overflow: hidden;
}

.source-logo-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.source-logo-fallback {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 16px;
  color: var(--text-tertiary);
}

.source-logo-name {
  white-space: nowrap;
}

.upload-area-wrapper {
  flex: 1;
}

.golden-upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 300px;
  padding: 32px;
  background: #f5f7fa;
  border: 2px dashed #888;
  border-radius: 14px;
  transition: all 0.3s;
}

.golden-upload:hover {
  border-color: var(--color-primary);
}

.golden-upload.is-dragover {
  background: var(--color-primary-10) !important;
  border: 2px solid var(--color-primary) !important;
}

.golden-upload.is-dragover .upload-icon {
  color: var(--color-primary);
  transform: scale(1.1);
}

.upload-icon {
  margin-bottom: 16px;
  font-size: 64px;
  color: var(--color-primary);
  transition:
    color 0.2s,
    transform 0.2s;
}

.upload-text {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
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

.upload-btn:hover {
  opacity: 0.9;
}

.upload-btn:active {
  transform: scale(0.98);
}

.upload-error {
  padding: 12px 16px;
  margin-top: 16px;
  font-size: 14px;
  color: var(--color-danger);
  text-align: center;
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger-30);
  border-radius: 6px;
}

.upload-error-detail {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  text-align: left;
}

.parsing-status {
  width: 100%;
  max-width: 680px;
  margin: 0 auto;
  text-align: center;
}

.loading-icon {
  margin-right: 4px;
  font-size: 16px;
  animation: spin 1s linear infinite;
}

.format-guide {
  padding: 16px;
  margin-top: 0;
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  box-shadow: 0 1px 4px rgb(0 0 0 / 4%);
}

.format-guide-header {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.format-guide-icon {
  font-size: 18px;
  color: var(--color-primary);
}

.format-guide-list {
  padding-left: 0;
  margin: 0;
  list-style: none;
  counter-reset: step-counter;
}

.format-guide-list li {
  display: flex;
  align-items: baseline;
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  counter-increment: step-counter;
}

.format-guide-list li::before {
  flex-shrink: 0;
  min-width: 18px;
  margin-right: 8px;
  font-weight: 600;
  color: var(--color-primary);
  content: counter(step-counter) ".";
}

/* 步骤2 - 预览修正 */
.step3-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 160px);
  margin-top: 16px;
  overflow: hidden;
}

.step3-header {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  margin-bottom: 16px;
}

.header-ledger {
  margin-left: 16px;
  font-weight: 500;
  color: var(--text-secondary);
}

.step3-body {
  display: flex;
  flex: 1;
  gap: 0;
  min-height: 0;
  overflow: hidden;
}

.step3-left {
  flex-shrink: 0;
  width: 340px;
  padding-right: 12px;
  overflow-y: auto;
  border-right: 1px solid var(--border-default);
  transition: width 0.25s ease;
}

.step3-left.collapsed {
  width: 0;
  padding-right: 0;
  overflow: hidden;
  border-right: none;
}

.step3-divider {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  justify-content: center;
  width: 32px;
  margin: 0 4px;
  cursor: pointer;
  background: var(--bg-muted);
  border-radius: 4px;
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
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  padding-left: 12px;
  overflow: hidden;
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
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
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
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.summary-card-title {
  display: flex;
  align-items: center;
  font-weight: 600;
  color: var(--text-primary);
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
  flex-shrink: 0;
  gap: 12px;
  align-items: center;
  padding: 8px 0;
  margin: 12px 0;
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
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  box-shadow: 0 1px 4px rgb(0 0 0 / 4%);
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}

.batch-fix-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgb(0 0 0 / 8%);
}

.batch-fix-group--active .batch-fix-card {
  background: var(--color-primary-20);
  border-color: var(--color-primary);
  border-left: 4px solid var(--color-primary);
  box-shadow: 0 2px 12px rgb(122 127 168 / 15%);
}

.batch-fix-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.batch-fix-info {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
}

.batch-fix-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.batch-fix-desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary);
}

.batch-fix-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
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
  font-size: 13px;
  text-align: center;
  border-radius: 6px;
  transition: all 0.2s;
}

.allocation-group-panel {
  padding: 16px;
  margin-bottom: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  box-shadow: 0 1px 4px rgb(0 0 0 / 4%);
}

.allocation-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border-default);
}

.allocation-group-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.allocation-group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
  gap: 8px;
  align-items: center;
}

.allocation-group-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.table-controls {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.table-controls > div:last-child {
  display: flex;
  gap: 8px;
  align-items: center;
}

.table-wrapper {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.highlight-legend {
  display: flex;
  flex-shrink: 0;
  gap: 24px;
  padding: 8px 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.legend-item {
  display: flex;
  gap: 6px;
  align-items: center;
}

.legend-color {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  border-radius: 3px;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  background-color: var(--color-danger-20) !important;
  border-left: 3px solid var(--color-danger) !important;
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
  gap: 6px;
  align-items: center;
}

.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
}

.op-type-cell {
  display: flex;
  gap: 6px;
  align-items: center;
}

.op-type-label {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}

.type-tag-inline {
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 20px;
  color: #fff;
  border: none;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.fixed-action-bar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  flex-shrink: 0;
  margin-top: 12px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-default);
  box-shadow: 0 -2px 8px rgb(0 0 0 / 6%);
}

.action-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1200px;
  padding: 16px 24px;
  margin: 0 auto;
}

.selected-count {
  font-size: 14px;
  color: var(--text-secondary);
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
  gap: 24px;
  align-items: center;
  justify-content: center;
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
  margin-bottom: 4px;
  font-weight: 600;
  color: var(--text-primary);
}

.error-collapse {
  margin-top: 4px;
  border: none;
}

/* 全局 */
.step-content {
  height: auto;
  min-height: 380px;
  margin-top: 20px;
  overflow: visible;
}

.ledger-select-flash :deep(.el-input__wrapper) {
  border-color: var(--color-primary) !important;
  animation: ledger-flash 0.6s ease-in-out 2;
}
</style>
