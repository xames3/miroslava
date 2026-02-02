"""\
Miroslava's Globals
===================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 28 January, 2026
Last updated on: 02 February, 2026

This module exposes the global proxies. Each proxy uses ``contextvars``
to resolve to the appropriate object for the active request or
application context.

.. note::

    Attempting to access a proxy outside its required context raises a
    clear ``RuntimeError`` message to aid debugging.
"""

from __future__ import annotations

import typing as t
from contextvars import ContextVar

from miroslava.local import LocalProxy

if t.TYPE_CHECKING:
    from miroslava.app import Miroslava
    from miroslava.ctx import AppContext
    from miroslava.ctx import RequestContext
    from miroslava.ctx import _AppCtxGlobals
    from miroslava.wrappers import Request

type SessionMixin = dict[str, t.Any]

_no_app_msg = """\
Working outside of application context.

This means that you attempted to use functionality that needed to
interface with the current application object. Create an application
context with app.app_context() before accessing this proxy.
"""

_cv_app: ContextVar[AppContext] = ContextVar("miroslava.app_ctx")
app_ctx: AppContext = LocalProxy(_cv_app, unbound_message=_no_app_msg)
current_app: Miroslava = LocalProxy(_cv_app, "app", unbound_message=_no_app_msg)
g: _AppCtxGlobals = LocalProxy(_cv_app, "g", unbound_message=_no_app_msg)

_no_req_msg = """\
Working outside of request context.

This means that you attempted to use functionality that needed an
active HTTP request. Establish a request context before accessing this
proxy.
"""

_cv_request: ContextVar[RequestContext] = ContextVar("miroslava.request_ctx")
request_ctx: RequestContext = LocalProxy(
    _cv_request, unbound_message=_no_req_msg
)
request: Request = LocalProxy(
    _cv_request, "request", unbound_message=_no_req_msg
)
session: SessionMixin = LocalProxy(
    _cv_request, "session", unbound_message=_no_req_msg
)
