/**
 * 系统状态页口径单测（#980 批 B9）。
 *
 * 这些映射决定「状态页说的绿是真绿还是假绿」，而页面本身几乎只做排版，
 * 所以把三件会撒谎的事钉在这里：
 *   ① 未收录的状态码 —— 不能显示成「正常」；
 *   ② 未收录的状态色调 —— 兜底到 error（需关注），不是 ok；
 *   ③ 取数失败 —— 横幅必须报错，不能因为「没有异常数据」就说「全部正常」。
 */
import { describe, expect, it } from "vitest";
import type { HealthData } from "@/api/health";
import {
  buildBanner,
  buildComponentRows,
  STATUS_TEXT,
  statusText,
  statusTone
} from "../statusModel";

function health(
  overrides: {
    dbStatus?: string;
    dbMessage?: string;
    schedulerStatus?: string;
    schedulerEnabled?: boolean;
    lastRun?: string | null;
    schedulerMessage?: string;
    llmStatus?: string;
    llmConfigured?: boolean;
    provider?: string;
    model?: string;
    llmMessage?: string;
  } = {}
): HealthData {
  return {
    status: "ok",
    message: "",
    components: {
      database: {
        status: overrides.dbStatus ?? "healthy",
        dialect: "sqlite",
        message: overrides.dbMessage
      },
      scheduler: {
        status: overrides.schedulerStatus ?? "healthy",
        enabled: overrides.schedulerEnabled ?? true,
        last_success_run: overrides.lastRun ?? null,
        message: overrides.schedulerMessage
      },
      llm: {
        status: overrides.llmStatus ?? "healthy",
        configured: overrides.llmConfigured ?? true,
        provider: overrides.provider ?? "deepseek",
        model: overrides.model ?? "chat",
        message: overrides.llmMessage
      }
    }
  };
}

describe("statusText", () => {
  it("已知枚举译成中文", () => {
    expect(statusText("healthy")).toBe("正常");
    expect(statusText("ok")).toBe("正常");
    expect(statusText("degraded")).toBe("降级");
    expect(statusText("unhealthy")).toBe("异常");
    expect(statusText("disabled")).toBe("未启用");
  });

  it("后端新增的未知枚举原样透出，不冒充「正常」", () => {
    expect(statusText("maintenance")).toBe("maintenance");
  });

  it("映射表本身不得为空：它是文案的唯一来源", () => {
    expect(Object.keys(STATUS_TEXT).length).toBeGreaterThanOrEqual(5);
  });
});

describe("statusTone", () => {
  it("健康态归 ok", () => {
    expect(statusTone("healthy")).toBe("ok");
    expect(statusTone("ok")).toBe("ok");
  });

  it("disabled 归 muted（未启用不算故障）", () => {
    expect(statusTone("disabled")).toBe("muted");
  });

  it("degraded 归 warn，unhealthy 归 error", () => {
    expect(statusTone("degraded")).toBe("warn");
    expect(statusTone("unhealthy")).toBe("error");
  });

  it("未知状态兜底到 error —— 宁可多报红，也不让故障藏在「正常」里", () => {
    expect(statusTone("maintenance")).toBe("error");
  });
});

describe("buildComponentRows", () => {
  it("无数据时返回空数组（骨架屏阶段）", () => {
    expect(buildComponentRows(null)).toEqual([]);
  });

  it("三行固定顺序：数据库 / 数据调度 / AI 识别", () => {
    expect(buildComponentRows(health()).map(r => r.name)).toEqual([
      "数据库",
      "数据调度",
      "AI 识别"
    ]);
  });

  it("数据库要点是方言大写", () => {
    expect(buildComponentRows(health())[0].detail).toBe("SQLITE");
  });

  it("数据库正常时不留原因位（无消息即正常）", () => {
    expect(buildComponentRows(health())[0].hint).toBe("");
  });

  it("数据库异常时把后端 message 原样带上", () => {
    const rows = buildComponentRows(
      health({ dbStatus: "unhealthy", dbMessage: "连接超时" })
    );
    expect(rows[0].hint).toBe("连接超时");
  });

  it("调度关闭时要点说「未开启自动更新」，且不显示原因", () => {
    const row = buildComponentRows(
      health({ schedulerEnabled: false, schedulerStatus: "disabled" })
    )[1];
    expect(row.detail).toBe("未开启自动更新");
    expect(row.hint).toBe("");
  });

  it("调度开启但无成功记录时说「尚无成功记录」", () => {
    expect(buildComponentRows(health())[1].detail).toBe("尚无成功记录");
  });

  it("有成功记录时截到分钟并换成空格分隔（不是原始 ISO 串）", () => {
    const row = buildComponentRows(
      health({ lastRun: "2026-10-27T06:06:39.184874" })
    )[1];
    expect(row.detail).toBe("最近成功运行 2026-10-27 06:06");
  });

  it("调度降级且带 message 时显示原因", () => {
    const row = buildComponentRows(
      health({ schedulerStatus: "degraded", schedulerMessage: "上次运行失败" })
    )[1];
    expect(row.hint).toBe("上次运行失败");
  });

  it("AI 已配置时要点是「provider · model」，缺一项就只留一项", () => {
    expect(buildComponentRows(health())[2].detail).toBe("deepseek · chat");
    expect(buildComponentRows(health({ model: "" }))[2].detail).toBe(
      "deepseek"
    );
  });

  it("AI 未配置时要点说「未配置」，不显示半截 provider", () => {
    const row = buildComponentRows(health({ llmConfigured: false }))[2];
    expect(row.detail).toBe("未配置");
  });

  it("AI 停用（disabled）不显示原因，异常才显示", () => {
    expect(
      buildComponentRows(
        health({ llmStatus: "disabled", llmMessage: "不该出现" })
      )[2].hint
    ).toBe("");
    expect(
      buildComponentRows(
        health({ llmStatus: "unhealthy", llmMessage: "额度用尽" })
      )[2].hint
    ).toBe("额度用尽");
  });
});

describe("buildBanner", () => {
  it("取数失败压过一切：即使有旧数据也报错", () => {
    const banner = buildBanner({
      errorMessage: "无法连接后端服务",
      hasHealth: true,
      rows: buildComponentRows(health())
    });
    expect(banner).toMatchObject({
      tone: "error",
      title: "暂时无法获取状态",
      desc: "无法连接后端服务"
    });
  });

  it("既没数据也没报错时返回 null（页面出骨架屏）", () => {
    expect(
      buildBanner({ errorMessage: "", hasHealth: false, rows: [] })
    ).toBeNull();
  });

  it("全部正常时 desc 留空（不啰嗦）", () => {
    const banner = buildBanner({
      errorMessage: "",
      hasHealth: true,
      rows: buildComponentRows(health())
    });
    expect(banner).toMatchObject({ tone: "ok", title: "所有组件运行正常" });
    expect(banner?.desc).toBe("");
  });

  it("有降级时列出受影响组件与它的中文状态", () => {
    const banner = buildBanner({
      errorMessage: "",
      hasHealth: true,
      rows: buildComponentRows(
        health({ schedulerStatus: "degraded", dbStatus: "unhealthy" })
      )
    });
    expect(banner?.tone).toBe("warn");
    expect(banner?.title).toBe("部分组件需要关注");
    expect(banner?.desc).toBe("数据库：异常；数据调度：降级");
  });

  it("未知状态也会被列进「需要关注」，不会被静默放过", () => {
    const banner = buildBanner({
      errorMessage: "",
      hasHealth: true,
      rows: buildComponentRows(health({ dbStatus: "maintenance" }))
    });
    expect(banner?.tone).toBe("warn");
    expect(banner?.desc).toBe("数据库：maintenance");
  });

  it("只有 disabled（未启用）不算需要关注", () => {
    const banner = buildBanner({
      errorMessage: "",
      hasHealth: true,
      rows: buildComponentRows(
        health({
          llmStatus: "disabled",
          llmConfigured: false,
          schedulerStatus: "disabled",
          schedulerEnabled: false
        })
      )
    });
    expect(banner?.tone).toBe("ok");
  });
});
