<template>
  <section class="profile-card profile-card-enter">
    <!-- ===== 区块二：账号安全 ===== -->
    <SectionHeader title="账号安全" />

    <!-- 邮箱行 -->
    <div class="setting-row">
      <div class="setting-row__label">
        <span class="setting-row__name">登录邮箱</span>
        <span class="setting-row__desc"
          >用来接收你的专属通知，也守护着你的账户登录</span
        >
      </div>
      <div class="setting-row__main">
        <span class="field-value field-value--mono">{{
          p.email || "未设置"
        }}</span>
        <button
          type="button"
          class="modify-link"
          @click="p.emailDialogVisible = true"
        >
          修改
        </button>
      </div>
    </div>

    <!-- 密码行 -->
    <div class="setting-row">
      <div class="setting-row__label">
        <span class="setting-row__name">登录密码</span>
        <span class="setting-row__desc"
          >安全护盾，隔段时间加固一次，更安心</span
        >
      </div>
      <div class="setting-row__main">
        <span class="field-value field-value--mono">••••••••</span>
        <button
          type="button"
          class="modify-link"
          @click="p.passwordDialogVisible = true"
        >
          修改
        </button>
      </div>
    </div>

    <!-- 危险操作区 -->
    <div class="danger-zone">
      <div class="danger-zone__text">
        <span class="danger-zone__label">退出登录</span>
        <span class="danger-zone__desc">我们不说再见，只说后会有期</span>
      </div>
      <button type="button" class="danger-btn" @click="p.onLogout">退出</button>
    </div>

    <!-- 退出确认弹窗（自定义 el-dialog，替代 ElMessageBox） -->
    <el-dialog
      v-model="p.logoutDialogVisible"
      title="退出登录"
      width="300px"
      :close-on-click-modal="false"
    >
      <div class="dialog-content">确定要退出当前账户吗？</div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="p.logoutDialogVisible = false">取消</el-button>
          <el-button type="danger" @click="p.confirmLogout">退出</el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { useProfileData } from "../composables/useProfileData";

defineOptions({ name: "ProfileSecuritySection" });

const props = defineProps<{ page: ReturnType<typeof useProfileData> }>();

/** 共享状态单体的响应式视图（详见 ProfileBasicSection 同名注释） */
const p = reactive(props.page);
</script>

<style scoped>
/* ===== 账号安全行 ===== */
.setting-row {
  display: flex;
  gap: var(--space-standard);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) 0;
  border-top: 1px solid var(--border-subtle);
}

.setting-row:first-of-type {
  padding-top: var(--space-3);
  border-top: none;
}

.setting-row:last-child {
  padding-bottom: var(--space-3);
}

.setting-row__label {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 4px;
  min-width: 100px;
}

.setting-row__name {
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-primary);
}

.setting-row__desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}

.setting-row__main {
  display: flex;
  flex: 1;
  gap: var(--space-standard);
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
}

.field-value {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  color: var(--text-primary);
  white-space: nowrap;
}

.field-value--mono {
  font-family: var(--font-mono, "SF Mono", "JetBrains Mono", monospace);
  font-variant-numeric: tabular-nums;
}

/* ===== 修改链接 ===== */
.modify-link {
  padding: 0;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--brand-700);
  cursor: pointer;
  background: none;
  border: none;
  transition: color 0.15s ease;
}

.modify-link:hover {
  color: var(--brand-800);
}

.modify-link:focus-visible {
  outline: none;
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

/* ===== 危险操作区 ===== */
.danger-zone {
  display: flex;
  gap: var(--space-5);
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-standard);
  margin-top: var(--space-standard);
  border-top: 1px solid var(--border-subtle);
}

.danger-zone__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.danger-zone__label {
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1.4;
  color: var(--text-primary);
}

.danger-zone__desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}

/* ===== 危险幽灵按钮 ===== */

/* 危险色走语义别名 --danger（= --color-danger #d4364a，design.md 危险按钮规范）。
   #1602：原 -system 后缀已去除，全站唯一危险色就是 --color-danger */
.danger-btn {
  flex-shrink: 0;
  height: 40px;
  padding: 0 24px;
  font-family: inherit;
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1;
  color: var(--danger);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--danger);
  border-radius: var(--radius-sm);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.danger-btn:hover {
  color: var(--text-inverse);
  background-color: var(--danger);
  border-color: transparent;
}

.danger-btn:focus-visible {
  outline: none;
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

.danger-btn:active {
  color: var(--text-inverse);
  background-color: var(--danger);
  border-color: transparent;
  box-shadow: inset 0 0 0 1px rgb(255 255 255 / 15%);
}

/* ===== 退出确认弹窗内容 ===== */
.dialog-content {
  padding: var(--space-2) 0 var(--space-3);
  font-size: var(--text-small);
  line-height: 1.6;
  color: var(--text-primary);
}

.dialog-footer {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

/* ===== 响应式 ===== */

/* 窄屏（<640px）：设置页的行式布局改竖排。
   ⚠️ 本块原先排在各自的基础声明**之前**——媒体查询不改变特异性，覆盖被后面同选择器的声明压掉、**从未生效**（2026-09-18 修复，见 #1576 同类台账）。 */
@media (width <= 640px) /* breakpoint-allow: 本文件 style 块是纯 CSS（无 lang="scss"），无法用 bp mixin */ {
  .setting-row {
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-start;
  }

  .setting-row__label {
    flex-basis: auto;
    min-width: 0;
  }

  .setting-row__main {
    justify-content: flex-start;
    width: 100%;
  }

  .danger-zone {
    align-items: flex-start;
  }
}
</style>
