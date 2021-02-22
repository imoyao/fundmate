---
title: 自定义RESTAPI的处理
---

## 自定义RESTAPI的处理

现存的框架比较知名的有django-rest-framework和flask-restapi，但是这些框架我都不太满意，而对于我这个项目用它们还太重了。好吧，手动写一个实现。首先是借用 DispatcherMiddleware 实现对/j这样的路径特殊处理（[commentbox/app.py at master · dongweiming/commentbox · GitHub](https://github.com/dongweiming/commentbox/blob/master/app.py class=)）：

    from werkzeug.wsgi import DispatcherMiddleware                                                                     
    
    
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, OrderedDict((                                                
            ('/j', json_api),                                                                                          
    )))  
    

我希望/j开头的返回的响应都是json格式的内容：

    from flask import Flask
    
    
    class ApiFlask(Flask):                                                                                             
        def make_response(self, rv):                                                                                   
            if isinstance(rv, dict):                                                                                   
                if 'r' not in rv:                                                                                      
                    rv['r'] = 1                                                                                        
                rv = ApiResult(rv)                                                                                     
            if isinstance(rv, ApiResult):                                                                              
                return rv.to_response()                                                                                
            return Flask.make_response(self, rv)                                                                       
                                                                                                                       
                                                                                                                       
    json_api = ApiFlask(__name__)         
    

其中返回了一个额外的字段r, 如果是0表示响应的结果是正确的，为1表示响应的内容有问题。

接着我们自定义错误处理的方式，比如404返回这样：

    {
        message: "Not Found"
    }

怎么实现呢：

    from flask import json                                                                                             
    from werkzeug.wrappers import Response                                                                                                                                                                                               
                                                                                                                  
                                                                                                                       
    class ApiResult(object):                                                                                           
        def __init__(self, value, status=200):                                                                         
            self.value = value                                                                                         
            self.status = status                                                                                       
        def to_response(self):                                                                                         
            return Response(json.dumps(self.value),                                                                    
                            status=self.status,                                                                        
                            mimetype='application/json')                                                               
                                                                                                                                                                   
                                                                                                                       
    class ApiException(Exception):                                                                                     
        def __init__(self, message, status=400):                                                                       
            self.message = message                                                                                     
            self.status = status                                                                                       
        def to_result(self):                                                                                           
            return ApiResult({'message': self.message, 'r': 1},                                                        
                             status=self.status)
    
    
    @json_api.errorhandler(ApiException)                                                                               
    def api_error_handler(error):                                                                                      
        return error.to_result()                                                                                       
                                                                                                                       
                                                                                                                       
    @json_api.errorhandler(403)                                                                                        
    @json_api.errorhandler(404)                                                                                        
    @json_api.errorhandler(500)                                                                                        
    def error_handler(error):                                                                                          
        if hasattr(error, 'name'):                                                                                     
            msg = error.name                                                                                           
            code = error.code                                                                                          
        else:                                                                                                          
            msg = error.message                                                                                        
            code = 500                                                                                                 
        return ApiResult({'message': msg}, status=code)  
    

而且响应也被封装了：

    def success(res=None, status_code=200):                                                                            
        res = res or {}                                                                                                
                                                                                                                       
        dct = {                                                                                                        
            'r': 1                                                                                                     
        }                                                                                                              
                                                                                                                       
        if res and isinstance(res, dict):                                                                              
            dct.update(res)                                                                                            
                                                                                                                       
        return ApiResult(dct, status_code)                                                                             
                                                                                                                       
                                                                                                                       
    def failure(message, status_code):                                                                                 
        dct = {                                                                                                        
            'r': 0,                                                                                                    
            'status': status_code,                                                                                     
            'message': message                                                                                         
        }                                                                                                              
        return dct                                                                                                     
                                                                                                                       
                                                                                                                       
    def updated(res=None):                                                                                             
        return success(res=res, status_code=204)                                                                       
                                                                                                                       
                                                                                                                       
    def bad_request(message, res=None):                                                                                
        return failure(message, 400)
    

使用的时候可以让返回的正确和错误结果的格式都保持统一。

### API 规范

由于 Flask 本身的灵活性，社区中涌现出了一些便捷开发 Flask Restful API 的框架，其中包括 `flask-restful`，`flask-restplus` 等。就 Flask 本身而言，我们觉得它对于API 的粒度控制不够好，因此我们提供了一个 `红图` 的机制来帮助我们细粒度的控制API。相较于 `flask-restful`，`flask-restplus` 这些框架而言，红图更注重**小**与**轻**。红图的源代码如下：
```python
class Redprint:
 def __init__(self, name, with_prefix=True):
     self.name = name
     self.with_prefix = with_prefix
     self.mound = []
 def route(self, rule, **options):
     def decorator(f):
         self.mound.append((f, rule, options))
         return f
     return decorator
 def register(self, bp, url_prefix=None):
     if url_prefix is None and self.with_prefix:
         url_prefix = '/' + self.name
     else:
         url_prefix = ''
     for f, rule, options in self.mound:
         endpoint = self.name + '+' + options.pop("endpoint", f.__name__)
         if rule:
             url = url_prefix + rule
             bp.add_url_rule(url, endpoint, f, **options)
         else:
             bp.add_url_rule(url_prefix, endpoint, f, **options)
```

红图本身只有 24 行代码，极易学习和掌握，它的作用并非去控制 API，而是做一个纽带将细粒度的 API 传递到相应的蓝图（Flask 自带的机制）中。因此红图的书写方式几乎与蓝图保持一致，相较于其它 API 开发方式，你几乎不需要任何学习成本。

一般的，我们推荐你在一类 API 中新建一个红图（如 Book 这一类，它负责与图书相关的API）。如下：
```python
 # book.py
 book_api = Redprint('book') # 创建book红图
 @book_api.route('/<id>', methods=['GET'])
 def get_book(id):
     book = Book.query.filter_by(id=id).first()
     if book is None:
         raise NotFound(msg='没有找到相关书籍')
     return jsonify(book)
```

如果你熟悉 Flask，你会发现这几乎与 Flask 的标准开发方式一样。新建红图时，你需传入红图的名称，如`book`，而后红图会自己在访问的 url 中加入`/book`前缀。

在 Flask 的开发中，几乎都会墨守成规的使用_装饰器_来优雅的书写视图函数，我们承袭了这一特点，也希望你能够喜欢。


### 异常处理规范

提起异常，大多时候我们都并不想碰见，因为它经常会与程序 crash 一起出现。但它确实又是程序中不可或缺的一部分，在 Lin 中我们默认集成了全局异常处理机制。因此不论你程序出现何种异常，都将会返回固定格式的提示信息给前端。对于前端来说，这是非常友好的一种交互。

在 Lin 的源码中关于异常处理的代码如下：
```python
def handle_error(self, app):
    @app.errorhandler(Exception)
    def handler(e):
        if isinstance(e, APIException):# 已知的自定义异常直接返回
            return e
        if isinstance(e, HTTPException): # 未知的http异常，取信息再以特定的格式返回
            code = e.code
            msg = e.description
            error_code = 1007
            return APIException(msg, code, error_code)
        else:
            if not app.config['DEBUG']:
                return UnknownException() # 未定义异常，返回未知异常
            else:
                raise e
```

熟悉 Flask 的肯定知道，这就是 Flask 处理异常的方式。在项目开发中我们强力推荐，甚至可以说是**要求**你在开发的过程中，关于某一类的异常一定要通过继承`APIException`的方式来自定义，这会让前后端的交互更加友好。

当然，当你每自定义一个异常后，别忘记在根目录下的`code.md`中记录相关异常的error\_code 和 msg，方便前端查阅和团队协作。


## 参考链接
- [使用 Flask 设计 RESTful APIs — Designing a RESTful API with Python and Flask 1.0 documentation](http://www.pythondoc.com/flask-restful/index.html) TODO
- [flask - 项目结构及开发规范 - 《Lin CMS 文档手册》 - 书栈网 · BookStack](https://www.bookstack.cn/read/Lin-CMS/2227eb2232b6e6d3.md#API%20%E8%A7%84%E8%8C%83)
- [Flask最佳实践 - 知乎](https://zhuanlan.zhihu.com/p/22774028)