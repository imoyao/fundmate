import { reactive, ref, computed, onMounted, h } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage } from "element-plus";
import { supabase } from "@/utils/supabase";
import { getMe, updateMe } from "@/api/auth";
import { useUserStoreHook } from "@/store/modules/user";
import {
  type AvatarStyle,
  DEFAULT_AVATAR_STYLE,
  buildAvatarUrl,
  hashSeed,
  randomSeed,
  randomAvatarStyle,
  defaultAvatarUrl,
  parseAvatarUrl,
  isAvatarUrl
} from "@/utils/avatar";
import { Icon as IconifyIconOffline } from "@iconify/vue";

/**
 * 个人中心页面状态单体（#980 P1-A 结构拆分）：
 * 资料/头像/账号安全三块共享的表单状态、保存动作与数据加载都收敛在这里，
 * index.vue 只做编排，子组件经 `page` prop 注入同一实例（P0 同款模式）。
 * onMounted 在此注册，挂载到调用方（index.vue）生命周期，与拆分前时序一致。
 */
export function useProfileData() {
  const userStore = useUserStoreHook();

  // 成功反馈的珊瑚红对勾
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

  const savedNickname = ref("");
  const savedUsername = ref("");

  const nicknameSaving = ref(false);
  const usernameSaving = ref(false);

  const nicknameDirty = computed(
    () => profileForm.nickname !== savedNickname.value
  );
  const usernameDirty = computed(
    () => profileForm.username !== savedUsername.value
  );

  // ── 用户名/昵称敏感词提示（前端仅提示，硬拦截在后端的 contains_sensitive）──
  // 与后端词库不同源，这里只放少量常见词做实时预警，避免每次输入都打到后端。
  const SENSITIVE_HINT_WORDS = [
    "傻瓜",
    "笨蛋",
    "白痴",
    "蠢货",
    "废物",
    "垃圾",
    "贱人",
    "混蛋",
    "滚蛋",
    "弱智",
    "智障",
    "脑残",
    "傻逼",
    "色情",
    "裸聊",
    "约炮",
    "卖淫",
    "嫖娼",
    "性爱",
    "赌博",
    "博彩",
    "毒品",
    "诈骗",
    "传销",
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "bastard",
    "sb"
  ];

  function containsSensitiveHint(text: string): boolean {
    const t = (text || "").toLowerCase();
    return SENSITIVE_HINT_WORDS.some(w => t.includes(w.toLowerCase()));
  }

  const usernameSensitive = computed(() =>
    containsSensitiveHint(profileForm.username)
  );
  const nicknameSensitive = computed(() =>
    containsSensitiveHint(profileForm.nickname)
  );

  const currentNickname = computed(
    () => userStore.nickname || userStore.username || "未设置"
  );

  const email = computed(() => me.value?.email || "");

  // 用户 supabase 唯一标识（用于默认头像 seed）
  const supabaseId = computed(
    () => me.value?.supabase_id || userStore.username
  );

  // ============================================
  // 头像：style + seed 联合决定"画风 + 脸型"
  // ============================================
  const avatarStyle = ref<AvatarStyle>(DEFAULT_AVATAR_STYLE);
  const avatarSeed = ref<string>("");
  /** 头像动画开关（默认开，仅对官方动画风格生效；用户可关） */
  const avatarAnimated = ref(true);

  /** 风格卡片缩略图固定用统一 seed，避免每张卡片随用户头像变化而抖动 */
  const avatarThumbSeed = hashSeed("fundmate-style-thumb");

  /** 确定性伪随机错位（按键名哈希，刷新不跳动） */
  function styleCardStyle(style: AvatarStyle): Record<string, string> {
    const h = hashSeed(`card-${style}`);
    const rot = (Number(h.slice(0, 2)) % 5) - 2; // -2° ~ 2°
    const lift = (Number(h.slice(2, 4)) % 7) - 3; // -3px ~ 3px
    return {
      "--tilt": `rotate(${rot}deg) translateY(${lift}px)`
    };
  }

  const savedAvatarUrl = computed(() =>
    userStore.avatar && isAvatarUrl(userStore.avatar) ? userStore.avatar : ""
  );

  /** 进入个人中心时已保存的头像 URL（会话级快照，供"撤销"回滚，误触不怕丢原头像） */
  const avatarSnapshot = ref("");
  /** 头像是否被改动过（与进入时的快照不一致即视为脏，显示撤销按钮） */
  const avatarDirty = computed(
    () => avatarSnapshot.value && avatarSnapshot.value !== avatarPreview.value
  );

  const avatarPreview = computed(() => {
    if (avatarSeed.value) {
      return buildAvatarUrl(avatarStyle.value, avatarSeed.value, {
        animated: avatarAnimated.value
      });
    }
    return savedAvatarUrl.value || defaultAvatarUrl(supabaseId.value);
  });

  /** 进入页面时记录当前已保存头像，作为回滚基线 */
  function captureAvatarSnapshot() {
    avatarSnapshot.value =
      savedAvatarUrl.value || defaultAvatarUrl(supabaseId.value);
  }

  /** 撤销到头像快照（恢复进入时的风格/seed/动画并写库） */
  async function onRevertAvatar() {
    const parsed = parseAvatarUrl(avatarSnapshot.value);
    if (!parsed) {
      avatarStyle.value = DEFAULT_AVATAR_STYLE;
      avatarSeed.value = hashSeed(supabaseId.value || "fundmate-anon");
      avatarAnimated.value = true;
    } else {
      avatarStyle.value = parsed.style;
      avatarSeed.value = parsed.seed;
      avatarAnimated.value = parsed.animated;
    }
    await persistAvatar();
  }

  function initAvatar() {
    const parsed = parseAvatarUrl(savedAvatarUrl.value);
    if (parsed) {
      avatarStyle.value = parsed.style;
      avatarSeed.value = parsed.seed;
      avatarAnimated.value = parsed.animated;
      return;
    }
    avatarSeed.value = hashSeed(supabaseId.value || "fundmate-anon");
  }

  async function onRandomizeAvatar() {
    avatarStyle.value = randomAvatarStyle();
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
    const newUrl = buildAvatarUrl(avatarStyle.value, avatarSeed.value, {
      animated: avatarAnimated.value
    });
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
  // 资料保存
  // ============================================
  async function onSaveNickname() {
    const value = profileForm.nickname.trim();
    if (value.length < 5) {
      ElMessage.warning("昵称至少 5 个字符");
      return;
    }
    if (containsSensitiveHint(value)) {
      ElMessage.warning("昵称包含不当词汇，请更换");
      return;
    }
    nicknameSaving.value = true;
    try {
      const { data } = await updateMe({ nickname: value });
      const nickname = data.nickname ?? value;
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
    const value = profileForm.username.trim();
    if (value.length < 5) {
      ElMessage.warning("用户名至少 5 个字符");
      return;
    }
    if (containsSensitiveHint(value)) {
      ElMessage.warning("用户名包含不当词汇，请更换");
      return;
    }
    usernameSaving.value = true;
    try {
      const { data } = await updateMe({ username: value });
      const username = data.username ?? value;
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

  // 弹窗逻辑 (邮箱、密码)
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

  // 退出登录
  const logoutDialogVisible = ref(false);

  // 触发退出确认框
  async function onLogout() {
    logoutDialogVisible.value = true;
  }

  // 确认退出执行
  async function confirmLogout() {
    logoutDialogVisible.value = false;
    await userStore.logOut();
  }

  // 数据加载
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
      captureAvatarSnapshot();
      initAvatar();
    } catch (e: any) {
      if (e?.response?.status !== 401) {
        ElMessage.error("加载个人信息失败");
      }
    }
  });

  return {
    profileForm,
    nicknameDirty,
    usernameDirty,
    nicknameSaving,
    usernameSaving,
    nicknameSensitive,
    usernameSensitive,
    onSaveNickname,
    onSaveUsername,
    currentNickname,
    email,
    avatarStyle,
    avatarSeed,
    avatarAnimated,
    avatarDirty,
    avatarPreview,
    avatarThumbSeed,
    styleCardStyle,
    onRevertAvatar,
    onRandomizeAvatar,
    onSelectStyle,
    persistAvatar,
    emailDialogVisible,
    emailForm,
    emailFormRef,
    emailSubmitting,
    emailRules,
    onSaveEmail,
    passwordDialogVisible,
    passwordForm,
    passwordFormRef,
    passwordSubmitting,
    passwordRules,
    onSavePassword,
    logoutDialogVisible,
    onLogout,
    confirmLogout
  };
}
