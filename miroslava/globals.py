"""\
Miroslava's Globals
===================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 28 January, 2026
Last updated on: 02 February, 2026

This module exposes the global proxies. Each proxy uses ``contextvars``
to resolve to the appropriate object for the active request or
application context. One of the proxy object is the ``LocalProxy``,
which forwards attribute and item access to an object stored in
a ``ContextVar`` or returned by a callable.

This design keeps globals like ``request`` or ``current_app`` safe
across threads and asynchronous tasks while preserving a natural
attribute-based API for developers.

Finally, it also has the ``AppContext``, which stores the application
instance and a namespace object for user data. While, the
``RequestContext`` stores the ``Request`` object and optional session
data. Each context is pushed to ``contextvars`` so access remains
isolated per thread or asynchronous task, mirroring Flask's context
management model.

.. note::

    Attempting to access a proxy outside its required context raises a
    clear ``RuntimeError`` message to aid debugging.
"""

from __future__ import annotations

import typing as t
from contextvars import ContextVar
from contextvars import Token
from operator import attrgetter

from miroslava.utils import set_module as m

if t.TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

    from miroslava.app import Miroslava
    from miroslava.wrappers import Request

T = t.TypeVar("T")
type SessionMixin = dict[str, t.Any]


@m("miroslava.ctx")
class _AppCtxGlobals:
    """Namespace object that stores arbitrary attributes."""

    def get(self, name: str, default: t.Any | None = None) -> t.Any:
        """Return an attribute value by name or a default."""
        return self.__dict__.get(name, default)

    def pop(self, name: str, default: t.Any | None = None) -> t.Any:
        """Remove and return an attribute value by name."""
        return self.__dict__.pop(name, default)

    def __contains__(self, item: str) -> bool:
        """Return ``True`` when an attribute is present."""
        return item in self.__dict__

    def __iter__(self) -> Iterator[str]:
        """Iterate over stored attribute names."""
        return iter(self.__dict__)


@m("miroslava.ctx")
class AppContext:
    """Application context carrying the app and a user namespace.

    It stores the application instance and a writable namespace ``g``
    that developers can attach arbitrary attributes to for the lifetime
    of the context. Context instances are pushed before handling a
    request and popped afterwards, keeping state contained to the
    active execution flow.

    :param app: Application instance.
    """

    def __init__(self, app: Miroslava) -> None:
        """Initialise the application context for the given app."""
        self.app = app
        self.g: _AppCtxGlobals = _AppCtxGlobals()
        self._cv_tokens: list[Token[AppContext]] = []

    def __enter__(self) -> t.Self:
        """Push context when entering a ``with`` block."""
        self.push()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Pop context when exiting a ``with`` block."""
        self.pop()

    def push(self) -> None:
        """Push the context to the current context variable stack."""
        self._cv_tokens.append(_cv_app.set(self))

    def pop(self) -> None:
        """Pop the context from the current context variable stack."""
        if self._cv_tokens:
            _cv_app.reset(self._cv_tokens.pop())


@m("miroslava.ctx")
class RequestContext:
    """Request context storing request and session state.

    It wraps the WSGI environment in a ``Request`` object, optionally
    accepts an existing request, and stores session data. Each
    ``RequestContext`` is pushed around request handling so global
    proxies like request and session resolve correctly for the
    active task.

    :param app: Application instance.
    :param environ: WSGI environment created by the server. This is
        currently unused.
    :param request: Request data to hold in, defaults to ``None``.
    :param session: Simplified fake session, defaults to ``None``.
    """

    def __init__(
        self,
        app: Miroslava,
        environ: dict[str, t.Any],
        request: Request | None = None,
        session: SessionMixin | None = None,
    ) -> None:
        """Initialise the request context for a WSGI environment."""
        self.app = app
        if request is None:
            request = app.request_class(environ)
        self.request: Request = request
        self.session: SessionMixin | None = session
        self._cv_tokens: list[Token[RequestContext]] = []

    def __enter__(self) -> t.Self:
        """Push context when entering a ``with`` block."""
        self.push()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Pop context when exiting a ``with`` block."""
        self.pop()

    def push(self) -> None:
        """Push the context to the current context variable stack."""
        self._cv_tokens.append(_cv_request.set(self))

    def pop(self) -> None:
        """Pop the context from the current context variable stack."""
        if self._cv_tokens:
            _cv_request.reset(self._cv_tokens.pop())


@m("miroslava.twerkzeug.local")
def _identity[T](o: T) -> T:
    """Return itself."""
    return o


@m("miroslava.twerkzeug.local")
class LocalProxy[T]:
    """Proxy that forwards operations to a context-local object.

    The proxy defers attribute and item access, iteration, truthiness,
    and callable behaviour to the underlying object looked up at access
    time.

    :param local: The context-local variable carrying the target object
        or a zero-argument callable returning it.
    :param name: Optional attribute (name) to fetch from the target
        object before returning, defaults to ``None``.
    :param unbound_message: Error text raised when the context is
        missing, defaults to ``None``.
    """

    __slots__: tuple[str, str] = ("__get_current_object", "__wrapped")

    def __init__(
        self,
        local: ContextVar[T] | t.Callable[[], T],
        name: str | None = None,
        *,
        unbound_message: str | None = None,
    ) -> None:
        """Initialise the proxy wrapper."""
        get_name = _identity if name is None else attrgetter(name)
        if unbound_message is None:
            unbound_message = "object is not bound"

        def _get_current_object() -> T:
            if isinstance(local, ContextVar):
                try:
                    obj = local.get()
                except LookupError:
                    raise RuntimeError(unbound_message) from None
                return get_name(obj)
            return get_name(local())

        object.__setattr__(self, "_LocalProxy__wrapped", local)
        object.__setattr__(
            self, "_LocalProxy__get_current_object", _get_current_object
        )

    def __repr__(self) -> str:
        """Human-readable representation of the proxy object."""
        try:
            obj = self._get_current_object()
        except RuntimeError:
            return f"<{type(self).__name__} unbound>"
        return repr(obj)

    def __str__(self) -> str:
        """Delegate string conversion to the proxied object."""
        try:
            return str(self._get_current_object())
        except RuntimeError:
            return repr(self)

    def __getattr__(self, name: str) -> t.Any:
        """Delegate attribute access to the proxied object."""
        if name == "_get_current_object":
            return object.__getattribute__(
                self, "_LocalProxy__get_current_object"
            )
        return getattr(self._get_current_object(), name)

    def __setattr__(self, name: str, value: t.Any) -> None:
        """Delegate attribute setting to the proxied object."""
        setattr(self._get_current_object(), name, value)

    def __delattr__(self, name: str) -> None:
        """Delegate attribute deletion to the proxied object."""
        delattr(self._get_current_object(), name)

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> t.Any:
        """Delegate calling to the proxied object."""
        return self._get_current_object()(*args, **kwargs)

    def __getitem__(self, key: t.Any) -> t.Any:
        """Delegate item access to the proxied object."""
        return self._get_current_object()[key]

    def __setitem__(self, key: t.Any, value: t.Any) -> None:
        """Delegate item assignment to the proxied object."""
        self._get_current_object()[key] = value

    def __delitem__(self, key: t.Any) -> None:
        """Delegate item deletion to the proxied object."""
        del self._get_current_object()[key]

    def __iter__(self) -> t.Iterator[t.Any]:
        """Delegate iteration to the proxied object."""
        return iter(self._get_current_object())

    def __len__(self) -> int:
        """Delegate length queries to the proxied object."""
        return len(self._get_current_object())

    def __bool__(self) -> bool:
        """Delegate truthiness to the proxied object."""
        try:
            return bool(self._get_current_object())
        except RuntimeError:
            return False

    def __eq__(self, other: object) -> bool:
        """Compare equality against the proxied object."""
        try:
            return self._get_current_object() == other
        except RuntimeError:
            return False

    def _get_current_object(self) -> T:
        """Return the current object this proxy is pointing to."""
        return object.__getattribute__(
            self, "_LocalProxy__get_current_object"
        )()


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
