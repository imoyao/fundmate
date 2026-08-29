<template>
  <div
    class="account-detail p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部操作栏 -->
    <div class="mb-4 flex justify-between items-center">
      <el-button text @click="$router.back()">
        <IconifyIconOffline icon="ep:arrow-left" class="mr-1" /> 返回
      </el-button>
      <div v-if="!isUnclassified && accountInfo" class="flex gap-2">
        <el-button @click="router.push({ name: 'InvestmentReconcile' })">
          <IconifyIconOffline icon="ep:data-analysis" class="mr-1" /> 对账
        </el-button>
        <el-button @click="openEditDialog">
          <IconifyIconOffline icon="ep:edit" class="mr-1" /> 编辑
        </el-button>
        <el-button v-if="accountInfo" @click="toggleArchiveDetail(accountInfo)">
          <IconifyIconOffline
            :icon="
              accountInfo.is_active === false ? 'ep:refresh-left' : 'ep:box'
            "
            class="mr-1"
          />
          {{ accountInfo.is_active === false ? "激活" : "归档" }}
        </el-button>
        <el-button
          v-if="!isUnclassified && holdingsTotal > 0"
          @click="openBatchMigrateDialog"
        >
          <IconifyIconOffline icon="ep:share" class="mr-1" /> 批量迁移
        </el-button>
        <div class="flex items-center gap-1">
          <el-button
            v-if="!isUnclassified && accountInfo"
            type="danger"
            text
            @click="openDeleteDialog(accountInfo)"
          >
            <IconifyIconOffline icon="ep:delete" class="mr-1" /> 删除
          </el-button>
          <IconifyIconOffline
            icon="ep:arrow-right"
            :style="{ color: 'var(--text-tertiary)' }"
          />
        </div>
      </div>
    </div>

    <!-- ✅ 核心修复：在外层增加一个 div，保证 <Transition> 动画时只有一个根节点 -->
    <div class="w-full">
      <!-- 加载状态：结构匹配的骨架屏。阈值控制（200ms）在 script 侧：请求太快则不显示，避免闪屏 -->
      <PageSkeleton
        v-if="loading && showSkeleton"
        :cards="3"
        :chart-cols="2"
        :table-rows="6"
      />

      <template v-else>
        <!-- 账户信息头部 -->
        <div class="mb-6 flex items-center justify-between">
          <div>
            <h2
              class="text-2xl font-bold"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ accountName }}
            </h2>
            <div class="flex items-center gap-2 mt-1">
              <el-tag size="small" type="info" round>{{ subTitle }}</el-tag>
              <template v-if="summaryData?.portfolio_name">
                <span
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  · 组合: {{ summaryData.portfolio_name }}</span
                >
              </template>
            </div>
          </div>
        </div>

        <!-- 核心概览卡片矩阵（2行 × 3列，或自适应） -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <!-- 1. 总资产 -->
          <div class="summary-card">
            <div class="summary-card__label">
              <IconifyIconOffline icon="ep:money" class="text-base" /> 总资产
            </div>
            <div class="summary-card__value">
              <MoneyDisplay
                :value="summaryData?.total_market_value || 0"
                :show-sign="false"
                :auto-color="false"
                size="lg"
              />
            </div>
          </div>

          <!-- 2. 持有盈亏（严格涨红跌绿） -->
          <div class="summary-card">
            <div class="summary-card__label">
              <IconifyIconOffline icon="ep:trend-charts" class="text-base" />
              持仓盈亏
            </div>
            <div class="summary-card__value">
              <MoneyDisplay :value="summaryData?.position_pnl || 0" size="lg" />
            </div>
          </div>

          <!-- 3. 持仓数量 + 资金余额（合并为一个卡片） -->
          <div class="summary-card">
            <div class="summary-card__label">
              <IconifyIconOffline icon="ep:box" class="text-base" /> 持仓与余额
            </div>
            <div class="mt-2 flex gap-6">
              <div>
                <div class="summary-card__sub-label">持仓数量</div>
                <div class="summary-card__sub-value">
                  {{ summaryData?.position_count || 0 }} 项
                </div>
              </div>
              <div>
                <div class="summary-card__sub-label">资金余额</div>
                <div class="summary-card__sub-value">
                  <MoneyDisplay
                    v-if="summaryData?.cash_balance != null"
                    :value="summaryData.cash_balance"
                    :show-sign="false"
                    :auto-color="false"
                  />
                  <template v-else>--</template>
                </div>
              </div>
            </div>

            <!-- 关联负债（仅银行账户且有负债时展示） -->
            <div
              v-if="
                summaryData?.ledger_type === 'bank' &&
                summaryData?.linked_liability > 0
              "
              class="summary-card__divider flex justify-between"
            >
              <span class="summary-card__sub-label">关联负债</span>
              <span
                class="text-xs font-semibold"
                :style="{ color: 'var(--color-danger-system)' }"
              >
                <MoneyDisplay
                  :value="-summaryData.linked_liability"
                  :auto-color="false"
                  size="xs"
                />
              </span>
            </div>

            <!-- 货币基金收益（仅基金账户展示，后端 summary 对该类型输出 money_fund_stats） -->
            <div
              v-if="summaryData?.ledger_type === 'fund'"
              class="summary-card__divider"
            >
              <div class="flex justify-between items-center">
                <span class="summary-card__sub-label">货基今日收益</span>
                <MoneyDisplay
                  v-if="moneyFundData"
                  :value="moneyFundData.today_income"
                  size="sm"
                />
                <span v-else class="summary-card__sub-label">--</span>
              </div>
              <div class="flex justify-between items-center mt-1">
                <span class="summary-card__sub-label">货基累计收益</span>
                <MoneyDisplay
                  v-if="moneyFundData"
                  :value="moneyFundData.total_income"
                  size="sm"
                />
                <span v-else class="summary-card__sub-label">--</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 类现金 / 中高风险（#1137）：借鉴支付宝但主次反转——
             本产品是投资工具，中高风险资产为主显示（--text-hero），
             类现金单独成块作辅助（--text-small），给用户明确的敞口暗示。 -->
        <CardBlock
          v-if="
            summaryData?.ledger_type === 'stock' ||
            summaryData?.ledger_type === 'fund' ||
            summaryData?.ledger_type === 'e_account'
          "
          class="mb-6"
        >
          <div class="cash-like">
            <div class="cash-like__main">
              <div class="cash-like__label">投资资产（中高风险）</div>
              <MoneyDisplay
                :value="summaryData?.investment_amount ?? 0"
                :show-sign="false"
                :auto-color="false"
                size="hero"
              />
            </div>

            <div class="cash-like__divider" />

            <div class="cash-like__aux">
              <span class="cash-like__aux-label">类现金</span>
              <MoneyDisplay
                :value="summaryData?.cash_like_amount ?? 0"
                :show-sign="false"
                :auto-color="false"
                size="sm"
                class="cash-like__aux-value"
              />
              <span class="cash-like__aux-detail">
                货基
                <MoneyDisplay
                  :value="summaryData?.money_fund_amount ?? 0"
                  :show-sign="false"
                  :auto-color="false"
                  size="xs"
                />
                · 现金
                <MoneyDisplay
                  :value="summaryData?.cash_amount ?? 0"
                  :show-sign="false"
                  :auto-color="false"
                  size="xs"
                />
                · 逆回购计入类现金，债券基金不计入
              </span>
            </div>
          </div>
        </CardBlock>

        <!-- 账户深度分析（规划中，敬请期待，详见内部工作记录 ledger-detail-info-redesign-plan-2026-08-27） -->
        <CardBlock class="mb-6">
          <div
            class="flex min-h-[160px] flex-1 items-center justify-center rounded-lg border border-dashed text-sm"
            :style="{
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-tertiary)'
            }"
          >
            账户深度分析（持仓集中度 / 行业分布 / 收益日历等）规划中，敬请期待
          </div>
        </CardBlock>
        <!-- Tab 切换 + 搜索同行（#982）：左 Tab 右搜索，共用一个输入框按当前 Tab 绑定 -->
        <el-card shadow="never">
          <div class="tabs-toolbar">
            <el-tabs
              v-model="activeTab"
              class="ledger-tabs"
              @tab-change="onTabChange"
            >
              <!-- 持仓明细 Tab -->
              <el-tab-pane label="持仓明细" name="holdings">
                <el-table
                  :data="holdingsList"
                  stripe
                  size="default"
                  :default-sort="{ prop: 'market_value', order: 'descending' }"
                  @row-click="openPositionDrawer"
                >
                  <el-table-column
                    label="产品信息"
                    min-width="150"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <ProductDisplay
                        :name="row.name"
                        :symbol="row.symbol"
                        :type-label="row.type_label"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="市值"
                    width="110"
                    align="right"
                    sortable
                    prop="market_value"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.market_value || 0"
                        :show-sign="false"
                        :auto-color="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="盈亏"
                    width="110"
                    align="right"
                    sortable
                    prop="pnl"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <MoneyDisplay :value="row.pnl || 0" size="sm" />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="盈亏率"
                    width="100"
                    align="right"
                    sortable
                    prop="pnl_rate"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.pnl_rate || 0"
                        :precision="2"
                        :show-currency="false"
                        suffix="%"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="配置目标"
                    width="90"
                    align="right"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <span
                        class="px-2 py-0.5 rounded-full text-xs"
                        :style="{ color: getAllocColor(row.allocation) }"
                      >
                        {{ row.allocation_label }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    v-if="!isUnclassified"
                    label="操作"
                    width="130"
                    fixed="right"
                  >
                    <template #default="{ row }">
                      <div
                        class="flex items-center gap-1"
                        style="white-space: nowrap"
                      >
                        <el-button
                          text
                          size="small"
                          @click.stop="
                            openMigrateDialog(row as LedgerHoldingRow)
                          "
                          >迁移</el-button
                        >
                        <el-button
                          text
                          size="small"
                          type="danger"
                          @click.stop="
                            confirmDeletePosition(row as LedgerHoldingRow)
                          "
                          >删除</el-button
                        >
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column
                    v-if="isUnclassified"
                    label="归入账户"
                    width="160"
                  >
                    <template #default="{ row }">
                      <el-select
                        v-model="assignMap[row.id]"
                        placeholder="选择账户"
                        size="small"
                        @change="handleAssign(row.id)"
                      >
                        <el-option
                          v-for="ledger in ledgers"
                          :key="ledger.id"
                          :label="ledger.name"
                          :value="ledger.id"
                        />
                      </el-select>
                    </template>
                  </el-table-column>
                </el-table>

                <div class="flex justify-end mt-4">
                  <el-pagination
                    v-model:current-page="holdingsPage"
                    :page-size="holdingsPageSize"
                    layout="prev, pager, next"
                    :total="holdingsTotal"
                    small
                    @current-change="loadHoldings"
                  />
                </div>
              </el-tab-pane>

              <!-- 交易记录 Tab -->
              <el-tab-pane label="交易记录" name="transactions">
                <el-table
                  :data="transactionsList"
                  stripe
                  size="default"
                  :default-sort="{ prop: 'confirm_date', order: 'descending' }"
                >
                  <el-table-column
                    prop="confirm_date"
                    label="日期"
                    width="110"
                    sortable
                  >
                    <template #default="{ row }">{{
                      formatDate(row.confirm_date)
                    }}</template>
                  </el-table-column>
                  <!-- 资产列宽统一 160（产品信息列宽度规范，见 docs/design/components.md） -->
                  <el-table-column
                    label="资产名称"
                    min-width="160"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <span class="txn-asset-name">{{
                        row.position_name
                      }}</span>
                      <span v-if="row.symbol" class="txn-asset-code">{{
                        row.symbol
                      }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="类型" width="80">
                    <template #default="{ row }">
                      <span :class="getTxnTypeClass(row.txn_type)">{{
                        txnTypeLabel(row.txn_type)
                      }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="价格" width="100" align="right">
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.price || 0"
                        :precision="pricePrecision(row.asset_type)"
                        :show-sign="false"
                        :show-currency="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="数量" width="80" align="right">
                    <template #default="{ row }">{{ row.quantity }}</template>
                  </el-table-column>
                  <el-table-column
                    label="金额"
                    width="120"
                    align="right"
                    sortable
                    prop="amount"
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.amount || 0"
                        :show-sign="false"
                        :auto-color="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="手续费"
                    width="80"
                    align="right"
                    prop="fee"
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.fee || 0"
                        :show-sign="false"
                        :auto-color="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    v-if="!isUnclassified"
                    label="操作"
                    width="140"
                    fixed="right"
                  >
                    <template #default="{ row }">
                      <div
                        class="flex items-center gap-1"
                        style="white-space: nowrap"
                      >
                        <el-button
                          text
                          size="small"
                          @click.stop="openEditTxnDialog(row as LedgerTxnRow)"
                          >编辑</el-button
                        >
                        <el-button
                          text
                          size="small"
                          type="danger"
                          @click.stop="confirmDeleteTxn(row as LedgerTxnRow)"
                          >删除</el-button
                        >
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <div
                  v-if="transactionsTotal === 0"
                  class="text-center py-8"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  暂无交易记录
                </div>
                <div v-if="transactionsTotal > 0" class="flex justify-end mt-4">
                  <el-pagination
                    v-model:current-page="transactionsPage"
                    :page-size="transactionsPageSize"
                    layout="prev, pager, next"
                    :total="transactionsTotal"
                    small
                    @current-change="loadTransactions"
                  />
                </div>
              </el-tab-pane>
            </el-tabs>
            <!-- 搜索框与 Tab 同行：按当前 Tab 绑定各自搜索词（#982） -->
            <el-input
              v-model="activeSearch"
              placeholder="搜索产品名称 / 代码"
              clearable
              class="tab-search-input"
              :prefix-icon="Search"
              @input="onSearchInput"
            />
          </div>
        </el-card>
      </template>

      <!-- 弹窗部分保持不变（略去重复代码，保留原有全部Dialog功能） -->
      <el-dialog
        v-model="showEditDialog"
        title="编辑账户"
        width="420px"
        destroy-on-close
      >
        <el-form :model="editForm" label-width="100px">
          <el-form-item label="账户名称" required>
            <el-input v-model="editForm.name" />
          </el-form-item>
          <el-form-item label="配置目标">
            <el-select
              v-model="editForm.default_allocation"
              class="w-full"
              clearable
            >
              <el-option
                v-for="opt in ALLOCATION_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
          <AccountFormFields
            v-model:ledger-type="editForm.ledger_type"
            v-model:linked-cash-id="editForm.linked_cash_ledger_id"
            v-model:linked-money-fund-code="editForm.linked_money_fund_code"
            v-model:auto-purchase-money-fund="editForm.auto_purchase_money_fund"
            v-model:portfolio-id="editForm.portfolio_id"
            v-model:fee-config="editForm.fee_config"
            v-model:sales-institution-id="editForm.sales_institution_id"
            :linked-money-fund-name="
              accountInfo?.linked_money_fund_name ?? null
            "
            :cash-ledgers="cashLedgers"
            :portfolio-list="portfolioList"
            :sales-institutions="salesInstitutions"
          />
          <el-form-item label="备注">
            <el-input v-model="editForm.notes" type="textarea" :rows="2" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showEditDialog = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleUpdate"
            >保存</el-button
          >
        </template>
      </el-dialog>

      <el-dialog
        v-model="migrateDialogVisible"
        title="迁移资产到其他账户"
        width="400px"
        destroy-on-close
      >
        <el-form label-width="80px">
          <el-form-item label="资产名称"
            ><span>{{
              migratingItem?.name || migratingItem?.symbol
            }}</span></el-form-item
          >
          <el-form-item label="目标账户">
            <el-select
              v-model="migrateTargetLedgerId"
              placeholder="选择同类型账户"
              class="w-full"
            >
              <el-option
                v-for="ledger in sameTypeLedgers"
                :key="ledger.id"
                :label="ledger.name"
                :value="ledger.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="migrateDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            :disabled="!migrateTargetLedgerId"
            @click="handleMigrate"
            >确认迁移</el-button
          >
        </template>
      </el-dialog>

      <el-dialog
        v-model="batchMigrateVisible"
        title="批量迁移持仓"
        width="400px"
        destroy-on-close
      >
        <p class="mb-4" :style="{ color: 'var(--text-secondary)' }">
          将账户「{{
            accountName
          }}」下的全部持仓与资产并入目标账户。先预览迁移方案，确认无误后才会写入。
        </p>
        <el-form label-width="80px">
          <el-form-item label="目标账户">
            <el-select
              v-model="batchTargetLedgerId"
              class="w-full"
              placeholder="选择同类型账户"
            >
              <!-- 同销售机构候选排最前并标注机构名（软优先，见 batchTargetOptions） -->
              <el-option
                v-for="opt in batchTargetOptions"
                :key="opt.ledger.id"
                :label="opt.ledger.name"
                :value="opt.ledger.id"
              >
                <div class="mig-option">
                  <span class="mig-option__name">{{ opt.ledger.name }}</span>
                  <span
                    v-if="opt.institutionName"
                    class="mig-option__inst"
                    :class="{ 'is-same': opt.sameInstitution }"
                    >{{ opt.institutionName }}</span
                  >
                </div>
              </el-option>
            </el-select>
          </el-form-item>
        </el-form>
        <p v-if="migrationBindingHint" class="mig-bind-hint">
          {{ migrationBindingHint }}
        </p>
        <template #footer>
          <el-button @click="batchMigrateVisible = false">取消</el-button>
          <el-button
            type="primary"
            :disabled="!batchTargetLedgerId"
            :loading="migrationPreviewLoading"
            @click="handlePreviewMigration"
          >
            预览迁移方案
          </el-button>
        </template>
      </el-dialog>

      <!-- 迁移确认决议面板（§7）：三区呈现 + conflict 行内联决议，全部决议完成后才可提交 -->
      <el-dialog
        v-model="migrationPanelVisible"
        title="确认迁移"
        width="720px"
        destroy-on-close
      >
        <div class="mig-summary">
          <div class="mig-route">
            <span class="mig-route__name">{{ accountName }}</span>
            <IconifyIconOffline
              icon="ep:arrow-right"
              class="mig-route__arrow"
            />
            <span class="mig-route__name">{{ targetLedgerName }}</span>
            <span class="mig-route__total"
              >共 {{ previewItems.length }} 项</span
            >
          </div>
          <p class="mig-note">
            关闭弹窗不会写入任何数据；确认后按下方决议执行迁移。
          </p>
        </div>

        <div class="mig-body">
          <!-- 区一：直接迁移 -->
          <section v-if="keepItems.length" class="mig-section">
            <header class="mig-section__head">
              <span class="mig-section__title">直接迁移</span>
              <span class="mig-section__count">{{ keepItems.length }} 项</span>
              <span class="mig-section__hint">来源数值原样并入目标账户</span>
            </header>
            <ul class="mig-rows">
              <li
                v-for="item in keepItems"
                :key="migrationRowKey(item)"
                class="mig-row"
              >
                <span class="mig-row__name">
                  {{ item.name }}
                  <span v-if="item.symbol" class="mig-row__symbol">{{
                    item.symbol
                  }}</span>
                </span>
                <span class="mig-row__values">{{ snapshotSummary(item) }}</span>
              </li>
            </ul>
          </section>

          <!-- 区二：重复自动丢弃 -->
          <section v-if="duplicateItems.length" class="mig-section">
            <header class="mig-section__head">
              <span class="mig-section__title">重复自动丢弃</span>
              <span class="mig-section__count"
                >{{ duplicateItems.length }} 项</span
              >
              <span class="mig-section__hint"
                >与目标账户数据一致，只保留一份、不相加</span
              >
            </header>
            <ul class="mig-rows">
              <li
                v-for="item in duplicateItems"
                :key="migrationRowKey(item)"
                class="mig-row"
              >
                <span class="mig-row__name">
                  {{ item.name }}
                  <span v-if="item.symbol" class="mig-row__symbol">{{
                    item.symbol
                  }}</span>
                </span>
                <span class="mig-row__values">{{ snapshotSummary(item) }}</span>
              </li>
            </ul>
          </section>

          <!-- 区三：需要你决议（conflict 行内联单选） -->
          <section v-if="conflictItems.length" class="mig-section">
            <header class="mig-section__head">
              <span class="mig-section__title">需要你决议</span>
              <span class="mig-section__count"
                >{{ conflictItems.length }} 项</span
              >
              <span class="mig-section__hint"
                >同一标的两边数值不一致，逐条选择处理方式</span
              >
            </header>

            <div
              v-for="item in conflictItems"
              :key="migrationRowKey(item)"
              class="mig-conflict"
            >
              <div class="mig-conflict__head">
                <span class="mig-conflict__name">
                  {{ item.name }}
                  <span v-if="item.symbol" class="mig-conflict__symbol">{{
                    item.symbol
                  }}</span>
                </span>
                <span class="mig-conflict__fields"
                  >不一致字段：{{ diffFieldLabels(item) }}</span
                >
              </div>

              <!-- 源/目标数值并排对比，差异字段高亮（警示色底） -->
              <div class="mig-compare">
                <span class="mig-compare__label" />
                <span class="mig-compare__tag">来源账户</span>
                <span class="mig-compare__tag">目标账户</span>
                <template v-for="cell in compareCells(item)" :key="cell.key">
                  <span class="mig-compare__label">{{ cell.label }}</span>
                  <span
                    class="mig-compare__value"
                    :class="{ 'is-diff': cell.diff }"
                    >{{ cell.source }}</span
                  >
                  <span
                    class="mig-compare__value"
                    :class="{ 'is-diff': cell.diff }"
                    >{{ cell.target }}</span
                  >
                </template>
              </div>

              <div class="mig-decide">
                <el-radio-group
                  v-model="resolutions[migrationRowKey(item)]"
                  size="small"
                >
                  <el-radio
                    v-for="opt in actionOptions(item)"
                    :key="opt.value"
                    :value="opt.value"
                    >{{ opt.label }}</el-radio
                  >
                </el-radio-group>
                <p v-if="actionNote(item)" class="mig-action-note">
                  {{ actionNote(item) }}
                </p>
              </div>
            </div>
          </section>

          <div v-if="!previewItems.length" class="mig-empty">
            两个账户之间没有需要迁移的数据。
          </div>
        </div>

        <template #footer>
          <div class="mig-footer">
            <span class="mig-footer__status">{{ footerStatusText }}</span>
            <div>
              <el-button @click="migrationPanelVisible = false">取消</el-button>
              <el-button
                type="primary"
                :disabled="!previewItems.length || pendingCount > 0"
                :loading="migrationCommitting"
                @click="handleCommitMigration"
                >确认迁移</el-button
              >
            </div>
          </div>
        </template>
      </el-dialog>

      <!-- 复用持仓明细抽屉同款的「编辑交易」弹窗，保证两处编辑字段一致（#982 体验统一） -->
      <TransactionEditDialog
        v-model="editTxnDialogVisible"
        :transaction="editingTxn"
        :asset-type="editingTxn?.asset_type"
        :symbol="editingTxn?.symbol"
        @saved="onTxnSaved"
      />

      <DeleteLedgerDialog
        v-model:visible="deleteDialogVisible"
        :ledger-id="deletingAccount?.id ?? 0"
        :ledger-name="deletingAccount?.name ?? ''"
        :position-count="holdingsTotal"
        @deleted="router.push({ name: 'AssetLedgers' })"
      />
    </div>
    <!-- 持仓明细抽屉 -->
    <PositionTransactionsDrawer
      v-model:visible="drawerVisible"
      :position-data="selectedPosition"
    />
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";

import PageSkeleton from "@/components/PageSkeleton/index.vue";
import {
  getLedgers,
  updateLedger,
  previewLedgerMigration,
  commitLedgerMigration,
  getLedgerSummary,
  getLedgerPositions,
  getLedgerTransactions,
  updateLedgerPosition,
  deleteLedgerPosition,
  archiveLedger,
  unarchiveLedger,
  getSalesInstitutions,
  type LedgerItem,
  type SalesInstitution,
  type MigrationPreviewItem,
  type MigrationPreviewResult,
  type MigrationAction,
  type MigrationResolution,
  type MigrationCommitPayload,
  type MigrationCommitResult,
  type MigrationConservation
} from "@/api/ledger";
import { deleteTransaction } from "@/api/transaction";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import { updateAsset } from "@/api/assets";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import {
  getLedgerTypeLabel,
  ALLOCATION_OPTIONS,
  txnTypeLabel
} from "@/constants";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";
import TransactionEditDialog from "./components/TransactionEditDialog.vue";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";

defineOptions({ name: "LedgerDetail" });

// ---- 类型定义（以接口实际返回为准） ----

/** 账户概览（GET /api/ledgers/{id}/summary/） */
interface LedgerSummaryData {
  ledger_id?: number;
  ledger_name?: string;
  ledger_type?: string;
  portfolio_name?: string | null;
  total_market_value?: number;
  position_pnl?: number;
  position_count?: number;
  cash_balance?: number | null;
  /** 类现金合计（#1137）：货基 + 逆回购 + 账户现金，口径同 XIRR EXCLUDED_ASSET_TYPES */
  cash_like_amount?: number;
  /** 中高风险投资资产 = 总市值 - 类现金（#1137） */
  investment_amount?: number;
  /** 类现金明细：货基市值 */
  money_fund_amount?: number;
  /** 类现金明细：账户现金 */
  cash_amount?: number;
  linked_liability?: number;
  type_distribution?: Record<string, number>;
}

/** 持仓行（GET /api/ledgers/{id}/positions/ 分页 items） */
interface LedgerHoldingRow {
  id: number;
  symbol?: string;
  name?: string | null;
  asset_type?: string;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  avg_price?: number;
  current_price?: number;
  allocation?: string | null;
  allocation_label?: string;
  quantity?: number;
  account_name?: string;
}

/** 交易行（GET /api/ledgers/{id}/transactions/ 分页 items） */
interface LedgerTxnRow {
  id: number;
  confirm_date?: string | null;
  trade_date?: string | null;
  asset_type?: string | null;
  ledger_id?: number;
  position_name?: string;
  symbol?: string;
  txn_type: string;
  price?: number;
  quantity?: number;
  amount?: number;
  fee?: number;
  notes?: string | null;
}

const route = useRoute();
const router = useRouter();

const ledgerId = computed(() => route.params.id as string);
const isUnclassified = computed(
  () => ledgerId.value === "unclassified" || !!route.query.name
);
const targetAccountName = computed(
  () => route.query.name as string | undefined
);

const loading = ref(true);
// 骨架屏阈值控制：请求 ≤200ms 返回时直接渲染内容、跳过骨架屏，避免"闪屏"（骨架刚出现就消失）
const showSkeleton = ref(false);
let skeletonTimer: ReturnType<typeof setTimeout> | null = null;
const ledgers = ref<LedgerItem[]>([]);
const portfolioList = ref<PortfolioItem[]>([]);
/** 基金销售机构候选（AMAC 名录，编辑账户可选关联） */
const salesInstitutions = ref<SalesInstitution[]>([]);
const assignMap = ref<Record<number, number>>({});
const deleteDialogVisible = ref(false);
const deletingAccount = ref<LedgerItem | null>(null);
const batchMigrateVisible = ref(false);
const batchTargetLedgerId = ref<number | null>(null);

// ── 批量迁移（两段式）：preview 只读出分类与冲突，用户在决议面板逐条选择后 commit ──
const migrationPanelVisible = ref(false);
const migrationPreviewLoading = ref(false);
const migrationCommitting = ref(false);
const migrationPreview = ref<MigrationPreviewResult | null>(null);
/** conflict 行决议表：行键 → 动作；打开面板时按系统建议初始化（§7 默认选中 suggestion） */
const resolutions = ref<Record<string, MigrationAction>>({});

/** 冲突行唯一键：持仓按 symbol，资产按名称+两级分类（与 commit 决议定位口径一致） */
function migrationRowKey(item: MigrationPreviewItem): string {
  return item.kind === "position"
    ? `position:${item.symbol}`
    : `asset:${item.name}|${item.major_category ?? ""}|${item.minor_category ?? ""}`;
}

const previewItems = computed(() => migrationPreview.value?.items ?? []);
const keepItems = computed(() =>
  previewItems.value.filter(i => i.classification === "keep")
);
const duplicateItems = computed(() =>
  previewItems.value.filter(i => i.classification === "duplicate")
);
const conflictItems = computed(() =>
  previewItems.value.filter(i => i.classification === "conflict")
);

/** 未决议数：全部归零前「确认迁移」保持禁用 */
const pendingCount = computed(
  () =>
    conflictItems.value.filter(
      item => !resolutions.value[migrationRowKey(item)]
    ).length
);

const targetLedgerName = computed(
  () =>
    ledgers.value.find(l => l.id === batchTargetLedgerId.value)?.name ||
    "目标账户"
);

/** 跨机构迁移放行标记：二次确认通过后置位，commit 时随请求携带 */
const allowCrossInstitution = ref(false);

/** 未绑定销售机构的统一提示文案（源或候选任一缺失时展示） */
const MIGRATION_UNBOUND_HINT =
  "该账户未绑定销售机构，建议先在账户设置中绑定，便于同机构自动归账";

interface MigrationTargetOption {
  ledger: LedgerItem;
  /** 绑定的销售机构 id（null=未绑定） */
  institutionId: number | null;
  /** 销售机构展示名（未绑定或名录缺失时为空串） */
  institutionName: string;
  /** 与源账本绑定同一销售机构 */
  sameInstitution: boolean;
}

/** 机构 id → 展示名（AMAC 名录，display_name 优先） */
function salesInstitutionName(id: number | null | undefined): string {
  if (!id) return "";
  const inst = salesInstitutions.value.find(s => s.id === id);
  return inst?.display_name || inst?.org_name || "";
}

/**
 * 批量迁移目标候选：同销售机构优先（软优先策略）——
 * 同机构候选排最前并标注机构名，其余保持原排序；不禁止跨机构，仅影响排序与默认选中。
 */
const batchTargetOptions = computed<MigrationTargetOption[]>(() => {
  const sourceInstId = accountInfo.value?.sales_institution_id ?? null;
  const candidates = sameTypeLedgers.value.map(l => ({
    ledger: l,
    institutionId: l.sales_institution_id ?? null,
    institutionName: salesInstitutionName(l.sales_institution_id),
    sameInstitution:
      !!sourceInstId &&
      !!l.sales_institution_id &&
      l.sales_institution_id === sourceInstId
  }));
  // 稳定分组：同机构在前，其余保持原顺序
  return [
    ...candidates.filter(c => c.sameInstitution),
    ...candidates.filter(c => !c.sameInstitution)
  ];
});

/** 未绑定提示：已选目标或源账本缺销售机构绑定时给出归账建议 */
const migrationBindingHint = computed(() => {
  const selected = batchTargetOptions.value.find(
    o => o.ledger.id === batchTargetLedgerId.value
  );
  if (
    (selected && !selected.institutionId) ||
    !accountInfo.value?.sales_institution_id
  ) {
    return MIGRATION_UNBOUND_HINT;
  }
  return "";
});

/** 跨机构判定：优先用 preview 返回的 institution 块；旧响应缺块时按本地绑定关系兜底 */
function resolveCrossInstitution(preview: MigrationPreviewResult): boolean {
  if (preview.institution) return preview.institution.cross_institution;
  const sourceInstId = accountInfo.value?.sales_institution_id ?? null;
  const targetInstId =
    ledgers.value.find(l => l.id === batchTargetLedgerId.value)
      ?.sales_institution_id ?? null;
  return !!sourceInstId && !!targetInstId && sourceInstId !== targetInstId;
}

/** 底栏状态文案：未决议时提示剩余量，就绪后预告将执行的动作计数 */
const footerStatusText = computed(() => {
  if (pendingCount.value > 0) {
    return `还有 ${pendingCount.value} 项待决议，决议完成后方可确认`;
  }
  const parts = [`${keepItems.value.length} 项直接迁移`];
  if (duplicateItems.value.length)
    parts.push(`${duplicateItems.value.length} 项丢弃重复`);
  if (conflictItems.value.length)
    parts.push(`${conflictItems.value.length} 项按决议处理`);
  return `已就绪：${parts.join("，")}`;
});

/**
 * 字段术语按资产类型区分（基金与股票是两个概念，各用专业口径）：
 * fund → 确认份额/确认净值/确认日期；stock 及其他非基金类型 → 持仓数量/成本价/成本日期。
 */
interface MigrationFieldTerms {
  quantity: string;
  avgPrice: string;
  confirmDate: string;
  /** 数量单位：基金为份，股票等为股 */
  quantityUnit: string;
  /** 合并说明中的加权平均措辞 */
  weightedAvgLabel: string;
  /** 合并说明中的日期取新措辞 */
  dateNewerLabel: string;
}

const FUND_FIELD_TERMS: MigrationFieldTerms = {
  quantity: "确认份额",
  avgPrice: "确认净值",
  confirmDate: "确认日期",
  quantityUnit: "份",
  weightedAvgLabel: "确认净值加权平均",
  dateNewerLabel: "确认日期取较新"
};

const STOCK_FIELD_TERMS: MigrationFieldTerms = {
  quantity: "持仓数量",
  avgPrice: "成本价",
  confirmDate: "成本日期",
  quantityUnit: "股",
  weightedAvgLabel: "成本加权平均",
  dateNewerLabel: "成本日期取较新"
};

/** 基金类持仓判定：仅 asset_type=fund 走净值口径，其余一律按数量/成本价口径 */
function isFundPosition(item: MigrationPreviewItem): boolean {
  return item.kind === "position" && item.asset_type === "fund";
}

function positionTerms(item: MigrationPreviewItem): MigrationFieldTerms {
  return isFundPosition(item) ? FUND_FIELD_TERMS : STOCK_FIELD_TERMS;
}

/** 冲突字段中文名（对比表与「不一致字段」标签共用），资产行只有金额 */
function fieldLabels(item: MigrationPreviewItem): Record<string, string> {
  const terms = positionTerms(item);
  return {
    quantity: terms.quantity,
    avg_price: terms.avgPrice,
    confirm_date: terms.confirmDate,
    amount: "金额"
  };
}

function diffFieldLabels(item: MigrationPreviewItem): string {
  const labels = fieldLabels(item);
  return (item.conflict_fields ?? []).map(f => labels[f] ?? f).join("、");
}

/**
 * 数字展示：至少 2 位小数（对齐设计规范）、最多 4 位——
 * 对比场景需区分 0.0001 份级差异，避免「显示相等实则不等」误导决议。
 */
function formatMigrationNumber(value: number, digits = 2): string {
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: 4
  });
}

function formatMigrationAmount(value: number): string {
  return `¥${value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

/** keep/duplicate 行的数值摘要：持仓按类型取术语（基金净值口径/股票成本口径），资产展示金额 */
function snapshotSummary(item: MigrationPreviewItem): string {
  if (item.kind === "asset") {
    return formatMigrationAmount(item.source.amount);
  }
  const terms = positionTerms(item);
  const parts = [
    `${formatMigrationNumber(item.source.quantity)} ${terms.quantityUnit}`,
    `${terms.avgPrice} ${formatMigrationNumber(item.source.avg_price)} 元`
  ];
  if (item.source.confirm_date)
    parts.push(formatDate(item.source.confirm_date));
  return parts.join(" · ");
}

interface MigrationCompareCell {
  key: string;
  label: string;
  source: string;
  target: string;
  /** 该字段在 conflict_fields 中 → 双方数值均高亮警示 */
  diff: boolean;
}

/** 源/目标并排对比单元格：持仓按类型比数量/成本（净值）/日期，资产只比金额 */
function compareCells(item: MigrationPreviewItem): MigrationCompareCell[] {
  const conflicts = item.conflict_fields ?? [];
  const labels = fieldLabels(item);
  if (item.kind === "asset") {
    return [
      {
        key: "amount",
        label: labels.amount,
        source: formatMigrationAmount(item.source.amount),
        target: item.target ? formatMigrationAmount(item.target.amount) : "—",
        diff: conflicts.includes("amount")
      }
    ];
  }
  const fmtDate = (d: string | null) => (d ? formatDate(d) : "—");
  return [
    {
      key: "quantity",
      label: labels.quantity,
      source: formatMigrationNumber(item.source.quantity),
      target: item.target ? formatMigrationNumber(item.target.quantity) : "—",
      diff: conflicts.includes("quantity")
    },
    {
      key: "avg_price",
      label: labels.avg_price,
      source: formatMigrationNumber(item.source.avg_price),
      target: item.target ? formatMigrationNumber(item.target.avg_price) : "—",
      diff: conflicts.includes("avg_price")
    },
    {
      key: "confirm_date",
      label: labels.confirm_date,
      source: fmtDate(item.source.confirm_date),
      target: item.target ? fmtDate(item.target.confirm_date) : "—",
      diff: conflicts.includes("confirm_date")
    }
  ];
}

const MIGRATION_ACTION_LABELS: Record<MigrationAction, string> = {
  keep_source: "保留源",
  keep_target: "保留目标",
  merge: "合并"
};

/** 决议选项：持仓三选，资产无合并语义仅二选（§5.2） */
function actionOptions(item: MigrationPreviewItem): {
  value: MigrationAction;
  label: string;
}[] {
  const base = [
    {
      value: "keep_source" as const,
      label: MIGRATION_ACTION_LABELS.keep_source
    },
    {
      value: "keep_target" as const,
      label: MIGRATION_ACTION_LABELS.keep_target
    }
  ];
  return item.kind === "position"
    ? [
        ...base,
        { value: "merge" as const, label: MIGRATION_ACTION_LABELS.merge }
      ]
    : base;
}

/**
 * 合并预计结果（§5.2.1 展示口径）：数量相加、加权平均（四舍五入到分）、日期取较新。
 * 措辞按资产类型切换（基金：确认净值加权平均/确认日期取较新；股票等：成本加权平均/成本日期取较新）。
 * 仅为选中态说明文案，入库口径以后端整数运算为准。
 */
function mergeNote(item: MigrationPreviewItem): string {
  if (item.kind !== "position") return "";
  const terms = positionTerms(item);
  const qSrc = item.source.quantity;
  const pSrc = item.source.avg_price;
  const qTgt = item.target?.quantity ?? 0;
  const pTgt = item.target?.avg_price ?? 0;
  const qty = qSrc + qTgt;
  // 展示口径允许浮点四舍五入到分；非入库计算路径
  const price =
    qty > 0 ? Math.round(((qSrc * pSrc + qTgt * pTgt) / qty) * 100) / 100 : 0;
  const newestDate = [item.source.confirm_date, item.target?.confirm_date]
    .filter((d): d is string => !!d)
    .sort()
    .pop();
  const parts = [
    `合并后：${formatMigrationNumber(qty)} ${terms.quantityUnit}`,
    `${terms.weightedAvgLabel}：${formatMigrationNumber(price)} 元`
  ];
  if (newestDate)
    parts.push(`${terms.dateNewerLabel}：${formatDate(newestDate)}`);
  return parts.join(" · ");
}

/** 当前决议的说明文案：merge 展示预计结果，二选一展示动作含义 */
function actionNote(item: MigrationPreviewItem): string {
  const action = resolutions.value[migrationRowKey(item)];
  if (!action) return "";
  if (action === "keep_source") return "以来源数值写入目标账户，目标原值被覆盖";
  if (action === "keep_target") return "保留目标数值，来源这笔不迁入";
  return mergeNote(item);
}

/** 默认决议：跟随系统建议（§5.2）；建议缺失或对行类型无意义时取安全兜底 */
function defaultResolution(item: MigrationPreviewItem): MigrationAction {
  const suggestion = item.suggestion;
  if (item.kind === "position") {
    return suggestion === "keep_target" || suggestion === "merge"
      ? suggestion
      : "merge";
  }
  // 资产无合并语义：默认保留源值（迁移语义是把源数据并入目标）
  return suggestion === "keep_target" ? "keep_target" : "keep_source";
}

function applyDefaultResolutions(items: MigrationPreviewItem[]) {
  const map: Record<string, MigrationAction> = {};
  for (const item of items) {
    if (item.classification !== "conflict") continue;
    map[migrationRowKey(item)] = defaultResolution(item);
  }
  resolutions.value = map;
}

/** 守恒结果转文案（成功提示用；未知键原样输出键名） */
function conservationText(conservation?: MigrationConservation): string {
  if (!conservation) return "";
  const labels: Record<string, string> = {
    source_out_positions: "源账本迁出份额",
    target_in_positions: "目标账本迁入份额",
    source_out_assets: "源账本迁出金额",
    target_in_assets: "目标账本迁入金额"
  };
  const parts: string[] = [];
  for (const [key, value] of Object.entries(conservation)) {
    if (typeof value !== "number") continue;
    parts.push(`${labels[key] ?? key} ${formatMigrationNumber(value)}`);
  }
  return parts.join("，");
}

/** 成功提示：各项计数 + 守恒结果；后端计数缺省时降级用本地预览计数 */
function commitSuccessMessage(result?: MigrationCommitResult): string {
  const total = result?.total ?? previewItems.value.length;
  const parts = [`共处理 ${total} 项`];
  if (result?.position_count != null)
    parts.push(`持仓 ${result.position_count} 项`);
  if (result?.asset_count != null) parts.push(`资产 ${result.asset_count} 项`);
  const conservation = conservationText(result?.conservation);
  if (conservation) parts.push(conservation);
  return `迁移完成：${parts.join("，")}`;
}

const showEditDialog = ref(false);
const saving = ref(false);
const editForm = ref({
  name: "",
  ledger_type: "bank",
  default_allocation: null as string | null,
  notes: "",
  portfolio_id: null as number | null,
  linked_cash_ledger_id: null as number | null,
  // 类现金产品绑定（#1137）：基金代码 + 自动申购开关
  linked_money_fund_code: null as string | null,
  auto_purchase_money_fund: false,
  fee_config: null as Record<string, unknown> | null,
  sales_institution_id: null as number | null
});

const drawerVisible = ref(false);
const selectedPosition = ref<LedgerHoldingRow | null>(null);

const migrateDialogVisible = ref(false);
const migratingItem = ref<LedgerHoldingRow | null>(null);
const migrateTargetLedgerId = ref<number | null>(null);

// 概览数据
const summaryData = ref<LedgerSummaryData | null>(null);

// 货币基金收益（仅基金账户拉取）
const moneyFundData = ref<MoneyFundIncomeData | null>(null);

async function loadMoneyFundIncome() {
  if (isUnclassified.value) return;
  moneyFundData.value = null;
  try {
    const res = await getMoneyFundIncome({
      scope: "ledger",
      ledger_id: Number(ledgerId.value)
    });
    moneyFundData.value = res.data;
  } catch (e) {
    // 禁止静默吞错：失败保留占位 "--"，仅记日志不打断页面
    console.error("货基收益加载失败", e);
  }
}

// 持仓 Tab 数据
const holdingsPage = ref(1);
const holdingsPageSize = 20;
const holdingsList = ref<LedgerHoldingRow[]>([]);
const holdingsTotal = ref(0);
// 名称/代码搜索（#982）：后端 LIKE 过滤，防抖后重置回第一页
const holdingsSearch = ref("");

// 交易 Tab 数据
const transactionsPage = ref(1);
const transactionsPageSize = 20;
const transactionsList = ref<LedgerTxnRow[]>([]);
const transactionsTotal = ref(0);
const transactionsSearch = ref("");

/** 搜索防抖（300ms）：变更即重置回第一页；输入框按当前 Tab 经 activeSearch 绑定 */
const searchTimers: Record<"holdings" | "transactions", number | undefined> = {
  holdings: undefined,
  transactions: undefined
};

/** 当前激活 Tab 的搜索词代理：一个输入框服务两个列表 */
const activeSearch = computed({
  get: () =>
    activeTab.value === "holdings"
      ? holdingsSearch.value
      : transactionsSearch.value,
  set: (v: string) => {
    if (activeTab.value === "holdings") holdingsSearch.value = v;
    else transactionsSearch.value = v;
  }
});

function onSearchInput() {
  const tab = activeTab.value === "holdings" ? "holdings" : "transactions";
  if (searchTimers[tab]) window.clearTimeout(searchTimers[tab]);
  searchTimers[tab] = window.setTimeout(() => {
    if (tab === "holdings") void loadHoldings(1);
    else void loadTransactions(1);
  }, 300);
}

const activeTab = ref("holdings");

// 交易编辑（复用持仓明细抽屉同款弹窗）
const editTxnDialogVisible = ref(false);
const editingTxn = ref<LedgerTxnRow | null>(null);

// 账户信息
const accountInfo = computed(
  () => ledgers.value.find(l => String(l.id) === ledgerId.value) || null
);
const accountName = computed(() => {
  if (targetAccountName.value) return targetAccountName.value;
  if (isUnclassified.value) return "未归置持仓";
  return (
    accountInfo.value?.name || summaryData.value?.ledger_name || "账户详情"
  );
});

const subTitle = computed(() => {
  if (isUnclassified.value) return "将以下资产关联到已有账户";
  const type = summaryData.value?.ledger_type || accountInfo.value?.ledger_type;
  return getLedgerTypeLabel(type) || "其他";
});

// 五笔钱颜色映射
function getAllocColor(alloc: string | null): string {
  const colorMap: Record<string, string> = {
    liquid: "var(--sankey-liquid)",
    stable: "var(--sankey-stable)",
    longterm: "var(--sankey-longterm)",
    speculative: "var(--sankey-speculative)",
    security: "var(--sankey-security)"
  };
  return colorMap[alloc || ""] || "var(--text-tertiary)";
}

// 关联现金账户列表
const cashLedgers = computed(() =>
  ledgers.value.filter(l => l.ledger_type === "bank")
);
const sameTypeLedgers = computed(() =>
  accountInfo.value
    ? ledgers.value.filter(
        l =>
          l.ledger_type === accountInfo.value!.ledger_type &&
          l.id !== Number(ledgerId.value)
      )
    : []
);

function openPositionDrawer(row: LedgerHoldingRow) {
  selectedPosition.value = row; // 把当前点击的持仓数据传进去
  drawerVisible.value = true; // 打开抽屉
}

async function handleGlobalRefresh() {
  console.log("收到全局记账完成信号，刷新当前页面数据...");
  if (!isUnclassified.value) {
    await loadSummary();
  }
  await loadHoldings();
  // 如果当前用户正在看的是交易记录 Tab，顺便刷新交易记录
  if (activeTab.value === "transactions") {
    await loadTransactions();
  }
}

async function loadSummary() {
  try {
    const res = await getLedgerSummary(Number(ledgerId.value));
    summaryData.value = (res as { data?: LedgerSummaryData })?.data ?? {};
  } catch (e) {
    ElMessage.error("概览加载失败");
  }
}

/** 销售机构候选加载：失败仅记日志，编辑弹窗下拉留空（可选字段不阻塞页面） */
async function loadSalesInstitutions() {
  try {
    const res = await getSalesInstitutions();
    salesInstitutions.value = res?.data ?? [];
  } catch (e) {
    console.error("销售机构名录加载失败", e);
  }
}

// 持仓加载
async function loadHoldings(page = 1) {
  holdingsPage.value = page;
  try {
    const res = await getLedgerPositions(Number(ledgerId.value), {
      page,
      per_page: holdingsPageSize,
      search: holdingsSearch.value.trim() || undefined
    });
    const result = (
      res as { data?: { items?: LedgerHoldingRow[]; total?: number } }
    )?.data;
    holdingsList.value = result?.items ?? [];
    holdingsTotal.value = result?.total ?? 0;
  } catch (e) {
    ElMessage.error("持仓加载失败");
  }
}

// 交易记录加载
async function loadTransactions(page = 1) {
  transactionsPage.value = page;
  try {
    const res = await getLedgerTransactions(Number(ledgerId.value), {
      page,
      per_page: transactionsPageSize,
      search: transactionsSearch.value.trim() || undefined
    });
    const result = (
      res as { data?: { items?: LedgerTxnRow[]; total?: number } }
    )?.data;
    transactionsList.value = result?.items ?? [];
    transactionsTotal.value = result?.total ?? 0;
  } catch (e) {
    ElMessage.error("交易记录加载失败");
  }
}

function onTabChange(tabName: string) {
  if (tabName === "holdings" && holdingsList.value.length === 0) {
    loadHoldings();
  } else if (
    tabName === "transactions" &&
    transactionsList.value.length === 0
  ) {
    loadTransactions();
  }
}

function getTxnTypeClass(type: string) {
  // 涨红跌绿：买入/存入=红（rise），卖出/取出=绿（fall），分红等中性=info
  if (type === "buy" || type === "deposit") return "text-[var(--color-rise)]";
  if (type === "sell" || type === "withdraw") return "text-[var(--color-fall)]";
  return "text-[var(--color-info)]";
}

async function handleMigrate() {
  if (!migrateTargetLedgerId.value || !migratingItem.value) return;
  const ledger = ledgers.value.find(l => l.id === migrateTargetLedgerId.value);
  if (!ledger) return;
  try {
    if (migratingItem.value.id > 100000) {
      await updateAsset(migratingItem.value.id - 100000, {
        account_name: ledger.name
      });
    } else {
      await updateLedgerPosition(
        Number(ledgerId.value),
        migratingItem.value.id,
        { account_name: ledger.name }
      );
    }
    ElMessage.success(`已迁移至「${ledger.name}」`);
    migrateDialogVisible.value = false;
    loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "迁移失败");
  }
}

function openMigrateDialog(row: LedgerHoldingRow) {
  migratingItem.value = row;
  migrateTargetLedgerId.value = null;
  migrateDialogVisible.value = true;
}

function openBatchMigrateDialog() {
  // 同机构软优先：存在同机构候选时默认选中第一个，减少跨机构误选
  const firstSame = batchTargetOptions.value.find(o => o.sameInstitution);
  batchTargetLedgerId.value = firstSame ? firstSame.ledger.id : null;
  allowCrossInstitution.value = false;
  migrationPreview.value = null;
  resolutions.value = {};
  batchMigrateVisible.value = true;
}

/** 第一步：调 preview 拉取迁移方案（只读不写库），成功后进入决议面板 */
async function handlePreviewMigration() {
  if (!batchTargetLedgerId.value) return;
  migrationPreviewLoading.value = true;
  try {
    const res = await previewLedgerMigration(
      Number(ledgerId.value),
      batchTargetLedgerId.value
    );
    const data = res.data ?? { items: [] };
    // 跨机构目标需二次确认；取消则停留在选择步，不进入决议面板
    if (resolveCrossInstitution(data)) {
      try {
        await ElMessageBox.confirm(
          "来源账户与目标账户绑定了不同销售机构。跨机构迁移会使交易归属与销售机构口径不一致，建议优先迁移到同机构账户。确定继续？",
          "跨机构迁移确认",
          {
            confirmButtonText: "继续迁移",
            cancelButtonText: "返回重选",
            type: "warning"
          }
        );
        allowCrossInstitution.value = true;
      } catch {
        // 用户取消：留在选择步重选目标
        return;
      }
    } else {
      allowCrossInstitution.value = false;
    }
    migrationPreview.value = data;
    applyDefaultResolutions(data.items);
    batchMigrateVisible.value = false;
    migrationPanelVisible.value = true;
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "预览失败，请稍后再试");
  } finally {
    migrationPreviewLoading.value = false;
  }
}

/** 由决议表组装 commit 入参：持仓按 symbol 三选一，资产按三级分类键二选一 */
function buildResolutions(): MigrationResolution[] {
  const list: MigrationResolution[] = [];
  for (const item of conflictItems.value) {
    const action = resolutions.value[migrationRowKey(item)];
    // 决议齐备才允许提交（按钮禁用兜底），此分支仅为类型收窄
    if (!action) continue;
    if (item.kind === "position") {
      list.push({ kind: "position", symbol: item.symbol, action });
    } else {
      list.push({
        kind: "asset",
        name: item.name,
        major_category: item.major_category ?? "",
        minor_category: item.minor_category ?? "",
        // 资产行无合并选项；状态异常落入 merge 时归一到保留源
        action: action === "merge" ? "keep_source" : action
      });
    }
  }
  return list;
}

/** 第二步：全部 conflict 决议完成后提交（单事务，失败整体回滚） */
async function handleCommitMigration() {
  if (!batchTargetLedgerId.value || pendingCount.value > 0) return;
  migrationCommitting.value = true;
  try {
    const payload: MigrationCommitPayload = {
      target_ledger_id: batchTargetLedgerId.value,
      resolutions: buildResolutions()
    };
    // 跨机构迁移仅在用户二次确认后携带放行标记
    if (allowCrossInstitution.value) payload.allow_cross_institution = true;
    const res = await commitLedgerMigration(Number(ledgerId.value), payload);
    migrationPanelVisible.value = false;
    ElMessage.success(commitSuccessMessage(res.data));
    // 主动清列表缓存并刷新：交易列表置空（切换 Tab 重拉）、持仓与概览同步更新
    transactionsList.value = [];
    transactionsTotal.value = 0;
    loadSummary();
    loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "迁移失败，源数据未变更");
  } finally {
    migrationCommitting.value = false;
  }
}

async function handleAssign(itemId: number) {
  const targetLedgerId = assignMap.value[itemId];
  if (!targetLedgerId) return;
  const ledger = ledgers.value.find(l => l.id === targetLedgerId);
  if (!ledger) return;
  try {
    if (itemId > 100000) {
      await updateAsset(itemId - 100000, { account_name: ledger.name });
    } else {
      await updateLedgerPosition(Number(ledgerId.value), itemId, {
        account_name: ledger.name
      });
    }
    ElMessage.success(`已归入「${ledger.name}」`);
    loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "归入失败");
  }
}

// 原有的 openEditDialog
async function openEditDialog() {
  if (!accountInfo.value) return;

  // 🔥 新增：点开编辑弹窗时，才去拉取关联的下拉列表数据
  try {
    // 为了不阻塞用户体验，可以加个 loading
    const [ledgerRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getPortfolios()
    ]);
    ledgers.value = ledgerRes.data ?? [];
    portfolioList.value =
      (portfolioRes as { data?: PortfolioItem[] })?.data ?? [];
  } catch (e) {
    ElMessage.error("加载关联账户或组合列表失败");
    return; // 加载失败不打开弹窗
  }

  // 构建编辑表单
  editForm.value = {
    name: accountInfo.value.name,
    ledger_type: accountInfo.value.ledger_type || "bank",
    default_allocation: accountInfo.value.default_allocation || null,
    notes: accountInfo.value.notes || "",
    portfolio_id: accountInfo.value.portfolio_id || null,
    linked_cash_ledger_id: accountInfo.value.linked_cash_ledger_id || null,
    linked_money_fund_code: accountInfo.value.linked_money_fund_code ?? null,
    auto_purchase_money_fund:
      accountInfo.value.auto_purchase_money_fund ?? false,
    fee_config: accountInfo.value.fee_config,
    sales_institution_id: accountInfo.value.sales_institution_id ?? null
  };
  showEditDialog.value = true;
}

/** 详情页归档/激活：归档给一次确认（保留全部数据、仅隐藏） */
async function toggleArchiveDetail(ledger: any) {
  const archiving = ledger.is_active !== false;
  try {
    if (archiving) {
      await ElMessageBox.confirm(
        `归档后「${ledger.name}」将从日常列表隐藏，但全部交易/持仓数据仍保留并计入收益。确定归档？`,
        "归档账户",
        { confirmButtonText: "归档", cancelButtonText: "取消", type: "warning" }
      );
    }
    if (archiving) {
      await archiveLedger(ledger.id);
      ElMessage.success(`已归档「${ledger.name}」`);
    } else {
      await unarchiveLedger(ledger.id);
      ElMessage.success(`已激活「${ledger.name}」`);
    }
    // 刷新账户信息（accountInfo 由 ledgers 派生）+ 顶部统计
    const res = await getLedgers(true);
    ledgers.value = res.data ?? [];
    await loadSummary();
    await loadHoldings();
  } catch (e: any) {
    if (e !== "cancel" && e?.action !== "cancel") {
      ElMessage.error(e?.message || "操作失败");
    }
  }
}

async function handleUpdate() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning("名称不能为空");
    return;
  }
  saving.value = true;
  try {
    await updateLedger(Number(ledgerId.value), editForm.value);
    ElMessage.success("账户已更新");
    showEditDialog.value = false;
    const ledgerRes = await getLedgers();
    ledgers.value = ledgerRes.data ?? [];
    await loadSummary();
    await loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "更新失败");
  } finally {
    saving.value = false;
  }
}

async function confirmDeletePosition(row: LedgerHoldingRow) {
  const positionId = row.id;
  try {
    const action = await ElMessageBox.confirm(
      `确定删除持仓「${row.name || row.symbol}」吗？可选择同时删除关联交易记录。`,
      "删除持仓",
      {
        confirmButtonText: "删除持仓及交易",
        cancelButtonText: "仅删除持仓",
        distinguishCancelAndClose: true,
        type: "warning"
      }
    );

    // ✅ 用户点击了【删除持仓及交易】
    await deleteLedgerPosition(Number(ledgerId.value), positionId, true);
    ElMessage.success("持仓及关联交易已删除");

    // 刷新持仓列表
    loadHoldings();
    // 🔥 核心修复：清除交易列表缓存，保证用户切换 Tab 后会自动拉取最新数据
    transactionsList.value = [];
    transactionsTotal.value = 0;
  } catch (action: unknown) {
    // ✅ 用户点击了【仅删除持仓】（ElMessageBox 取消分支返回 "cancel"）
    if (action === "cancel") {
      try {
        await deleteLedgerPosition(Number(ledgerId.value), positionId, false);
        ElMessage.success("持仓已删除，交易记录保留");

        // 刷新持仓列表
        loadHoldings();
        // 🔥 核心修复：虽然保留了交易记录，但交易列表引用的是内存缓存，强制置空以触发刷新
        transactionsList.value = [];
        transactionsTotal.value = 0;
      } catch (e) {
        const err = e as { response?: { data?: { message?: string } } };
        ElMessage.error(err?.response?.data?.message || "删除失败");
      }
    }
  }
}

function openEditTxnDialog(row: LedgerTxnRow) {
  editingTxn.value = { ...row, ledger_id: Number(ledgerId.value) };
  editTxnDialogVisible.value = true;
}

function onTxnSaved() {
  editTxnDialogVisible.value = false;
  loadTransactions(transactionsPage.value);
}

// 只需一行，页面全自动刷新
usePageRefresh(async () => {
  if (!isUnclassified.value) {
    await loadSummary();
    if (summaryData.value?.ledger_type === "fund") await loadMoneyFundIncome();
  }
  await loadHoldings();
  if (activeTab.value === "transactions") await loadTransactions();
});

// 加载优化：概览与持仓并行拉取，减少首屏等待（loading 期间显示骨架屏，见模板）
onMounted(async () => {
  loading.value = true;
  // 阈值控制：200ms 后仍未完成才显示骨架屏；快速请求（<200ms）不显示，避免闪屏
  skeletonTimer = setTimeout(() => {
    showSkeleton.value = true;
  }, 200);
  try {
    // 销售机构候选：编辑弹窗下拉数据源（内部兜底，失败不打断主流程）
    await loadSalesInstitutions();
    if (!isUnclassified.value) {
      await Promise.all([loadSummary(), loadHoldings()]);
      // 货基收益依赖 summary 判定账户类型，故在 summary 就绪后再拉
      if (summaryData.value?.ledger_type === "fund")
        await loadMoneyFundIncome();
      // 修复：首屏填充 ledgers，使 accountInfo 可解析，从而显示右上角操作栏
      // （编辑/归档/删除/对账/批量迁移）。此前仅在点击这些按钮时才拉取，
      // 而按钮本身又在 v-if="accountInfo" 内，形成死锁导致操作栏永不显示。
      // 拉取失败仅影响操作栏可用性，不阻断概览/持仓等主流程，故单独兜底。
      try {
        const ledgerRes = await getLedgers(true);
        ledgers.value = ledgerRes.data ?? [];
      } catch (error) {
        console.error(
          "获取账本列表失败，操作栏暂不可用（其余详情正常）",
          error
        );
      }
    } else {
      await loadHoldings();
    }
  } catch (e) {
    const err = e as { message?: string };
    ElMessage.error(err?.message || "加载失败");
  } finally {
    if (skeletonTimer) {
      clearTimeout(skeletonTimer);
      skeletonTimer = null;
    }
    showSkeleton.value = false;
    loading.value = false;
  }
});

// 🔥 修复：确认删除交易
async function confirmDeleteTxn(row: LedgerTxnRow) {
  // 1. 查找这笔交易对应的持仓对象
  const targetPos = holdingsList.value.find(p => p.symbol === row.symbol);

  // 2. 如果找到了关联持仓，做防呆处理
  if (targetPos) {
    try {
      await ElMessageBox.confirm(
        `确定要删除这笔交易记录吗？<br/><br/>
        <span style="color: var(--color-warning); font-weight: bold;">重要提示</span><br/>
        当前持仓「${targetPos.name || targetPos.symbol}」共持有 ${targetPos.quantity} 份/股。<br/>
        如果删除这笔历史交易，<b style="color: var(--color-danger-system);">该持仓将丢失成本来源，变成“幽灵持仓”</b>。<br/><br/>
        <b>推荐操作：前往「持仓明细」Tab，找到该持仓并点击“删除”，选择“删除持仓及交易”。</b>`,
        "删除交易风险确认",
        {
          confirmButtonText: "我理解风险，只删除交易",
          cancelButtonText: "取消，我去持仓页操作",
          dangerouslyUseHTMLString: true,
          type: "warning"
        }
      );
      // 用户执意只删交易
      await deleteTransaction(row.id);
      ElMessage.warning("交易记录已删除（持仓已变成幽灵数据）");
      loadTransactions(transactionsPage.value);
      loadHoldings(); // 更新持仓成本
    } catch (e: unknown) {
      if (e !== "cancel") {
        const err = e as { response?: { data?: { message?: string } } };
        ElMessage.error(err?.response?.data?.message || "删除失败");
      }
    }
  } else {
    // 3. 如果找不到对应的持仓（说明本来就是个幽灵交易），直接删
    await deleteTransaction(row.id);
    ElMessage.success("孤立交易已删除");
    loadTransactions(transactionsPage.value);
    loadHoldings();
  }
}

function openDeleteDialog(account: LedgerItem) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}
</script>

<style scoped>
/* 类现金 / 中高风险（#1137）：主次反转布局。
   主显示用 --text-hero（48px/600，design.md 总资产规格）由 MoneyDisplay size=hero 承载；
   辅助信息用 --text-small / --text-label + --text-tertiary 弱化，但**单独成块**，
   让用户一眼看到「多少在中高风险里」。颜色/间距全部走 token，禁止硬编码。 */
.cash-like {
  display: flex;
  flex-direction: column;
}

.cash-like__label {
  margin-bottom: var(--space-2);
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary);
}

.cash-like__divider {
  margin: var(--space-4) 0 var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

.cash-like__aux {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.cash-like__aux-label {
  font-size: var(--text-small);
  line-height: 20px;
  color: var(--text-secondary);
}

.cash-like__aux-detail {
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary);
}

/* 概览卡片：token 化（与 CardBlock/MetricCard 同一套卡片语言，仅因需内嵌 MoneyDisplay 故用局部类） */
.summary-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: var(--space-compact) var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.summary-card__label {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.summary-card__value {
  margin-top: var(--space-2);
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.summary-card__sub-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.summary-card__sub-value {
  margin-top: 4px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.summary-card__divider {
  padding-top: var(--space-2);
  margin-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

/* 交易表资产名称列：名称 + 代码 */
.txn-asset-name {
  color: var(--text-primary);
}

.txn-asset-code {
  margin-left: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* Tab 工具栏（#982）：搜索框绝对定位到 Tab 头右侧，与标签同一行。
   不能用 flex 横排——el-tabs 包含整个内容区，横排会把输入框挤到表格右侧 */
.tabs-toolbar {
  position: relative;
}

.tab-search-input {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 1;
  width: 220px;
}

/* ===== 批量迁移决议面板（§7）：三区呈现 + conflict 行内联决议 ===== */

/* 概要：来源 → 目标 路由与总数 */
.mig-summary {
  margin-bottom: var(--space-3);
}

.mig-route {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.mig-route__name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-route__arrow {
  font-size: 14px;
  color: var(--text-tertiary);
}

/* 总数右对齐：等宽数字保证跳动时不抖 */
.mig-route__total {
  margin-left: auto;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.mig-note {
  margin-top: var(--space-1);
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 长列表限高滚动：底栏（状态 + 确认按钮）始终可见 */
.mig-body {
  max-height: 56vh;
  padding-right: 2px;
  overflow-y: auto;
}

.mig-section {
  margin-bottom: var(--space-3);
}

.mig-section__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
}

.mig-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-section__count {
  padding: 0 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  line-height: 20px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.mig-section__hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* keep / duplicate 行：名称居左、数值摘要居右 */
.mig-rows {
  padding: 0;
  margin: var(--space-2) 0 0;
  list-style: none;
}

.mig-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
}

.mig-row + .mig-row {
  border-top: 1px dashed var(--border-light);
}

.mig-row__name {
  font-size: 13px;
  color: var(--text-primary);
}

.mig-row__symbol,
.mig-conflict__symbol {
  margin-left: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: normal;
  color: var(--text-tertiary);
}

.mig-row__values {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  text-align: right;
}

/* conflict 卡片：头部 + 对比表 + 内联决议 */
.mig-conflict {
  padding: var(--space-3);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.mig-conflict + .mig-conflict {
  margin-top: var(--space-2);
}

.mig-conflict__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.mig-conflict__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-conflict__fields {
  font-size: 12px;
  color: var(--text-secondary);
}

/* 源/目标并排对比：标签列 + 双值列；警示底色只落在数值单元格上，
   文字保持 --text-primary 保证 WCAG 对比度（--color-warning 直接做小字文字色不达标） */
.mig-compare {
  display: grid;
  grid-template-columns: 72px 1fr 1fr;
  overflow: hidden;
  background: var(--bg-warm);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.mig-compare > span {
  padding: 6px 10px;
  font-size: 13px;
  line-height: 20px;
  border-top: 1px solid var(--border-subtle);
}

.mig-compare > span:nth-child(-n + 3) {
  border-top: none;
}

.mig-compare__tag {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-soft);
}

.mig-compare__label {
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

.mig-compare__value {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 差异字段高亮：警示色 20% 底 + 左侧警示色细条，亮暗色均由语义变量驱动 */
.mig-compare__value.is-diff {
  font-weight: 600;
  background: var(--color-warning-20);
  box-shadow: inset 2px 0 0 var(--color-warning);
}

/* 决议区：单选 + 当前选中态说明文案 */
.mig-decide {
  margin-top: var(--space-2);
}

.mig-action-note {
  margin: 4px 0 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.mig-empty {
  padding: var(--space-loose) 0;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

/* 底栏：左侧状态文案 + 右侧操作按钮 */
.mig-footer {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.mig-footer__status {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ===== 目标账户选择器：机构标注与未绑定提示 ===== */

/* 下拉选项：名称居左、销售机构标注居右 */
.mig-option {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
}

.mig-option__name {
  color: var(--text-primary);
}

.mig-option__inst {
  flex-shrink: 0;
  padding: 0 8px;
  font-size: 12px;
  line-height: 20px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

/* 同机构候选高亮为品牌软色（「优先候补」软按钮语义，允许引用 --brand-*） */
.mig-option__inst.is-same {
  color: var(--brand-700);
  background: var(--brand-100);
}

/* 未绑定销售机构的提示文案 */
.mig-bind-hint {
  margin: var(--space-1) 0 0;
  font-size: 12px;
}
</style>
