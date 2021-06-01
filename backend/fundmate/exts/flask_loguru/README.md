
logging42
=========

A configuration for the loguru ([https://github.com/Delgan/loguru](https://github.com/Delgan/loguru)) logger.

It is important that it be the first import to run so the standard logging basicConfig method has an effect.

Features
--------

*   Stderr output
*   intercepted logging from client libraries
*   Disabled better exceptions for log levels above debug to mitigate secret leaking
*   Configuration retriever which safely logs retrieved values

Installation
------------
```bash
pip install logging42
```

Examples
--------
```python
# base.py

from flask_loguru import logger

logger.debug('hello world)
```
## 原地址
[logging42 · PyPI](https://pypi.org/project/logging42/)