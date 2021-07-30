---
title: 项目中代码规范问题
permalink: /dev/guideline
---
## 约定
### 编码
1. 项目应该尽可能遵循 PEP8 代码规范，更多请参阅[此页面](/dev/code-style)
2. 引入 typing，需要对代码中的输入输出做类型提示；
4. assert 不应该用于参数校验，原因参见
   [Python: Don’t use assert for Data Evaluation | by Bala Vignesh | Medium](https://medium.com/@crystelpheonix/python-dont-use-assert-for-data-evaluation-721bfa93c571)
   使用`-O` 可以禁用断言判断
   [notes/when-to-use-assert.md at master · emre/notes](https://github.com/emre/notes/blob/master/python/when-to-use-assert.md)
### 格式
1. 时间我们统一为 ISO-8601 格式，参阅：https://kirby.kevinson.org/blog/iso-8601-the-better-date-format/

## per-commit
使用该操作在提交代码前检查代码的格式是否符合设置

## gitignore
项目根目录下的`.gitignore`文件用于忽略项目开发中产生的通用应该被忽略的文件或目录，你可以借助[gitignore.io - 为你的项目创建必要的 .gitignore 文件](https://www.toptal.com/developers/gitignore) 生成。对于个人独有的需要忽略的文件或目录，你可以在`$GIT_DIR/info/exclude`文件（亦即：项目根目录下的`.git\info\exclude`文件）中写入排除的文件及目录路径，写法与`.gitignore`文件相同。参阅[git - Can I make a user-specific gitignore file? - Stack Overflow](https://stackoverflow.com/questions/5724455/can-i-make-a-user-specific-gitignore-file)
