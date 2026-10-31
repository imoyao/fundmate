import Axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type CustomParamsSerializer
} from "axios";
import type {
  PureHttpError,
  RequestMethods,
  PureHttpResponse,
  PureHttpRequestConfig
} from "./types.d";
import { stringify } from "qs";
import { formatToken } from "@/utils/auth";
import { supabase } from "@/utils/supabase";
import { message } from "@/utils/message";
import { PRO_NOT_ENTITLED_CODE } from "@/constants/errorCodes";

/** 5xx 的对外文案：与后端 `ErrorCode.INTERNAL_ERROR.msg` 同级，绝不拼接异常细节 */
const SERVER_ERROR_TEXT = "服务暂时不可用，请稍后重试";

// 相关配置请参考：www.axios-js.com/zh-cn/docs/#axios-request-config-1
const defaultConfig: AxiosRequestConfig = {
  // 请求超时时间
  timeout: 10000,
  headers: {
    Accept: "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
  },
  // 数组格式参数序列化（https://github.com/axios/axios/issues/5142）
  paramsSerializer: {
    serialize: stringify as unknown as CustomParamsSerializer
  }
};

class PureHttp {
  constructor() {
    this.httpInterceptorsRequest();
    this.httpInterceptorsResponse();
  }

  /** 初始化配置对象 */
  private static initConfig: PureHttpRequestConfig = {};

  /** 保存当前`Axios`实例对象 */
  private static axiosInstance: AxiosInstance = Axios.create(defaultConfig);

  /** 请求拦截 */
  private httpInterceptorsRequest(): void {
    PureHttp.axiosInstance.interceptors.request.use(
      async (config: PureHttpRequestConfig): Promise<any> => {
        // 优先判断post/get等方法是否传入回调，否则执行初始化设置等回调
        if (typeof config.beforeRequestCallback === "function") {
          config.beforeRequestCallback(config);
          return config;
        }
        if (PureHttp.initConfig.beforeRequestCallback) {
          PureHttp.initConfig.beforeRequestCallback(config);
          return config;
        }
        // token 来源：Supabase 会话（后端以 Bearer 头验签，见 D2）。
        // 探市/健康等免登录接口不强求带 token，未登录请求也直接放行。
        const { data } = await supabase.auth.getSession();
        const accessToken = data.session?.access_token;
        if (accessToken) {
          config.headers["Authorization"] = formatToken(accessToken);
        }
        return config;
      },
      error => {
        return Promise.reject(error);
      }
    );
  }

  /** 响应拦截 */
  private httpInterceptorsResponse(): void {
    const instance = PureHttp.axiosInstance;
    instance.interceptors.response.use(
      (response: PureHttpResponse) => {
        const $config = response.config;
        // 优先判断post/get等方法是否传入回调，否则执行初始化设置等回调
        if (typeof $config.beforeResponseCallback === "function") {
          $config.beforeResponseCallback(response);
          return response.data;
        }
        if (PureHttp.initConfig.beforeResponseCallback) {
          PureHttp.initConfig.beforeResponseCallback(response);
          return response.data;
        }
        return response.data;
      },
      (error: PureHttpError) => {
        const $error = error;
        $error.isCancelRequest = Axios.isCancel($error);
        // 未授权/登录过期 → 清理本地会话并跳转登录
        if ($error.response?.status === 401) {
          message("登录已过期，请重新登录", { type: "warning" });
          // 延迟导入，避免与 store 产生循环依赖
          void import("@/store/modules/user").then(({ useUserStoreHook }) => {
            useUserStoreHook().forceLogout();
          });
        }
        // 无权限（viewer 只读 / 角色不足）→ 统一提示
        if ($error.response?.status === 403) {
          const payload = $error.response.data as
            { message?: string; error_code?: number } | undefined;
          // Pro 权益边界（error_code=1007）**不弹全局 toast**：Pro 各内容块会就地
          // 渲染「未开通」说明卡（`views/product/components/ProductProEntitlementNotice.vue`）。
          // 一个页面三块同时被挡时会叠三条一模一样的警告，把「讲边界」变成刷屏；
          // 付费墙开着时更不该再打扰一次。
          if (payload?.error_code !== PRO_NOT_ENTITLED_CODE) {
            message(payload?.message || "没有权限执行此操作", {
              type: "warning"
            });
          }
        }
        // 5xx 一律**不透传后端 message**：后端某些视图把 str(e) 拼进 message，
        // 一次 IntegrityError 就会让 SQL 全文、绑定参数（family_id / ledger_id /
        // 金额）与 sqlalche.me 链接直接出现在页面上（2026-10-29 实测）。
        // 在拦截器里统一替换，比要求每个组件各自兜底可靠——组件是逐个写的，会漏。
        if ($error.response?.status >= 500) {
          const payload = $error.response.data as
            { message?: string } | undefined;
          if (payload && typeof payload === "object") {
            payload.message = SERVER_ERROR_TEXT;
          }
        }
        // 所有的响应异常 区分来源为取消请求/非取消请求
        return Promise.reject($error);
      }
    );
  }

  /** 通用请求工具函数 */
  public request<T>(
    method: RequestMethods,
    url: string,
    param?: AxiosRequestConfig,
    axiosConfig?: PureHttpRequestConfig
  ): Promise<T> {
    const config = {
      method,
      url,
      ...param,
      ...axiosConfig
    } as PureHttpRequestConfig;

    // 单独处理自定义请求/响应回调
    return new Promise((resolve, reject) => {
      PureHttp.axiosInstance
        .request(config)
        .then((response: undefined) => {
          resolve(response);
        })
        .catch(error => {
          reject(error);
        });
    });
  }

  /** 单独抽离的`post`工具函数 */
  public post<T, P>(
    url: string,
    params?: AxiosRequestConfig<P>,
    config?: PureHttpRequestConfig
  ): Promise<T> {
    return this.request<T>("post", url, params, config);
  }

  /** 单独抽离的`get`工具函数 */
  public get<T, P>(
    url: string,
    params?: AxiosRequestConfig<P>,
    config?: PureHttpRequestConfig
  ): Promise<T> {
    return this.request<T>("get", url, params, config);
  }
}

export const http = new PureHttp();
