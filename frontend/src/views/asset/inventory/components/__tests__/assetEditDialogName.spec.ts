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

/** 取出 save() 里 updateAsset 的请求体对象内容 */
function saveBody(): string {
  const match = stripped.match(
    /await updateAsset\(form\.value\.id, \{([\s\S]*?)\}\);/
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

  it("未保存离开提示覆盖名称", () => {
    expect(stripped).toContain("资产名称／金额／备注已改动");
  });
});
