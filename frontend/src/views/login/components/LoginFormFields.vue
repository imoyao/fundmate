<template>
  <!--
            输入框等宽说明：
            el-form-item 是 block 级 flex（display:flex），el-input 默认 width:100%，
            理论上各输入框已等宽；实际观感差异多来自 clearable / show-password 的
            suffix 图标在 wrapper 内以 flex-shrink:0 流式占位，撑窄内部文本区。
            页面级兜底见样式区「输入框等宽」：显式 100% 撑满内容区与输入框根元素，
            保证登录/注册所有输入框与提交按钮左右边缘严格对齐。
          -->
  <!--
            el-form 默认 validate-on-rule-change=true：:rules 切换（登录↔注册）时
            自动触发全量校验。该校验是异步的（flush:"post" 与 nextTick 竞态），
            切换瞬间 clearValidate 清完、500ms 后错误又全数回来 → 全部字段飘红。
            关闭自动校验根治竞态；toggleMode 里的 clearValidate 保留，
            负责清掉登录模式提交/失焦失败后的残留 error 状态。
          -->
  <el-form
    ref="ruleFormRef"
    :model="p.ruleForm"
    :rules="p.isRegisterMode ? p.registerRules : p.loginRules"
    :validate-on-rule-change="false"
    size="large"
    class="w-full"
  >
    <!-- 邮箱 / 用户名（登录模式二选一） -->
    <Motion class="w-full" :delay="100">
      <el-form-item prop="email" class="w-full">
        <el-input
          v-model="p.ruleForm.email"
          clearable
          :placeholder="p.isRegisterMode ? '邮箱地址' : '邮箱或用户名'"
          :prefix-icon="useRenderIcon(User)"
        />
      </el-form-item>
    </Motion>

    <!-- 昵称（仅注册模式） -->
    <Motion v-if="p.isRegisterMode" class="w-full" :delay="150">
      <el-form-item prop="username" class="w-full">
        <el-input
          v-model="p.ruleForm.username"
          clearable
          maxlength="16"
          placeholder="昵称（用于展示）"
          :prefix-icon="useRenderIcon(User)"
        />
      </el-form-item>
    </Motion>

    <!-- 密码 -->
    <Motion class="w-full" :delay="200">
      <el-form-item prop="password" class="w-full">
        <el-input
          v-model="p.ruleForm.password"
          clearable
          show-password
          placeholder="密码（至少8位）"
          :prefix-icon="useRenderIcon(Lock)"
        />
      </el-form-item>
      <!-- 忘记密码（仅登录模式）：右对齐小链接，与切换/隐私政策链接同风格 -->
      <div v-if="!p.isRegisterMode" class="login-forgot flex justify-end">
        <el-link type="primary" @click="p.openForgotDialog">忘记密码？</el-link>
      </div>
    </Motion>

    <!-- 确认密码（仅注册模式） -->
    <Motion v-if="p.isRegisterMode" class="w-full" :delay="250">
      <el-form-item prop="confirmPassword" class="w-full">
        <el-input
          v-model="p.ruleForm.confirmPassword"
          clearable
          show-password
          placeholder="确认密码"
          :prefix-icon="useRenderIcon(Lock)"
        />
      </el-form-item>
    </Motion>

    <!-- 隐私政策（仅注册模式） -->
    <Motion v-if="p.isRegisterMode" class="w-full" :delay="300">
      <el-form-item prop="agreePolicy" class="w-full">
        <div class="privacy-policy-wrapper">
          <el-checkbox
            v-model="p.ruleForm.agreePolicy"
            class="privacy-checkbox"
          />
          <span class="privacy-text">
            我已阅读并同意
            <el-link type="primary" @click="p.openPrivacyPolicy"
              >《隐私政策》</el-link
            >
            <span class="privacy-separator">·</span>
            <el-link type="primary" @click="p.openTerms">《服务条款》</el-link>
          </span>
        </div>
      </el-form-item>
    </Motion>

    <!-- 提交按钮（size=large 与 40px 输入框等高，避免 :deep 改组件内部样式） -->
    <Motion class="w-full" :delay="p.isRegisterMode ? 350 : 250">
      <el-button
        class="login-submit mt-4! w-full"
        size="large"
        type="primary"
        :loading="p.loading"
        :disabled="p.disabled"
        @click="p.onSubmit(ruleFormRef)"
      >
        {{ p.isRegisterMode ? "注册" : "登录" }}
      </el-button>
    </Motion>
  </el-form>

  <!-- 忘记密码弹窗：收集邮箱发起重置邮件（防用户枚举，统一提示已发送） -->
  <el-dialog
    v-model="p.forgotVisible"
    title="重置密码"
    width="min(400px, calc(100vw - 32px))"
    :close-on-click-modal="false"
    append-to-body
    class="login-forgot-dialog"
  >
    <el-form
      ref="forgotFormRef"
      :model="p.forgotForm"
      :rules="p.forgotRules"
      size="large"
    >
      <el-form-item prop="email" class="w-full">
        <el-input
          v-model="p.forgotForm.email"
          clearable
          placeholder="请输入注册邮箱"
          :prefix-icon="useRenderIcon(User)"
          @keyup.enter="p.onForgotSubmit(forgotFormRef)"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="p.forgotVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="p.forgotLoading"
        @click="p.onForgotSubmit(forgotFormRef)"
      >
        发送重置邮件
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import Motion from "../utils/motion";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import type { useLogin } from "../composables/useLogin";
import Lock from "~icons/ri/lock-fill";
import User from "~icons/ri/user-3-fill";

defineOptions({ name: "LoginFormFields" });

const props = defineProps<{ page: ReturnType<typeof useLogin> }>();

/**
 * 共享状态单体（useLogin）的响应式视图（#980 P1-C，P1-A/B 同款）：
 * reactive 会解包嵌套 ref，模板内可直接读值、写回同一实例。
 */
const p = reactive(props.page);

// el-form / 忘记密码弹窗的模板 ref 复用状态单体里的同名 Ref：
// 模板字符串 ref 命中 setup 同名绑定后写入其 .value，
// composable 侧（键盘提交、toggleMode、注册回切清校验）读到的是同一实例，无需回写同步。
const ruleFormRef = props.page.ruleFormRef;
const forgotFormRef = props.page.forgotFormRef;
</script>

<style lang="scss" scoped>
/* 提交按钮果冻弹性：hover 微弹起，active 按下回弹（弹性曲线） */
.login-submit {
  transition:
    transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1),
    background-color 0.2s ease,
    border-color 0.2s ease;

  &:hover:not(:disabled) {
    transform: scale(1.02);
  }

  &:active:not(:disabled) {
    transform: scale(0.97);
  }
}

/* 输入框等宽兜底（问题 2 回归修复）：
   EP 的 .el-input 默认 width: var(--el-input-width)=100%、.el-form-item__content 是 flex:1，
   理论已等宽；这里显式 100% 撑满，不依赖 EP 内部默认值，覆盖任何版本差异，
   确保登录/注册所有输入框与提交按钮（w-full）左右边缘严格对齐。 */
:deep(.el-form-item__content) {
  width: 100%;
}

:deep(.el-input) {
  width: 100%;
}

/* 输入框聚焦呼吸：保留 EP 的 1px inset 描边（默认 --el-input-focus-border-color，
   即品牌色 --brand-700），再叠加柔和外发光。
   注意不能整体替换 box-shadow：EP 用 box-shadow inset 画边框，整体替换会导致
   聚焦瞬间输入框自身描边消失、只剩突兀外扩光晕（回归根因）。
   error 态由 EP 的 .el-form-item.is-error 规则（特异性更高）覆盖，红边优先，不受本规则影响。 */
:deep(.el-input__wrapper) {
  transition:
    box-shadow 0.4s ease,
    border-color 0.4s ease;

  /* hover：1px 描边微亮 + 若有若无的光晕，为聚焦呼吸做铺垫 */
  &:hover {
    box-shadow:
      0 0 0 1px var(--el-input-hover-border-color) inset,
      0 0 0 3px color-mix(in srgb, var(--brand-700) 6%, transparent);
  }

  &.is-focus {
    box-shadow:
      0 0 0 1px var(--el-input-focus-border-color) inset,
      0 0 0 3px color-mix(in srgb, var(--brand-700) 12%, transparent);
  }
}

/* 浏览器自动填充背景覆盖：清除 Chrome 默认浅蓝底色，
   避免与左右图标容器形成「白-蓝-白」三明治（与 reset-password.vue 同一处理）。
   注：部分新浏览器对 box-shadow inset 覆盖 autofill 背景的旧技巧已不完全生效
   （会漏出浅蓝底色），故追加 background-color: transparent 与
   background-clip: content-box 兜底：前者直接置透明，后者把背景裁剪到内容盒
   （避免 padding 区域残留色块），双保险覆盖 autofill 底色。 */
:deep(input:-webkit-autofill),
:deep(input:-webkit-autofill:hover),
:deep(input:-webkit-autofill:focus),
:deep(input:-webkit-autofill:active) {
  caret-color: var(--text-primary);
  background-color: transparent !important;
  background-clip: content-box !important;
  box-shadow: 0 0 0 1000px var(--bg-card) inset !important;
  -webkit-text-fill-color: var(--text-primary) !important;
}

/* 暗色聚焦协调：全局 dark.scss 用 --focus-ring 双层硬环（!important）覆盖输入框聚焦，
   登录页品牌面改用与亮色一致的内描边 + 低透明度光晕（同 index.vue 样式区「暗色模式独立
   视觉适配」段注释的降饱和 color-mix 手法，暗色品牌色已降 20% 饱和度，故光晕透明度略高于亮色）。
   两条规则都以 !important 对抗全局；error 规则特异性更高，红边优先。
   注：Vue scoped 编译器不支持 :global(X) :deep(Y) 组合（deep 部分会丢失），
   故整条选择器放入 :global，用 .login-page 锚定本页。 */
:global(.dark .login-page .el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px var(--el-input-focus-border-color) inset,
    0 0 0 3px color-mix(in srgb, var(--brand-700) 14%, transparent) !important;
}

:global(.dark .login-page .el-form-item.is-error .el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--el-color-danger) inset !important;
}

/* ---------- 表单内辅助样式 ---------- */

/* 隐私政策 */
.privacy-policy-wrapper {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
  user-select: none;

  .privacy-checkbox {
    flex-shrink: 0;
    margin-right: 0;
  }

  .privacy-text {
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-secondary);

    .el-link {
      padding: 0 2px;
      font-size: 14px;
      vertical-align: baseline;
    }

    .privacy-separator {
      margin: 0 4px;

      /* audit-text-contrast: exempt 装饰性分隔符（「·」），不承载信息、无相邻文本语义，属 WCAG 1.4.3 的 incidental；若改为信息性分隔请用 --text-tertiary-ink。登记见 docs/spec/tech-debt.md（#1599 batch 3） */
      color: var(--border-default);
    }
  }
}

/* 忘记密码链接：右对齐小链接，与切换/隐私政策链接同风格 */
.login-forgot {
  margin-top: 2px;
}

.login-forgot .el-link {
  font-size: 13px;
}

/* 忘记密码弹窗：对齐登录卡片视觉（半透明边框 + 品牌柔影） */
:global(.login-forgot-dialog) {
  --el-dialog-bg-color: var(--bg-card);
  --el-dialog-border-radius: var(--radius-lg);

  border: 1px solid color-mix(in srgb, var(--brand-700) 18%, transparent);
  box-shadow: 0 8px 32px -8px
    color-mix(in srgb, var(--brand-700) 8%, transparent);
}

:global(.login-forgot-dialog .el-dialog__title) {
  font-weight: 600;
  color: var(--text-primary);
}

/* 窄屏隐私区（内容级阈值，与页面布局断点不同轴） */
@media (width <= 480px) /* breakpoint-allow: 隐私区内容级阈值 */ {
  /* 说明（已上移到 @media 同行）：隐私文案的字号/对齐属内容级阈值 */
  .privacy-policy-wrapper {
    align-items: flex-start;

    .privacy-checkbox {
      margin-top: 2px;
    }

    .privacy-text {
      font-size: 13px;
    }
  }
}
</style>
