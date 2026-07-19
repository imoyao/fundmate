// scripts/patch-theme.js
const fs = require("fs");
const path = require("path");

const filePath = path.resolve(
  __dirname,
  "../node_modules/vuepress-theme-antdocs/util/index.js",
);

if (fs.existsSync(filePath)) {
  let content = fs.readFileSync(filePath, "utf-8");

  // 1. 修复 getHash: path 为 undefined 时不崩溃
  content = content.replace(
    /function getHash\s*\(\s*path\s*\)\s*\{/,
    "function getHash(path) { if (!path) return null;",
  );

  // 2. 修复 isActive 中的 path.match
  content = content.replace(/path\.match/g, '(path || "").match');

  fs.writeFileSync(filePath, content, "utf-8");
  console.log("✅ Patched vuepress-theme-antdocs util/index.js");
} else {
  console.log("⚠️  File not found:", filePath);
}
