---
title: 使用 Flask-Admin 增加后台管理界面
---
## Flask-Admin 后台管理

Flask-Admin 是一个简单易用的 Flask 扩展，让你可以很方便并快速地为 Flask 应用程序增加管理界面。

### 上手

先用 pip 安装 flask-admin 扩展

```plain
pip install flask-admin 
```

初始化

```python
from flask import Flask

from flask_admin import Admin, BaseView, expose

app = Flask(__name__)

admin = Admin(app[,name=u'后台管理系统'])

app.run()

```

访问[http://localhost:5000/admin/](http://localhost:5000/admin/)就可以看到一个简单的 Home 页面，其中 name 为自定义系统名，会显示在导航栏上

![](https://upload-images.jianshu.io/upload_images/3645027-950445e715de63fb.png?imageMogr2/auto-orient/strip|imageView2/2/w/465/format/webp)

后台

### 增加视图

在之前代码上增加

```plain
from flask import Flask
from flask.ext.admin import Admin, BaseView, expose

class MyView(BaseView):
    @expose('/')
    def index(self):
        return self.render('index.html')

app = Flask(__name__)

admin = Admin(app)
admin.add_view(MyView(name='Hello'))

app.run()
```
    

在 templates 下写模板文件 index.html

```plain
{% extends 'admin/master.html' %}   #为了保持一致，继承admin/master.html模板

{% block body %}

欢迎来到后台管理系统！

{% endblock %}
```
    

这里采用的模板语言为 Jinjia2，查看[Jinjia2 文档](https://link.jianshu.com?t=http://docs.jinkan.org/docs/jinja2/)

### 增加数据库模型视图

这是 Flask-Admin 很方便的一个部分，只需要很少的代码，就可以为某个数据库模型实现管理视图，这里采用 Flask-SQLAlchemy 作为 ORM 后端

```plain
from flask_admin.contrib.sqla import ModelView

# 在这里初始化Flask Flask-SQLAlchemy Flask-Admin

admin.add_view(ModelView(User, db.session))

```

模型视图例子

注:右上角加了管理员登录

不过网页默认显示全是英文，需要汉化处理，Flask-Admin 自带国际化，所以中文显示也很方便

### 用 Flask-BabelEx 做国际化

```plain
from flask_babelex import Babel

app = Flask(__name__)

babel = Babel(app)

app.config['BABEL_DEFAULT_LOCALE'] = 'zh_CN'
```
    

然后运行，很方便就可以以中文显示，如果改成其他语言也非常方便

中文显示

### 定制数据库模型视图

```plain
class UserView(ModelView):

#这三个变量定义管理员是否可以增删改，默认为True

can_delete = False

can_edit = False

can_create = False

#这里是为了自定义显示的column名字

column_labels = dict(

username=u'用户名',

)

#如果不想显示某些字段，可以重载这个变量

column_exclude_list = (

'password_hash',

)

# 只需把自己写的处理模型的视图加进去就行了，category是可选的目录

admin.add_view(UserView(User, db.session, name=u'信息', category=u'用户'))
```
    

更多可定制选项见[flask\_admin.model 文档](https://link.jianshu.com?t=http://flask-admin.readthedocs.io/en/latest/api/mod_model/?module-flask_admin.model)

### 用 Flask-Login 做身份验证

管理员系统不能是开放的，应该做一下身份验证，我这里用 Flask-Login 做身份验证

这里比较复杂一点，首先要定制 templates 下的模板文件 index.html

实现管理员登录带有 CSRF 令牌的安全表单

```text
    {% extends 'admin/master.html' %}
    
    {% block body %}
    
    {{ super() }}
    
    {% if current_user.is_authenticated %}

    
    欢迎来到后台管理系统！
    
    {% else %}
    
    {{ form.hidden_tag() if form.hidden_tag }}
    
    {% for f in form if f.type != 'CSRFTokenField' %}
    
    {{ f.label }}
    
    {{ f }}
    
    {% if f.errors %}
    
    {% for e in f.errors %}
    
    {{ e }}
    
    {% endfor %}
    
    {% endif %}
    
    {% endfor %}
    
    登陆
    
    {{ link | safe }}
    
    {% endif %}
    
    {% endblock body %}
    
```

处理管理员登录

```python
    #这里的fields和validators是用的Flask-WTForm
    
    from wtforms import fields, validators
    
    class LoginForm(FlaskForm):
    
        login = fields.StringField(label=u'管理员账号', validators=[validators.required()])
        
        password = fields.PasswordField(label=u'密码', validators=[validators.required()])
    
    def validate_login(self, field):
        
        user = self.get_user()
    
    if user is None:
    
        raise validators.ValidationError(u'账号不存在')
        
        #这里密码不能明文存储，我用sha256_crypt加密
    
        if not sha256_crypt.verify(self.password.data, user.password):
        
            raise validators.ValidationError(u'密码错误')
        
    def get_user(self):
        
        #AdminUser是存储管理员用户密码的表
        
        return db.session.query(AdminUser).filter_by(login=self.login.data).first()
```
    

安装 flask-login

```plain
pip install flask-login
    
```

初始化，调用 `init_login()`函数即可

```python
    from flask_login import current_user, login_user, logout_user, LoginManager
    
    def init_login():
    
        login_manager = LoginManager()
        
        login_manager.init_app(app)
        
        @login_manager.user_loader
        
        def load_user(user_id):
        
        return db.session.query(AdminUser).get(user_id)
```
    

然后在需要管理员权限的才能看到的视图中添加代码
```python
    
    # 决定身份验证可见
    
    def is_accessible(self):
        return current_user.is_authenticated
    
```

### 管理上传文件和图片

文件上传，很简单的调用 FileAdmin 即可
```python

from flask_admin.contrib.fileadmin import FileAdmin

import os.path as op

file_path = op.join(op.dirname(__file__), 'static')

admin.add_view(FileAdmin(file_path, '/static/', name='文件'))

```


假设 pics 为需要上传图片的字段

```plain
form_extra_fields = {

'pics': upload.ImageUploadField(label=u图片',

base_path=file_path),

}
```
    

![](https://cdn.jsdelivr.net/gh/masantu/statics/images/3645027-cb1843f09c795103.png)

### 参考
1. [Flask-Admin 后台管理介绍 - 简书](https://www.jianshu.com/p/aef7bbdf74fa)
2. [Flask-Admin 文档 Quick Start](https://link.jianshu.com?t=http://flask-admin.readthedocs.io/en/v1.0.9/quickstart/)
3. [flask-admin](http://examples.flask-admin.org/)
4. [Flask-Admin 中文入门教程](https://link.jianshu.com?t=http://flask123.sinaapp.com/article/57/)
5. [Flask-admin 使用经验技巧总结 - 傻白甜++ - 博客园](https://www.cnblogs.com/feifeifeisir/p/12858367.html)