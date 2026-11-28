import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  beginMcpOAuth,
  connectMcpStaticToken,
  disconnectMcp,
  listMcpConnections,
  verifyMcpConnection,
  type McpConnection
} from "@/api/mcp";
import {
  notifyOpenerAndClose,
  reauthorizeViaPopup,
  snapshotOf,
  type ConnectionSnapshot
} from "./oauthPopup";
import { MCP_SERVICES, serviceName } from "./mcpServices";

export type McpNotice = { type: "success" | "error"; text: string };

/** 每张卡片的连接校验状态：null = 没验证过 */
export type McpVerifyState = {
  status: "loading" | "ok" | "fail";
  text: string;
};

/**
 * 连接管理页的状态层。
 *
 * 两条连接方式的唯一分叉只在「怎么拿到凭据」：OAuth 整页跳授权站、回调由后端接；
 * API Key 在本站填、后端加密入库。拿到之后共用同一张凭据表，所以本层不区分后续
 * 的列表 / 断开逻辑。
 *
 * 错误文案固定为人话：上游响应体可能含 token，绝不把 err.message 直接显示出来。
 */
export function useMcpConnections() {
  const route = useRoute();
  const router = useRouter();

  const connections = ref<McpConnection[]>([]);
  const loading = ref(false);
  const pending = ref<string[]>([]);
  const notice = ref<McpNotice | null>(null);
  const verifyStates = ref<Record<string, McpVerifyState | undefined>>({});

  const byProvider = computed(
    () => new Map(connections.value.map(item => [item.provider, item]))
  );

  /** 服务清单（UI 侧登记）+ 该用户的实时连接状态 */
  const services = computed(() =>
    MCP_SERVICES.map(service => ({
      ...service,
      connection: byProvider.value.get(service.provider) ?? null
    }))
  );

  function fail(text: string): void {
    notice.value = { type: "error", text };
  }

  async function load(): Promise<void> {
    loading.value = true;
    try {
      const response = await listMcpConnections();
      connections.value = response.data ?? [];
    } catch {
      fail("连接列表加载失败，请稍后重试");
    } finally {
      loading.value = false;
    }
  }

  /** OAuth 回调回跳后的一次性成功提示；读完即清 query，刷新不再重复弹 */
  function consumeRedirectNotice(): void {
    if (route.query.mcp_connected !== "1") return;
    const provider = String(route.query.provider ?? "");
    // 弹窗通道：本页是在授权弹窗里落地 —— 通知主窗口授权完成后自关，
    // 提示由主窗口负责，这里不走整页 notice（关窗前闪一下反而误导）
    if (notifyOpenerAndClose(provider)) return;
    const name = serviceName(provider);
    notice.value = { type: "success", text: `${name}已授权连接` };

    const rest = { ...route.query };
    delete rest.mcp_connected;
    delete rest.provider;
    void router.replace({ path: route.path, query: rest });
  }

  function track(provider: string, on: boolean): void {
    pending.value = on
      ? [...pending.value, provider]
      : pending.value.filter(item => item !== provider);
  }

  /**
   * 浏览器授权：弹窗完成，不离开本页（静默重授权）。
   *
   * 弹窗里还留着上游会话时授权页自动跳回，用户无感；这是续期的主路径 ——
   * 上游 access_token 寿命短、refresh_token 不可用（见 oauthPopup.ts 头注释）。
   * 弹窗被拦截器挡掉时降级为整页跳转（旧行为，回调照旧落回本页）。
   */
  async function connectOAuth(provider: string): Promise<void> {
    const name = serviceName(provider);
    // 发起前抓快照：轮询靠「凭据相比发起前有变化」区分新授权与旧凭据
    const previous = byProvider.value.get(provider);
    const baseline: ConnectionSnapshot | null = previous
      ? snapshotOf(previous)
      : null;
    track(provider, true);
    try {
      const response = await beginMcpOAuth(provider);
      const url = response.data?.authorization_url;
      if (!url) {
        fail("授权地址获取失败，请稍后重试");
        return;
      }
      const result = await reauthorizeViaPopup(url, provider, baseline);
      if (result.ok) {
        notice.value = {
          type: "success",
          text: previous ? `${name}授权已静默恢复` : `${name}已授权连接`
        };
        await load();
        return;
      }
      if (result.reason === "blocked") {
        // 弹窗被拦截：降级为整页跳转，回调后仍会落回本页并提示
        window.location.assign(url);
        return;
      }
      fail(
        result.reason === "timeout"
          ? `${name}授权等待超时，请重试`
          : `${name}授权未完成，若浏览器拦截了弹窗请允许弹出后重试`
      );
      await load();
    } catch {
      fail("发起授权失败，请稍后重试");
    } finally {
      track(provider, false);
    }
  }

  /** 静态 API Key：前端只负责递交给后端，不留存、不回显 */
  async function connectStatic(
    provider: string,
    apiKey: string
  ): Promise<void> {
    track(provider, true);
    try {
      await connectMcpStaticToken({ provider, api_key: apiKey });
      notice.value = { type: "success", text: "API Key 已保存" };
      await load();
    } catch {
      fail("保存失败，请检查 API Key 后重试");
    } finally {
      track(provider, false);
    }
  }

  async function disconnect(provider: string): Promise<void> {
    track(provider, true);
    try {
      await disconnectMcp(provider);
      notice.value = { type: "success", text: "已断开连接" };
      await load();
    } catch {
      fail("断开失败，请稍后重试");
    } finally {
      track(provider, false);
    }
  }

  /**
   * 连接校验：向上游握手并拉工具清单 —— 「连接之后能干什么」的直接回答。
   * 过期 / Key 失效在这一步变成明确文案（后端 4xx message 可读，拦截器只覆盖 5xx）。
   */
  async function verify(provider: string): Promise<void> {
    setVerifyState(provider, { status: "loading", text: "" });
    try {
      const response = await verifyMcpConnection(provider);
      const data = response.data;
      const names = data.tools
        .slice(0, 6)
        .map(tool => tool.name)
        .join("、");
      const more = data.tool_count > 6 ? ` 等 ${data.tool_count} 个` : "";
      setVerifyState(provider, {
        status: "ok",
        text: `连接可用，上游提供 ${data.tool_count} 个工具：${names}${more}`
      });
    } catch (error) {
      const backendMessage =
        (
          error as {
            response?: { data?: { message?: string } };
          }
        )?.response?.data?.message || "验证失败，请稍后重试";
      // 后端对「凭据过期」的模板文案是「…请更新 Token」——对 API Key 型成立，
      // 但对浏览器授权型是死胡同：用户手里没有 Token 可更新，正确动作是
      // 点「重新连接」弹窗静默续期。本地已过期（expires_at 可判）时改写文案，
      // 把下一步动作指对；没过期时照原样透传（真失效 / 被撤销仍由后端文案描述）。
      const connection = byProvider.value.get(provider);
      const text = isExpired(connection?.expires_at)
        ? `${serviceName(provider)}授权已过期，点「重新连接」即可静默续期`
        : backendMessage;
      setVerifyState(provider, { status: "fail", text });
    }
  }

  function setVerifyState(provider: string, state: McpVerifyState): void {
    verifyStates.value = { ...verifyStates.value, [provider]: state };
  }

  function verifyState(provider: string): McpVerifyState | null {
    return verifyStates.value[provider] ?? null;
  }

  return {
    services,
    loading,
    pending,
    notice,
    load,
    consumeRedirectNotice,
    connectOAuth,
    connectStatic,
    disconnect,
    verify,
    verifyState,
    clearNotice: () => {
      notice.value = null;
    }
  };
}
