<!--
  Watchlist · 自选页（完整管理）

  与探市页（/explore）的区别与关联：
  - 探市 = 引流沙盒（未登录用 localStorage 本地草稿，仅"看 + 轻收藏"，登录后隐藏添加并引导去自选页）；
    自选 = 权威管理（后端 watchlist API，分组/标签/批量/OCR/实时估值齐全）。
  - 两者表格刻意不共用：产品边界不同（观察 vs 管理）。共享的是底层 composable：
    useAssetSearch / useRealtimeQuotes / useAuthState（见 explore-watchlist-replan-2026-08-08 决策）。
  - 迁移桥：POST /api/watchlist/import/explore 将探市本地草稿导入自选。

  未来优化方向（见重构 issue #980 / 技术债 #981 / #982）：
  - 本页 8 大功能模块（分组/标签/批量/实时估值/搜索分页/导出/OCR/移除）可进一步按
    composable 抽取（如 useWatchlistGroups / useWatchlistTags），当前仅拆出标签弹窗组件。
  - 标签管理 / 行内标签编辑已拆为共有组件 TagManagerDialog / TagEditorDialog
    （components/Watchlist/），未来其它页面需要标签能力可复用。
-->
<template>
  <div
    class="watchlist-page p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部操作栏 (已移除 size="small" 和 CSS 强制 32px 高度) -->
    <div class="flex flex-wrap items-center justify-between gap-4 mb-6 top-bar">
      <div class="flex items-center gap-3">
        <div class="flex items-center relative">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索当前自选列表..."
            clearable
            class="w-48"
            :prefix-icon="Search"
            @input="debounceSearch"
          />
          <el-tooltip
            content="在当前自选列表中按代码或名称过滤"
            placement="bottom-start"
            :offset="8"
          >
            <IconifyIconOffline
              icon="ep:info-filled"
              class="absolute right-[-22px] top-1/2 -translate-y-1/2 text-sm cursor-help transition-colors"
              :style="{ color: 'var(--text-tertiary)' }"
            />
          </el-tooltip>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- 批量模式下的特殊工具栏 -->
        <template v-if="batchMode">
          <div class="flex items-center gap-3">
            <span
              class="text-sm font-medium shrink-0"
              :style="{ color: 'var(--text-primary)' }"
            >
              已选 {{ selectedItems.length }} 项
            </span>
            <el-select
              v-model="batchMoveGroupId"
              placeholder="移动到分组"
              class="batch-move-select"
              clearable
              @change="handleBatchMoveToGroup"
            >
              <el-option
                v-for="group in customGroups"
                :key="group.id"
                :label="group.name"
                :value="group.id"
              >
                <div class="flex items-center gap-2">
                  <!-- 数据色例外：分组色为用户数据（非设计令牌），缺失时回退中性 token -->
                  <span
                    class="w-2.5 h-2.5 rounded-full"
                    :style="{
                      backgroundColor: group.color || 'var(--text-tertiary)'
                    }"
                  />
                  <span>{{ group.name }}</span>
                </div>
              </el-option>
            </el-select>
            <el-button
              class="batch-delete-btn"
              :disabled="selectedItems.length === 0"
              @click="handleBatchDelete"
            >
              <IconifyIconOffline icon="ep:delete" class="mr-1" />
              删除选中
            </el-button>
            <el-button type="primary" @click="toggleBatchMode">
              退出批量模式
            </el-button>
          </div>
        </template>

        <!-- 正常模式下的工具栏 -->
        <template v-else>
          <el-button type="primary" @click="showAddModal = true">
            <IconifyIconOffline icon="ep:plus" class="mr-1" />
            添加自选
          </el-button>

          <el-button plain @click="fetchData">
            <IconifyIconOffline icon="ep:refresh" class="mr-1" />
            刷新
          </el-button>

          <el-button plain @click="exportData">
            <IconifyIconOffline icon="ep:download" class="mr-1" />
            导出
          </el-button>

          <el-button plain @click="showOcrModal = true">
            <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
            AI 导入
          </el-button>

          <el-button plain @click="realtime.toggle()">
            {{ toggleBtnText }}
          </el-button>

          <el-button plain @click="showSettingsDrawer = true">
            <IconifyIconOffline icon="ep:setting" class="mr-1" />
            管理
          </el-button>
        </template>
      </div>
    </div>

    <!-- 主区域：单个工作区卡片（分组 tab 行 + 筛选行 + 表格，--border-subtle 分割线分区） -->
    <CardBlock class="watchlist-card">
      <!-- 分组 tab 行 + 场内/场外 segmented（justify-between：tab 左对齐、segmented 右对齐） -->
      <div
        class="flex items-center justify-between gap-4 pb-3 mb-4 border-b"
        :style="{ borderColor: 'var(--border-subtle)' }"
      >
        <div class="flex items-center gap-3 min-w-0">
          <span
            class="text-sm font-semibold shrink-0"
            :style="{ color: 'var(--text-primary)' }"
            >分组</span
          >
          <div
            class="group-tabs-scroll flex items-center gap-1.5 overflow-x-auto py-0.5"
          >
            <div
              v-for="group in allGroups"
              :key="group.key"
              class="group-tab shrink-0"
              :class="{ 'is-active': activeGroup === group.key }"
              @click="activeGroup = group.key"
            >
              <span
                class="w-2 h-2 rounded-full shrink-0"
                :style="{ backgroundColor: group.color }"
              />
              <span class="group-tab-label" :title="group.label">{{
                group.label
              }}</span>
              <span class="group-tab-count font-mono">({{ group.count }})</span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2 shrink-0">
          <!-- 标签筛选：触发按钮 + 弹出面板（GitHub Labels 式）。
               弃用 el-select 多选：原实现输入框随选中项无限拉长、勾选态仅靠下拉内小勾不够明显。
               改为固定宽度触发按钮（绝不拉长）+ 独立控制 max-height 的面板 + 前置 el-checkbox。
               append-to-body=false 让面板渲染在本组件内，scoped 样式可直接命中。 -->
          <el-popover
            v-model:visible="tagFilterVisible"
            placement="bottom-end"
            :width="264"
            trigger="click"
            popper-class="tag-filter-popover"
            :z-index="3000"
            :append-to-body="false"
            @show="onTagFilterShow"
          >
            <template #reference>
              <button
                type="button"
                class="tag-filter-trigger"
                :class="{ 'is-active': selectedFilterTagIds.length > 0 }"
              >
                <IconifyIconOffline icon="ep:collection-tag" />
                <span class="tag-filter-trigger__text">
                  {{ selectedFilterTagLabel }}
                </span>
                <IconifyIconOffline
                  v-if="selectedFilterTagIds.length > 0"
                  icon="ep:close"
                  class="tag-filter-trigger__clear"
                  @click.stop="clearTagFilter"
                />
              </button>
            </template>

            <!-- 面板：列表区固定 max-height + 滚动；底部 确定 / 清空筛选 -->
            <div class="tag-filter-panel">
              <div class="tag-filter-panel__list">
                <el-checkbox-group v-model="draftFilterTagIds">
                  <label
                    v-for="tag in allTags"
                    :key="tag.id"
                    class="tag-filter-item"
                  >
                    <el-checkbox :value="tag.id" />
                    <span
                      class="tag-filter-item__dot"
                      :style="{
                        backgroundColor: tag.color || 'var(--text-tertiary)'
                      }"
                    />
                    <span class="tag-filter-item__name">{{ tag.name }}</span>
                  </label>
                </el-checkbox-group>
                <div
                  v-if="allTags.length === 0"
                  class="tag-filter-panel__empty"
                >
                  暂无可选标签
                </div>
              </div>
              <div class="tag-filter-panel__footer">
                <el-button size="small" text bg @click="clearTagFilter"
                  >清空筛选</el-button
                >
                <el-button size="small" type="primary" @click="applyTagFilter"
                  >确定</el-button
                >
              </div>
            </div>
          </el-popover>
          <el-tooltip content="管理分组" placement="top">
            <el-button
              class="group-tab-add"
              circle
              size="small"
              @click="showGroupManager = true"
            >
              <IconifyIconOffline icon="ep:plus" />
            </el-button>
          </el-tooltip>
          <el-segmented
            v-model="currentView"
            :options="viewOptions"
            class="view-segmented"
            @change="handleViewChange"
          />
        </div>
      </div>
      <!-- 估值横幅与状态 -->
      <!-- ✅ 核心修复：用 template 包裹，加上 v-if 物理移除整个模块 -->
      <template v-if="realtimeEnabled">
        <RealtimeWarningBanner />

        <div class="flex items-center gap-2 mb-2">
          <RealtimeStatusIndicator
            :status="realtime.status.value"
            :lastUpdateTime="realtime.lastUpdateTime.value || ''"
          />
          <el-segmented
            :model-value="realtime.refreshInterval.value"
            size="small"
            :options="intervalOptions"
            class="refresh-segmented"
            @change="onRefreshIntervalChange"
          />
          <el-button
            v-if="realtimeEnabled"
            text
            :style="{ color: 'var(--text-secondary)' }"
            @click="handleManualRefresh"
          >
            <IconifyIconOffline
              icon="ep:refresh"
              class="mr-1 text-xs"
              :class="{ 'is-spinning': refreshing }"
            />
            刷新估值
          </el-button>
        </div>

        <!-- 估值汇总卡片：仅当有实际持仓市值时显示 -->
        <div
          v-if="summary && summary.totalMarketValue > 0"
          class="mb-3 p-3 rounded-lg"
          :style="{
            backgroundColor: 'var(--bg-soft)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex items-center gap-6 text-sm">
            <span>
              总市值：<strong :style="{ color: 'var(--text-primary)' }">
                <template v-if="summary?.totalMarketValue != null">
                  <MoneyDisplay
                    :value="summary.totalMarketValue"
                    :show-sign="false"
                    :auto-color="false"
                    size="sm"
                  />
                </template>
                <template v-else>--</template>
              </strong>
            </span>
            <span>
              总成本：<strong :style="{ color: 'var(--text-primary)' }">
                <template v-if="summary?.totalCost != null">
                  <MoneyDisplay
                    :value="summary.totalCost"
                    :show-sign="false"
                    :auto-color="false"
                    size="sm"
                  />
                </template>
                <template v-else>--</template>
              </strong>
            </span>
            <span>
              总盈亏：<strong>
                <template v-if="summary?.totalPnl != null">
                  <MoneyDisplay :value="summary.totalPnl" size="sm" />
                  <span v-if="summary?.totalPnlPercent != null"
                    >(<MoneyDisplay
                      :value="summary.totalPnlPercent"
                      :precision="2"
                      suffix="%"
                      size="sm"
                    />)</span
                  >
                </template>
                <template v-else>--</template>
              </strong>
            </span>
          </div>
        </div>
      </template>

      <!-- 批量删除（batchMode 时显示；原筛选行已并入分组行，批量删除按钮移至表格上方） -->
      <div
        v-if="batchMode && selectedItems.length > 0"
        class="flex justify-end mb-2"
      >
        <el-button
          type="danger"
          plain
          size="small"
          class="!h-7 !px-3 !text-xs"
          @click="handleBatchDelete"
        >
          删除选中 ({{ selectedItems.length }})
        </el-button>
      </div>

      <!--
          表格视觉基线（边框/表头/hover/文字色）统一在 src/style/el-table.css 维护，
          勿在本页 :deep(.el-table) 覆盖视觉基线；本页保留的 :deep 仅限行内行为样式。
          行高例外（2026-08-15）：全局基线 44px 偏松，自选页信息密度优先，本页覆盖为 40px
          （EP 默认行高，tr height 为最小高度语义，两行式名称列自动撑高不裁切）；
          覆盖规则见本页 style 区「本页行高覆盖」注释。
        -->
      <el-table
        v-loading="loading"
        :data="items"
        stripe
        @row-click="handleRowClick"
        @selection-change="handleSelectionChange"
      >
        <el-table-column
          v-if="batchMode"
          type="selection"
          width="50"
          align="center"
        />
        <el-table-column width="44" align="center" class-name="marker-column">
          <template #default="{ row }">
            <div class="flex items-center justify-center gap-0.5">
              <!-- 置顶/关注图标：--text-tertiary，行 hover 提亮 --text-secondary，语义靠 icon 形状区分 -->
              <span v-if="row.is_pinned" class="marker-icon" title="已置顶">
                <IconifyIconOffline icon="mdi:pin-outline" class="text-sm" />
              </span>
              <span v-if="row.favorite" class="marker-icon" title="特别关注">
                <IconifyIconOffline icon="ep:star" class="text-sm" />
              </span>
            </div>
          </template>
        </el-table-column>

        <!-- 产品信息列：名称（第一行）+ 标签 chips（第二行，最多 2 个 + +N）；fixed 左固定（横向滚动时保持可见） -->
        <el-table-column
          label="代码/名称"
          min-width="240"
          fixed="left"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <div class="flex flex-col gap-1 py-2">
              <ProductDisplay
                :name="row.display_name || row.symbol"
                :symbol="row.symbol"
                :type-label="row.type_label || ''"
              />
              <div class="flex items-center gap-1">
                <template v-if="row.tag_ids && row.tag_ids.length > 0">
                  <el-tag
                    v-for="tagId in row.tag_ids.slice(0, 2)"
                    :key="tagId"
                    size="small"
                    class="tag-chip text-[10px] px-1.5 py-0.5 rounded-full"
                    :style="{
                      backgroundColor: findTagColor(allTags, tagId) + '20',
                      color: 'var(--text-primary)',
                      border: '1px solid ' + findTagColor(allTags, tagId)
                    }"
                  >
                    {{ findTagName(allTags, tagId) }}
                  </el-tag>
                  <span
                    v-if="row.tag_ids.length > 2"
                    class="text-xs"
                    :style="{ color: 'var(--text-tertiary)' }"
                  >
                    +{{ row.tag_ids.length - 2 }}
                  </span>
                </template>
                <el-tooltip content="添加/编辑标签" placement="top">
                  <el-button
                    circle
                    size="small"
                    class="add-tag-btn"
                    @click.stop="openTagEditor(row as WatchlistItem)"
                  >
                    <IconifyIconOffline icon="ep:plus" class="text-[10px]" />
                  </el-button>
                </el-tooltip>
              </div>
            </div>
          </template>
        </el-table-column>

        <!-- 添加自选日（日期非数字，左对齐更易扫读） -->
        <el-table-column label="添加自选日" width="100" align="left">
          <template #default="{ row }">
            <span :style="{ color: 'var(--text-secondary)', fontSize: '13px' }">
              {{ formatDate(row.created_at) }}
            </span>
          </template>
        </el-table-column>

        <!-- 最新价 -->
        <el-table-column label="最新价" width="110" align="right">
          <template #default="{ row }">
            <template v-if="realtimeEnabled && getValuationItem(row.symbol)">
              <MoneyDisplay
                :value="getValuationItem(row.symbol)!.currentPrice"
                :show-sign="false"
                :show-currency="false"
                :precision="pricePrecision(row.asset_type)"
              />
            </template>
            <template v-else>
              <MoneyDisplay
                v-if="row.current_price != null"
                :value="row.current_price"
                :show-sign="false"
                :show-currency="false"
                :precision="pricePrecision(row.asset_type)"
              />
              <span v-else :style="{ color: 'var(--text-tertiary)' }">--</span>
            </template>
          </template>
        </el-table-column>

        <!-- 涨跌幅 (替换为全局 RiseFallText 组件) -->
        <el-table-column label="涨跌幅" width="100" align="right">
          <template #default="{ row }">
            <template v-if="realtimeEnabled && getValuationItem(row.symbol)">
              <RiseFallText :value="getValuationItem(row.symbol)!.changePct" />
            </template>
            <template v-else>
              <RiseFallText
                v-if="row.change_pct != null"
                :value="row.change_pct"
              />
              <span v-else :style="{ color: 'var(--text-tertiary)' }">--</span>
            </template>
          </template>
        </el-table-column>

        <!-- 持有数量 / 份额 -->
        <el-table-column label="持有数量" width="110" align="right">
          <template #default="{ row }">
            <template v-if="(row.holding_quantity ?? 0) > 0">
              <span
                class="tabular-nums"
                :style="{ color: 'var(--text-primary)', fontWeight: 500 }"
              >
                {{ formatQty(row.holding_quantity) }}
              </span>
              <span
                :style="{
                  color: 'var(--text-tertiary)',
                  fontSize: '11px',
                  marginLeft: '2px'
                }"
                >{{ row.venue === "OTC" ? "份" : "股" }}</span
              >
            </template>
            <span v-else :style="{ color: 'var(--text-tertiary)' }">--</span>
          </template>
        </el-table-column>

        <!-- 持仓市值 -->
        <el-table-column
          prop="position_market_value"
          label="持仓市值"
          width="120"
          align="right"
        >
          <template #default="{ row }">
            <MoneyWithRatio
              :value="row.position_market_value"
              :ratio="marketValueRatio(row)"
              :show-sign="false"
              :ratio-auto-color="false"
            />
          </template>
        </el-table-column>

        <!-- 添加后涨幅：金额(上) + 涨幅%(下)，与持仓收益列统一主次 -->
        <el-table-column label="添加后涨幅" width="110" align="right">
          <template #default="{ row }">
            <MoneyWithRatio
              :value="addedReturnAmount(row)"
              :ratio="addedReturnPct(row)"
              :show-currency="false"
              :show-sign="true"
            />
          </template>
        </el-table-column>

        <!-- 持仓收益：金额(上) + 收益率%(下)，合并原独立的「收益比」列 -->
        <el-table-column label="持仓收益" width="110" align="right">
          <template #default="{ row }">
            <MoneyWithRatio
              :value="
                (row.holding_quantity ?? 0) > 0 ? (row.holding_pnl ?? 0) : null
              "
              :ratio="
                (row.holding_quantity ?? 0) > 0
                  ? (row.holding_pnl_percent ?? 0)
                  : null
              "
              :show-currency="false"
              :show-sign="true"
              :auto-color="true"
            />
          </template>
        </el-table-column>

        <!-- 操作列：3 个 circle 按钮一行排布（flex + gap，避免 2 上 1 下换行） -->
        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <template v-if="!batchMode">
              <div class="flex items-center justify-center gap-1">
                <el-tooltip
                  :content="row.is_pinned ? '取消置顶' : '置顶'"
                  placement="top"
                >
                  <el-button
                    circle
                    size="small"
                    @click.stop="handleTogglePin(row as WatchlistItem)"
                  >
                    <IconifyIconOffline
                      :icon="row.is_pinned ? 'mdi:pin' : 'mdi:pin-outline'"
                    />
                  </el-button>
                </el-tooltip>
                <el-tooltip
                  :content="row.favorite ? '取消特别关注' : '特别关注'"
                  placement="top"
                >
                  <el-button
                    circle
                    size="small"
                    @click.stop="handleToggleFavorite(row as WatchlistItem)"
                  >
                    <IconifyIconOffline
                      :icon="row.favorite ? 'ep:star-filled' : 'ep:star'"
                    />
                  </el-button>
                </el-tooltip>
                <el-tooltip
                  :content="
                    row.status === 'HOLDING'
                      ? '持仓资产无法直接从自选移除'
                      : '移除'
                  "
                  placement="top"
                >
                  <el-button
                    circle
                    size="small"
                    class="btn-delete-ghost"
                    :disabled="row.status === 'HOLDING'"
                    @click.stop="confirmRemove(row as WatchlistItem)"
                  >
                    <IconifyIconOffline icon="ep:delete" />
                  </el-button>
                </el-tooltip>
              </div>
            </template>
            <template v-else>
              <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                >-</span
              >
            </template>
          </template>
        </el-table-column>

        <!-- 空状态：区分「标签筛选导致为空」与「本就无任何自选」，避免干巴巴的默认占位。
             注：design.md 规划了鹦鹉螺简笔画空状态，现仓库无对应资产，先用文案版，待插画资产到位后替换。 -->
        <template #empty>
          <div class="watchlist-empty">
            <p class="watchlist-empty__title">
              {{
                selectedFilterTagIds.length > 0
                  ? "暂无匹配所选标签的持仓"
                  : "暂无自选资产"
              }}
            </p>
            <p
              v-if="selectedFilterTagIds.length > 0"
              class="watchlist-empty__hint"
            >
              试试调整或清空标签筛选条件
            </p>
          </div>
        </template>
      </el-table>

      <div class="flex justify-end mt-4">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="totalItems"
          layout="total, prev, pager, next"
          small
          background
          @current-change="fetchData"
        />
      </div>
    </CardBlock>

    <!-- 弹窗部分 -->
    <AddToWatchlistModal
      v-model="showAddModal"
      :initial-group-id="activeCustomGroupId"
      @submitted="onItemAdded"
    />

    <OcrImportModal v-model="showOcrModal" @imported="onOcrImported" />

    <el-dialog v-model="removeDialogVisible" title="移除自选" width="400px">
      <p>
        确定要移除
        <strong>{{
          removingItem?.display_name || removingItem?.symbol
        }}</strong>
        吗？
      </p>
      <div
        v-if="
          removingItem &&
          removingItem.group_ids &&
          removingItem.group_ids.length > 0
        "
        class="mt-4"
      >
        <el-radio-group v-model="removeScope">
          <el-radio value="all">从所有分组移除并删除</el-radio>
          <el-radio value="current" :disabled="!currentIsCustom"
            >仅从当前分组移除</el-radio
          >
        </el-radio-group>
      </div>
      <template #footer>
        <el-button size="large" @click="removeDialogVisible = false"
          >取消</el-button
        >
        <el-button size="large" type="danger" @click="executeRemove"
          >确定</el-button
        >
      </template>
    </el-dialog>

    <!-- 标签管理弹窗（共有组件 TagManagerDialog，自本页拆出，见 docs/design/components.md） -->
    <TagManagerDialog
      v-model="showTagManager"
      :all-tags="allTags"
      :tag-usage="tagUsage"
      @tags-changed="fetchTags"
    />

    <!-- 分组管理弹窗（GitHub Labels 风格，与标签同构，见 docs/design/components.md） -->
    <GroupManagerDialog
      v-model="showGroupManager"
      :all-groups="customGroups"
      @groups-changed="fetchGroups"
    />

    <!-- 行内标签编辑弹窗（共有组件 TagEditorDialog） -->
    <TagEditorDialog
      v-model="showTagEditor"
      :item="editingItem"
      :all-tags="allTags"
      @saved="onTagEditorSaved"
    />

    <SettingsDrawer
      v-model="showSettingsDrawer"
      :realtime-enabled="realtimeEnabled"
      :refresh-interval="realtime.refreshInterval.value"
      @refresh-interval-change="realtime.setRefreshInterval"
      @manage-groups="
        showGroupManager = true;
        showSettingsDrawer = false;
      "
      @manage-tags="
        showTagManager = true;
        showSettingsDrawer = false;
      "
      @manage-batch="
        toggleBatchMode();
        showSettingsDrawer = false;
      "
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { Search } from "@element-plus/icons-vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { ElMessage, ElMessageBox } from "element-plus";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import OcrImportModal from "@/components/QuickEntry/OcrImportModal.vue";
import SettingsDrawer from "@/components/Watchlist/SettingsDrawer.vue";
import TagManagerDialog from "@/components/Watchlist/TagManagerDialog.vue";
import GroupManagerDialog from "@/components/Watchlist/GroupManagerDialog.vue";
import TagEditorDialog from "@/components/Watchlist/TagEditorDialog.vue";
import {
  getWatchlistItems,
  updateWatchlistItem,
  deleteWatchlistItem,
  removeItemFromGroup,
  addItemToGroup,
  type WatchlistItem
} from "@/api/watchlist";
import { findTagName, findTagColor } from "@/utils/tagHelpers";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue"; // 加入此组件引入
import MoneyWithRatio from "@/components/MoneyWithRatio/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import {
  useRealtimeQuotes,
  REFRESH_INTERVAL_OPTIONS,
  type RefreshInterval
} from "@/composables/useRealtimeQuotes";
import { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import { useWatchlistTags } from "@/composables/useWatchlistTags";
import RealtimeWarningBanner from "@/components/RealtimeWarningBanner/index.vue";
import RealtimeStatusIndicator from "@/components/RealtimeStatusIndicator/index.vue";
import type { Holding } from "@/utils/valuationEngine";
import { formatDate, formatDateTime } from "@/utils/date";

defineOptions({ name: "Watchlist" });

// 分组状态/逻辑已收敛到 composable（useWatchlistGroups）；标签状态/筛选面板收敛到 useWatchlistTags。
// 分组切换由组件内 watch(activeGroup) 触发刷新；标签筛选提交后通过 refresh 回调刷新。
const groups = useWatchlistGroups();
const tags = useWatchlistTags(() => {
  currentPage.value = 1;
  fetchData();
});
const {
  activeGroup,
  allGroups,
  customGroups,
  activeGroupLabel,
  currentIsCustom,
  activeCustomGroupId,
  fetchGroups
} = groups;
const {
  allTags,
  selectedFilterTagIds,
  tagFilterVisible,
  draftFilterTagIds,
  fetchTags,
  onTagFilterShow,
  applyTagFilter,
  clearTagFilter
} = tags;

// 触发按钮展示已选标签名。重构前用 el-select 多选会直接显示标签名 chips；
// 换成自定义 popover 面板后触发文案只显示数量，丢失了名称展示（回归 bug）。
// 此处补回：单选用名称、多选用「名称 +N」截断，保持触发按钮紧凑不拉长。
const selectedFilterTagLabel = computed(() => {
  const ids = selectedFilterTagIds.value;
  if (ids.length === 0) return "按标签筛选";
  const names = ids.map(id => findTagName(allTags.value, id));
  if (names.length <= 2) return names.join("、");
  return `${names[0]}、${names[1]} +${names.length - 2}`;
});

// ── 基础配置 ──
const currentView = ref("all");
const viewOptions = [
  { label: "全部", value: "all" },
  { label: "场内", value: "exchange" },
  { label: "场外", value: "otc" }
];

// 系统分组 / 标签预设色已收敛到 constants/watchlist.ts（SYSTEM_GROUPS / PRESET_TAG_COLORS）集中管理。

// ── 响应式数据 ──
const items = ref<WatchlistItem[]>([]);

// summary 是嵌套 Ref（非顶层解包），统一经 computed 解包供模板使用
const summary = computed(() => summary.value);

// 估值相关
const getValuationItem = (symbol: string) => {
  return realtime.items.value?.find(item => item.symbol === symbol);
};

/** 刷新档位选项（label 与 SettingsDrawer 一致：`${s}s`） */
const intervalOptions = REFRESH_INTERVAL_OPTIONS.map(s => ({
  label: `${s}s`,
  value: s
}));

/** 切换刷新档位：转发给 realtime（负责持久化 + 盘中重启定时器） */
const onRefreshIntervalChange = (value: string | number | boolean) => {
  realtime.setRefreshInterval(value as RefreshInterval);
};

/** 手动刷新时的旋转动效状态 */
const refreshing = ref(false);

/** 手动刷新估值：旋转图标至请求完成 */
const handleManualRefresh = async () => {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    await realtime.manualRefresh();
  } finally {
    refreshing.value = false;
  }
};

/**
 * 持有数量 / 份额格式化 */
function formatQty(qty: number): string {
  return qty.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

/** 添加后涨幅（%）=（当前价 - 添加日价格）/ 添加日价格 */
function addedReturnPct(row: {
  symbol?: string;
  current_price?: number | null;
  holding_quantity?: number | null;
  price_at_added?: number | null;
}): number | null {
  const added = row.price_at_added;
  if (!added) return null;
  const cur = (getValuationItem(row.symbol ?? "")?.currentPrice ??
    row.current_price) as number;
  if (!cur) return null;
  return ((cur - added) / added) * 100;
}

/** 添加后收益（元）=（当前价 - 添加日价格）× 持有数量，仅持有时有意义 */
function addedReturnAmount(row: {
  symbol?: string;
  current_price?: number | null;
  holding_quantity?: number | null;
  price_at_added?: number | null;
}): number | null {
  if (!row.holding_quantity || row.holding_quantity <= 0) return null;
  if (addedReturnPct(row) === null) return null;
  const cur = (getValuationItem(row.symbol ?? "")?.currentPrice ??
    row.current_price) as number;
  return (cur - (row.price_at_added as number)) * row.holding_quantity;
}

/** 持仓市值占总市值的比例（%）；无总市值或无市值时返回 null（组件仅显示金额） */
function marketValueRatio(row: {
  position_market_value?: number | null;
}): number | null {
  const total = summary.value?.totalMarketValue;
  if (!total || total <= 0 || row.position_market_value == null) return null;
  return (row.position_market_value / total) * 100;
}

const getHoldings = (): Holding[] => {
  return items.value
    .filter(item => item.symbol)
    .map(item => ({
      symbol: item.symbol,
      type:
        item.asset_type === "fund" || item.venue === "OTC" ? "fund" : "stock",
      // 使用真实持仓数量与成本价，使汇总卡与逐行盈亏正确
      quantity:
        item.status === "HOLDING" && (item.holding_quantity ?? 0) > 0
          ? (item.holding_quantity as number)
          : 0,
      costPrice:
        item.status === "HOLDING" && (item.holding_quantity ?? 0) > 0
          ? (item.holding_cost_price as number)
          : 0
    }));
};

const getStaticPrice = (symbol: string) => {
  const item = items.value.find(i => i.symbol === symbol);
  return item
    ? { currentPrice: item.current_price, changePct: item.change_pct }
    : undefined;
};

// 基金/ETF 最新价为净值，展示 4 位小数；其余证券 2 位
const pricePrecision = (assetType: string): number =>
  assetType === "fund" || assetType === "etf" ? 4 : 2;

// ... 你的其他代码 ...

const realtime = useRealtimeQuotes(getHoldings, getStaticPrice);

// ✅ 1. 新增：一个专门控制按钮文字的 computed，解决文字不更新的脏数据问题
const toggleBtnText = computed(() => {
  return realtime.enabled.value ? "关闭实时估值" : "开启实时估值";
});

// ✅ 2. 修复：原 watch 导致的死循环/卡顿，重构为更稳定的版本
watch(
  () => items.value,
  () => {
    if (realtime.enabled.value) {
      // 强制捕获异常，避免卡断响应式更新
      try {
        realtime.manualRefresh();
      } catch (e) {
        console.warn("手动刷新失败", e);
      }
    }
  }
);

// ✅ 3. 修改：监听实时行情数据，更新绿灯和时间
watch(
  () => realtime.items.value,
  newItems => {
    if (newItems && newItems.length > 0) {
      const hasValidPrice = newItems.some(item => item.currentPrice > 0);
      if (hasValidPrice) {
        realtime.status.value = "trading";
        // 统一走公共格式化：YYYY-MM-DD HH:mm（不带秒），与全站日期时间规范一致
        realtime.lastUpdateTime.value = formatDateTime(new Date());
      }
    }
  },
  { deep: true }
);

const loading = ref(false);
const searchKeyword = ref("");
const currentPage = ref(1);
const pageSize = ref(20);
const totalItems = ref(0);

// 标签状态（allTags / selectedFilterTagIds / tagFilterVisible / draftFilterTagIds）已随 useWatchlistTags 抽离，见文件顶部解构

const showAddModal = ref(false);
const showOcrModal = ref(false);
const showGroupManager = ref(false);
const showTagManager = ref(false);
const removeDialogVisible = ref(false);
const removingItem = ref<WatchlistItem | null>(null);
const removeScope = ref("all");

const showTagEditor = ref(false);
const editingItem = ref<WatchlistItem | null>(null);

const showSettingsDrawer = ref(false);

const batchMode = ref(false);
const selectedItems = ref<WatchlistItem[]>([]);

// 批量移动相关
const batchMoveGroupId = ref<number | null>(null);

// 计算属性
// activeGroupLabel / currentIsCustom / activeCustomGroupId 已随 useWatchlistGroups 抽离，见文件顶部解构

const tagUsage = computed(() => {
  const usage = new Map<number, number>();
  if (!Array.isArray(items.value)) return usage;
  items.value.forEach(item => {
    const tagIds = item?.tag_ids;
    if (Array.isArray(tagIds)) {
      tagIds.forEach(id => {
        if (typeof id === "number" && !isNaN(id)) {
          usage.set(id, (usage.get(id) || 0) + 1);
        }
      });
    }
  });
  return usage;
});

const fetchParams = computed(() => {
  const params: Record<string, string | number | boolean> = {
    page: currentPage.value,
    per_page: pageSize.value
  };
  if (selectedFilterTagIds.value.length > 0) {
    params.tag_ids = selectedFilterTagIds.value.join(",");
  }
  const groupKey = activeGroup.value;
  if (groupKey.startsWith("custom_")) {
    const groupId = activeCustomGroupId.value;
    if (groupId) params.group_id = groupId;
  } else {
    // 系统分组过滤已随 useWatchlistGroups 收敛到 allGroups（其 filter 由 getSystemFilter 填充），直接复用，避免两套数据源
    const group = allGroups.value.find(g => g.key === groupKey);
    if (group && group.filter) {
      Object.entries(group.filter).forEach(([k, v]) => {
        params[k === "cleared" ? "status" : k] =
          k === "cleared" ? "cleared" : v;
      });
    }
  }
  // venue 过滤由顶部 el-segmented（currentView）唯一承担（方案 B 收敛三套入口）
  if (currentView.value === "exchange") params.venue = "EXCHANGE";
  else if (currentView.value === "otc") params.venue = "OTC";
  if (searchKeyword.value) params.q = searchKeyword.value;
  return params;
});

// availableTagsForEditor 已内聚到 TagEditorDialog 组件（按 item.tag_ids 排除已选）

// 方法
function toggleBatchMode() {
  batchMode.value = !batchMode.value;
  if (!batchMode.value) selectedItems.value = [];
}

function handleSelectionChange(selection: WatchlistItem[]) {
  selectedItems.value = selection;
}

async function handleBatchDelete() {
  if (selectedItems.value.length === 0) return;
  try {
    await ElMessageBox.confirm(
      `确定要移除选中的 ${selectedItems.value.length} 个自选资产吗？`,
      "批量移除",
      { confirmButtonText: "确定", cancelButtonText: "取消", type: "warning" }
    );
    for (const item of selectedItems.value) {
      try {
        await deleteWatchlistItem(item.id);
      } catch (e) {
        /* ignore */
      }
    }
    ElMessage.success("批量移除完成");
    batchMode.value = false;
    selectedItems.value = [];
    fetchData();
  } catch (e) {
    /* 用户取消 */
  }
}

const handleBatchMoveToGroup = async (groupId: number | null) => {
  if (!groupId || selectedItems.value.length === 0) return;
  try {
    const promises = selectedItems.value.map(item =>
      addItemToGroup(item.id, groupId)
    );
    await Promise.all(promises);
    ElMessage.success(
      `已将 ${selectedItems.value.length} 个资产移动到所选分组`
    );
    batchMoveGroupId.value = null;
    toggleBatchMode();
    fetchData();
  } catch (e) {
    ElMessage.error("批量移动失败");
  }
};

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────
// getTagName / getTagColor 已提取到 utils/tagHelpers.ts（TagManagerDialog / TagEditorDialog 内部使用）
// 分组 Tab 的系统过滤映射 getSystemFilter 已随 useWatchlistGroups 抽离

let searchTimer: number | undefined;
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    currentPage.value = 1;
    fetchData();
  }, 300);
}

// ─────────────────────────────────────────────
// 数据请求
// ─────────────────────────────────────────────
async function fetchData() {
  loading.value = true;
  try {
    const res = await getWatchlistItems(fetchParams.value);
    items.value = res.data ?? [];
    totalItems.value = res.total ?? items.value.length;
  } catch (e) {
    ElMessage.error("获取自选列表失败");
    console.error("获取自选列表错误：", e);
  } finally {
    loading.value = false;
  }
}

// fetchGroups / fetchTags 已随 useWatchlistGroups / useWatchlistTags 抽离（见文件顶部 composable 调用）

// ─────────────────────────────────────────────
// 事件处理
// ─────────────────────────────────────────────
/**
 * segmented（全部/场内/场外）切换：venue 过滤由 fetchParams 依据 currentView 生效，
 * 与分组 tab 解耦（方案 B：分组选择保持独立，不再联动到系统分组「场内资产/场外基金」，二者已删除）。
 */
function handleViewChange() {
  currentPage.value = 1;
  fetchData();
}

// 标签筛选面板交互（onTagFilterShow / applyTagFilter / clearTagFilter）已随 useWatchlistTags 抽离。
// 其中 applyTagFilter / clearTagFilter 通过 refresh 回调（顶部定义）重置分页并触发 fetchData。

function resetFilters() {
  searchKeyword.value = "";
  groups.resetActiveGroup();
  currentView.value = "all";
  tags.resetTagFilter();
}

async function handleTogglePin(row: WatchlistItem) {
  const r = row as WatchlistItem;
  try {
    await updateWatchlistItem(r.id, { is_pinned: !r.is_pinned });
    ElMessage.success(r.is_pinned ? "已取消置顶" : "已置顶");
    fetchData();
  } catch (e) {
    ElMessage.error("置顶操作失败");
    console.error("置顶错误：", e);
  }
}

async function handleToggleFavorite(row: WatchlistItem) {
  const r = row as WatchlistItem;
  try {
    await updateWatchlistItem(r.id, { favorite: !r.favorite });
    ElMessage.success(r.favorite ? "已取消特别关注" : "已设为特别关注");
    fetchData();
  } catch (e) {
    ElMessage.error("关注操作失败");
    console.error("关注错误：", e);
  }
}

function handleRowClick(row: WatchlistItem) {}

function confirmRemove(row: WatchlistItem | any) {
  removingItem.value = row as WatchlistItem;
  removeScope.value = "all";
  removeDialogVisible.value = true;
}

async function executeRemove() {
  const item = removingItem.value;
  if (!item) return;
  try {
    if (removeScope.value === "current" && activeCustomGroupId.value) {
      await removeItemFromGroup(item.id, activeCustomGroupId.value);
      ElMessage.success("已从当前分组移除");
    } else {
      await deleteWatchlistItem(item.id);
      ElMessage.success("已移除自选");
    }
    removeDialogVisible.value = false;
    fetchData();
  } catch (e) {
    ElMessage.error("移除操作失败");
    console.error("移除错误：", e);
  }
}

async function exportData() {
  try {
    const params = new URLSearchParams(
      Object.entries(fetchParams.value).map(([k, v]) => [k, String(v)])
    ).toString();
    window.open(`/api/watchlist/items/export/?${params}`, "_blank");
  } catch (e) {
    ElMessage.error("导出失败");
    console.error("导出错误：", e);
  }
}

function onItemAdded() {
  showAddModal.value = false;
  fetchData();
  fetchTags();
}

function onOcrImported() {
  showOcrModal.value = false;
  fetchData();
  fetchTags();
}

// ─────────────────────────────────────────────
// 标签管理相关（交互已收敛到 TagManagerDialog / TagEditorDialog 共有组件）
// ─────────────────────────────────────────────
const openTagEditor = (row: WatchlistItem) => {
  editingItem.value = row as WatchlistItem;
  showTagEditor.value = true;
};

/** 标签保存成功（含弹窗内新建标签）后：刷新列表与标签 */
const onTagEditorSaved = () => {
  fetchData();
  fetchTags();
};

// ─────────────────────────────────────────────
// 生命周期
// ─────────────────────────────────────────────
onMounted(() => {
  fetchGroups();
  fetchTags();
  fetchData();
  watch(activeGroup, () => {
    currentPage.value = 1;
    fetchData();
  });
});

const realtimeEnabled = computed(() => realtime.enabled.value);
</script>

<style scoped>
@keyframes refresh-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

.refresh-interval-select {
  width: 96px;
}

.is-spinning {
  animation: refresh-spin 0.8s linear infinite;
}

.text-xs {
  font-size: 0.75rem;
}

.add-tag-btn {
  --el-button-text-color: var(--text-tertiary);

  width: 20px;
  height: 20px;
  min-height: 20px;
  color: var(--text-tertiary);
  opacity: 0;
  transition: opacity 150ms ease;
}

.el-table__row:hover .add-tag-btn {
  opacity: 1;
}

.add-tag-btn:only-child {
  opacity: 1;
}

/* 基金标识标签 */
.fund-tag {
  padding: 1px 4px;
  font-size: 10px;
  line-height: 1.4;
  color: var(--brand-700);
  white-space: nowrap;
  background-color: var(--brand-100);
  border-radius: 4px;
}

/* 颜色选择按钮 */
.color-swatch-btn {
  width: 20px;
  height: 20px;
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 50%;
  transition: all 0.2s ease;
}

.color-swatch-btn.is-selected {
  border-color: var(--brand-700);
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
  transform: scale(1.15);
}

.color-swatch-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}

/* ======================================
   批量模式工具栏优化
   ====================================== */
.batch-move-select {
  min-width: 180px;
}

.batch-move-select :deep(.el-input__wrapper) {
  padding-top: 0;
  padding-bottom: 0;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  box-shadow: none;
  transition: all 0.2s ease;
}

.batch-move-select :deep(.el-input__suffix) {
  display: flex;
  align-items: center;
}

.batch-move-select :deep(.el-input__wrapper:hover) {
  border-color: var(--brand-500);
}

.batch-move-select :deep(.el-input__wrapper.is-focus) {
  border-color: var(--brand-700);
  box-shadow: var(--focus-ring);
}

/* 删除选中按钮：幽灵危险按钮 */
.batch-delete-btn {
  color: var(--color-danger);
  background-color: transparent;
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  transition: all 0.2s ease;
}

.batch-delete-btn:hover {
  color: #fff;
  background-color: var(--color-danger);
  border-color: var(--color-danger);
}

.batch-delete-btn:active {
  transform: translateY(1px);
}

.batch-delete-btn:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
  border-color: var(--text-disabled);
  opacity: 0.5;
}

.batch-delete-btn:disabled:hover {
  color: var(--text-disabled);
  background-color: transparent;
}

/* ======================================
   基础输入框/下拉框样式
   ====================================== */
:deep(.el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  border-radius: var(--radius-sm);
}

:deep(.el-select .el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  border-radius: var(--radius-sm);
}

/* ======================================
   ✅ 已移除强制 32px 高度逻辑，按钮和输入框默认跟随 Element Plus 尺寸
   ====================================== */

/* 标签筛选：触发按钮 + 弹出面板（GitHub Labels 式）。
   2026-08-15 弃用 el-select 多选——原实现输入框随选中项无限拉长、勾选态仅靠下拉内小勾不够明显。
   现改为固定宽度触发按钮（绝不拉长）+ 独立控制 max-height 的面板 + 前置 el-checkbox。
   面板通过 el-popover :append-to-body="false" 渲染在本组件内，故下列类名为普通 scoped 选择器。 */
.tag-filter-trigger {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  max-width: 160px;
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: var(--bg-warm);
  border: none;
  border-radius: var(--radius-pill);
  transition:
    background-color 0.2s ease,
    box-shadow 0.2s ease;
}

.tag-filter-trigger:hover {
  background-color: var(--bg-hover);
}

.tag-filter-trigger.is-active {
  color: var(--brand-700);
  background-color: var(--bg-card);
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}

.tag-filter-trigger__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-filter-trigger__clear {
  display: inline-flex;
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
}

.tag-filter-trigger__clear:hover {
  color: var(--text-primary);
}

/* 弹出面板：列表区限高滚动，底部操作栏 */
.tag-filter-panel {
  display: flex;
  flex-direction: column;
  max-width: 264px;
}

.tag-filter-panel__list {
  max-height: 240px;
  padding: 4px 0;
  overflow-y: auto;
}

.tag-filter-panel .el-checkbox-group {
  display: flex;
  flex-direction: column;
}

.tag-filter-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.tag-filter-item:hover {
  background-color: var(--bg-soft);
}

.tag-filter-item__dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.tag-filter-item__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}

.tag-filter-panel__empty {
  padding: 12px 8px;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

.tag-filter-panel__footer {
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding: 8px;
  border-top: 1px solid var(--border-light);
}

/* 表格空状态：区分标签筛选为空与无自选（鹦鹉螺插画资产到位后可在文案前补简笔画） */
.watchlist-empty {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  padding: 32px 0;
}

.watchlist-empty__title {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.watchlist-empty__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ======================================
   视图 segmented（全部/场内/场外）：与分组 tab 胶囊语言统一
   （2026-08-15：用户反馈与「新建组」圆形按钮并排时缺胶囊感）
   ====================================== */
.view-segmented :deep(.el-segmented) {
  height: 32px;
  padding: 2px;
  background-color: var(--bg-muted);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.view-segmented :deep(.el-segmented__item) {
  height: 28px;
  padding: 0 14px;
  font-size: var(--text-label);
  line-height: 28px;
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.view-segmented :deep(.el-segmented__item:hover) {
  color: var(--text-primary);
}

.view-segmented :deep(.el-segmented__item.is-selected) {
  color: var(--brand-700);
  background-color: var(--brand-100);
  box-shadow: none;
}

.view-segmented :deep(.el-segmented__item.is-selected:hover) {
  background-color: var(--brand-200);
}

/* EP 选中态背景是独立子元素（默认白底+阴影），一并覆盖为品牌软按钮色 */
.view-segmented :deep(.el-segmented__item-selected) {
  background-color: var(--brand-100);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.view-segmented
  :deep(.el-segmented__item.is-selected:hover .el-segmented__item-selected) {
  background-color: var(--brand-200);
}

/* ======================================
   刷新频率 segmented（15s/30s/60s/90s）：与 view-segmented 胶囊语言统一
   （2026-08-15：与设置抽屉 SettingsDrawer 的 refresh-segmented 保持一致）
   ====================================== */
.refresh-segmented :deep(.el-segmented) {
  height: 24px;
  padding: 2px;
  background-color: var(--bg-muted);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.refresh-segmented :deep(.el-segmented__item) {
  height: 20px;
  padding: 0 10px;
  font-size: 12px;
  line-height: 20px;
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.refresh-segmented :deep(.el-segmented__item:hover) {
  color: var(--text-primary);
}

.refresh-segmented :deep(.el-segmented__item.is-selected) {
  color: var(--brand-700);
  background-color: var(--brand-100);
  box-shadow: none;
}

.refresh-segmented :deep(.el-segmented__item.is-selected:hover) {
  background-color: var(--brand-200);
}

.refresh-segmented :deep(.el-segmented__item-selected) {
  background-color: var(--brand-100);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.refresh-segmented
  :deep(.el-segmented__item.is-selected:hover .el-segmented__item-selected) {
  background-color: var(--brand-200);
}

/* ======================================
   按钮物理反馈（去除缩放，仅保留符合规范的 translateY）
   ====================================== */
:deep(.el-button--primary:active) {
  box-shadow: none !important;
  transform: translateY(1px);
}

/* 规范要求：软按钮/其他按钮点击不进行缩放位移，仅背景加深 */
:deep(.el-button.is-text:active) {
  transform: none;
}

.tag-fade-enter-active,
.tag-fade-leave-active {
  transition: all 0.2s ease;
}

.tag-fade-enter-from,
.tag-fade-leave-to {
  opacity: 0;
  transform: scale(0.8);
}

/* ======================================
   标签管理弹窗专属样式
   ====================================== */
.tag-manager-dialog {
  :deep(.el-dialog) {
    overflow: hidden;
    background-color: var(--bg-card);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
  }

  :deep(.el-dialog__header) {
    padding: var(--space-standard);
    padding-bottom: var(--space-3);
    margin-right: 0;
    border-bottom: 1px solid var(--border-light);
  }

  :deep(.el-dialog__title) {
    font-size: var(--text-heading);
    font-weight: 600;
    color: var(--text-primary);
  }

  :deep(.el-dialog__body) {
    padding: var(--space-standard);
  }

  :deep(.el-dialog__footer) {
    padding: var(--space-standard);
    padding-top: var(--space-3);
    border-top: 1px solid var(--border-light);
  }

  :deep(.el-select .el-input__wrapper) {
    --el-input-border-color: var(--border-default);

    height: 40px;
    border-radius: var(--radius-sm);
  }
}

/* 操作列按钮默认隐藏，行悬停时浮现（统一 150ms ease，与分组 tab 编辑/删除同一机制） */
:deep(.el-table__row .el-button) {
  opacity: 0;
  transition: opacity 150ms ease;
}

:deep(.el-table__row:hover .el-button) {
  opacity: 1;
}

/* 操作列 3 个 circle 按钮：flex 容器内归零 EP 相邻 margin，间距统一由 gap 控制，保证一行排布 */
:deep(.el-table__row .el-button + .el-button) {
  margin-left: 0;
}

/* 本页行高覆盖：全局基线 44px（el-table.css）偏松，自选页信息密度优先，降为 40px（EP 默认行高）。
   覆盖理由：全局 44px 为 2026-08-14 基线，影响探市/温度计等页面，不宜全局下调；
   本页名称列为两行式（名称+标签），tr height 为最小高度语义，40px 下多行内容仍自动撑高不裁切。 */
:deep(.el-table .el-table__row) {
  height: 40px;
}

/* ======================================
   分组胶囊 Tab（方案 B，2026-08-14）
   ====================================== */

/* 横向滚动条细化为 --border-light 色 */
.group-tabs-scroll {
  scrollbar-color: var(--border-light) transparent;
  scrollbar-width: thin;
}

.group-tabs-scroll::-webkit-scrollbar {
  height: 4px;
}

.group-tabs-scroll::-webkit-scrollbar-thumb {
  background-color: var(--border-light);
  border-radius: var(--radius-pill);
}

.group-tabs-scroll::-webkit-scrollbar-track {
  background: transparent;
}

/* tab 项：32px 胶囊；选中态软按钮（--brand-100/--brand-700/--brand-400），未选中 --text-secondary + hover --bg-hover */
.group-tab {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.group-tab:hover {
  background-color: var(--bg-hover);
}

.group-tab.is-active {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.group-tab.is-active:hover {
  background-color: var(--brand-200);
}

/* 分组名：展示截断 8 汉字（8em），全名由 title 提示（后端管存储、前端管展示） */
.group-tab-label {
  max-width: 8em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-tab-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.group-tab.is-active .group-tab-count {
  color: var(--brand-700);
}

/* 分组编辑/删除：hover 浮现（opacity 机制，与操作列统一） */
.group-tab-actions {
  display: flex;
  gap: 2px;
  align-items: center;
  opacity: 0;
  transition: opacity 150ms ease;
}

.group-tab:hover .group-tab-actions {
  opacity: 1;
}

.group-tab-edit-input {
  width: 96px;
}

/* 新建分组按钮：与 tab 同高 32px 的圆形 */
.group-tab-add {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: 50%;
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.group-tab-add:hover {
  color: var(--text-secondary);
  background-color: var(--bg-hover);
}

/* 置顶/关注标记图标：--text-tertiary，行 hover 提亮 --text-secondary，语义靠 icon 形状区分 */
.marker-icon {
  display: inline-flex;
  color: var(--text-tertiary);
  transition: color 150ms ease;
}

:deep(.el-table__row:hover .marker-icon) {
  color: var(--text-secondary);
}

/* 标签 chips（名称列第二行）：胶囊 + 数据色底与边框 */
.tag-chip {
  line-height: 1.4;
  border-radius: var(--radius-pill);
}
</style>
