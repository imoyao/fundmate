<template>
  <div
    class="profile-page min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="profile-head">
      <PageHeaderBar title="个人中心" subtitle="管理账户与安全" />
    </div>

    <div class="profile-shell">
      <!-- ===== 区块一：个人资料 ===== -->
      <section class="settings-card">
        <SectionHeader title="个人资料" />

        <!-- 头像区（n=3 超椭圆容器） -->
        <div class="avatar-zone">
          <Superellipse class="avatar-frame" :power="3">
            <img
              :src="avatarPreview"
              class="avatar-preview"
              :alt="currentNickname"
            />
          </Superellipse>

          <div class="avatar-control">
            <div class="style-group" role="radiogroup" aria-label="头像画风">
              <button
                v-for="style in AVATAR_STYLES"
                :key="style"
                type="button"
                role="radio"
                :aria-checked="avatarStyle === style"
                class="style-capsule"
                :class="{ 'style-capsule--active': avatarStyle === style }"
                @click="onSelectStyle(style)"
              >
                {{ AVATAR_STYLE_LABEL[style] }}
                <IconifyIconOffline
                  v-if="avatarStyle === style"
                  icon="lucide:check"
                  class="style-capsule__check"
                  aria-hidden="true"
                />
              </button>
            </div>
            <button type="button" class="link-btn" @click="onRandomizeAvatar">
              <IconifyIconOffline
                icon="lucide:shuffle"
                class="link-btn__icon"
                aria-hidden="true"
              />
              随机换一个
            </button>
          </div>
        </div>

        <!-- 昵称字段 -->
        <div class="field-block">
          <div class="field-block__row-top">
            <span class="field-block__label">昵称</span>
            <el-button
              class="field-block__save"
              :type="nicknameDirty ? 'primary' : 'default'"
              :disabled="!nicknameDirty"
              :loading="nicknameSaving"
              @click="onSaveNickname"
            >
              保存
            </el-button>
          </div>
          <span class="field-block__desc">在页面和消息中展示</span>
          <div class="field-block__input-row">
            <el-input
              v-model="profileForm.nickname"
              placeholder="请输入昵称"
              maxlength="20"
              class="field-input"
            >
              <template #suffix>
                <span class="char-count"
                  >{{ profileForm.nickname.length }}/20</span
                >
              </template>
            </el-input>
          </div>
        </div>

        <!-- 用户名字段 -->
        <div class="field-block">
          <div class="field-block__row-top">
            <span class="field-block__label">用户名</span>
            <el-button
              class="field-block__save"
              :type="usernameDirty ? 'primary' : 'default'"
              :disabled="!usernameDirty"
              :loading="usernameSaving"
              @click="onSaveUsername"
            >
              保存
            </el-button>
          </div>
          <span class="field-block__desc">用于登录</span>
          <div class="field-block__input-row">
            <el-input
              v-model="profileForm.username"
              placeholder="请输入用户名"
              maxlength="60"
              class="field-input"
            >
              <template #suffix>
                <span class="field-count"
                  >{{ profileForm.username.length }}/60</span
                >
              </template>
            </el-input>
          </div>
        </div>
      </section>

      <!-- ===== 区块二：账号安全（含退出登录危险区） ===== -->
      <section class="settings-card">
        <SectionHeader title="账号安全" />

        <!-- 邮箱行 -->
        <div class="setting-row">
          <div class="setting-row__label">
            <span class="setting-row__name">登录邮箱</span>
            <span class="setting-row__desc">用于登录与接收通知</span>
          </div>
          <div class="setting-row__main">
            <span class="field-value field-value--mono">{{
              email || "未设置"
            }}</span>
            <button
              type="button"
              class="modify-link"
              @click="emailDialogVisible = true"
            >
              修改
            </button>
          </div>
        </div>

        <!-- 密码行 -->
        <div class="setting-row">
          <div class="setting-row__label">
            <span class="setting-row__name">登录密码</span>
            <span class="setting-row__desc">建议定期更换</span>
          </div>
          <div class="setting-row__main">
            <span class="field-value field-value--mono">••••••••</span>
            <button
              type="button"
              class="modify-link"
              @click="passwordDialogVisible = true"
            >
              修改
            </button>
          </div>
        </div>

        <!-- 危险操作区：退出登录（分隔线下） -->
        <div class="danger-zone">
          <div class="danger-zone__text">
            <span class="danger-zone__label">退出登录</span>
            <span class="danger-zone__desc">退出后需重新登录</span>
          </div>
          <button type="button" class="danger-btn" @click="onLogout">
            退出
          </button>
        </div>
      </section>
    </div>

    <!-- 改邮箱弹窗 -->
    <el-dialog
      v-model="emailDialogVisible"
      title="修改登录邮箱"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="emailFormRef"
        :model="emailForm"
        :rules="emailRules"
        label-position="top"
      >
        <el-form-item label="新邮箱" prop="email">
          <el-input
            v-model="emailForm.email"
            placeholder="请输入新的邮箱地址"
          />
        </el-form-item>
      </el-form>
      <p class="dialog-hint">
        修改邮箱需要到新邮箱中完成验证，验证成功后登录邮箱将变更。
      </p>
      <template #footer>
        <el-button @click="emailDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="emailSubmitting"
          @click="onSaveEmail"
        >
          发送验证邮件
        </el-button>
      </template>
    </el-dialog>

    <!-- 改密码弹窗 -->
    <el-dialog
      v-model="passwordDialogVisible"
      title="修改登录密码"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-position="top"
      >
        <el-form-item label="新密码" prop="password">
          <el-input
            v-model="passwordForm.password"
            type="password"
            show-password
            placeholder="至少 8 位"
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input
            v-model="passwordForm.confirm"
            type="password"
            show-password
            placeholder="再次输入新密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="passwordSubmitting"
          @click="onSavePassword"
        >
          确认修改
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, h } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage, ElMessageBox } from "element-plus";
import { supabase } from "@/utils/supabase";
import { getMe, updateMe } from "@/api/auth";
import { useUserStoreHook } from "@/store/modules/user";
import {
  AVATAR_STYLES,
  AVATAR_STYLE_LABEL,
  type AvatarStyle,
  DEFAULT_AVATAR_STYLE,
  buildAvatarUrl,
  hashSeed,
  randomSeed,
  defaultAvatarUrl,
  parseAvatarUrl,
  isAvatarUrl
} from "@/utils/avatar";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import Superellipse from "@/components/Superellipse/index.vue";

const userStore = useUserStoreHook();

// 成功反馈的珊瑚红对勾（D15：成功 Toast 用中性容器 + 品牌红勾，禁绿）
const CheckMark = () =>
  h(IconifyIconOffline, {
    icon: "lucide:check",
    style: { color: "var(--brand-700)", fontSize: "18px", strokeWidth: 3 }
  });

const me = ref<{
  id: number;
  supabase_id: string | null;
  username: string | null;
  nickname: string | null;
  avatar: string | null;
  email: string | null;
  family: { id: number; name: string | null };
} | null>(null);

const profileForm = reactive({
  nickname: "",
  username: ""
});

// 上次成功保存的值（用于 Dirty 判定）
const savedNickname = ref("");
const savedUsername = ref("");

// 处理中标志（昵称 / 用户名各自独立，互斥仅限同一动作组）
const nicknameSaving = ref(false);
const usernameSaving = ref(false);

const nicknameDirty = computed(
  () => profileForm.nickname !== savedNickname.value
);
const usernameDirty = computed(
  () => profileForm.username !== savedUsername.value
);

const currentNickname = computed(
  () => userStore.nickname || userStore.username || "未设置"
);

const email = computed(() => me.value?.email || "");

// 用户 supabase 唯一标识（用于默认头像 seed）
const supabaseId = computed(() => me.value?.supabase_id || userStore.username);

// ============================================
// 头像：style + seed 联合决定"画风 + 脸型"，保存到 users.avatar
// ============================================
const avatarStyle = ref<AvatarStyle>(DEFAULT_AVATAR_STYLE);
const avatarSeed = ref<string>("");

const savedAvatarUrl = computed(() =>
  userStore.avatar && isAvatarUrl(userStore.avatar) ? userStore.avatar : ""
);

const avatarPreview = computed(() => {
  if (avatarSeed.value) {
    return buildAvatarUrl(avatarStyle.value, avatarSeed.value);
  }
  return savedAvatarUrl.value || defaultAvatarUrl(supabaseId.value);
});

function initAvatar() {
  const parsed = parseAvatarUrl(savedAvatarUrl.value);
  if (parsed) {
    avatarStyle.value = parsed.style;
    avatarSeed.value = parsed.seed;
    return;
  }
  avatarSeed.value = hashSeed(supabaseId.value || "fundmate-anon");
}

async function onRandomizeAvatar() {
  avatarSeed.value = randomSeed();
  await persistAvatar();
}

async function onSelectStyle(style: AvatarStyle) {
  if (style === avatarStyle.value) return;
  avatarStyle.value = style;
  if (!avatarSeed.value) {
    avatarSeed.value = hashSeed(supabaseId.value || "default");
  }
  await persistAvatar();
}

async function persistAvatar() {
  const newUrl = buildAvatarUrl(avatarStyle.value, avatarSeed.value);
  try {
    await updateMe({ avatar: newUrl });
    userStore.SET_AVATAR(newUrl);
    userStore.persist();
    ElMessage({ message: "头像已更新", icon: CheckMark });
  } catch {
    ElMessage.error("头像保存失败");
  }
}

// ============================================
// 资料保存（昵称 / 用户名独立动作组，互不干涉）
// ============================================
async function onSaveNickname() {
  nicknameSaving.value = true;
  try {
    const { data } = await updateMe({ nickname: profileForm.nickname.trim() });
    const nickname = data.nickname ?? profileForm.nickname.trim();
    userStore.SET_NICKNAME(nickname);
    userStore.persist();
    savedNickname.value = profileForm.nickname;
    ElMessage({
      message: "昵称已保存",
      icon: CheckMark
    });
  } catch {
    ElMessage.error("昵称保存失败，请重试");
  } finally {
    nicknameSaving.value = false;
  }
}

async function onSaveUsername() {
  usernameSaving.value = true;
  try {
    const { data } = await updateMe({ username: profileForm.username.trim() });
    const username = data.username ?? profileForm.username.trim();
    userStore.SET_USERNAME(username);
    userStore.persist();
    savedUsername.value = profileForm.username;
    ElMessage({
      message: "用户名已保存",
      icon: CheckMark
    });
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.error("该用户名已被使用，请更换");
    } else {
      ElMessage.error(e?.response?.data?.message || "保存失败，请重试");
    }
  } finally {
    usernameSaving.value = false;
  }
}

// ============================================
// 改邮箱
// ============================================
const emailDialogVisible = ref(false);
const emailForm = reactive({ email: "" });
const emailFormRef = ref<FormInstance>();
const emailSubmitting = ref(false);

const emailRules = reactive<FormRules>({
  email: [
    { required: true, message: "请输入邮箱", trigger: "blur" },
    { type: "email", message: "请输入有效的邮箱地址", trigger: "blur" }
  ]
});

async function onSaveEmail() {
  if (!emailFormRef.value) return;
  const valid = await emailFormRef.value.validate().catch(() => false);
  if (!valid) return;
  emailSubmitting.value = true;
  try {
    const { error } = await supabase.auth.updateUser({
      email: emailForm.email.trim()
    });
    if (error) throw error;
    ElMessage({
      message: "验证邮件已发送，请到新邮箱完成验证",
      icon: CheckMark
    });
    emailDialogVisible.value = false;
    emailForm.email = "";
  } catch (e: any) {
    ElMessage.error(e.message || "发送失败，请重试");
  } finally {
    emailSubmitting.value = false;
  }
}

// ============================================
// 改密码
// ============================================
const passwordDialogVisible = ref(false);
const passwordForm = reactive({ password: "", confirm: "" });
const passwordFormRef = ref<FormInstance>();
const passwordSubmitting = ref(false);

const passwordRules = reactive<FormRules>({
  password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 8, message: "密码至少 8 位", trigger: "blur" }
  ],
  confirm: [
    { required: true, message: "请确认新密码", trigger: "blur" },
    { validator: validateConfirm, trigger: "blur" }
  ]
});

function validateConfirm(
  _rule: unknown,
  value: string,
  callback: (err?: Error) => void
) {
  if (!value) return callback();
  if (value !== passwordForm.password) {
    callback(new Error("两次输入的密码不一致"));
  } else {
    callback();
  }
}

async function onSavePassword() {
  if (!passwordFormRef.value) return;
  const valid = await passwordFormRef.value.validate().catch(() => false);
  if (!valid) return;
  passwordSubmitting.value = true;
  try {
    const { error } = await supabase.auth.updateUser({
      password: passwordForm.password
    });
    if (error) throw error;
    ElMessage({ message: "密码已修改", icon: CheckMark });
    passwordDialogVisible.value = false;
    passwordForm.password = "";
    passwordForm.confirm = "";
  } catch (e: any) {
    ElMessage.error(e.message || "修改失败，请重试");
  } finally {
    passwordSubmitting.value = false;
  }
}

// ============================================
// 退出登录
// ============================================
async function onLogout() {
  try {
    await ElMessageBox.confirm("确定要退出当前账户吗？", "退出登录", {
      confirmButtonText: "退出",
      cancelButtonText: "取消",
      type: "warning"
    });
  } catch {
    return;
  }
  await userStore.logOut();
}

// ============================================
// 数据加载
// ============================================
onMounted(async () => {
  try {
    const { data } = await getMe();
    me.value = data;
    profileForm.nickname = data.nickname || "";
    profileForm.username = data.username || "";
    savedNickname.value = data.nickname || "";
    savedUsername.value = data.username || "";
    userStore.SET_NICKNAME(data.nickname || "");
    userStore.SET_USERNAME(data.username || "");
    if (data.avatar) userStore.SET_AVATAR(data.avatar);
    initAvatar();
  } catch (e: any) {
    // 401 已由拦截器处理跳转，这里仅兜底提示
    if (e?.response?.status !== 401) {
      ElMessage.error("加载个人信息失败");
    }
  }
});
</script>

<style scoped>
@keyframes style-pop {
  0% {
    transform: scale(1);
  }

  30% {
    transform: scale(0.92);
  }

  60% {
    transform: scale(1.05);
  }

  80% {
    transform: scale(0.97);
  }

  100% {
    transform: scale(1);
  }
}

/* ===== 响应式：窄屏下设置行堆叠、字号不缩水 ===== */
@media (width <= 640px) {
  .avatar-zone {
    align-items: flex-start;
  }

  .setting-row {
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-start;

    &__label {
      flex-basis: auto;
      min-width: 0;
    }

    &__main {
      justify-content: flex-start;
      width: 100%;
    }
  }

  .field-block__row-top {
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .style-group {
    justify-content: flex-start;
  }

  .field-input {
    max-width: 100%;
  }

  .danger-zone {
    align-items: flex-start;
  }
}

.profile-page {
  padding: var(--space-5);
}

.profile-head {
  :deep(.page-header) {
    /* D17：验收口径定稿 680，覆写 D15 的 960 */
    max-width: 680px;
  }
}

.profile-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: 680px;
  margin: 0 auto;
}

.settings-card {
  padding: var(--space-standard);
  background-color: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-raised);
}

/* ===== 头像区（超椭圆 + 画风胶囊 + 随机） ===== */
.avatar-zone {
  display: flex;
  gap: var(--space-5);
  align-items: center;
  padding: var(--space-3) 0 var(--space-standard);
  border-top: 1px solid var(--border-subtle);

  &:first-of-type {
    padding-top: 0;
    border-top: none;
  }
}

.avatar-frame {
  flex-shrink: 0;
  width: 88px;
  height: 88px;
  background-color: var(--bg-soft);
}

.avatar-preview {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-control {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-3);
  align-items: flex-start;
  min-width: 0;
}

/* ===== 果冻胶囊按钮组（头像风格选择） ===== */
.style-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.style-capsule {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 7px 16px;
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1;
  color: var(--text-tertiary);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transform: translateZ(0);
  transform-origin: center;
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    background-color 0.2s,
    color 0.2s,
    border-color 0.2s,
    box-shadow 0.2s;
  will-change: transform;

  &:hover {
    color: var(--text-primary);
    border-color: var(--brand-400);
  }

  &:active {
    transform: scale(0.92);
  }

  &--active {
    color: var(--brand-700);
    background-color: var(--brand-200);
    border-color: var(--brand-400);
    box-shadow: 0 1px 3px rgb(0 0 0 / 6%);
    animation: style-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);

    &:hover {
      color: var(--brand-700);
    }
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }

  &__check {
    font-size: 16px;
  }
}

/* ===== 随机换一个（纯文本按钮 + 珊瑚红 SVG） ===== */
.link-btn {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 4px 0;
  font-size: var(--text-small);
  color: var(--brand-700);
  cursor: pointer;
  background: none;
  border: none;
  transition: color 0.15s ease;

  &:hover {
    color: var(--brand-800);
  }

  &:focus-visible {
    outline: none;
    border-radius: var(--radius-sm);
    box-shadow: var(--focus-ring);
  }

  &__icon {
    font-size: 14px;
  }
}

/* ===== 字段块（标签+按钮上行、说明+输入框下行） ===== */
.field-block {
  padding: var(--space-5) 0;
  border-top: 1px solid var(--border-subtle);

  &:first-of-type {
    padding-top: 0;
    border-top: none;
  }

  &__row-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--space-2);
  }

  &__label {
    font-size: 14px;
    font-weight: 500;
    line-height: 1.4;
    color: var(--text-primary);
  }

  &__desc {
    display: block;
    margin-bottom: var(--space-2);
    font-size: 13px;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  &__input-row {
    display: flex;
    align-items: center;
  }

  &__save {
    /* 按钮物理占位，防止出现/消失导致 CLS 跳动 */
    flex-shrink: 0;
    width: 72px;
    height: 40px;
  }
}

/* 输入框（suffix 字数统计字体轻量化） */
.field-input {
  /* 宽屏下限制最大宽度，防止无限横向拉伸 */
  flex: 1;
  min-width: 0;
  max-width: 320px;

  :deep(.el-input__wrapper) {
    border-radius: var(--radius-sm);
  }
}

/* 输入框字数统计（轻量化，选择器合并） */
.char-count,
.field-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

/* ===== 账号安全设置行（Flex 布局，标签灵活宽度 + 值右对齐） ===== */
.setting-row {
  display: flex;
  gap: var(--space-standard);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) 0;
  border-top: 1px solid var(--border-subtle);

  &:first-of-type {
    padding-top: var(--space-3);
    border-top: none;
  }

  &:last-child {
    padding-bottom: var(--space-3);
  }

  &__label {
    display: flex;
    flex-shrink: 0;
    flex-direction: column;
    gap: 4px;
    min-width: 100px;
  }

  &__name {
    font-size: var(--text-small);
    font-weight: 500;
    line-height: 1.4;
    color: var(--text-primary);
  }

  &__desc {
    font-size: 12px;
    line-height: 1.4;
    color: var(--text-tertiary);
  }

  &__main {
    display: flex;
    flex: 1;

    /* 强制 24px 间距，避免邮箱值与「修改」粘连 */
    gap: var(--space-standard);
    align-items: center;
    justify-content: flex-end;
    min-width: 0;
  }
}

.field-value {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  color: var(--text-primary);
  white-space: nowrap;

  &--mono {
    font-family: var(--font-mono, "SF Mono", "JetBrains Mono", monospace);
    font-variant-numeric: tabular-nums;
  }
}

/* ===== 修改链接（品牌色纯文本按钮） ===== */
.modify-link {
  padding: 0;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--brand-700);
  cursor: pointer;
  background: none;
  border: none;
  transition: color 0.15s ease;

  &:hover {
    color: var(--brand-800);
  }

  &:focus-visible {
    outline: none;
    border-radius: var(--radius-sm);
    box-shadow: var(--focus-ring);
  }
}

/* ===== 危险操作区分隔区（退出登录） ===== */
.danger-zone {
  display: flex;
  gap: var(--space-5);
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-standard);
  margin-top: var(--space-standard);
  border-top: 1px solid var(--border-subtle);

  &__text {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  &__label {
    font-size: var(--text-small);
    font-weight: 500;
    line-height: 1.4;
    color: var(--text-primary);
  }

  &__desc {
    font-size: 12px;
    line-height: 1.4;
    color: var(--text-tertiary);
  }
}

/* 危险幽灵按钮：透明底 + 红色描边，Hover 红色实心白字 */
.danger-btn {
  flex-shrink: 0;
  height: 40px;
  padding: 0 24px;
  font-family: inherit;
  font-size: var(--text-small);
  font-weight: 500;
  line-height: 1;
  color: var(--color-danger);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  transition:
    background-color 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    color: #fff;
    background-color: var(--color-danger);
    border-color: transparent;
  }

  &:focus-visible {
    outline: none;
    border-radius: var(--radius-sm);
    box-shadow: var(--focus-ring);
  }

  &:active {
    color: #fff;
    background-color: var(--color-danger);
    border-color: transparent;
    box-shadow: inset 0 0 0 1px rgb(255 255 255 / 15%);
  }
}

.dialog-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 🔥 果冻回弹关键帧（与 manual 录入页一致，单一来源见 design 交互规范） */
</style>
