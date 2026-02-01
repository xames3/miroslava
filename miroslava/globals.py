"""\
Miroslava's  Proxies
====================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 28 January, 2026
Last updated on: 31 January, 2026

This module implements a proxy object thats delegates operations to
another context-local objects. This implementation supports
`contextvars`, allowing it to work in both threaded and asynchronous
environments.
"""

from __future__ import annotations

import threading
import typing as t
from contextvars import ContextVar
from operator import attrgetter

from miroslava.utils import set_module

if t.TYPE_CHECKING:
    from collections.abc import Iterator
    from contextvars import Token
    from types import TracebackType

    from miroslava.app import Miroslava
    from miroslava.wrappers import Request

T = t.TypeVar("T")
type WSGIEnvironment = dict[str, t.Any]
type SessionMixin = dict[str, t.Any]


@set_module("miroslava.local")
class LocalStack[T](threading.local):
    """Create a stack that stores data unique to each thread."""

    def __init__(self) -> None:
        """Initialise an instance with empty storage."""
        self._storage: list[T] = []

    @property
    def top(self) -> T | None:
        """Return the topmost context oon the storage stack."""
        if self._storage:
            return self._stack[-1]
        return None

    def push(self, obj: T) -> None:
        """Push a new context onto the storage stack."""
        self._storage.append(obj)

    def pop(self) -> T | None:
        """Remove the topmost context from the storage stack."""
        if self._storage:
            return self._storage.pop()
        return None


def _identity[T](o: T) -> T:
    """Return itself."""
    return o


def _get_name[T](obj: T, name: str) -> T:
    """Wrapper function for object."""
    return getattr(obj, name)


@set_module("miroslava.local")
class LocalProxy[T]:
    """Proxy that redirects operations to the object stored in a
    `ContextVar`.

    :param local: The context-local object that provies the proxied
        object.
    :param name: If provided, the proxy will access this attributes on
        the object retrieved from the context variable, defaults to
        `None`.
    :param unbound_message: Error message if the context variable is
        empty, defaults to `None`.
    """

    _get_current_object: t.ClassVar[t.Callable[[], T]]

    def __init__(
        self,
        local: ContextVar[T] | LocalStack[T] | t.Callable[[], T],
        name: str | None = None,
        *,
        unbound_message: str | None = None,
    ) -> None:
        """Initialise a proxy object."""
        get_name = _identity if name is None else attrgetter(name)
        if unbound_message is None:
            unbound_message = "object is not bound"
        if isinstance(local, LocalStack):

            def _get_current_object() -> T:
                obj = local.top
                if obj is None:
                    raise RuntimeError(unbound_message)
                return get_name(obj)

        elif isinstance(local, ContextVar):

            def _get_current_object() -> T:
                try:
                    obj = local.get()
                except LookupError:
                    raise RuntimeError(unbound_message) from None
                return get_name(obj)

        elif callable(local):

            def _get_current_object() -> T:
                return get_name(local())

        else:
            raise TypeError(f"Don't know how to proxy: {type(local)!r}")
        object.__setattr__(self, "_Local__wrapped", local)
        object.__setattr__(self, "_get_current_object", _get_current_object)

    def __repr__(self) -> str:
        """Human-readable representation of the proxy object."""
        try:
            obj = self._get_current_object()
        except RuntimeError:
            return f"<{type(self).__name__} unbound>"
        return repr(obj)

    def __bool__(self) -> bool:
        """Boolean status of the proxy object."""
        try:
            return bool(self._get_current_object())
        except RuntimeError:
            return False

    def __getattr__(self, name: str) -> t.Any:
        """Perform attribute access on the real object."""
        return getattr(self._get_current_object(), name)

    def __setattr__(self, name: str, value: t.Any) -> None:
        """Set attribute on to the real object."""
        setattr(self._get_current_object(), name, value)

    def __delattr__(self, name: str) -> None:
        """Delete attribute from the real object."""
        delattr(self._get_current_object(), name)


@set_module("miroslava.ctx")
class _AppCtxGlobals:
    """A fake plain object, used as a namespace for storing data
    during the application context.

    This is what the global `g` object resolves to. You can store any
    data here, and it'll persist for the duration of one request.
    """

    def get(self, name: str, default: t.Any | None = None) -> t.Any:
        """Get an attribute by name, or a default value."""
        return self.__dict__.get(name, default)

    def pop(self, name: str, default: t.Any | None = None) -> t.Any:
        """Get and remove an attribute by name."""
        return self.__dict__.pop(name, default)

    def __contains__(self, item: str) -> bool:
        """Implement membership check."""
        return item in self.__dict__

    def __iter__(self) -> Iterator[str]:
        """Implement iterator protocol."""
        return iter(self.__dict__)


@set_module("miroslava.ctx")
class AppContext:
    """The main application context.

    This class contains the active application instance and the
    application-specific global `g` information

    :param app: Application instance.
    """

    def __init__(self, app: Miroslava) -> None:
        """Initialise an application-specific context."""
        self.app = app
        self.g: _AppCtxGlobals = _AppCtxGlobals()
        self._cv_tokens: list[Token[AppContext]] = []

    def push(self) -> None:
        """Push the context to the current context variable."""
        self._cv_tokens.append(_cv_app.set(self))

    def pop(self) -> None:
        """Pop the context."""
        _cv_app.reset(self._cv_tokens.pop())


@set_module("miroslava.ctx")
class RequestContext:
    """The internal request context.

    This class contains the request-specific data. It's created at the
    begining of the request and pished to the `_cv_request` context
    variable.

    :param app: Miroslava's app instance.
    :param environ: WSGI environment created by the server. Currently,
        this is not being used.
    :param request: Request data to hold in, defaults to `None`.
    :param session: Simplified fake session, defaults to `None`.
    """

    def __init__(
        self,
        app: Miroslava,
        environ: WSGIEnvironment,
        request: Request | None = None,
        session: SessionMixin | None = None,
    ) -> None:
        """Initialise a request context with proper data."""
        self.app = app
        if request is None:
            request = app.request_class(environ)
        self.request: Request = request
        self.session: SessionMixin | None = session
        self._cv_tokens: list[
            tuple[Token[RequestContext], AppContext | None]
        ] = []

    def push(self) -> None:
        """Push the context to the current context variable."""
        self._cv_tokens.append(_cv_request.set(self))

    def pop(self) -> None:
        """Pop the context."""
        _cv_request.reset(self._cv_tokens.pop())

    def __enter__(self) -> t.Self:
        """Allow using like a context-manager."""
        self.push()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Allow using like a context-manager."""
        self.pop()


_no_app_msg = """\
Working outside of application context.

This typically means that you're attempting to use some functionality which is
intended to interface with the current application in some way.
"""

_cv_app: ContextVar[AppContext] = ContextVar("miroslava.app_ctx")
app_ctx: AppContext = LocalProxy(_cv_app, unbound_message=_no_app_msg)
current_app: Miroslava = LocalProxy(_cv_app, "app", unbound_message=_no_app_msg)
g: _AppCtxGlobals = LocalProxy(_cv_app, "g", unbound_message=_no_app_msg)

_no_req_msg = """\
Working outside of request context.

This means you're attempting something that is intended to interface with the
current application object in some way.
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
