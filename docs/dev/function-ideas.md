---
title: 功能实现备忘
---
## 注册
1. 目前更合理的主流设计是注册的时候不发确认邮件，等用户自行登录后，显示提示需要确认邮件，用户点击发送邮件按钮后再发送邮件。 
2. 此外，用户如果一个月不登录，则提前一周发送提示邮件并在到期后删除用户账号。
3. 用户可以选择第三方登录或者邮箱注册：
    1. 如果使用第三方登录，则需要提示用户绑定邮箱
    2. 如果使用邮箱注册，则需要加延时，避免骚扰用户。同时用户登录之后提示用户激活邮箱，用户激活设置有效期，避免过期泄露
4. 通知用户信息功能实现，后端可以自定义发送信息给前端

### 相关链接
- [vue+elementUI+WebSocket 接收后台实时消息推送 - 简书](https://www.jianshu.com/p/c0a29ea2da46)
- [全双工通信的 WebSocket](https://halfrost.com/websocket/)
- [H5 页面前后端通信 （3 种方式简单介绍） - 吴飞 ff - 博客园](https://www.cnblogs.com/wfblog/p/9814620.html)

## 登录
1. 支持 oauth2 登录
2. 如果是 oauth2 登录，则需要绑定邮箱

## 注销
用户选择注销，则提示备份数据（可以主动备份并发送给用户）

## [CatChat - Flask Web开发实战](http://helloflask.com/projects/catchat/)

- [ ] Gravatar头像
- [ ] 第三方登录
## [Albumy - Flask Web开发实战](http://helloflask.com/projects/albumy/)
- [x] 大型项目组织形式
- [ ] 用户资料弹窗
