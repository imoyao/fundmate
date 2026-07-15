<template>
  <div
    class="watchlist-page p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部操作栏（统一 small 尺寸，紧凑现代） -->
    <div class="flex flex-wrap items-center justify-between gap-4 mb-6 top-bar">
      <div class="flex items-center gap-3">
        <el-segmented
          v-model="currentView"
          :options="viewOptions"
          size="small"
          @change="handleViewChange"
        />
        <div class="flex items-center relative">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索当前自选列表..."
            clearable
            class="w-48"
            size="small"
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
        <!-- ✅ 主按钮：强制 small，靠品牌色突出，不再靠体积 -->
        <el-button type="primary" size="small" @click="showAddModal = true">
          <IconifyIconOffline icon="ep:plus" class="mr-1" />
          添加自选
        </el-button>

        <!-- ✅ 次要按钮：全部用 plain，强制 small -->
        <el-button size="small" plain @click="exportData">
          <IconifyIconOffline icon="ep:download" class="mr-1" />
          导出
        </el-button>
        <el-button size="small" plain @click="showTagManager = true">
          <IconifyIconOffline icon="ep:setting" class="mr-1" />
          管理标签
        </el-button>

        <!-- ✅ 刷新建议也统一为 plain 或 text，保持横向节奏 -->
        <el-button size="small" plain @click="fetchData">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" />
          刷新
        </el-button>
      </div>
    </div>

    <!-- 主区域：分组 + 表格 -->
    <div class="flex gap-6 flex-wrap">
      <!-- 左侧分组树（新增悬停交互） -->
      <div
        class="w-56 shrink-0 rounded-2xl p-4 h-fit"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
      >
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-bold" :style="{ color: 'var(--text-primary)' }">
            分组
          </h3>
          <el-button text size="small" @click="handleAddGroup">
            <IconifyIconOffline icon="ep:plus" />
          </el-button>
        </div>
        <div class="space-y-1">
          <div
            v-for="group in allGroups"
            :key="group.key"
            class="group-item relative flex items-center justify-between px-3 py-1.5 rounded-lg text-sm cursor-pointer transition-colors"
            :style="
              activeGroup === group.key
                ? {
                    backgroundColor: 'var(--brand-100)',
                    color: 'var(--brand-700)',
                    fontWeight: 500
                  }
                : {
                    color: 'var(--text-secondary)',
                    backgroundColor: 'transparent'
                  }
            "
            @mouseenter="hoveringGroupKey = group.key"
            @mouseleave="hoveringGroupKey = null"
            @click="activeGroup = group.key"
          >
            <!-- 编辑态 -->
            <template
              v-if="
                editingGroupId !== null &&
                group.key === `custom_${editingGroupId}`
              "
            >
              <el-input
                v-model="editGroupName"
                size="small"
                class="flex-1 mr-1"
                @blur="saveEditGroup"
                @keyup.enter="saveEditGroup"
                @keyup.esc="cancelEditGroup"
                @click.stop
              />
              <el-button
                link
                size="small"
                class="shrink-0"
                @click.stop="cancelEditGroup"
              >
                <IconifyIconOffline icon="ep:close" class="text-xs" />
              </el-button>
            </template>
            <!-- 正常态 -->
            <template v-else>
              <div class="flex items-center gap-2">
                <span
                  class="w-2 h-2 rounded-full"
                  :style="{ backgroundColor: group.color }"
                />
                <span>{{ group.label }}</span>
              </div>
            </template>

            <div class="flex items-center gap-1">
              <span
                v-if="
                  !(
                    editingGroupId !== null &&
                    group.key === `custom_${editingGroupId}`
                  )
                "
                class="text-xs"
                :style="{ color: 'var(--text-tertiary)' }"
              >
                {{ group.count }}
              </span>
              <Transition name="fade-scale">
                <div
                  v-if="
                    hoveringGroupKey === group.key &&
                    group.key.startsWith('custom_') &&
                    !editingGroupId
                  "
                  class="flex items-center gap-0.5"
                  @click.stop
                  @mouseenter.stop
                >
                  <el-button link size="small" @click="startEditGroup(group)">
                    <IconifyIconOffline icon="ep:edit" class="text-xs" />
                  </el-button>
                  <el-popconfirm
                    title="确定删除该分组？分组内的资产不会被删除。"
                    :teleported="false"
                    @confirm="deleteGroupConfirm(group)"
                  >
                    <template #reference>
                      <el-button link size="small" type="danger">
                        <IconifyIconOffline icon="ep:delete" class="text-xs" />
                      </el-button>
                    </template>
                  </el-popconfirm>
                </div>
              </Transition>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧表格 -->
      <div
        class="flex-1 min-w-[600px] rounded-2xl p-6"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
      >
        <!-- 资产类型快捷筛选胶囊 -->
        <div class="flex items-center gap-2 mb-3">
          <button
            v-for="item in VENUE_FILTER_OPTIONS"
            :key="item.value"
            class="px-3 py-1 text-xs rounded-full border transition-colors cursor-pointer"
            :class="
              currentVenueFilter === item.value
                ? 'bg-[var(--brand-100)] text-[var(--brand-700)] border-[var(--brand-400)]'
                : 'bg-transparent text-[var(--text-secondary)] border-[var(--border-default)] hover:bg-[var(--bg-hover)]'
            "
            @click="setVenueFilter(item.value)"
          >
            {{ item.label }}
            <template v-if="item.value === 'all'">{{
              venueStats.total
            }}</template>
            <template v-if="item.value === 'EXCHANGE'">{{
              venueStats.exchange
            }}</template>
            <template v-if="item.value === 'OTC'">{{
              venueStats.otc
            }}</template>
          </button>
        </div>
        <!-- 标签筛选与批量管理 -->
        <div class="flex flex-wrap items-center justify-between mb-4 gap-2">
          <p
            class="text-xs shrink-0"
            :style="{ color: 'var(--text-tertiary)' }"
          >
            {{ activeGroupLabel }} · {{ totalItems }} 项
            <el-button text size="small" class="ml-2" @click="toggleBatchMode">
              {{ batchMode ? "取消" : "批量管理" }}
            </el-button>
            <el-button
              v-if="batchMode && selectedItems.length > 0"
              type="danger"
              size="small"
              plain
              class="ml-1"
              @click="handleBatchDelete"
            >
              删除选中 ({{ selectedItems.length }})
            </el-button>
          </p>
          <div class="flex items-center gap-2">
            <el-select
              v-model="selectedFilterTagIds"
              multiple
              filterable
              clearable
              placeholder="按标签筛选..."
              size="small"
              class="w-56 min-w-[180px] modern-filter-select"
              @change="handleTagFilterChange"
            >
              <el-option
                v-for="tag in allTags"
                :key="tag.id"
                :label="tag.name"
                :value="tag.id"
              >
                <div class="flex items-center gap-2">
                  <span
                    class="w-3 h-3 rounded-full"
                    :style="{ backgroundColor: tag.color || '#C5C9B8' }"
                  />
                  <span>{{ tag.name }}</span>
                </div>
              </el-option>
            </el-select>
          </div>
        </div>

        <el-table
          v-loading="loading"
          :data="items"
          stripe
          size="default"
          :row-style="{ height: '48px' }"
          @row-click="handleRowClick"
          @selection-change="handleSelectionChange"
        >
          <!-- 批量选择列（仅批量模式下显示） -->
          <el-table-column
            v-if="batchMode"
            type="selection"
            width="50"
            align="center"
          />

          <!-- 标记列 -->
          <el-table-column width="50" align="center" class-name="marker-column">
            <template #default="{ row }">
              <div class="flex items-center justify-center gap-0.5">
                <span
                  v-if="row.is_pinned"
                  class="text-yellow-500"
                  title="已置顶"
                >
                  <IconifyIconOffline icon="mdi:pin-outline" class="text-sm" />
                </span>
                <span
                  v-if="row.favorite"
                  class="text-purple-400"
                  title="特别关注"
                >
                  <IconifyIconOffline icon="ep:star" class="text-sm" />
                </span>
              </div>
            </template>
          </el-table-column>

          <!-- 产品信息列（与标签同行） -->
          <el-table-column label="代码/名称" min-width="200">
            <template #default="{ row }">
              <div class="flex items-center gap-2 h-full py-2">
                <!-- 产品主体信息 -->
                <ProductDisplay
                  :name="row.display_name || row.symbol"
                  :symbol="row.symbol"
                  :type-label="row.type_label || ''"
                />
                <!-- 基金标识 -->
                <span
                  v-if="row.venue === 'OTC'"
                  class="fund-tag"
                >[基]</span>
                <div class="flex items-center gap-1 flex-shrink-0">
                  <template v-if="row.tag_ids && row.tag_ids.length > 0">
                    <el-tag
                      v-for="tagId in row.tag_ids.slice(0, 2)"
                      :key="tagId"
                      size="small"
                      class="text-[10px] px-1.5 py-0.5 rounded border-none"
                      :style="{
                        backgroundColor: getTagColor(tagId) + '20',
                        color: 'var(--text-primary)',
                        border: '1px solid ' + getTagColor(tagId)
                      }"
                    >
                      {{ getTagName(tagId) }}
                    </el-tag>
                    <!-- 如果标签超过2个，显示 +N -->
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
                      class="add-tag-btn !w-[16px] !h-[16px] !min-h-[16px] !ml-1"
                      @click.stop="openTagEditor(row)"
                    >
                      <IconifyIconOffline icon="ep:plus" class="text-[10px]" />
                    </el-button>
                  </el-tooltip>
                </div>
              </div>
            </template>
          </el-table-column>

          <el-table-column
            prop="current_price"
            label="最新价"
            width="110"
            align="right"
          >
            <template #default="{ row }">
              <MoneyDisplay
                v-if="row.current_price != null"
                :value="row.current_price"
                :show-sign="false"
                :show-currency="false"
                size="sm"
              />
              <span v-else :style="{ color: 'var(--text-tertiary)' }">--</span>
            </template>
          </el-table-column>

          <el-table-column
            prop="change_pct"
            label="涨跌幅"
            width="100"
            align="right"
          >
            <template #default="{ row }">
              <span
                v-if="row.change_pct != null"
                class="inline-block px-1.5 py-0.5 rounded text-xs font-medium"
                :class="{ 'font-bold': Math.abs(row.change_pct) >= 2 }"
                :style="{
                  backgroundColor:
                    row.change_pct >= 0
                      ? 'rgba(227, 79, 56, 0.08)'
                      : 'rgba(123, 196, 154, 0.1)',
                  color:
                    row.change_pct >= 0
                      ? 'var(--color-rise)'
                      : 'var(--color-fall)'
                }"
              >
                {{ row.change_pct >= 0 ? '▲' : '▼' }}{{ Math.abs(row.change_pct).toFixed(2) }}%
              </span>
              <span v-else :style="{ color: 'var(--text-tertiary)' }">--</span>
            </template>
          </el-table-column>

          <el-table-column
            prop="position_market_value"
            label="持仓市值"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <MoneyDisplay
                v-if="row.position_market_value != null"
                :value="row.position_market_value"
                :show-sign="false"
                size="sm"
              />
              <span v-else :style="{ color: 'var(--text-tertiary)' }">--</span>
            </template>
          </el-table-column>

          <!-- 操作列（批量模式下隐藏部分操作） -->
          <el-table-column
            label="操作"
            width="120"
            align="center"
            fixed="right"
          >
            <template #default="{ row }">
              <template v-if="!batchMode">
                <el-tooltip
                  :content="row.is_pinned ? '取消置顶' : '置顶'"
                  placement="top"
                >
                  <el-button
                    circle
                    size="small"
                    @click.stop="handleTogglePin(row)"
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
                    @click.stop="handleToggleFavorite(row)"
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
                    @click.stop="confirmRemove(row)"
                  >
                    <IconifyIconOffline icon="ep:delete" />
                  </el-button>
                </el-tooltip>
              </template>
              <template v-else>
                <!-- 批量模式下禁用单行操作 -->
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                  >-</span
                >
              </template>
            </template>
          </el-table-column>
        </el-table>

        <div class="flex justify-end mt-4">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="totalItems"
            layout="prev, pager, next"
            small
            background
            @current-change="fetchData"
          />
        </div>
      </div>
    </div>

    <!-- 弹窗部分（逻辑保持不变） -->
    <AddToWatchlistModal
      v-model="showAddModal"
      :initial-group-id="activeCustomGroupId"
      @submitted="onItemAdded"
    />

    <el-dialog v-model="showGroupDialog" title="新建分组" width="320px">
      <el-input v-model="newGroupName" placeholder="分组名称" />
      <template #footer>
        <el-button @click="showGroupDialog = false">取消</el-button>
        <el-button type="primary" @click="createGroup">确定</el-button>
      </template>
    </el-dialog>

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
        <el-button @click="removeDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="executeRemove">确定</el-button>
      </template>
    </el-dialog>

    <!-- 标签管理对话框 -->
    <el-dialog
      v-model="showTagManager"
      title="管理标签"
      width="560px"
      class="tag-manager-dialog"
      :close-on-click-modal="false"
    >
      <div class="tag-manager-body">
        <!-- 1. 标签选择器 -->
        <div class="mb-4">
          <div
            class="text-sm font-medium mb-2"
            :style="{ color: 'var(--text-secondary)' }"
          >
            选择要管理的标签
          </div>
          <el-select
            v-model="selectedTagIdsForManager"
            multiple
            filterable
            placeholder="搜索并选择标签..."
            class="w-full"
            size="default"
            popper-class="tag-manager-select-dropdown"
            @change="handleSelectChange"
          >
            <el-option
              v-for="tag in allTags"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <div class="flex items-center gap-2">
                <span
                  class="w-3 h-3 rounded-full"
                  :style="{ backgroundColor: tag.color || '#B6B09C' }"
                />
                <span>{{ tag.name }}</span>
              </div>
            </el-option>
          </el-select>
        </div>

        <!-- 2. 已选标签操作列表（点击可直接编辑） -->
        <div v-if="selectedTagIdsForManager.length > 0" class="mb-4">
          <div class="text-xs mb-2" :style="{ color: 'var(--text-tertiary)' }">
            已选标签（点击可编辑）
          </div>
          <div class="flex flex-wrap gap-2">
            <div
              v-for="tagId in selectedTagIdsForManager"
              :key="tagId"
              class="flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-colors select-none"
              :class="{ 'ring-2 ring-offset-2': editingTagId === tagId }"
              :style="{
                backgroundColor: getTagColor(tagId) + '20',
                border:
                  '1px solid ' +
                  (editingTagId === tagId
                    ? 'var(--brand-700)'
                    : getTagColor(tagId)),
                boxShadow: editingTagId === tagId ? 'var(--focus-ring)' : 'none'
              }"
              @click="selectTagForEdit(tagId)"
            >
              <span :style="{ color: 'var(--text-primary)' }">{{
                getTagName(tagId)
              }}</span>
              <el-icon
                class="cursor-pointer hover:text-danger transition-colors"
                @click.stop="removeTagFromSelection(tagId)"
              >
                <Close />
              </el-icon>
            </div>
          </div>
        </div>

        <!-- 3. 新建/编辑表单区域 -->
        <div
          class="p-4 rounded-xl"
          :style="{ backgroundColor: 'var(--bg-warm)' }"
        >
          <div class="flex flex-wrap items-end gap-3">
            <div class="flex-1 min-w-[150px]">
              <!-- ✅ 修复 v-model 报错：使用 v-if/v-else 区分 -->
              <el-input
                v-if="editingTagId"
                ref="editInputRef"
                v-model="editTagName"
                placeholder="修改标签名称..."
                size="default"
                class="w-full"
                @keyup.enter="saveEditTag(editingTagId)"
              />
              <el-input
                v-else
                v-model="newTagNameInManager"
                placeholder="输入新标签名..."
                size="default"
                class="w-full"
                @keyup.enter="addNewTagInManager"
              />
            </div>
            <div class="flex gap-1.5 items-center shrink-0">
              <button
                v-for="c in presetColors"
                :key="c"
                class="color-swatch-btn"
                :class="{
                  'is-selected': editingTagId
                    ? editTagColor === c
                    : newTagColorInManager === c
                }"
                :style="{ backgroundColor: c }"
                @click="
                  editingTagId ? (editTagColor = c) : (newTagColorInManager = c)
                "
              />
            </div>
            <el-button
              v-if="editingTagId"
              type="primary"
              size="default"
              @click="saveEditTag(editingTagId)"
            >
              保存修改
            </el-button>
            <el-button
              v-else
              type="primary"
              size="default"
              @click="addNewTagInManager"
            >
              添加标签
            </el-button>
          </div>

          <!-- 只有在编辑模式下才展示危险删除按钮 -->
          <div v-if="editingTagId" class="flex justify-end mt-3">
            <el-popconfirm
              title="确定要删除该标签吗？"
              @confirm="deleteTag(editingTagId)"
            >
              <template #reference>
                <el-button type="danger" link size="small">
                  <el-icon class="mr-1"><Delete /></el-icon> 删除此标签
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button size="default" @click="showTagManager = false"
          >关闭</el-button
        >
      </template>
    </el-dialog>

    <!-- 行内标签编辑弹窗 -->
    <el-dialog v-model="showTagEditor" title="编辑标签" width="420px">
      <div class="mb-4">
        <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
          为
          <strong>{{
            editingItem?.display_name || editingItem?.symbol
          }}</strong>
          添加或移除标签
        </span>
      </div>

      <div v-if="editingItem && editingItem.tag_ids.length > 0" class="mb-4">
        <span
          class="text-xs block mb-2"
          :style="{ color: 'var(--text-tertiary)' }"
          >已有标签</span
        >
        <div class="flex flex-wrap gap-2">
          <el-tag
            v-for="tagId in editingItem.tag_ids"
            :key="tagId"
            size="small"
            closable
            :style="{
              backgroundColor: getTagColor(tagId) + '20',
              color: '#333333',
              border: '1px solid ' + getTagColor(tagId)
            }"
            @close="removeTagFromEditingItem(tagId)"
          >
            {{ getTagName(tagId) }}
          </el-tag>
        </div>
      </div>

      <div class="mb-4">
        <span
          class="text-xs block mb-2"
          :style="{ color: 'var(--text-tertiary)' }"
          >添加标签</span
        >
        <div class="flex gap-2">
          <el-select
            v-model="editingItemNewTagIds"
            multiple
            filterable
            placeholder="选择标签"
            class="flex-1"
            size="small"
          >
            <el-option
              v-for="tag in availableTagsForEditor"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <div class="flex items-center gap-2">
                <span
                  class="w-3 h-3 rounded-full"
                  :style="{ backgroundColor: tag.color || '#C5C9B8' }"
                />
                <span>{{ tag.name }}</span>
              </div>
            </el-option>
          </el-select>
          <el-button size="small" @click="showNewTagFormInEditor = true">
            <IconifyIconOffline icon="ep:plus" />
          </el-button>
        </div>

        <div
          v-if="showNewTagFormInEditor"
          class="mt-2 p-3 bg-gray-50 rounded-lg flex items-end gap-2"
        >
          <el-input
            v-model="newTagNameInEditor"
            placeholder="标签名"
            size="small"
            class="w-24"
          />
          <div class="flex gap-1">
            <button
              v-for="c in presetColors"
              :key="c"
              class="w-5 h-5 rounded-full border-2 transition-colors cursor-pointer"
              :class="
                newTagColorInEditor === c
                  ? 'border-gray-800 scale-110'
                  : 'border-transparent'
              "
              :style="{ backgroundColor: c }"
              @click="newTagColorInEditor = c"
            />
          </div>
          <el-button type="primary" size="small" @click="createTagInEditor"
            >确定</el-button
          >
          <el-button size="small" @click="showNewTagFormInEditor = false"
            >取消</el-button
          >
        </div>
      </div>

      <template #footer>
        <el-button @click="showTagEditor = false">取消</el-button>
        <el-button type="primary" :loading="savingTags" @click="saveTagChanges"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  onBeforeUnmount,
  watch,
  nextTick
} from "vue";
import { Search, Close, Delete } from "@element-plus/icons-vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { ElInput } from "element-plus";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import {
  getWatchlistItems,
  getWatchlistGroups,
  createWatchlistGroup,
  updateWatchlistGroup,
  deleteWatchlistGroup,
  updateWatchlistItem,
  deleteWatchlistItem,
  removeItemFromGroup,
  getWatchlistTags,
  updateWatchlistTag,
  deleteWatchlistTag,
  addTagToItem,
  removeTagFromItem,
  createWatchlistTag,
  type WatchlistItem,
  type WatchlistGroup,
  type WatchlistTag
} from "@/api/watchlist";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";

defineOptions({ name: "Watchlist" });

// ─────────────────────────────────────────────
// 基础配置
// ─────────────────────────────────────────────
const currentView = ref("all");
const viewOptions = [
  { label: "全部", value: "all" },
  { label: "场内", value: "exchange" },
  { label: "场外", value: "otc" }
];

const systemGroups = [
  { key: "all", label: "全部", color: "#949599", filter: {} },
  {
    key: "holding",
    label: "持仓",
    color: "#e07a5f",
    filter: { status: "HOLDING" }
  },
  {
    key: "watching",
    label: "观察中",
    color: "#81b29a",
    filter: { status: "WATCHING" }
  },
  {
    key: "cleared",
    label: "已清仓",
    color: "#f2cc8f",
    filter: { cleared: true }
  },
  {
    key: "exchange",
    label: "场内资产",
    color: "#819cd1",
    filter: { venue: "EXCHANGE" }
  },
  { key: "otc", label: "场外基金", color: "#9d81a9", filter: { venue: "OTC" } },
  {
    key: "favorite",
    label: "特别关注",
    color: "#a89f94",
    filter: { favorite: true }
  }
];

const presetColors = [
  "#B8A99A",
  "#9CAF88",
  "#8DA3B8",
  "#C4A0A8",
  "#9B9EB0",
  "#B6B09C"
];

// ─────────────────────────────────────────────
// 响应式数据
// ─────────────────────────────────────────────
const activeGroup = ref("holding");
const allGroups = ref<any[]>([]);
const customGroups = ref<WatchlistGroup[]>([]);

const items = ref<WatchlistItem[]>([]);
const loading = ref(false);
const searchKeyword = ref("");
const currentPage = ref(1);
const pageSize = ref(20);
const totalItems = ref(0);

const allTags = ref<WatchlistTag[]>([]);
const selectedFilterTagIds = ref<number[]>([]);
const showTagManager = ref(false);
const editingTagId = ref<number | null>(null);
const editTagName = ref("");
const editTagColor = ref("#B6B09C");
const selectedTagIdsForManager = ref<number[]>([]);
const editInputRef = ref<InstanceType<typeof ElInput> | null>(null);

const showAddModal = ref(false);
const showGroupDialog = ref(false);
const newGroupName = ref("");
const removeDialogVisible = ref(false);
const removingItem = ref<WatchlistItem | null>(null);
const removeScope = ref("all");

const showTagEditor = ref(false);
const editingItem = ref<WatchlistItem | null>(null);
const editingItemNewTagIds = ref<number[]>([]);
const savingTags = ref(false);
const showNewTagFormInEditor = ref(false);
const newTagNameInEditor = ref("");
const newTagColorInEditor = ref("#B6B09C");
const newTagNameInManager = ref("");
const newTagColorInManager = ref("#B6B09C");

// 🆕 分组管理
const hoveringGroupKey = ref<string | null>(null);
const editingGroupId = ref<number | null>(null);
const editGroupName = ref("");

const venueStats = computed(() => {
  const total = items.value.length;
  const exchange = items.value.filter(i => i.venue === "EXCHANGE").length;
  const otc = items.value.filter(i => i.venue === "OTC").length;
  return { total, exchange, otc };
});

// 资产类型筛选选项
const VENUE_FILTER_OPTIONS = [
  { label: "全部", value: "all" },
  { label: "股票", value: "EXCHANGE" },
  { label: "基金", value: "OTC" }
] as const;

const currentVenueFilter = ref<"all" | "EXCHANGE" | "OTC">("all");

// 🆕 批量操作
const batchMode = ref(false);
const selectedItems = ref<WatchlistItem[]>([]);
// ─────────────────────────────────────────────
// 计算属性
// ─────────────────────────────────────────────
const activeGroupLabel = computed(() => {
  const group = allGroups.value.find(g => g.key === activeGroup.value);
  return group?.label || "全部";
});

const currentIsCustom = computed(() => activeGroup.value.startsWith("custom_"));

const activeCustomGroupId = computed(() => {
  if (currentIsCustom.value) {
    const idStr = activeGroup.value.replace("custom_", "");
    return /^\d+$/.test(idStr) ? parseInt(idStr) : undefined;
  }
  return undefined;
});

let outsideClickHandler: ((e: MouseEvent) => void) | null = null;

const usedTagIds = computed(() => {
  const ids = new Set<number>();
  if (!Array.isArray(items.value)) return ids;
  items.value.forEach(item => {
    const tagIds = item?.tag_ids;
    if (Array.isArray(tagIds)) {
      tagIds.forEach(id => {
        if (typeof id === "number" && !isNaN(id)) ids.add(id);
      });
    }
  });
  return ids;
});

const fetchParams = computed(() => {
  const params: Record<string, any> = {
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
    const group = systemGroups.find(g => g.key === groupKey);
    if (group && group.filter) {
      Object.entries(group.filter).forEach(([k, v]) => {
        params[k === "cleared" ? "status" : k] =
          k === "cleared" ? "cleared" : v;
      });
    }
  }
  if (currentVenueFilter.value !== "all") {
    params.venue = currentVenueFilter.value;
  }
  if (currentView.value === "exchange") params.venue = "EXCHANGE";
  else if (currentView.value === "otc") params.venue = "OTC";
  if (searchKeyword.value) params.q = searchKeyword.value;
  return params;
});

const availableTagsForEditor = computed(() => {
  if (!editingItem.value) return allTags.value;
  const existingIds = new Set(editingItem.value.tag_ids);
  return allTags.value.filter(t => !existingIds.has(t.id));
});
// 批量操作相关方法
function toggleBatchMode() {
  batchMode.value = !batchMode.value;
  if (!batchMode.value) {
    selectedItems.value = [];
  }
}

function setVenueFilter(venue: "all" | "EXCHANGE" | "OTC") {
  currentVenueFilter.value = venue;
  fetchData();   // 始终使用 fetchData，它会从 fetchParams 中读取 currentVenueFilter
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
        // 忽略单个失败
      }
    }
    ElMessage.success("批量移除完成");
    batchMode.value = false;
    selectedItems.value = [];
    fetchData();
  } catch (e) {
    // 用户取消
  }
}

function startEditGroup(group: any) {
  if (group.key.startsWith("custom_")) {
    const id = parseInt(group.key.replace("custom_", ""));
    // 如果已经在编辑当前分组，则取消编辑
    if (editingGroupId.value === id) {
      cancelEditGroup();
      return;
    }
    editingGroupId.value = id;
    editGroupName.value = group.label;
    // 添加全局点击监听，点击外部取消编辑
    nextTick(() => {
      if (outsideClickHandler)
        document.removeEventListener("click", outsideClickHandler);
      outsideClickHandler = (e: MouseEvent) => {
        const target = e.target as HTMLElement;
        // 点击在分组项内部或弹窗内不取消
        if (target.closest(".group-item") || target.closest(".el-popconfirm"))
          return;
        cancelEditGroup();
      };
      // 延迟绑定，避免立即触发起始按钮的 click
      setTimeout(
        () => document.addEventListener("click", outsideClickHandler!),
        0
      );
    });
  } else {
    ElMessage.info("系统分组暂不支持编辑");
  }
}

function cancelEditGroup() {
  editingGroupId.value = null;
  editGroupName.value = "";
  if (outsideClickHandler) {
    document.removeEventListener("click", outsideClickHandler);
    outsideClickHandler = null;
  }
}

async function saveEditGroup() {
  if (!editingGroupId.value || !editGroupName.value.trim()) return;
  const originalGroup = allGroups.value.find(
    g => g.key === `custom_${editingGroupId.value}`
  );
  // 名称未改变，直接退出编辑态（无需请求后端）
  if (originalGroup && editGroupName.value.trim() === originalGroup.label) {
    cancelEditGroup();
    return;
  }
  try {
    await updateWatchlistGroup(editingGroupId.value, {
      name: editGroupName.value.trim()
    });
    ElMessage.success("分组已更新");
    cancelEditGroup();
    fetchGroups();
  } catch (e) {
    ElMessage.error("更新分组失败");
  }
}

async function deleteGroupConfirm(group: any) {
  if (!group.key.startsWith("custom_")) return;
  const groupId = parseInt(group.key.replace("custom_", ""));
  try {
    await deleteWatchlistGroup(groupId);
    ElMessage.success("分组已删除");
    fetchGroups();
  } catch (e) {
    ElMessage.error("删除分组失败");
  }
}

// ─────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────
function getTagName(tagId: number): string {
  return allTags.value.find(t => t.id === tagId)?.name || "?";
}

function getTagColor(tagId: number): string {
  return allTags.value.find(t => t.id === tagId)?.color || "#d9d9d9";
}

function getSystemFilter(key: string): Record<string, any> {
  const map: Record<string, Record<string, any>> = {
    all: {},
    holding: { status: "HOLDING" },
    watching: { status: "WATCHING" },
    cleared: { status: "cleared" },
    exchange: { venue: "EXCHANGE" },
    otc: { venue: "OTC" },
    favorite: { favorite: true }
  };
  return map[key] || {};
}

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
    items.value = (res as any).data ?? [];
    totalItems.value = (res as any).total ?? items.value.length;
  } catch (e) {
    ElMessage.error("获取自选列表失败");
    console.error("获取自选列表错误：", e);
  } finally {
    loading.value = false;
  }
}

async function fetchGroups() {
  try {
    const res = await getWatchlistGroups();
    const data: WatchlistGroup[] = (res as any).data ?? [];
    const system: any[] = [];
    const custom: WatchlistGroup[] = [];
    data.forEach(g => {
      if (g.is_system) {
        system.push({
          key: g.key!,
          label: g.label || g.name || g.key,
          color: g.color,
          count: g.count || 0,
          filter: getSystemFilter(g.key!)
        });
      } else {
        custom.push(g);
        system.push({
          key: `custom_${g.id}`,
          label: g.name,
          color: g.color || systemGroups[0].color,
          count: g.count || 0,
          filter: { group_id: g.id }
        });
      }
    });
    allGroups.value = system;
    customGroups.value = custom;
  } catch (e) {
    console.error("获取分组失败：", e);
  }
}

async function fetchTags() {
  try {
    const res = await getWatchlistTags();
    allTags.value = (res as any).data ?? [];
  } catch (e) {
    console.error("获取标签失败：", e);
  }
}

// ─────────────────────────────────────────────
// 事件处理
// ─────────────────────────────────────────────
function handleViewChange(val: string) {
  activeGroup.value = val === "exchange" || val === "otc" ? val : "all";
}

function handleTagFilterChange() {
  currentPage.value = 1;
  fetchData();
}

function resetFilters() {
  searchKeyword.value = "";
  activeGroup.value = "holding";
  currentView.value = "all";
  selectedFilterTagIds.value = [];
}

async function handleTogglePin(row: WatchlistItem) {
  try {
    await updateWatchlistItem(row.id, { is_pinned: !row.is_pinned });
    ElMessage.success(row.is_pinned ? "已取消置顶" : "已置顶");
    fetchData();
  } catch (e) {
    ElMessage.error("置顶操作失败");
    console.error("置顶错误：", e);
  }
}

async function handleToggleFavorite(row: WatchlistItem) {
  try {
    await updateWatchlistItem(row.id, { favorite: !row.favorite });
    ElMessage.success(row.favorite ? "已取消特别关注" : "已设为特别关注");
    fetchData();
  } catch (e) {
    ElMessage.error("关注操作失败");
    console.error("关注错误：", e);
  }
}

function handleRowClick(row: WatchlistItem) {}

function confirmRemove(row: WatchlistItem) {
  removingItem.value = row;
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

onBeforeUnmount(() => {
  if (outsideClickHandler) {
    document.removeEventListener("click", outsideClickHandler);
    outsideClickHandler = null;
  }
});

async function exportData() {
  try {
    const params = new URLSearchParams(fetchParams.value as any).toString();
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

function handleAddGroup() {
  showGroupDialog.value = true;
  newGroupName.value = "";
}

async function createGroup() {
  const groupName = newGroupName.value.trim();
  if (!groupName) {
    ElMessage.warning("请输入分组名称");
    return;
  }
  try {
    await createWatchlistGroup({ name: groupName });
    ElMessage.success("分组已创建");
    showGroupDialog.value = false;
    fetchGroups();
  } catch (e) {
    ElMessage.error("创建分组失败");
    console.error("创建分组错误：", e);
  }
}

// ─────────────────────────────────────────────
// 标签管理相关
// ─────────────────────────────────────────────
const openTagEditor = (row: WatchlistItem) => {
  editingItem.value = row;
  editingItemNewTagIds.value = [];
  showNewTagFormInEditor.value = false;
  showTagEditor.value = true;
};

// ✅ 新增：处理下拉框变更重置状态
const handleSelectChange = () => {
  if (selectedTagIdsForManager.value.length === 0) {
    editingTagId.value = null;
    editTagName.value = "";
  }
};

// ✅ 新增：点击已选标签卡片进入编辑态
const selectTagForEdit = (tagId: number) => {
  const tag = allTags.value.find(t => t.id === tagId);
  if (!tag) return;

  if (editingTagId.value === tagId) {
    editingTagId.value = null;
    editTagName.value = "";
    return;
  }

  editingTagId.value = tagId;
  editTagName.value = tag.name;
  editTagColor.value = tag.color || "#B6B09C";

  // 自动聚焦
  nextTick(() => {
    editInputRef.value?.focus();
  });
};

// ✅ 新增：移除已选标签卡片
const removeTagFromSelection = (tagId: number) => {
  selectedTagIdsForManager.value = selectedTagIdsForManager.value.filter(
    id => id !== tagId
  );
  if (editingTagId.value === tagId) {
    editingTagId.value = null;
    editTagName.value = "";
  }
};

const addNewTagInManager = async () => {
  if (!newTagNameInManager.value.trim()) return;
  try {
    const res = await createWatchlistTag({
      name: newTagNameInManager.value.trim(),
      color: newTagColorInManager.value
    });
    const newTag = (res as any).data;
    allTags.value.push({
      id: newTag.id,
      name: newTag.name,
      color: newTag.color || newTagColorInManager.value
    });
    // ✅ 新增：自动选中刚创建的标签
    selectedTagIdsForManager.value.push(newTag.id);

    newTagNameInManager.value = "";
    newTagColorInManager.value = "#B6B09C";
    ElMessage.success(`标签「${newTag.name}」已创建`);
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning("该标签已存在");
    } else {
      ElMessage.error("创建标签失败");
    }
  }
};

const removeTagFromEditingItem = async (tagId: number) => {
  if (!editingItem.value) return;
  try {
    await removeTagFromItem(editingItem.value.id, tagId);
    editingItem.value.tag_ids = editingItem.value.tag_ids.filter(
      id => id !== tagId
    );
    ElMessage.success("标签已移除");
  } catch (e) {
    ElMessage.error("移除标签失败");
  }
};

const createTagInEditor = async () => {
  if (!newTagNameInEditor.value.trim()) return;
  try {
    const res = await createWatchlistTag({
      name: newTagNameInEditor.value.trim(),
      color: newTagColorInEditor.value
    });
    const newTag = (res as any).data;
    allTags.value.push({
      id: newTag.id,
      name: newTag.name,
      color: newTag.color || newTagColorInEditor.value
    });
    editingItemNewTagIds.value.push(newTag.id);
    showNewTagFormInEditor.value = false;
    newTagNameInEditor.value = "";
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning("该标签已存在");
    } else {
      ElMessage.error("创建标签失败");
    }
  }
};

const saveTagChanges = async () => {
  if (!editingItem.value) return;
  savingTags.value = true;
  try {
    const itemId = editingItem.value.id;
    for (const tagId of editingItemNewTagIds.value) {
      await addTagToItem(itemId, tagId);
    }
    ElMessage.success("标签已更新");
    showTagEditor.value = false;
    await fetchData();
    await fetchTags();
  } catch (e) {
    ElMessage.error("保存标签失败");
  } finally {
    savingTags.value = false;
  }
};

const saveEditTag = async (tagId: number) => {
  const originalTag = allTags.value.find(t => t.id === tagId);
  if (!originalTag) return;
  const newName = editTagName.value.trim();
  if (!newName) {
    ElMessage.warning("请输入标签名称");
    editTagName.value = originalTag.name;
    return;
  }
  if (
    newName === originalTag.name &&
    editTagColor.value === (originalTag.color || "#B6B09C")
  ) {
    editingTagId.value = null;
    return;
  }
  try {
    await updateWatchlistTag(tagId, {
      name: newName,
      color: editTagColor.value
    });
    ElMessage.success("标签已更新");
    editingTagId.value = null;
    await fetchTags();
    // 确保编辑态自动退出
    editingTagId.value = null;
    editTagName.value = "";
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning("标签名称已存在");
      editTagName.value = originalTag.name;
    } else {
      ElMessage.error("更新标签失败");
    }
  }
};

const deleteTag = async (tagId: number) => {
  if (usedTagIds.value.has(tagId)) {
    ElMessage.warning("该标签正被使用，无法删除");
    return;
  }
  try {
    await deleteWatchlistTag(tagId);
    ElMessage.success("标签已删除");
    await fetchTags();

    // 清理
    removeTagFromSelection(tagId);
    selectedTagIdsForManager.value = selectedTagIdsForManager.value.filter(
      id => id !== tagId
    );
  } catch (e) {
    ElMessage.error("删除标签失败");
    console.error("删除标签错误：", e);
  }
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
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}
.add-tag-btn {
  opacity: 0;
  transition: opacity 0.2s;
  width: 20px;
  height: 20px;
  min-height: 20px;
}
.el-table__row:hover .add-tag-btn {
  opacity: 1;
}
.add-tag-btn:only-child {
  opacity: 1;
}

/* 基金标识标签 */
.fund-tag {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 4px;
  background-color: var(--brand-100);
  color: var(--brand-700);
  line-height: 1.4;
  white-space: nowrap;
}

/* 编辑标签时的输入框宽度控制 */
.edit-tag-input {
  width: 100px;
}

/* 颜色选择按钮 */
.color-swatch-btn {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}
.color-swatch-btn.is-selected {
  border-color: var(--brand-700);
  transform: scale(1.15);
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}
.color-swatch-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}

/* ======================================
   基础输入框/下拉框样式（不规定高度，交由组件自己控制）
   ====================================== */
:deep(.el-input__wrapper) {
  border-radius: var(--radius-sm);
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}
:deep(.el-select .el-input__wrapper) {
  border-radius: var(--radius-sm);
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);
}

/* ======================================
   ✅ 核心修正区：仅对顶部工具栏 (class="top-bar") 强制 32px 高度
   绝对不会影响表格里的圆按钮、标签或其他地方的按钮！
   ====================================== */
.top-bar :deep(.el-input.el-input--small .el-input__wrapper) {
  height: 32px !important;
  padding: 0 12px !important;
}
.top-bar :deep(.el-button.el-button--small) {
  height: 32px !important;
  padding: 6px 14px !important;
  min-height: 32px !important;
}
.top-bar :deep(.el-button--primary.el-button--small) {
  height: 32px !important;
}

/* 顶部筛选下拉框（现代极简风） */
.top-bar :deep(.modern-filter-select .el-input__wrapper) {
  height: 32px !important;
  background-color: var(--bg-warm);
  border: none !important;
  box-shadow: none !important;
  border-radius: var(--radius-pill);
  padding: 0 12px;
  transition: all 0.2s ease;
}
.top-bar :deep(.modern-filter-select .el-input__wrapper:hover) {
  background-color: var(--bg-hover);
}
.top-bar :deep(.modern-filter-select .el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700) !important;
  background-color: #ffffff;
}
.top-bar :deep(.modern-filter-select .el-input__suffix-inner) {
  color: var(--text-tertiary);
}

/* ======================================
   按钮动效（移除所有对 height 的强制覆盖，纯动效过渡）
   ====================================== */
:deep(.el-button--primary:active) {
  transform: translateY(1px) scale(0.96);
  box-shadow: none !important;
}
:deep(.el-button:not(.el-button--primary)) {
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}
:deep(.el-button:not(.el-button--primary):active) {
  transform: scale(0.94);
}
:deep(.el-button.is-text:active) {
  transform: scale(0.96);
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
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
    background-color: var(--bg-card);
    overflow: hidden;
  }
  :deep(.el-dialog__header) {
    padding: var(--space-standard);
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--border-light);
    margin-right: 0;
  }
  :deep(.el-dialog__title) {
    font-size: var(--text-heading);
    color: var(--text-primary);
    font-weight: 600;
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
    height: 40px;
    border-radius: var(--radius-sm);
    --el-input-border-color: var(--border-default);
  }
}

/* 操作列按钮默认隐藏，行悬停时浮现 */
:deep(.el-table__row .el-button) {
  opacity: 0;
  transition: opacity 0.2s ease;
}
:deep(.el-table__row:hover .el-button) {
  opacity: 1;
}
</style>
