import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * 资产名称可编辑的防回潮判据（设计见
 * `docs/design/asset-value-history-design.md` §9.1 / 验收 A1）。
 *
 * 这个需求的特殊之处：`name` 在数据库、后端 PATCH schema、前端 TS 类型三层
 * **一直都存在**，唯一缺的是编辑弹窗这个入口。因此最易回潮的形态不是「报错」，
 * 而是「输入框还在、保存时却漏提交 name」——界面看起来正常，改名静默失效。
 * 故判据必须同时钉住「渲染 / 回填 / 基线 / 提交 / 非空校验」五处，且**剥注释后
 * 匹配源码**：注释里写了字段名不算数（D87 在 cashLikeCardGuard 上踩过假绿）。
 */
const source = readFileSync(
  new URL("../AssetEditDialog.vue", import.meta.url),
  "utf8"
);

/** 去掉 HTML / 块注释 / 整行行注释，避免「注释里写着就算已实现」的假绿 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

const stripped = stripComments(source);

/**
 * 取出 save() 里的请求体：第 2 期把内联对象抽成了 `payload` 变量
 * （delta != 0 时才追加事件字段），所以判据跟着改为读这个变量。
 */
function saveBody(): string {
  const match = stripped.match(
    /const payload: AssetUpdateInput = \{([\s\S]*?)\};/
  );
  return match?.[1] ?? "";
}

describe("AssetEditDialog 名称可编辑（防回潮）", () => {
  it("模板真的渲染了名称输入框", () => {
    expect(stripped).toContain('v-model="form.name"');
    expect(stripped).toContain('label="资产名称"');
  });

  it("打开弹窗时按传入行回填名称", () => {
    expect(stripped).toContain('name: props.asset?.name || ""');
  });

  it("EMPTY_FORM 含 name，脏基线不会漏掉新字段（#1880）", () => {
    expect(stripped).toMatch(/EMPTY_FORM\s*=\s*\{[^}]*name:\s*""/);
  });

  it("保存请求体提交 name —— 防止「输入框在、改名静默失效」", () => {
    expect(saveBody()).toContain("name,");
  });

  it("提交前 trim 且拒绝空名，避免把空名写进按 name 聚合的口径", () => {
    expect(stripped).toContain("const name = form.value.name.trim()");
    expect(stripped).toContain('ElMessage.warning("资产名称不能为空")');
  });

  it("未保存离开提示覆盖全部可改字段（含 G5 新增的配置目标）", () => {
    // 这句提示是用户**唯一能看见的脏字段清单**。新增一个可改字段却不同步文案，
    // 用户会以为这次只改了无关项、放心点 ×（配置目标就此静默丢失）。
    // 故逐项断言而不是比对整句：既拦住漏字段，也不因调整语序/连接符而假红。
    const match = stripped.match(/message:\s*\n?\s*"([^"]*已改动[^"]*)"/);
    expect(match, "找不到未保存离开提示文案").not.toBeNull();
    for (const field of [
      "资产名称",
      "配置目标",
      "变动量",
      "变动日期",
      "说明",
      "备注"
    ]) {
      expect(match![1], `提示未覆盖「${field}」`).toContain(field);
    }
  });
});
