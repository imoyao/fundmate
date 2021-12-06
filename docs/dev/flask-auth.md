---
title: 再一次，认识注册、登录功能
---

[认证、授权、鉴权和权限控制 | 滩之南](http://www.hyhblog.cn/2018/04/25/user_login_auth_terms/)

## token 而不是 cookie

API 通常希望每次请求都将访问凭证/令牌发送到 API。这类似于 web 服务(Flask)直接返回 html/js 代码时对请求进行身份验证的方式。

然而，区别在于C/S用于提交身份验证证明的机制。在B/S的典型应用程序中，前端代码 cookie 用于存储会话信息，这些 cookie 由客户端(浏览器)随每个请求自动发送到后端。

在通常的Web应用中，通常使用Flask-Login 查看这些 cookie 并验证它们的真实性，并从服务器上的会话中存储的信息确定是哪个用户发出了请求。关于它的使用可以参阅：
[cookie在flask中的应用、flask-login模块的使用（login_user、@login_required、@login_manager.user_loader）current_user_Null的博客-CSDN博客](https://blog.csdn.net/JENREY/article/details/86671856)

您提到您的客户端是一个使用 Python 请求库的桌面应用程序，因此如果您想继续使用您拥有的 auth 方法，您将希望编程您的桌面客户端使用请求发送请求。会话对象。这基本上封装您的请求并为您存储 cookie。为此，您需要发出一个初始化请求，以使用该请求进行登录。Session 对象，然后所有后续请求将自动发送 cookie，您的 Flask 应用程序将看到您的桌面应用程序已登录。查看文档了解更多信息。

但是，使用 api， Flask web 服务器不会直接向客户端提供前端代码。事实上，API 不应该关心客户端是否有前端。所有 API 都知道客户端可能是另一个脚本，或者是在终端上运行 curl 命令的用户等等。重要的是，客户端可能有也可能没有“cookie”的概念。因此，API 需要一种方法来验证传入的请求是否得到了授权。

就像 cookie 需要与每个请求一起发送一样，API 需要与每个请求一起发送“嘿，服务器，我是一个请求，我被授权了。”

最明显的解决方案是在每次请求时都发送用户名和密码。这个解决方案非常基本，称为基本认证。显然，这里存在安全问题，但是如果 http 流量是加密的(https)，那么在客户机是一个运行在安全框上的进程(从受保护的文件读取密码)的实例中，基本身份验证就可以了。

Python 的 requests 库也可以实现用户名和密码登录：
```python
import requests
requests.get('https://api.github.com/user', auth=('user', 'pass'))
```
在后端代码中
```python
import request

@app.route(...)
def some_route():
  username = request.authorization.username
  password = request.authorization.password
  # check to make sure username/password is okay
  # could abstract this code as a decorator and apply it to multiple routes
  # that you want protected by basic auth
```
还有一个 [Flask-BasicAuth](https://flask-basicauth.readthedocs.io/en/latest/) 模块，该项目声称可以让 Flask 非常容易地整合 basic auth，尽管我从未使用过它。

然而在客户机的实例不能被认为是超级安全，说一个前端的 web 应用程序，您的开发人员可能不希望将用户名和密码直接存储在浏览器和本地存储等等，有人有机会看到用户凭证。

基于令牌的身份验证是另一个更安全的选项，基本上客户机将用户名/密码凭据发送到后端一次，然后用它们交换令牌。然后，这个令牌与客户机发出的每个请求一起发送。在后端，web 服务器可以验证令牌的真实性，并从中提取身份。令牌可以通过 HTTP 头发送，也可以通过 url 查询字符串发送。例如`www.myapi.com/some-end-point?token=12345678`

然后，如果令牌被破坏，用户可以使用相同的用户名/密码获得另一个令牌，旧令牌就会过期。

如果您想使用基于令牌的认证方法，请查看 JSON Web Tokens (JWT)，特别是以下 Flask 插件: [Flask-JWT-Extended](https://github.com/vimalloc/flask-jwt-extended) [Flask-Praetorian](https://flask-praetorian.readthedocs.io/en/latest/)


## 注册
1. 目前更合理的主流设计是注册的时候不发确认邮件，等用户自行登录后，显示提示需要确认邮件，用户点击发送邮件按钮后再发送邮件。 
2. 此外，用户如果一个月不登录，则提前一周发送提示邮件并在到期后删除用户账号。
3. 用户可以选择第三方登录或者邮箱注册：
    1. 如果使用第三方登录，则需要提示用户绑定邮箱
    2. 如果使用邮箱注册，则需要加延时，避免骚扰用户。同时用户登录之后提示用户激活邮箱，用户激活设置有效期，避免过期泄露
4. 通知用户信息功能实现，后端可以自定义发送信息给前端

## 实现

我们使用加密算法将用户密码而不是明文密码保存起来，注意：MD5 不是加密算法，我们可以使用`werkzeug.security`实现，当然还有很多扩展可以做这件事，比如：[Passlib](https://passlib.readthedocs.io/en/stable/)
关于两者的区别参阅此处：[flask-bcrypt vs werkzeug.security · Issue #42](https://github.com/maxcountryman/flask-bcrypt/issues/42) 和 [此处](https://www.reddit.com/r/flask/comments/54ptgs/what_is_the_difference_between_flaskbcrypt_and/)
一句话来说区别就是：
`werkzeug.security`使用`PBKDF`算法而后者使用`bcrypt`加密算法，这使得攻击者如果使用 GPU 硬件加速的话，可能理论上来讲后者（bcrypt）破解难度更小；但是也不用过于担心，参见 [此处](https://stackoverflow.com/questions/42445270/werkzeug-security-generate-password-hash-alternative-without-sha-1)

[RESTful Authentication with Flask - miguelgrinberg.com](https://blog.miguelgrinberg.com/post/restful-authentication-with-flask)

### Flask-Login vs Flask-HTTPAuth

> For a REST service you do not need Flask-Login. Typically in web services you do not store client state (what Flask-Login does), instead you authenticate each and every request. Flask-HTTPAuth does this for you.
>
>You would use both only if you have an application that has a web component and a REST API component. In that case Flask-Login will handle the web app routes, and Flask-HTTPAuth will handle the API routes.

###  Flask-JWT VS Flask-Login

[Tutorial on how to combine authentication between Flask-JWT and Flask-Login · Issue #253 · maxcountryman/flask-login](https://github.com/maxcountryman/flask-login/issues/253)
[python - For a REST API, can I use authentication mechanism provided by flask-login or do I explicitly have to use token based authentication like JWT? - Stack Overflow](https://stackoverflow.com/questions/65520316/for-a-rest-api-can-i-use-authentication-mechanism-provided-by-flask-login-or-do)

[Using Flask-JWT with Flask-Login - Ivan's Software Engineering BlogIvan's Software Engineering Blog](https://ai-facets.org/using-flask-jwt-with-flask-login/)

::: warning
JWT:由于[此处-Issue #123](https://github.com/mattupstate/flask-jwt/issues/123) 提到的原因我们选择 [Flask-JWT-Extended’s Documentation — flask-jwt-extended 3.25.0 documentation](https://flask-jwt-extended.readthedocs.io/en/stable/) 作为实现 JWT 的扩展。
:::

满足所有：由于 ~~[Flask-Security — Flask-Security 3.0.0 documentation](https://pythonhosted.org/Flask-Security/)~~ 不再积极维护，我们转向 [Welcome to Flask-Security（TOO） — Flask-Security 4.0.0 documentation](https://flask-security-too.readthedocs.io/en/stable/)
## [flask-praetorian vs flask-jwt-extended](https://flask-praetorian.readthedocs.io/en/latest/comparison.html#flask-jwt-extended)


一种保护 API 的方式：
[python - flask: how to bridge front-end with back-end service to render api authentication? - Stack Overflow](https://stackoverflow.com/questions/61329021/flask-how-to-bridge-front-end-with-back-end-service-to-render-api-authenticatio)

### 相关链接
- [vue+elementUI+WebSocket 接收后台实时消息推送 - 简书](https://www.jianshu.com/p/c0a29ea2da46)
- [全双工通信的 WebSocket](https://halfrost.com/websocket/)
- [H5 页面前后端通信 （3 种方式简单介绍） - 吴飞 ff - 博客园](https://www.cnblogs.com/wfblog/p/9814620.html)
- [flask-socketio-doc-zh/Flask-SocketIO 中文文档.md at master · shenyushun/flask-socketio-doc-zh](https://github.com/shenyushun/flask-socketio-doc-zh/blob/master/Flask-SocketIO%E4%B8%AD%E6%96%87%E6%96%87%E6%A1%A3.md)

## 登录
1. 支持 oauth2 登录
2. 如果是 oauth2 登录，则需要绑定邮箱

## 注销
用户选择注销，则提示备份数据（可以主动备份并发送给用户）

## 推荐阅读
0. [security - The definitive guide to form-based website authentication - Stack Overflow](https://stackoverflow.com/questions/549/the-definitive-guide-to-form-based-website-authentication)
1. [Welcome to Flask-HTTPAuth’s documentation! — Flask-HTTPAuth documentation](https://flask-httpauth.readthedocs.io/en/latest/)
2. [python - flask: how to bridge front-end with back-end service to render api authentication? - Stack Overflow](https://stackoverflow.com/questions/61329021/flask-how-to-bridge-front-end-with-back-end-service-to-render-api-authenticatio)
3. [Single Page Apps with Vue.js and Flask: JWT Authentication](https://stackabuse.com/single-page-apps-with-vue-js-and-flask-jwt-authentication/)
4. [Token-Based Authentication With Flask – Real Python](https://realpython.com/token-based-authentication-with-flask/)
5. [Using Flask-JWT with Flask-Login - Ivan's Software Engineering BlogIvan's Software Engineering Blog](https://ai-facets.org/using-flask-jwt-with-flask-login/)
6. [RESTful Authentication with Flask - miguelgrinberg.com](https://blog.miguelgrinberg.com/post/restful-authentication-with-flask)
7. [细说 API – 认证、授权和凭证 - 知乎](https://zhuanlan.zhihu.com/p/60522006)
8. [HTTP API 认证授权术 | 酷 壳 - CoolShell](https://coolshell.cn/articles/19395.html)
9. [REST 接口安全认证方式对比：API Key vs OAuth 令牌 vs JWT_王浩的技术博客-CSDN 博客_apikey 认证方式](https://peterwanghao.blog.csdn.net/article/details/81170785)
10. [傻傻分不清之 Cookie、Session、Token、JWT - 掘金](https://juejin.cn/post/6844904034181070861)

## 权限

[最好的权限设计，是先区分功能权限和数据权限 | 人人都是产品经理](http://www.woshipm.com/pd/2889402.html)

[产品注册&登录设计，需要注意的 23 条规则 | 人人都是产品经理](http://www.woshipm.com/pd/1483348.html)

[后台经验分享：如何做权限管理系统设计 | 人人都是产品经理](http://www.woshipm.com/pd/835248.html)

[大家心心念念的权限管理功能，这次安排上了！](https://juejin.cn/post/6844904067525771272)

[如何从零开始设计权限管理系统 | Echo Blog](https://houbb.github.io/2020/09/17/how-to-design-privilege-system#%E4%BC%A0%E7%BB%9F-rbac-%E7%9A%84%E4%B8%8D%E8%B6%B3)

[常见权限系统设计模型分析（DAC，MAC，RBAC，ABAC） - 简书](https://www.jianshu.com/p/ce0944b4a903)

[可能是史上最全的权限系统设计 - 知乎](https://zhuanlan.zhihu.com/p/73414693)