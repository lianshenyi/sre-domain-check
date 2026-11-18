# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, absolute_import, division


def register_app_routers(app, routers, methods=('POST', 'GET')):
    """注册路由函数"""
    for url, func in routers.items():
        app.add_url_rule(url, None, func, methods=methods)
