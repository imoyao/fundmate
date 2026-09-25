<template>
  <section class="profile-card profile-card-enter">
    <!-- ===== 区块一：个人资料 ===== -->
    <SectionHeader title="个人资料" />

    <!-- 头像区（重构为：顶部预览+控制，底部选项网格） -->
    <div class="avatar-zone">
      <!-- 第一排：头像预览 + 控制区 -->
      <div class="avatar-top-row">
        <!-- 放大预览 -->
        <Superellipse class="avatar-frame" :power="3">
          <img
            :src="p.avatarPreview"
            class="avatar-preview"
            :alt="p.currentNickname"
          />
        </Superellipse>

        <!-- 控制区（开关 + 随机） -->
        <div class="avatar-control">
          <label class="avatar-anim-toggle">
            <el-switch
              v-model="p.avatarAnimated"
              size="small"
              @change="p.persistAvatar"
            />
            <span class="avatar-anim-toggle__label">使用动态头像</span>
          </label>
          <!-- 两个操作按钮并排一行：撤销的出现/消失不改变行高，避免页面高度变化引发滚动条抖动 -->
          <div class="avatar-actions">
            <button type="button" class="link-btn" @click="p.onRandomizeAvatar">
              <IconifyIconOffline
                icon="lucide:shuffle"
                class="link-btn__icon"
                aria-hidden="true"
              />
              随机换一个
            </button>
            <button
              v-if="p.avatarDirty"
              type="button"
              class="link-btn link-btn--muted"
              @click="p.onRevertAvatar"
            >
              <IconifyIconOffline
                icon="lucide:undo-2"
                class="link-btn__icon"
                aria-hidden="true"
              />
              撤销更改
            </button>
          </div>
        </div>
      </div>

      <!-- 第二排：下方头像网格 -->
      <ProfileAvatarStyleGrid
        :avatar-style="p.avatarStyle"
        :avatar-thumb-seed="p.avatarThumbSeed"
        :style-card-style="p.styleCardStyle"
        @select="p.onSelectStyle"
      />
    </div>

    <!-- 昵称字段 -->
    <div class="field-block">
      <div class="field-block__row-top">
        <div class="field-block__label-group">
          <span class="field-block__label">昵称</span>
          <span class="field-block__desc">你希望我们这样称呼你</span>
        </div>
      </div>
      <div class="field-block__input-row">
        <el-input
          v-model="p.profileForm.nickname"
          placeholder="请输入昵称"
          maxlength="16"
          class="field-input"
        >
          <template #suffix>
            <span class="char-count"
              >{{ p.profileForm.nickname.length }}/16</span
            >
          </template>
        </el-input>
        <el-button
          class="field-block__save"
          :type="p.nicknameDirty ? 'primary' : 'default'"
          :disabled="!p.nicknameDirty || p.nicknameSensitive"
          :loading="p.nicknameSaving"
          @click="p.onSaveNickname"
        >
          保存
        </el-button>
      </div>
      <p v-if="p.nicknameSensitive" class="field-hint field-hint--warn">
        昵称可能包含不当词汇，请修改后再保存
      </p>
    </div>

    <!-- 用户名字段 -->
    <div class="field-block">
      <div class="field-block__row-top">
        <div class="field-block__label-group">
          <span class="field-block__label">用户名</span>
          <span class="field-block__desc">它会陪你见证你的每一次复利成长</span>
        </div>
      </div>
      <div class="field-block__input-row">
        <el-input
          v-model="p.profileForm.username"
          placeholder="请输入用户名"
          maxlength="20"
          class="field-input"
        >
          <template #suffix>
            <span class="char-count"
              >{{ p.profileForm.username.length }}/20</span
            >
          </template>
        </el-input>
        <el-button
          class="field-block__save"
          :type="p.usernameDirty ? 'primary' : 'default'"
          :disabled="!p.usernameDirty || p.usernameSensitive"
          :loading="p.usernameSaving"
          @click="p.onSaveUsername"
        >
          保存
        </el-button>
      </div>
      <p v-if="p.usernameSensitive" class="field-hint field-hint--warn">
        用户名可能包含不当词汇，请修改后再保存
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import Superellipse from "@/components/Superellipse/index.vue";
import type { useProfileData } from "../composables/useProfileData";
import ProfileAvatarStyleGrid from "./ProfileAvatarStyleGrid.vue";

defineOptions({ name: "ProfileBasicSection" });

const props = defineProps<{ page: ReturnType<typeof useProfileData> }>();

/**
 * 共享状态单体（useProfileData）的响应式视图：
 * reactive 会解包嵌套 ref，模板内可直接读值、v-model 写回同一实例，
 * 与其他兄弟组件（安全区/弹窗）共享同一份状态。
 */
const p = reactive(props.page);
</script>

<style scoped>
/* ========================================== */

/* ===== 头像区：预览 + 控制 + 网格（视觉降级，整体平衡） ===== */

/* ========================================== */

.avatar-zone {
  display: flex;
  flex-direction: column;

  /* 原用 --space-4 但该令牌未定义，gap 退化为 0 导致主头像与下方网格贴在一起 */
  gap: var(--space-standard);
  padding: var(--space-3) 0 var(--space-standard);
  border-top: 1px solid var(--border-subtle);
}

.avatar-zone:first-of-type {
  padding-top: 0;
  border-top: none;
}

/* 第一排：预览 + 控制区 */
.avatar-top-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  width: 100%;
}

.avatar-frame {
  flex-shrink: 0;
  width: 100px;
  height: 100px;
  background-color: var(--bg-soft);
  transition:
    width 0.2s,
    height 0.2s;
}

.avatar-preview {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 控制区：预览居左、控制靠右，保持画面平衡 */
.avatar-control {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-end;
}

/* 操作按钮行：随机在上、撤销在下，条件显示的次要操作不影响主要按钮位置 */
.avatar-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  align-items: flex-end;
  min-height: 28px;
}

.avatar-anim-toggle {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  color: var(--text-secondary);
  cursor: pointer;
}

.avatar-anim-toggle__label {
  font-size: var(--text-small);
}

/* ===== 随机换一个 / 撤销更改 ===== */

/* 轻量文字链接，不与头像选择竞争视觉层级 */
.link-btn {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 4px 0;
  font-size: var(--text-small);
  color: var(--brand-ink);
  cursor: pointer;
  background: none;
  border: none;
  transition: color 0.15s ease;
}

/* 撤销：次级语义，用中性灰与主操作（随机）区分 */
.link-btn--muted {
  color: var(--text-secondary);
}

.link-btn:hover {
  color: var(--brand-ink);
}

.link-btn--muted:hover {
  color: var(--text-primary);
}

.link-btn:focus-visible {
  outline: none;
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

.link-btn__icon {
  font-size: 14px;
  line-height: 1;
}

/* ===== 字段块 ===== */
.field-block {
  padding: var(--space-5) 0;
  border-top: 1px solid var(--border-subtle);
}

.field-block:first-of-type {
  padding-top: 0;
  border-top: none;
}

.field-block__row-top {
  display: flex;
  align-items: flex-start;
  width: 100%;
  margin-bottom: var(--space-2);
}

.field-block__label-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.field-block__label {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-primary);
}

.field-block__desc {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}

.field-block__input-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  width: 100%;
}

.field-input {
  flex: 1;
  min-width: 120px;
  max-width: 100%;
}

.field-input :deep(.el-input__wrapper) {
  border-radius: var(--radius-sm);
}

.field-block__save {
  flex-shrink: 0;
  width: 72px;
  height: 40px;
  margin-left: auto;
  transition: all 0.15s ease;
}

/* 🔥 禁用态优化：去除灰底，变为幽灵按钮，视觉轻量不抢戏 */
.field-block__save.is-disabled {
  /* audit-text-contrast: exempt .field-block__save.is-disabled 为**真禁用**控件，按 WCAG 1.4.3 对 inactive component 的豁免；**「无数据占位符」不适用本豁免**（那是信息，须用 --text-tertiary-ink）。登记见 docs/spec/tech-debt.md（#1599） */
  color: var(--text-disabled) !important;
  cursor: not-allowed !important;
  background: transparent !important;
  border: 1px solid var(--border-light) !important;
  opacity: 1 !important;
}

/* ===== 输入框字数统计 ===== */
.char-count,
.field-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* ===== 敏感词提示 ===== */
.field-hint {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  line-height: 1.4;
}

.field-hint--warn {
  color: var(--color-warning-ink);
}

/* ===== 响应式 ===== */

/* 窄屏（<640px）：设置页的行式布局改竖排。
   ⚠️ 本块原先排在各自的基础声明**之前**——媒体查询不改变特异性，覆盖被后面同选择器的声明压掉、**从未生效**（2026-09-18 修复，见 #1576 同类台账）。 */
@media (width <= 640px) {
  /* breakpoint-allow: 本文件 style 块是纯 CSS（无 lang="scss"），无法用 bp mixin */
  .avatar-zone {
    align-items: flex-start;
  }

  .avatar-top-row {
    width: 100%;
  }

  .field-block__input-row {
    flex-direction: column;
    gap: var(--space-2);
    align-items: stretch;
  }

  .field-input {
    width: 100%;
    max-width: 100%;
  }

  .field-block__save {
    align-self: flex-end;
    margin-left: 0;
  }
}
</style>
