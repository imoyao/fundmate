---
title: 前后端分离项目中使用 github-action
---
## 如何在子目录运行 action

- [github - Running actions in another directory - Stack Overflow](https://stackoverflow.com/questions/58139175/running-actions-in-another-directory)

```yml
name: CI

on: [push]

jobs:
  phpunit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v1
      - name: Setup and run tests
        working-directory: ./app
        run: |
          cp .env.dev .env
          composer install --prefer-dist
          php bin/phpunit
```
