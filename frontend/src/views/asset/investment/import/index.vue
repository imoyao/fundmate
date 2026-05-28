<template>
  <div class="inventory-page">
    <el-steps :active="currentStep" finish-status="success" align-center>
      <el-step title="选择导入模式"/>
      <el-step title="上传文件"/>
      <el-step title="预览与修正"/>
      <el-step title="导入完成"/>
    </el-steps>


    <div class="step-content">
      <!-- 步骤1：选择导入模式（保持不变） -->
      <div v-if="currentStep === 0">
        <div class="import-mode-cards">
          <div v-for="mode in importModes" :key="mode.key" class="mode-card"
               :class="{ active: selectedMode === mode.key }" @click="selectMode(mode.key)">
            <IconifyIconOffline :icon="mode.icon" class="mode-icon"/>
            <h4 class="mode-title">{{ mode.title }}</h4>
            <p class="mode-desc">{{ mode.description }}</p>
          </div>
          <div
            class="mode-card"
            @click="goToManualEntry"
          >
            <IconifyIconOffline icon="ep:edit" class="mode-icon"/>
            <h4 class="mode-title">手动批量录入</h4>
            <p class="mode-desc">没有文件？在网页表格中逐行快速录入交易记录</p>
          </div>
          <div class="mode-card" @click="goToLiabilityForm">
            <IconifyIconOffline icon="ep:document-add" class="mode-icon"/>
            <h4 class="mode-title">录入负债 / 应收款</h4>
            <p class="mode-desc">记录信用卡、房贷等非交易类资产</p>
          </div>
        </div>

        <div class="template-download-area">
          <p class="template-download-desc">使用标准模板导入？先下载模板，按格式填写数据后再上传。</p>
          <a :href="templateDownloadUrl" download class="template-link">
            <IconifyIconOffline icon="ep:download" class="mr-1"/>
            下载标准模板（CSV）
          </a>
        </div>
      </div>

      <!-- 步骤2：文件上传 / 解析中 -->
      <div v-else-if="currentStep === 1" class="upload-step">
        <!-- 解析中骨架屏 -->
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

        <!-- 正常状态：左右分栏 -->
        <div v-show="!parsing" class="upload-layout">
          <!-- 左侧：账户选择 + 上传区域 -->
          <div class="upload-left">
            <!-- 账户选择模块 -->
            <div class="ledger-select-area">
              <el-form label-position="top">
                <el-form-item style="display: block">
                  <template #label>
                    <span class="text-base font-medium text-gray-700">
                      请选择交易所属账户 <span class="required-star">*</span>
                    </span>
                  </template>
                  <div class="flex gap-3 items-start">
                    <el-select
                      ref="ledgerSelectRef"
                      v-model="selectedLedgerId"
                      placeholder="请选择交易所属账户"
                      class="flex-1"
                      style="min-width: 220px"
                      :disabled="parsing"
                      size="large"
                      @change="onLedgerSelected"
                      @blur="ledgerTouched = true"
                    >
                      <el-option
                        v-for="ledger in ledgers"
                        :key="ledger.id"
                        :label="ledger.name"
                        :value="ledger.id"
                      />
                    </el-select>
                    <el-button
                      :disabled="parsing"
                      @click="showCreateLedgerDialog = true"
                      size="large"
                      plain
                      class="add-ledger-btn"
                    >
                      <IconifyIconOffline icon="ep:plus" class="mr-1" />
                      添加新账户
                    </el-button>
                  </div>
                  <p class="ledger-hint">
                    <IconifyIconOffline icon="ep:info-filled" class="mr-1" style="font-size: 14px; vertical-align: middle;" />
                    选择账户后，上传的交易将自动归属到该账户下
                  </p>
                  <div v-if="!selectedLedgerId && ledgerTouched" class="ledger-error">
                    <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
                    请先选择交易所属账户
                  </div>
                </el-form-item>
              </el-form>
            </div>

            <!-- 上传区域 -->
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
                  <div class="upload-content" :class="{ 'is-dragover': isDragover }">
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
                      :disabled="!selectedLedgerId"
                      @click="handleUploadClick"
                    >
                      点击上传
                    </el-button>
                    <p class="upload-hint">
                      {{ selectedMode === 'ths' ? '同花顺历史交割单导出文件' : '使用标准模板格式的文件' }}
                    </p>
                    <p class="upload-format-info">支持 XLS、XLSX、CSV ｜ 最大 10MB</p>
                  </div>
                </template>
              </el-upload>
            </div>
          </div>

          <!-- 右侧：格式说明卡片 -->
          <div v-if="formatGuides[selectedMode]" class="upload-right">
            <div class="format-guide">
              <div class="format-guide-header">
                <IconifyIconOffline icon="ep:info-filled" class="format-guide-icon" />
                <span>{{ formatGuides[selectedMode].title }}</span>
              </div>
              <ol class="format-guide-list">
                <li v-for="(tip, index) in formatGuides[selectedMode].tips" :key="index">{{ tip }}</li>
              </ol>
              <div v-if="selectedMode === 'ths'" class="format-guide-footer">
                <a href="#" @click.prevent="showMoreBrokers">查看更多券商导出指南</a>
              </div>
            </div>
          </div>
        </div>

        <!-- 新建账户弹窗 -->
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

      <!-- 步骤3：预览与修正（左右分栏重构） -->
      <div v-else-if="currentStep === 2" class="step3-container">
        <!-- 顶部信息栏 -->
        <div class="step3-header">
          <el-button size="default" @click="currentStep = 1">返回上一步</el-button>
          <span class="header-ledger">导入账户：{{ selectedLedgerName }}</span>
          <div class="header-actions ml-auto flex items-center gap-3">
            <el-button size="default" @click="toggleAllocationPanel">
              <IconifyIconOffline icon="ep:setting" class="mr-1"/>
              {{ showAllocationGroupPanel ? '收起配置' : '设置配置目标' }}
            </el-button>
          </div>
        </div>

        <!-- 主体区域：左侧面板 + 右侧表格 -->
        <div class="step3-body">
          <!-- 左侧面板区 -->
          <div class="step3-left" :class="{ collapsed: !showLeftPanel }">
            <!-- 问题摘要面板 -->
            <div class="summary-panel">
              <div class="summary-cards">
                <div class="summary-card summary-card--success">
                  <div class="summary-card-header">
                    <span class="summary-card-title">已校验</span>
                  </div>
                  <div class="summary-card-count">
                    <el-tag type="success" size="default">{{ validRowsCount }} 条</el-tag>
                  </div>
                  <div class="summary-card-body">
                    <p>代码已匹配、字段完整、无重复，可直接导入</p>
                    <p class="summary-card-hint" v-if="validRowsCount === selectedCount && validRowsCount > 0">
                      已选中全部有效数据
                    </p>
                    <p class="summary-card-hint" v-else-if="validRowsCount > 0 && selectedCount > 0">
                      已选中 {{ selectedCount }} / {{ validRowsCount }} 条有效数据
                    </p>
                  </div>
                </div>
                <div v-if="duplicateCount > 0" class="summary-card summary-card--warning">
                  <div class="summary-card-header">
                    <span class="summary-card-title">重复项</span>
                  </div>
                  <div class="summary-card-count">
                    <el-tag type="warning" size="small">{{ duplicateCount }} 条</el-tag>
                  </div>
                  <div class="summary-card-body">
                    <p>已自动跳过，如需保留请手动勾选</p>
                  </div>
                </div>

                <div v-if="blockedCount > 0 || errorCount > 0" class="summary-card summary-card--danger">
                  <div class="summary-card-header">
                    <span class="summary-card-title">待确认</span>
                  </div>
                  <div class="summary-card-count">
                    <el-tag type="danger" size="small">{{ blockedCount + errorCount }} 条</el-tag>
                  </div>
                  <div class="summary-card-body">
                    <p v-if="errorCount > 0">· {{ errorCount }} 条解析错误</p>
                    <p>信息缺失（数量或价格为空）</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- 批量修正按钮（独立且显眼） -->
            <div v-if="(blockedCount + errorCount) > 0" class="batch-fix-bar">
              <el-button
                :type="showBatchFix ? '' : 'primary'"
                @click="toggleBatchFix"
                size="default"
              >
                <IconifyIconOffline icon="ep:setting" class="mr-1"/>
                {{ showBatchFix ? '收起批量修正' : '批量修正问题数据' }}
              </el-button>
              <span class="batch-fix-hint" v-if="!showBatchFix">
                {{ blockedCount + errorCount }} 条待处理
              </span>
            </div>

            <!-- 分类批量修正面板 -->
            <div v-if="showBatchFix && problemCategories.length > 0" class="batch-fix-panel">
              <div
                v-for="cat in problemCategories"
                :key="cat.key"
                class="batch-fix-group"
                :class="{ 'batch-fix-group--active': isCategoryActive(cat.key) }"
                @click="filterByCategory(cat.key)"
              >
                <div class="batch-fix-card">
                  <!-- 卡片头部：标题 + 数量标签 -->
                  <div class="batch-fix-card-header">
                    <div class="batch-fix-info">
                      <span class="batch-fix-label">{{ cat.label }}</span>
                      <span class="batch-fix-desc">{{ getCategoryDesc(cat.key) }}</span>
                    </div>
                    <el-tag
                      size="small"
                      effect="dark"
                      :type="getCategoryTagType(cat.key, cat.count)"
                    >
                      {{ cat.count }} 条
                    </el-tag>
                  </div>

                  <!-- 卡片操作区 -->
                  <div class="batch-fix-actions" @click.stop>
                    <template v-if="cat.key === 'missingCode'">
                      <el-input
                        v-model="batchCodeInput"
                        placeholder="输入证券代码"
                        size="small"
                        class="batch-fix-input"
                      />
                      <el-button
                        type="primary"
                        size="small"
                        class="batch-fix-btn batch-fix-btn--primary"
                        @click="batchFillCode(cat.rows, batchCodeInput)"
                      >
                        应用到当前 {{ cat.count }} 条
                      </el-button>
                    </template>
                    <!-- 数据不一致卡片 -->
                    <template v-if="cat.key === 'mismatch'">
                      <el-tooltip content="以数量×价格为准修正金额" placement="top">
                        <el-button
                          type="primary"
                          size="small"
                          class="batch-fix-btn batch-fix-btn--primary"
                          @click="batchFixAmount(cat.rows)"
                        >
                          修正金额
                        </el-button>
                      </el-tooltip>
                    </template>
                    <template v-if="cat.key === 'missingQtyPrice'">
                      <el-button
                        type="primary"
                        size="small"
                        class="batch-fix-btn batch-fix-btn--primary"
                        @click="showFullTable = true; showProblemOnly = true"
                      >
                        展开查看并手动编辑
                      </el-button>
                    </template>
                    <el-button
                      size="small"
                      class="batch-fix-btn batch-fix-btn--secondary"
                      @click="skipCategory(cat.rows)"
                    >
                      跳过当前
                    </el-button>
                  </div>
                </div>
              </div>
            </div>

          </div>

          <!-- 配置目标分组设置面板 -->
          <div v-if="showAllocationGroupPanel" class="allocation-group-panel">
            <div class="allocation-group-header">
              <span class="font-weight-500">按产品类型设置配置目标</span>
              <div class="flex items-center gap-3">
                <el-button size="small" text @click="showAllocationGroupPanel = false">取消</el-button>
              </div>
            </div>

            <!-- 已选行批量设置 -->
            <div class="allocation-group-item" v-if="selectedCount > 0">
              <div class="allocation-group-info">
                <span class="allocation-group-label">已选行批量设置</span>
                <el-tag size="small" type="primary">{{ selectedCount }} 条已选</el-tag>
              </div>
              <el-select
                model-value=""
                placeholder="选择配置目标"
                size="small"
                style="width: 140px"
                @change="(val: string) => batchSetAllocation(val)"
              >
                <el-option
                  v-for="opt in allocationOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </div>

            <div class="allocation-group-list">
              <div
                v-for="group in currentAllocationGroups"
                :key="group.type || group.account"
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
                  @change="(val: string) => applyAllocationGroupSetting(group, val)"
                >
                  <el-option
                    v-for="opt in allocationOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </div>

              <div v-if="currentAllocationGroups.length === 0" class="text-center text-gray-400 py-4">
                所有数据已手动设置配置目标，无需分组调整
              </div>
            </div>
          </div>

          <!-- 分隔条（侧边把手） -->
          <div class="step3-divider" @click="toggleLeftPanel"
               :title="showLeftPanel ? '收起侧边栏' : '展开数据摘要'">
            <IconifyIconOffline
              :icon="showLeftPanel ? 'ep:d-arrow-left' : 'ep:d-arrow-right'"
              class="divider-icon"
            />
            <span v-if="!showLeftPanel" class="divider-text">摘要</span>
          </div>

          <!-- 右侧表格区 -->
          <div class="step3-right">
            <!-- 表格控制栏 -->
            <div class="table-controls">
              <div class="flex items-center gap-4 flex-wrap">
                <el-select v-model="tableStatusFilter" placeholder="按状态筛选" size="small" style="width: 130px"
                           clearable>
                  <el-option label="全部" value=""/>
                  <el-option label="待补全" value="blocked"/>
                  <el-option label="重复" value="duplicate"/>
                  <el-option label="错误" value="error"/>
                  <el-option label="正常" value="normal"/>
                </el-select>
                <el-switch v-model="showProblemOnly" active-text="只看问题数据" inactive-text="全部数据"/>
                <el-input v-model="tableFilterKeyword" placeholder="搜索代码或名称" size="small" style="width: 200px"
                          clearable/>
                <el-select v-model="tableTypeFilter" placeholder="按类型筛选" size="small" style="width: 140px"
                           clearable multiple collapse-tags collapse-tags-tooltip>
                  <el-option v-for="(label, key) in typeLabels" :key="key" :label="label" :value="key"/>
                </el-select>
              </div>
              <div class="flex items-center gap-2">
                <!-- 新增：一键取消重复行勾选 -->
                <el-button
                  v-if="duplicateCount > 0"
                  size="small"
                  :type="duplicatesHandled ? 'warning' : ''"
                  @click="deselectAllDuplicates"
                >
                  {{ duplicatesHandled ? '恢复查看重复行' : '取消显示重复行' }}
                </el-button>
                <!-- 原有折叠/展开按钮 -->
                <el-button type="text" @click="showFullTable = !showFullTable">
                  <IconifyIconOffline :icon="showFullTable ? 'ep:arrow-up' : 'ep:arrow-down'"/>
                  {{ showFullTable ? '收起列表' : '展开列表' }}
                </el-button>
              </div>
            </div>

            <!-- 高亮图例 -->
            <div v-if="showFullTable && (duplicateCount > 0 || blockedCount > 0)" class="highlight-legend">
              <span class="legend-item">
                <span class="legend-color legend-color--duplicate"></span>
                黄色背景：已识别的重复数据，已自动跳过，可手动勾选保留
              </span>
              <span class="legend-item" v-if="blockedCount > 0">
                <span class="legend-color legend-color--blocked"></span>
                红色左边框：信息缺失，需补全数量或价格后可导入
              </span>
            </div>

            <!-- 数据表格 -->
            <div v-show="showFullTable" class="table-wrapper">
              <!-- 数据表格 -->
              <div v-show="showFullTable" class="table-wrapper">
                <el-table
                    :data="filteredPagedData"
                    row-key="_rowKey"
                    :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
                    default-expand-all
                    stripe
                    size="default"
                    :row-class-name="getRowClassName"
                    :cell-class-name="getCellClassName"
                    @selection-change="handleSelectionChange"
                  >
                  <!-- 复选框列（自定义表头全选） -->
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
                        <el-checkbox :model-value="false" disabled/>
                      </el-tooltip>
                      <el-checkbox
                        v-else
                        :model-value="isRowSelected(row)"
                        :disabled="row.is_duplicate || row.error || isRowBlocked(row)"
                        @change="(val: boolean) => handleRowCheckboxChange(row, val)"
                      />
                    </template>
                  </el-table-column>

                  <!-- 其余列通过配置数组循环生成 -->
                  <el-table-column
                    v-for="col in tableColumns"
                    :key="col.prop || col.type"
                    v-bind="col"
                  >
                    <!-- 状态列 -->
                    <template v-if="col.slot === 'status'" #default="{ row }">
                      <el-tag v-if="row.is_duplicate" type="warning" size="small">重复</el-tag>
                      <el-tag v-else-if="row.error" type="danger" size="small">错误</el-tag>
                      <el-tag v-else-if="isRowBlocked(row)" type="info" size="small">待补全</el-tag>
                      <el-tag v-else type="success" size="small">正常</el-tag>
                    </template>

                    <!-- 产品信息列（名称 + 代码上下排列） -->
                    <template v-else-if="col.slot === 'product'" #default="{ row }">
                      <div class="product-cell">
                        <span class="product-name">{{ row.name || row.symbol || '--' }}</span>
                        <span class="product-code"># {{ row.symbol || '--' }}</span>
                      </div>
                    </template>

                    <!-- 操作类型列（操作名 + 类型标签） -->
                    <template v-else-if="col.slot === 'opType'" #default="{ row }">
                      <div class="op-type-cell">
                        <span class="op-type-label">{{ row.op_type_label || '--' }}</span>
                        <el-tag
                          v-if="!row.is_merged"
                          :color="getTypeColor(row.type)"
                          size="small"
                          class="type-tag-inline"
                        >
                          {{ typeLabels[row.type] || row.type || '未知' }}
                        </el-tag>
                      </div>
                    </template>
                    <!-- 数量列（可编辑 popover） -->
                    <template v-else-if="col.slot === 'quantity'" #default="{ row }">
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
                            {{ row.symbol }} {{ row.name }} - <span class="font-semibold">数量</span>
                          </div>
                          <el-input-number
                            v-model="row.quantity"
                            size="default"
                            :precision="4"
                            :min="0"
                            class="w-full"
                            controls-position="right"
                            ref="inputRef"
                            @vue:mounted="(el: any) => el?.input?.focus()"
                          />
                          <div class="flex justify-end gap-2">
                            <el-button type="primary" size="small" @click.stop="finishEdit(row, 'quantity', true)">
                              确认
                            </el-button>
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

                    <!-- 单价列（可编辑 popover） -->
                    <template v-else-if="col.slot === 'price'" #default="{ row }">
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
                            {{ row.symbol }} {{ row.name }} - <span class="font-semibold">价格</span>
                          </div>
                          <el-input-number
                            v-model="row.price"
                            size="default"
                            :precision="4"
                            :min="0"
                            class="w-full"
                            controls-position="right"
                            ref="inputRef"
                            @vue:mounted="(el: any) => el?.input?.focus()"
                          />
                          <div class="flex justify-end gap-2">
                            <el-button type="primary" size="small" @click.stop="finishEdit(row, 'price', true)">确认
                            </el-button>
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

                    <!-- 配置目标列 -->
                    <template v-else-if="col.slot === 'allocation'" #default="{ row }">
                      <el-select
                        v-model="row.allocation"
                        size="small"
                        :disabled="row.is_cash_transfer || row.is_duplicate || row.error"
                        @change="onRowAllocationChange(row)"
                      >
                        <el-option
                          v-for="opt in allocationOptions"
                          :key="opt.value"
                          :label="opt.label"
                          :value="opt.value"
                        />
                      </el-select>
                    </template>
                  </el-table-column>

                </el-table>

                <!-- 分页 -->
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
        </div>

        <!-- 底部固定操作栏 -->
        <div class="fixed-action-bar">
          <div class="action-content">
            <span class="selected-count">
              本次导入识别 {{ totalRows }} 条，已选中 <strong>{{ selectedCount }}</strong> 条有效数据
              <span v-if="(duplicateCount + blockedCount + errorCount) > 0">
                ，另有 {{ duplicateCount + blockedCount + errorCount }} 条待处理
                （{{ duplicateCount }}条重复 / {{ blockedCount }}条待补全<template v-if="errorCount > 0"> / {{
                  errorCount
                }}条错误</template>）
              </span>
            </span>
            <div class="flex gap-3">
              <el-button
                v-if="(duplicateCount + blockedCount + errorCount) > 0"
                @click="importNormalOnly"
                :loading="importing"
              >
                仅导入校验通过的数据
              </el-button>
              <el-button
                type="primary"
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
      </div>

      <!-- 步骤4：导入完成 -->
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
                  <div class="number-divider"/>
                  <div class="number-item">
                    <span class="number-value" style="color: var(--text-tertiary)">{{ skippedCount }}</span>
                    <span class="number-label">笔跳过</span>
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
                  <el-alert :title="`导入过程中 ${importErrors.length} 条记录因以下原因被跳过`" type="warning"
                            :closable="false" show-icon>
                    <template #default>
                      <div v-for="group in errorSummary" :key="group.reason" class="error-group">
                        <p class="error-reason">{{ group.reason }}（共 {{ group.count }} 条）</p>
                        <el-collapse v-if="group.items.length > 1" class="error-collapse">
                          <el-collapse-item
                            :title="`涉及标的：${group.items.slice(0, 3).join('、')}${group.items.length > 3 ? ' 等' : ''}`">
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

                <!-- 智能建议：更新持仓市价 -->
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
                        <router-link to="/asset/investment/stocks" class="text-primary">检查持仓市价</router-link>
                        ，以确保资产计算准确。
                      </p>
                    </template>
                  </el-alert>
                </div>

              </div>
              <div class="flex gap-2 justify-center mt-6">
                <el-button type="primary" @click="goToTransactions" v-if="importedCount > 0 || orphanCount > 0">
                  查看交易流水
                </el-button>
                <el-button @click="resetImport">继续导入</el-button>
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
                        <el-collapse-item
                          :title="`涉及标的：${group.items.slice(0, 3).join('、')}${group.items.length > 3 ? ' 等' : ''}`">
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
import {parseFile, confirmImport as confirmImportApi} from '@/api/importer';
import type {UploadRequestOptions} from 'element-plus';
import {ArrowDown, Warning} from '@element-plus/icons-vue'
import {ref, onMounted, computed, watch, nextTick} from 'vue';
import {useRouter} from 'vue-router';
import {ElMessage} from 'element-plus';
import {getLedgers, createLedger as createLedgerApi} from '@/api/ledger';
import type {LedgerItem} from '@/api/ledger';

defineOptions({name: 'Inventory'});

const router = useRouter();

// 基础状态
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
const fileSize = ref('');
const editingRowKey = ref<string | null>(null);
const newLedgerAllocation = ref('longterm');

const formatGuides: Record<string, { title: string; tips: string[] }> = {
  standard: {
    title: '标准模板格式说明',
    tips: [
      '下载标准模板 CSV 文件，按表头填写数据',
      '代码格式：A股 6 位数字，港股 5 位数字，美股字母代码',
      '日期格式：YYYY-MM-DD，如 2026-01-15',
      '操作类型：buy=买入, sell=卖出, dividend=分红',
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
};

// 配置目标分组设置
const showAllocationGroupPanel = ref(false);
// 账户相关
const ledgers = ref<LedgerItem[]>([]);
const selectedLedgerId = ref<number | null>(null);
const showCreateLedgerDialog = ref(false);
const newLedgerName = ref('');
const ledgerTouched = ref(false);

const activeCategoryFilter = ref('');  // 'missingCode' | 'mismatch' | ''

// 配置目标选项
const allocationOptions = [
  {value: 'liquid', label: '活钱'},
  {value: 'stable', label: '稳健底仓'},
  {value: 'longterm', label: '长期增值'},
  {value: 'speculative', label: '高风险博弈'},
  {value: 'security', label: '保险保障'},
];

// 类型映射
const typeLabels: Record<string, string> = {
  stock: '股票',
  fund: '基金',
  bond: '可转债',
  crypto: '虚拟货币',
  saving: '银行存款',
  cash: '现金',
  money_fund: '现金理财',
  reverse_repo: '逆回购',
  static: '其他',
};

// 类型 → 颜色变量映射（使用全局莫兰迪色板）
const typeColorMap: Record<string, string> = {
  stock: 'var(--tag-muted-blue)',
  fund: 'var(--tag-rose-taupe)',
  bond: 'var(--tag-warm-sand)',
  etf: 'var(--tag-mint-green)',
  crypto: 'var(--tag-caramel)',
  saving: 'var(--tag-sage-green)',
  cash: 'var(--tag-periwinkle)',
  static: 'var(--tag-stone-gray)',
};

const templateDownloadUrl = '/templates/showbuy_import_template.csv';

// 分页
const currentPage = ref(1);
const pageSize = ref(50);
const totalRows = ref(0);
const inputRef = ref<any>(null);

// 选择与筛选
const selectedKeys = ref<Set<string>>(new Set());
const isAllSelected = ref(false);
const isIndeterminate = ref(false);
const showProblemOnly = ref(false);
const tableFilterKeyword = ref('');
const tableTypeFilter = ref<string[]>([]);
const tableStatusFilter = ref('');

// UI 控制
const showFullTable = ref(true);
const showBatchFix = ref(false);
const batchCodeInput = ref('');
const showLeftPanel = ref(false);  // 控制左侧面板显示/折叠

// 导入错误
const importErrors = ref<any[]>([]);

// 新增状态：标记重复数据是否已被用户处理
const duplicatesHandled = ref(false);

const ledgerSelectRef = ref<any>(null);

const importModes = [
  {key: 'standard', icon: 'ep:document', title: '标准模板', description: '使用 ShowBuy 通用模板导入交易记录'},
  {key: 'ths', icon: 'ep:bank-card', title: '同花顺交割单', description: '直接上传同花顺导出的历史交割单'},
];

const selectedLedgerName = computed(() => {
  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  return ledger?.name || '未选择';
});

// 拖拽状态
const isDragover = ref(false);

// 按产品类型分组的配置目标
const allocationGroupsByType = computed(() => {
  const groups: Record<string, { label: string; count: number; currentAllocation: string }> = {};

  previewData.value.forEach(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer || isRowBlocked(row) || row._allocationManual) return;

    const type = row.type || 'unknown';
    if (!groups[type]) {
      groups[type] = {
        label: typeLabels[type] || type,
        count: 0,
        currentAllocation: row.allocation || 'longterm',
      };
    }
    groups[type].count++;
  });

  return Object.entries(groups).map(([type, data]) => ({type, ...data}));
});

const currentAllocationGroups = computed(() => allocationGroupsByType.value);


// 表格列配置
const tableColumns = computed(() => [
  {prop: 'status', label: '状态', width: 80, slot: 'status', align: 'center'},
  {prop: 'product', label: '产品信息', width: 160, slot: 'product'},
  {prop: 'opType', label: '操作类型', width: 110, slot: 'opType'},
  {prop: 'trade_date', label: '日期', width: 100},
  {prop: 'quantity', label: '数量', width: 90, slot: 'quantity', align: 'right', cellClass: 'cell-highlight-quantity'},
  {prop: 'price', label: '单价', width: 90, slot: 'price', align: 'right', cellClass: 'cell-highlight-price'},
  {prop: 'amount', label: '交易金额', width: 120, align: 'right'},
  {prop: 'fee', label: '手续费', width: 90, align: 'right', cellClass: 'cell-highlight-fee'},
  {prop: 'contract_id', label: '合同编号', width: 110},
  {prop: 'net_amount', label: '发生金额', width: 120, align: 'right'},
  {prop: 'allocation', label: '配置目标', width: 120, slot: 'allocation'},
  {prop: 'notes', label: '备注', minWidth: 120},
]);

// 问题分类
const problemCategories = computed(() => {
  const cats = [
    {key: 'missingCode', label: '代码未匹配', count: 0, rows: [] as any[]},
    {key: 'missingQtyPrice', label: '数量或价格缺失', count: 0, rows: [] as any[]},
    {key: 'mismatch', label: '数据不一致', count: 0, rows: [] as any[]},
  ];

  previewData.value.forEach(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer) return;
    const qty = Number(row.quantity);
    const prc = Number(row.price);
    const amt = Number(row.amount);

    if (!row.symbol || row.symbol === 'UNKNOWN') {
      cats[0].rows.push(row);
      cats[0].count++;
    } else if (isRowBlocked(row)) {
      cats[1].rows.push(row);
      cats[1].count++;
    } else if (!isNaN(qty) && qty > 0 && !isNaN(prc) && prc > 0 && !isNaN(amt) && Math.abs(qty * prc - amt) > 0.01) {
      cats[2].rows.push(row);
      cats[2].count++;
    }
  });

  return cats.filter(c => c.count > 0);
});

const errorSummary = computed(() => {
  const groups: Record<string, { count: number; items: string[] }> = {};
  importErrors.value.forEach(err => {
    const reason = err.error || '未知错误';
    const name = err.name || err.symbol || '--';
    if (!groups[reason]) groups[reason] = {count: 0, items: []};
    groups[reason].count++;
    groups[reason].items.push(name);
  });
  return Object.entries(groups).map(([reason, data]) => ({reason, ...data}));
});

const nothingImported = computed(() => importedCount.value === 0 && orphanCount.value === 0 && importErrors.value.length > 0);

const validRowsCount = ref(0);

const blockedCount = computed(() => {
  return previewData.value.filter(row => isRowBlocked(row) && !row.is_duplicate && !row.error && !row.is_cash_transfer).length;
});

// 是否建议更新持仓市价
const showPriceUpdateTip = computed(() => {
  if (importedCount.value === 0) return false;
  // 检查导入成功的记录中是否包含股票或基金
  return previewData.value.some(row => {
    if (!selectedKeys.value.has(row._rowKey)) return false;
    if (row.is_duplicate || row.error || row.is_cash_transfer || isRowBlocked(row)) return false;
    return ['stock', 'fund', 'etf', 'bond'].includes(row.type);
  });
});

// 分页过滤
const filteredPagedData = computed(() => {
  let list = previewData.value;

  if (tableStatusFilter.value === 'blocked') {
    list = list.filter(row => isRowBlocked(row) && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  } else if (tableStatusFilter.value === 'duplicate') {
    list = list.filter(row => row.is_duplicate);
  } else if (tableStatusFilter.value === 'error') {
    list = list.filter(row => row.error);
  } else if (tableStatusFilter.value === 'normal') {
    list = list.filter(row => !row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer);
  }

  if (activeCategoryFilter.value === 'missingCode') {
    list = list.filter(row => (!row.symbol || row.symbol === 'UNKNOWN') && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  } else if (activeCategoryFilter.value === 'mismatch') {
    list = list.filter(row => {
      if (row.is_duplicate || row.error || row.is_cash_transfer) return false;
      const qty = Number(row.quantity);
      const prc = Number(row.price);
      const amt = Number(row.amount);
      return !isNaN(qty) && qty > 0 && !isNaN(prc) && prc > 0 && !isNaN(amt) && Math.abs(qty * prc - amt) > 0.01;
    });
  }

  if (showProblemOnly.value) {
    list = list.filter(row => {
      // 已被用户处理的重复行，不在问题视图中显示
      if (row.is_duplicate && row._duplicateHandled) return false;
      return isRowBlocked(row) || row.error || row.is_duplicate || row.isEditingQty || row.isEditingPrice;
    });
  }
  if (tableFilterKeyword.value) {
    const kw = tableFilterKeyword.value.toLowerCase();
    list = list.filter(row =>
      String(row.symbol).toLowerCase().includes(kw) ||
      String(row.name).toLowerCase().includes(kw)
    );
  }
  if (tableTypeFilter.value.length > 0) {
    list = list.filter(row => tableTypeFilter.value.includes(row.type));
  }
  // ── 合并 link_group_id 相同的关联行 ──
  const mergedList: any[] = [];
  const processedGroupIds = new Set<string>();

  for (const row of list) {
    const groupId = row.link_group_id;

    if (groupId && !processedGroupIds.has(groupId)) {
      // 找到同一组的所有行
      const groupRows = list.filter(r => r.link_group_id === groupId);

      if (groupRows.length === 2) {
        const interestRow = groupRows.find(r => r.op_type === 'dividend') || groupRows[0];
        const taxRow = groupRows.find(r => r.op_type === 'tax') || groupRows[1];
        const netAmount = (interestRow.amount || 0) + (taxRow.amount || 0);

        // 生成父行唯一 key，避免与子行冲突
        const parentKey = `merged_${interestRow._rowKey}`;
        // 子行保留原始的 _rowKey，确保树形渲染正确
        const detailRows = groupRows.map(r => ({ ...r }));

        mergedList.push({
          ...interestRow,
          _rowKey: parentKey,
          amount: netAmount,
          net_amount: netAmount,
          is_merged: true,
          children: detailRows,   // 树形子节点
          notes: `税前${interestRow.amount?.toFixed(2)}元，扣税${Math.abs(taxRow.amount || 0).toFixed(2)}元，实收${netAmount.toFixed(2)}元`,
          op_type_label: '利息收入',
        });
        processedGroupIds.add(groupId);
      } else {
        // 不完整的配对，原样显示
        groupRows.forEach(r => mergedList.push(r));
        processedGroupIds.add(groupId);
      }
    } else if (!groupId) {
      // 无关联的普通行
      mergedList.push(row);
    }
  }

  const start = (currentPage.value - 1) * pageSize.value;
  return mergedList.slice(start, start + pageSize.value);
});

const filteredTotal = computed(() => {
  let list = previewData.value;

  if (tableStatusFilter.value === 'blocked') {
    list = list.filter(row => isRowBlocked(row) && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  } else if (tableStatusFilter.value === 'duplicate') {
    list = list.filter(row => row.is_duplicate);
  } else if (tableStatusFilter.value === 'error') {
    list = list.filter(row => row.error);
  } else if (tableStatusFilter.value === 'normal') {
    list = list.filter(row => !row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer);
  }

  if (activeCategoryFilter.value === 'missingCode') {
    list = list.filter(row => (!row.symbol || row.symbol === 'UNKNOWN') && !row.is_duplicate && !row.error && !row.is_cash_transfer);
  } else if (activeCategoryFilter.value === 'mismatch') {
    list = list.filter(row => {
      if (row.is_duplicate || row.error || row.is_cash_transfer) return false;
      const qty = Number(row.quantity);
      const prc = Number(row.price);
      const amt = Number(row.amount);
      return !isNaN(qty) && qty > 0 && !isNaN(prc) && prc > 0 && !isNaN(amt) && Math.abs(qty * prc - amt) > 0.01;
    });
  }

  if (showProblemOnly.value) {
    list = list.filter(row => {
      // 已被用户处理的重复行，不在问题视图中显示
      if (row.is_duplicate && row._duplicateHandled) return false;
      return isRowBlocked(row) || row.error || row.is_duplicate || row.isEditingQty || row.isEditingPrice;
    });
  }
  if (tableFilterKeyword.value) {
    const kw = tableFilterKeyword.value.toLowerCase();
    list = list.filter(row =>
      String(row.symbol).toLowerCase().includes(kw) ||
      String(row.name).toLowerCase().includes(kw)
    );
  }
  if (tableTypeFilter.value.length > 0) {
    list = list.filter(row => tableTypeFilter.value.includes(row.type));
  }
  // ── 合并 link_group_id 相同的关联行（与 filteredPagedData 一致）──
  const mergedList: any[] = [];
  const processedGroupIds = new Set<string>();

  for (const row of list) {
    const groupId = row.link_group_id;

    if (groupId && !processedGroupIds.has(groupId)) {
      const groupRows = list.filter(r => r.link_group_id === groupId);

      if (groupRows.length === 2) {
        // 合并为一行，只用于计数
        mergedList.push(groupRows[0]);
        processedGroupIds.add(groupId);
      } else {
        groupRows.forEach(r => mergedList.push(r));
        processedGroupIds.add(groupId);
      }
    } else if (!groupId) {
      mergedList.push(row);
    }
  }

  return mergedList.length;
});

const selectedCount = computed(() => selectedKeys.value.size);

function isRowSelected(row: any): boolean {
  return selectedKeys.value.has(row._rowKey);
}

function handleRowCheckboxChange(row: any, checked: boolean) {
  if (checked) {
    selectedKeys.value.add(row._rowKey);
  } else {
    selectedKeys.value.delete(row._rowKey);
  }
  selectedKeys.value = new Set(selectedKeys.value);
  updateSelectAllState();
}

function applyAllocationGroupSetting(group: any, allocation: string) {
  previewData.value.forEach(row => {
    if (row.is_duplicate || row.error || row.is_cash_transfer || isRowBlocked(row)) return;
    if (row.type === group.type) {
      row.allocation = allocation;
      row._allocationManual = true;
    }
  });
  previewData.value = [...previewData.value];
  ElMessage.success(`已将「${group.label}」的配置目标设为「${allocationOptions.find(o => o.value === allocation)?.label}」`);
}

// 增强的闪烁动画函数（修复版）
function flashLedgerSelect() {
  // 直接通过 DOM 查询获取 el-select 的根元素，更稳定
  const el = document.querySelector('.ledger-select-area .el-select');
  if (!el) return;
  el.classList.add('ledger-select-flash');
  setTimeout(() => {
    el.classList.remove('ledger-select-flash');
  }, 600);
}

// 处理未选账户时的上传点击
function handleUploadClick() {
  if (!selectedLedgerId.value) {
    ElMessage.warning('请先选择交易所属账户');
    flashLedgerSelect();
    ledgerTouched.value = true;
  }
}

function recalcValidRowsCount() {
  validRowsCount.value = previewData.value.filter(
    row => !row.is_duplicate && !row.error && !isRowBlocked(row) && !row.is_cash_transfer
  ).length;
}

// 在 beforeUpload 中捕获文件名和大小
function beforeUpload(file: File) {
  if (!selectedLedgerId.value) {
    ElMessage.warning('请先选择交易所属账户');
    flashLedgerSelect();
    ledgerTouched.value = true;
    return false;
  }
  const allowedExtensions = ['.csv', '.xls', '.xlsx'];
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (!allowedExtensions.includes(ext)) {
    ElMessage.error('仅支持 CSV 或 Excel 文件');
    return false;
  }
  fileSize.value = formatFileSize(file.size);
  return true;
}

function showMoreBrokers() {
  ElMessage.info('更多券商导出指南正在整理中，敬请期待');
}

// 工具函数
function addRowKeys(data: any[]) {
  return data.map((item, idx) => ({...item, _rowKey: `row_${idx}`}));
}

function getTypeColor(type: string): string {
  return typeColorMap[type] || 'var(--tag-stone-gray)';
}

function isRowBlocked(row: any): boolean {
  if (row.is_cash_transfer || row.error || row.is_duplicate) return false;
  if (row.op_type === 'tax') return false;  // 扣税行不校验
  if (row.type === 'money_fund' || row.type === 'reverse_repo') return false; // 现金管理产品不校验
  const qty = Number(row.quantity);
  const prc = Number(row.price);
  return (isNaN(qty) || qty <= 0) || (isNaN(prc) || prc <= 0);
}

// 格式化文件大小
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

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

// 行内编辑
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
  const wasBlocked = isRowBlocked(row);
  if (!save) {
    row[field] = row._oldValue;
  } else {
    smartFill(row, field);
  }
  delete row._oldValue;
  if (field === 'quantity') row.isEditingQty = false;
  else if (field === 'price') row.isEditingPrice = false;

  editingRowKey.value = null;

  const nowBlocked = isRowBlocked(row);
  if (wasBlocked && !nowBlocked) {
    selectedKeys.value.add(row._rowKey);
    selectedKeys.value = new Set(selectedKeys.value);
    if (showProblemOnly.value) {
      showProblemOnly.value = false;
      ElMessage.success('数据已修正，已自动切换为全部数据视图');
    } else {
      ElMessage.success('数据已自动勾选');
    }
  } else if (!wasBlocked && nowBlocked) {
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

function getCellClassName({row, column}: { row: any; column: any }) {
  const prop = column.property;
  // 代码未匹配（在产品信息列中体现，但产品信息列没有 prop，我们用 symbol 字段的列）
  // 注意：我们现在没有单独的 symbol 列，产品信息列 slot='product' 也没有 prop
  // 所以代码未匹配的高亮改为在整行高亮时体现，或者通过 row 的状态标签
  // 这里暂对数量、价格、手续费字段做高亮

  if (prop === 'quantity' && isRowBlocked(row) && !row.is_duplicate && !row.error) {
    return 'cell-blocked';
  }
  if (prop === 'price' && isRowBlocked(row) && !row.is_duplicate && !row.error) {
    return 'cell-blocked';
  }
  if (prop === 'fee') {
    const fee = parseFloat(row.fee);
    if (isNaN(fee) || fee === null || fee === undefined) {
      return 'cell-missing';
    }
  }
  return '';
}

function saveAllEditingRows() {
  previewData.value.forEach(row => {
    if (row.isEditingQty) finishEdit(row, 'quantity', true);
    if (row.isEditingPrice) finishEdit(row, 'price', true);
  });
}

function toggleAllocationPanel() {
  if (showAllocationGroupPanel.value) {
    // 当前已展开 → 收起
    showAllocationGroupPanel.value = false;
  } else {
    // 当前未展开 → 展开配置目标面板，同时关闭批量修正面板
    showAllocationGroupPanel.value = true;
    showBatchFix.value = false;
    showLeftPanel.value = true;
  }
}


function toggleBatchFix() {
  if (showBatchFix.value) {
    showBatchFix.value = false;
  } else {
    showBatchFix.value = true;
    showAllocationGroupPanel.value = false;
    showLeftPanel.value = true;
  }
}

function toggleLeftPanel() {
  if (showLeftPanel.value) {
    // 收起左侧面板，同时关闭批量修正面板
    showLeftPanel.value = false;
    showBatchFix.value = false;
  } else {
    showLeftPanel.value = true;
  }
}

function getRowClassName({row}: { row: any }) {
  if (row.is_duplicate) return 'row-duplicate';
  if (row.error || isRowBlocked(row)) return 'row-blocked';
  return '';
}

// 批量修正
async function batchFillCode(rows: any[], code: string) {
  if (!code.trim()) return ElMessage.warning('请输入有效的证券代码');
  rows.forEach(r => {
    r.symbol = code.trim();
  });
  // 强制刷新表格
  recalcValidRowsCount();
  updateSelectAllState();
  await nextTick();
  previewData.value = [...previewData.value];
  ElMessage.success(`已为 ${rows.length} 条记录设置代码「${code}」`);
}

async function batchFixAmount(rows: any[]) {
  rows.forEach(r => {
    const qty = Number(r.quantity);
    const prc = Number(r.price);
    if (!isNaN(qty) && !isNaN(prc)) {
      r.amount = parseFloat((qty * prc).toFixed(2));
    }
  });
  recalcValidRowsCount();
  updateSelectAllState();
  await nextTick();
  previewData.value = [...previewData.value];
  ElMessage.success(`已修正 ${rows.length} 条记录的金额`);
}

async function skipCategory(rows: any[]) {
  rows.forEach(row => {
    selectedKeys.value.delete(row._rowKey);
  });
  selectedKeys.value = new Set(selectedKeys.value);
  updateSelectAllState();
  await nextTick();
  previewData.value = [...previewData.value];
  ElMessage.success(`已跳过 ${rows.length} 条记录`);
}


// 步骤控制
function selectMode(mode: string) {
  selectedMode.value = mode;
  currentStep.value = 1;
}

function goToManualEntry() {
  router.push('/asset/inventory/investment/manual');
}

async function fetchLedgers() {
  try {
    const res = await getLedgers();
    ledgers.value = (res as any).data ?? [];
  } catch (e) {
    console.error(e);
  }
}

function onLedgerSelected(id: number) {
  ledgerTouched.value = false;
}

async function createLedger() {
  const name = newLedgerName.value.trim();
  if (!name) return;
  try {
    const res = await createLedgerApi({
      name,
      default_allocation: newLedgerAllocation.value,
    });
    await fetchLedgers();
    const newId = (res as any).data?.id;
    if (newId) {
      selectedLedgerId.value = newId;
    }
    showCreateLedgerDialog.value = false;
    newLedgerName.value = '';
    newLedgerAllocation.value = 'longterm';
    ElMessage.success(`已添加账户「${name}」`);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '添加失败');
  }
}

async function handleUpload(options: UploadRequestOptions) {
  const file = options.file as File;

  if (!selectedLedgerId.value) {
    ElMessage.warning('请先选择一个账户');
    return;
  }

  parsing.value = true;
  await new Promise(resolve => setTimeout(resolve, 50));

  try {
    const res = await parseFile(file, selectedMode.value);
    const rawData = (res as any).data ?? [];
    previewData.value = addRowKeys(rawData);
    totalRows.value = previewData.value.length;
    duplicateCount.value = (res as any).duplicate_count ?? 0;
    errorCount.value = (res as any).error_count ?? 0;

    const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
    const ledgerName = ledger?.name || '默认账户';
    const defaultAlloc = ledger?.default_allocation || 'longterm';

    previewData.value.forEach(row => {
      row.account_name = row.account_name && row.account_name !== '默认证券账户' ? row.account_name : ledgerName;
      if (!row.allocation || !row._allocationManual) {
        row.allocation = defaultAlloc;
      }
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
    showFullTable.value = true;
    // 新增解析完成提示
    ElMessage({
        message: `解析完成，共识别 ${totalRows.value} 条记录`,
        type: 'success',
        duration: 5000,
      });

    currentStep.value = 2;
    options.onSuccess(res);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '文件解析失败');
    options.onError(e);
  } finally {
    parsing.value = false;
  }
}

async function confirmImport() {
  if (!selectedLedgerId.value) {
    ElMessage.warning('请先在第二步选择导入账户');
    return;
  }

  const ledger = ledgers.value.find(l => l.id === selectedLedgerId.value);
  if (!ledger) {
    ElMessage.error('所选账户无效，请重新选择');
    return;
  }

  saveAllEditingRows();

  const defaultAlloc = ledger.default_allocation || 'longterm';
  previewData.value.forEach(row => {
    if (!row._allocationManual) {
      row.allocation = defaultAlloc;
    }
    row.account_name = ledger.name;
  });

  const rowsToImport = previewData.value.filter(row => {
    return selectedKeys.value.has(row._rowKey) && !row.is_duplicate && !row.error && !row.is_cash_transfer && !isRowBlocked(row);
  });

  if (rowsToImport.length === 0) {
    ElMessage.warning('没有可导入的有效记录');
    return;
  }

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

function onRowAllocationChange(row: any) {
  row._allocationManual = true;
}

// 获取分类描述文案
function getCategoryDesc(key: string): string {
  const descMap: Record<string, string> = {
    missingCode: '系统无法识别以下证券代码，请手动输入正确代码或跳过',
    missingQtyPrice: '以下记录的数量或价格缺失，需要补全后才能导入',
    mismatch: '以下记录的金额与数量×价格的计算结果不符，建议修正',
  };
  return descMap[key] || '';
}

// 获取标签类型（根据数量区分优先级）
function getCategoryTagType(key: string, count: number): 'danger' | 'warning' | 'success' | 'info' {
  if (count > 200) return 'danger';
  if (count > 50) return 'warning';
  if (count > 10) return 'info';
  return 'success';
}

function isCategoryActive(categoryKey: string): boolean {
  if (categoryKey === 'missingCode') return activeCategoryFilter.value === 'missingCode';
  if (categoryKey === 'missingQtyPrice') return tableStatusFilter.value === 'blocked' && activeCategoryFilter.value === '';
  if (categoryKey === 'mismatch') return activeCategoryFilter.value === 'mismatch';
  return false;
}

function batchSetAllocation(target: string) {
  let applied = 0;
  previewData.value.forEach(row => {
    if (selectedKeys.value.has(row._rowKey) && !row.is_cash_transfer && !row.is_duplicate && !row.error) {
      row.allocation = target;
      row._allocationManual = true;
      applied++;
    }
  });
  previewData.value = [...previewData.value];
  if (applied > 0) {
    ElMessage.success(`已将 ${applied} 条已选数据的配置目标设为「${allocationOptions.find(o => o.value === target)?.label}」`);
  } else {
    ElMessage.warning('没有可设置的数据，请先勾选需要设置的行');
  }
}

function deselectAllDuplicates() {
  if (duplicatesHandled.value) {
    // 当前是"已处理"状态 → 恢复全部重复行
    previewData.value.forEach(row => {
      if (row.is_duplicate) {
        row._duplicateHandled = false;
        // 恢复勾选状态回到初始：重复行默认不勾选，所以这里也不勾选
        // 但要让它们重新出现在问题视图中
      }
    });
    duplicatesHandled.value = false;
    recalcValidRowsCount();
    updateSelectAllState();
    ElMessage.success('已恢复全部重复数据');
  } else {
    // 当前是"未处理"状态 → 取消全部重复行
    previewData.value.forEach(row => {
      if (row.is_duplicate) {
        row._duplicateHandled = true;
        selectedKeys.value.delete(row._rowKey);
      }
    });
    selectedKeys.value = new Set(selectedKeys.value);
    duplicatesHandled.value = true;
    recalcValidRowsCount();
    updateSelectAllState();
    ElMessage.success(`已取消 ${duplicateCount.value} 条重复数据的展示`);
  }
}

function filterByCategory(categoryKey: string) {
  // 先确保表格展开，左侧面板可保持打开
  showFullTable.value = true;
  showProblemOnly.value = false;  // 关闭"只看问题数据"，避免冲突
  tableStatusFilter.value = '';   // 清空状态筛选

  // 根据分类 key 设置筛选
  if (categoryKey === 'missingCode') {
    // 代码缺失：暂无对应的 tableStatusFilter，可用 showProblemOnly 或临时变量
    // 这里我们设置一个自定义筛选标记
    activeCategoryFilter.value = 'missingCode';
    tableStatusFilter.value = '';
  } else if (categoryKey === 'missingQtyPrice') {
    tableStatusFilter.value = 'blocked';
    activeCategoryFilter.value = '';
  } else if (categoryKey === 'mismatch') {
    activeCategoryFilter.value = 'mismatch';
    tableStatusFilter.value = '';
  }
}

function goToTransactions() {
  router.push('/transactions');
}

function goToLiabilityForm() {
  router.push("/asset/asset-entry");
}

function goToImportGuide() {
  ElMessage.info('当前支持买入、卖出、分红操作类型。其他类型（如 other）暂不支持，请联系我们或手动录入。');
}

function reimport() {
  resetImport();
}

function resetImport() {
  currentStep.value = 0;
  selectedMode.value = 'standard';
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
}

function handleSizeChange(val: number) {
  pageSize.value = val;
  currentPage.value = 1;
}

function handlePageChange(val: number) {
  currentPage.value = val;
}

function handleSelectionChange() {
}

// 监听 el-upload 的拖拽事件（通过原生事件）
// 可以在组件挂载后给 upload 区域添加监听
onMounted(async () => {
  await fetchLedgers();
});

</script>

<style scoped>
/* ============================================
   1. 步骤 1 - 模式选择卡片
   ============================================ */
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

/* 模板下载区域 */
.template-download-area {
  margin-top: 24px;
  text-align: center;
}

.template-download-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.template-link {
  font-size: 14px;
  color: var(--color-primary);
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.template-link:hover {
  text-decoration: underline;
}

/* ============================================
   2. 步骤 2 - 左右分栏布局
   ============================================ */
.upload-step {
  padding: 8px 0;
  min-height: 420px;
}


/* 左右分栏容器 */
.upload-layout {
  display: flex;
  gap: 28px;
  align-items: flex-start;
  max-width: 1100px;
  margin: 0 auto;
}

/* 左侧：账户 + 上传 */
.upload-left {
  flex: 1;
  min-width: 0;
}

/* 右侧：格式说明 */
.upload-right {
  width: 300px;
  flex-shrink: 0;
}

/* 格式说明卡片（放在右侧后无需 margin-top） */
.upload-right .format-guide {
  margin-top: 0;
  padding: 20px;
  background: var(--bg-muted);
  border-radius: 10px;
  border: 1px solid var(--border-default);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

/* 格式说明列表 */
.format-guide-list {
  list-style: none;
  padding-left: 0;
  margin: 0;
  counter-reset: step-counter;
}

.format-guide-list li {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
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

.format-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
  margin-bottom: 14px;
}

.format-guide-icon {
  color: var(--color-primary);
  font-size: 18px;
}

.format-guide-footer {
  margin-top: 12px;
  font-size: 13px;
  padding-top: 10px;
  border-top: 1px solid var(--border-default);
}

.format-guide-footer a {
  color: var(--color-primary);
}

/* 解析中骨架屏 */
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

/* 账户选择 */
.ledger-select-area {
  margin-bottom: 20px;
}

.ledger-select-area :deep(.el-form-item__content) {
  display: block !important;
}

.ledger-hint {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 12px;
  display: flex;
  align-items: center;
}

.ledger-error {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: var(--color-danger);
  margin-top: 8px;
  line-height: 1.5;
}

.add-ledger-btn {
  flex-shrink: 0;
}

.required-star {
  color: var(--color-danger);
  margin-left: 2px;
}

/* 上传组件 */
.upload-area-wrapper {
  /* 移除居中，左侧自然对齐 */
}

.golden-upload {
  width: 100%;
  max-width: 680px;
  height: 300px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  border: 2px dashed var(--border-default);
  border-radius: 14px;
  background: var(--bg-card);
  transition: all 0.3s;
}

.golden-upload:hover {
  border-color: var(--color-primary);
  background: var(--bg-hover);
}

.golden-upload :deep(.el-upload-dragger) {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  border: none;
  background: transparent;
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 20px;
}

.upload-content.is-dragover {
  background-color: var(--color-primary-20);
  border-radius: 14px;
}

.upload-icon {
  font-size: 48px;
  color: var(--text-disabled);
  margin-bottom: 12px;
  transition: color 0.2s;
}

.upload-icon.icon-active {
  color: var(--color-primary);
}

.upload-text {
  font-size: 16px;
  color: var(--text-primary);
  margin: 0 0 14px;
}

.upload-btn {
  margin-bottom: 12px;
}

.upload-btn:hover {
  opacity: 0.9;
}

.upload-btn:active {
  transform: scale(0.98);
}

.upload-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
}

.upload-format-info {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 6px;
}

/* 账户选择框闪烁动画 */
@keyframes ledgerFlash {
  0%, 100% { box-shadow: 0 0 0 0 rgba(122, 127, 168, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(122, 127, 168, 0.15); }
}

.ledger-select-flash :deep(.el-input__wrapper) {
  animation: ledgerFlash 0.6s ease-in-out 2;
  border-color: var(--color-primary) !important;
}

/* ============================================
   3. 步骤 3 - 预览与修正（整体布局）
   ============================================ */
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

/* 左右分栏 */
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

/* 分隔条（侧边把手） */
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

/* 右侧表格区 */
.step3-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  padding-left: 12px;
}

/* ============================================
   4. 左侧面板内容
   ============================================ */
/* 摘要面板 */
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
}

.summary-card-count {
  margin-bottom: 8px;
}

.summary-card-body p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.summary-card-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

/* 批量修正入口 */
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

/* 批量修正面板 */
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

/* 配置目标分组面板 */
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

/* 账户选择框闪烁动画 */
@keyframes ledgerFlash {
  0%, 100% { box-shadow: 0 0 0 0 rgba(122, 127, 168, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(122, 127, 168, 0.15); }
}

.ledger-select-flash :deep(.el-input__wrapper) {
  animation: ledgerFlash 0.6s ease-in-out 2;
  border-color: var(--color-primary) !important;
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

/* ============================================
   5. 表格区域
   ============================================ */
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

/* 表格高亮图例 */
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

/* 表格内部样式 */
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

.merge-expand-content {
  padding: 8px 16px;
  background-color: var(--bg-muted);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.merge-expand-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.merge-expand-type {
  color: var(--text-secondary);
  display: flex;
  align-items: center;
}

.merge-expand-amount {
  font-weight: 500;
  color: var(--text-primary);
}

/* 产品信息列 */
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

.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 操作类型列 */
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

/* 分页 */
.pagination-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* ============================================
   6. 底部固定操作栏
   ============================================ */
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

/* ============================================
   7. 步骤 4 - 导入完成
   ============================================ */
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

/* ============================================
   8. 全局步骤内容容器
   ============================================ */
.step-content {
  margin-top: 32px;
  min-height: 400px;
  /* 移除固定高度和 overflow: hidden，让第二步可以自然撑开或滚动 */
  height: auto;
  overflow: visible;
}
</style>
