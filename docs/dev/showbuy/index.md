

## 使用 Ruff 替代 isort 和 yapf 这两个工具
``
# 安装
pdm add -d ruff

# 检查和自动修复
pdm run ruff check --fix .
# 仅格式化
pdm run ruff format .
```

## 后端启动
```
cd backend
pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000
```
然后访问`http://192.168.0.109:8000/docs` 查看目前可用api。
