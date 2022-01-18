---
title: 再一次，认识注册、登录功能
---

## 厘清概念
首先需要厘清 token 和 cookie 的区别
### token 而不是 cookie
:::warning
这是一段翻译，所以可能读起来有点拗口，如果需要深入理解可以阅读这篇文章：👉 [傻傻分不清之 Cookie、Session、Token、JWT - 掘金](https://juejin.cn/post/6844904034181070861)
:::

API 通常希望每次请求都将访问凭证/令牌发送到 API。这类似于 web 服务(Flask)直接返回 html/js 代码时对请求进行身份验证的方式。

然而，区别在于 C/S 用于提交身份验证证明的机制。在 B/S 的典型应用程序中，前端代码 cookie 用于存储会话信息，这些 cookie 由客户端(浏览器)随每个请求自动发送到后端。

在 Web 应用中，通常使用 Flask-Login 查看这些 cookie 并验证它们的真实性，并从服务器上的会话中存储的信息确定是哪个用户发出了请求。关于该模块的使用可以参阅：
[cookie 在 flask 中的应用、flask-login 模块的使用（login_user、@login_required、@login_manager.user_loader）current_user_Null 的博客-CSDN 博客](https://blog.csdn.net/JENREY/article/details/86671856)


但是，如果我们编写 api 接口， Flask web 服务器不会直接向客户端提供前端代码。事实上，API 不关心客户端是否有前端。所有 API 都应该知道客户端可能是来自一个脚本，或者是在终端上运行 curl 命令的用户等等。重要的是，客户端可能有、也可能没有“cookie”的概念。因此，API 需要一种方法来验证传入的请求是否得到了授权。

就像 cookie 需要与每个请求一起发送一样，API 需要在每个请求时发送“嘿，服务器，我是一个请求，我被授权了，你看，这是我的凭证（token）”

最明显的解决方案是在每次请求时都发送用户名和密码。这个解决方案非常基本，称为基本认证。显然，这里存在安全问题。（在网络传输过程中，可能客户端的用户名密码会被第三方窃取到）。但如果 http 流量是加密的(https)，且客户机是一个运行在安全的进程(从受保护的文件读取密码)的实例中，基本身份验证就可以了。

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

然而在客户机的实例不能被认为是超级安全，一个前端的 web 应用程序，开发人员可能不希望将用户名和密码直接存储在浏览器和本地存储等等，因为有人有机会看到用户凭证。

基于令牌的身份验证是另一个更安全的选项，基本上客户机将用户名/密码凭据发送到后端一次，然后用它们交换令牌。然后，这个令牌与客户机发出的每个请求一起发送。在后端，web 服务器可以验证令牌的真实性，并从中提取身份。令牌可以通过 HTTP 头发送，也可以通过 url 查询字符串发送。例如`www.myapi.com/some-end-point?token=12345678`

然后，如果令牌被破坏，用户可以使用相同的用户名/密码获得另一个令牌，旧令牌就会过期。

如果您想使用基于令牌的认证方法，请查看 JSON Web Tokens (JWT)，特别是以下 Flask 插件: [Flask-JWT-Extended](https://github.com/vimalloc/flask-jwt-extended) [Flask-Praetorian](https://flask-praetorian.readthedocs.io/en/latest/)


第二个需要区分的概念是认证，授权和权限控制。

### [认证、授权、鉴权和权限控制 | 滩之南](http://www.hyhblog.cn/2018/04/25/user_login_auth_terms/)

- Identity（身份识别） – who claims to be making an API request? 
- Authentication （认证）– are they really who they say they are?
- Authorization （授权）– are they allowed to do what they are trying to do?

[Do you need API keys? API Identity vs. Authorization - Srimax % | Srimax](https://www.srimax.com/2014/02/19/do-you-need-api-keys-api-identity-vs-authorization/)


## 扩展横向对比
[flask-praetorian comparison to other libraries — flask-praetorian 1.3.0 documentation](https://flask-praetorian.readthedocs.io/en/latest/comparison.html#flask-jwt-extended)

* ~~flask-jwt~~
  1. 不再积极维护
  2. 实现了密码校验（authentication ）但是 verification 不够完整
  3. 权限控制不够完整
* flask-jwt-extended

  flask-jwt 的继任者；

  与 flask-praetorian 相比的优势：
     1. 使用 Cookie 进行 JWT 存储
     2. 部分路线保护
     3. 需要新鲜的 token
     4. 在 HTTP 请求中自定义 JWT（标题，正文等） 
     5. CSRF 保护
  
  缺点
    1. 密码哈希法
    2. 密码验证
    3. 基于角色的访问
    4. 电子邮件注册和验证。
    5. flask-praetorian 的 API 更简单，配置也更少。

  Flask-praetorian 旨在成为一个完整的安全扩展，而 flask-jwt-extended 则侧重于基于 jwt 的 auth 并支持许多访问模式。
* ~~flask-jwt-simple~~ 

  除了生成 JWT token 和 auth_required 装饰器外，别无他物。如果是快速成型很好用。
* ~~flask-security~~ 

  flask-praetorian 的灵感来源，但是它*包括 wtform 组件和其他东西不需要 Flask 为基础的 api*。在 API 中包含所有额外的内容既麻烦又不必要。

对于一个 RESTful API，首先出局的是~~Flask-Login~~。

### ~~Flask-Login~~ vs Flask-HTTPAuth

> For a REST service you do not need Flask-Login. Typically in web services you do not store client state (what Flask-Login does), instead you authenticate each and every request. Flask-HTTPAuth does this for you.
>
>  You would use both only if you have an application that has a web component and a REST API component. In that case Flask-Login will handle the web app routes, and Flask-HTTPAuth will handle the API routes.
[来源](https://stackoverflow.com/a/26221147/14295718)

简单来说，flask-login 会存储客户端的状态，而不是每一次请求到来时认证，这对 API 来说是不够安全的。而且，flask-login 继承了太多表单验证的东西，在 restful 中这些由我们后端自己通过 [marshmallow · PyPI](https://pypi.org/project/marshmallow/) 进行校验。参阅：[Better parameter validation in Flask with marshmallow - Cameron MacLeod](https://www.cameronmacleod.com/blog/better-validation-flask-marshmallow)

然后出局的是~~Flask-JWT~~。
###  ~~Flask-JWT~~ VS Flask-HTTPAuth
[security - API Keys vs HTTP Authentication vs OAuth in a RESTful API - Stack Overflow](https://stackoverflow.com/questions/6767813/api-keys-vs-http-authentication-vs-oauth-in-a-restful-api)
=======
[security - API Keys vs HTTP Authentication vs OAuth in a RESTful API - Stack Overflow](https://stackoverflow.com/questions/6767813/api-keys-vs-http-authentication-vs-oauth-in-a-restful-api)

###  Flask-JWT VS Flask-Login

[Tutorial on how to combine authentication between Flask-JWT and Flask-Login · Issue #253 · maxcountryman/flask-login](https://github.com/maxcountryman/flask-login/issues/253)
[python - For a REST API, can I use authentication mechanism provided by flask-login or do I explicitly have to use token based authentication like JWT? - Stack Overflow](https://stackoverflow.com/questions/65520316/for-a-rest-api-can-i-use-authentication-mechanism-provided-by-flask-login-or-do)
>>>>>>> Stashed changes

[Using Flask-JWT with Flask-Login - Ivan's Software Engineering BlogIvan's Software Engineering Blog](https://ai-facets.org/using-flask-jwt-with-flask-login/)

::: warning
JWT:由于[此处-Issue #123](https://github.com/mattupstate/flask-jwt/issues/123) 提到的原因我们选择 [Flask-JWT-Extended’s Documentation — flask-jwt-extended 3.25.0 documentation](https://flask-jwt-extended.readthedocs.io/en/stable/) 作为实现 JWT 的扩展。
::: 
### ~~Flask-Security~~ vs ~~Flask-Security（TOO）~~ vs Flask-praetorian
满足所有：由于 ~~[Flask-Security — Flask-Security 3.0.0 documentation](https://pythonhosted.org/Flask-Security/)不再积极维护，我们转向 [Welcome to Flask-Security（TOO） — Flask-Security 4.0.0 documentation](https://flask-security-too.readthedocs.io/en/stable/)~~ 基于此处[flask-praetorian comparison to other libraries — flask-praetorian 1.3.0 documentation](https://flask-praetorian.readthedocs.io/en/latest/comparison.html#flask-security) 原因，我们抛弃 Flask-Security 而选择[Flask-praetorian](https://flask-praetorian.readthedocs.io/en/latest/)

最终，我们决定先使用 Flask-HTTPAuth 实现最基本的认证（apiflask 内置），之后再考虑在 Flask-JWT-Extended 和 Flask-praetorian 之间抉择。

::: tip UPDATE

目前已实现基于`Flask-praetorian`的认证、登录、找回、重置密码，更新token的操作；大致记录一下需要注意的点：

1. 在`register_extensions`函数中初始化`Flask-praetorian`时**必须**传入`model.py`中定义的`User`，否则报错`flask_praetorian.exceptions.PraetorianError: The user_class must have a lookup class method`。此外，用户必须定义相应的`lookup`、`identity`等方法；
```python

def register_extensions(app: APIFlask):
    """Register Flask extensions."""
    ...
    # **注意** 此处必须传入User 的定义 see also: https://github.com/dusktreader/flask-praetorian/issues/224
    guard.init_app(app, user.models.User)
    ...
```
2. 发送邮件时必须确保系统存在环境变量`PRAETORIAN_CONFIRMATION_SENDER`和`PRAETORIAN_RESET_SENDER`，否则会报错`A sender is required to send confirmation email`；
3. 注册发送邮件时的token中包含用户id信息，所以必须确保发送邮件前用户信息已经写入数据库；如果没有写入，则token中没有用户的id信息，此时会报错`Could not fetch an id from the registration token`，相关代码参阅[此处](https://github.com/dusktreader/flask-praetorian/blob/c23d10e0d6e34b2b3102b9b71e48f006b8397467/flask_praetorian/base.py#L447)
```python
def encode_jwt_token():
    ...
    payload_parts = {
        "iat": moment.int_timestamp,
        "exp": access_expiration,
        "jti": str(uuid.uuid4()),
        "id": user.identity,
        "rls": ",".join(user.rolenames),
        REFRESH_EXPIRATION_CLAIM: refresh_expiration,
    }
    ...
```
4. 禁用自带异常处理
本节内容主要参考[Error Handling — flask-praetorian 1.3.0 documentation](https://flask-praetorian.readthedocs.io/en/latest/notes.html#error-handling)
尽管`flask-praetorian`已经自带异常处理，但是它返回的错误信息类似于：
```python
{
    "error": "MissingToken",
    "message": "Could not find token in any of the given locations: ['header', 'cookie']",
    "status_code": 401
}
```
而我们系统自定义的的错误为：
```python
{
    "docs": "",
    "error_code": 7001,
    "message": "xxxx"       # 中文错误提示
}
```
两者信息并不一致，此外，英文提示对于国内并不友好，无法直接显示给用户；而且，错误码是http的状态码，并不与错误码中定义统一。
:::

[Web Authentication Methods Compared | TestDriven.io](https://testdriven.io/blog/web-authentication-methods/)

## 实现

我们使用加密算法将用户密码而不是明文密码保存起来，注意：MD5 不是加密算法，我们可以使用`werkzeug.security`实现，当然还有很多扩展可以做这件事，比如：[Passlib](https://passlib.readthedocs.io/en/stable/)
关于两者的区别参阅此处：[flask-bcrypt vs werkzeug.security · Issue #42](https://github.com/maxcountryman/flask-bcrypt/issues/42) 和 [此处](https://www.reddit.com/r/flask/comments/54ptgs/what_is_the_difference_between_flaskbcrypt_and/)
一句话来说区别就是：
`werkzeug.security`使用`PBKDF`算法而后者使用`bcrypt`加密算法，这使得攻击者如果使用 GPU 硬件加速的话，可能理论上来讲后者（bcrypt）破解难度更小；但是也不用过于担心，参见 [此处](https://stackoverflow.com/questions/42445270/werkzeug-security-generate-password-hash-alternative-without-sha-1)

[RESTful Authentication with Flask - miguelgrinberg.com](https://blog.miguelgrinberg.com/post/restful-authentication-with-flask)

设置 token 需要注意的事情：[关于 token 存放在 cookie 中 - SegmentFault 思否](https://segmentfault.com/q/1010000014763987)

1. token 是否过期，应该后端接口中来判断，不该前端来判断。正常流程是：用户拿到一个 token，然后一直在用这个 token，直到到达后端设置的系统token过期时间，返回 401 错误。
2. 建议把 token 存在 cookie 上，不设置过期时间，如果 token 失效，就让后端在接口中返回固定的状态（401）表示 token 失效，需要重新登录，再重新登录的时候，重新设置 cookie 中的 token 就行。
3. js 创建 cookie 时用 `document.cookie = 'token=xxx'` 是更方便也是更安全的方法。
4. 让后端在接口的返回值 header 里添加 set-Cookie，这样的话浏览器会自动把 token 设置到 cookie 里。
5. 还有，如果接口的返回值 header 里有设，Http-Only: true 的话，js 里是不能直接修改 cookie 的，这样更安全点。

[Web Authentication Methods Compared | TestDriven.io](https://testdriven.io/blog/web-authentication-methods/)

找回密码，导出数据时有用。
```python

from time import sleep

import pyotp

if __name__ == "__main__":
    otp = pyotp.TOTP(pyotp.random_base32())
    code = otp.now()
    print(f"OTP generated: {code}")
    print(f"Verify OTP: {otp.verify(code)}")
    sleep(30)
    print(f"Verify after 30s: {otp.verify(code)}")
```

## TODO
以下是一些可能在第一阶段不会完成和实现的功能。

### 注册
1. 目前更合理的主流设计是注册的时候不发确认邮件，等用户自行登录后，显示提示需要确认邮件，用户点击发送邮件按钮后再发送邮件。（有待商榷）
2. 此外，用户如果一个月不登录，则提前一周发送提示邮件并在到期后删除用户账号。
3. 用户可以选择第三方登录或者邮箱注册：
    1. 如果使用第三方登录，则需要提示用户绑定邮箱
    2. 如果使用邮箱注册，则需要加延时，避免骚扰用户。同时用户登录之后提示用户激活邮箱，用户激活设置有效期，避免过期泄露
4. 通知用户信息功能实现，后端可以自定义发送信息给前端
   - [vue+elementUI+WebSocket 接收后台实时消息推送 - 简书](https://www.jianshu.com/p/c0a29ea2da46)
   - [全双工通信的 WebSocket](https://halfrost.com/websocket/)
   - [H5 页面前后端通信 （3 种方式简单介绍） - 吴飞 ff - 博客园](https://www.cnblogs.com/wfblog/p/9814620.html)
   - [flask-socketio-doc-zh/Flask-SocketIO 中文文档.md at master · shenyushun/flask-socketio-doc-zh](https://github.com/shenyushun/flask-socketio-doc-zh/blob/master/Flask-SocketIO%E4%B8%AD%E6%96%87%E6%96%87%E6%A1%A3.md)

### 登录
1. 支持 oauth2 登录
2. 如果是 oauth2 登录，则需要绑定邮箱

### 注销
用户选择注销账户，则提示备份数据（可以主动备份并发送给用户）

### 权限控制

一种保护 API 的方式：
[python - flask: how to bridge front-end with back-end service to render api authentication? - Stack Overflow](https://stackoverflow.com/questions/61329021/flask-how-to-bridge-front-end-with-back-end-service-to-render-api-authenticatio)

[最好的权限设计，是先区分功能权限和数据权限 | 人人都是产品经理](http://www.woshipm.com/pd/2889402.html)

[产品注册&登录设计，需要注意的 23 条规则 | 人人都是产品经理](http://www.woshipm.com/pd/1483348.html)

[后台经验分享：如何做权限管理系统设计 | 人人都是产品经理](http://www.woshipm.com/pd/835248.html)

[大家心心念念的权限管理功能，这次安排上了！](https://juejin.cn/post/6844904067525771272)

[如何从零开始设计权限管理系统 | Echo Blog](https://houbb.github.io/2020/09/17/how-to-design-privilege-system#%E4%BC%A0%E7%BB%9F-rbac-%E7%9A%84%E4%B8%8D%E8%B6%B3)

[常见权限系统设计模型分析（DAC，MAC，RBAC，ABAC） - 简书](https://www.jianshu.com/p/ce0944b4a903)

[可能是史上最全的权限系统设计 - 知乎](https://zhuanlan.zhihu.com/p/73414693)

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

