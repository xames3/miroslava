"""\
Miroslava's Application
=======================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 31 January, 2026
Last updated on: 31 January, 2026

The main application class that ties together routing, configuration,
and the server loop. The main `Miroslava` class implemented in this
module actually implements the WSGI interface (at least conceptually)
and provides the `route` decorator, which is the hallmakr of the Flask
API.

It includes a built-in development server based on `socket` for
immediate use.
"""

from __future__ import annotations

import os
import sys
import typing as t

from miroslava.utils import DefaultJSONProvider
from miroslava.utils import get_root_path
from miroslava.wrappers import Response

if t.TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Sequence

    from miroslava.wrappers import Headers

type ResponseValue = (
    "Response" | str | bytes | list[t.Any] | Mapping[str, t.Any]
)
type HeaderValue = str | list[str] | tuple[str, ...]
type HeadersValue = (
    "Headers" | Mapping[str, HeaderValue] | Sequence[tuple[str, HeaderValue]]
)
type ResponseReturnValue = (
    ResponseValue
    | tuple[ResponseValue, HeadersValue]
    | tuple[ResponseValue, int]
    | tuple[ResponseValue, int, HeadersValue]
)
RouteCallable = t.Callable[..., ResponseReturnValue]
T_route = t.TypeVar("T_route", bound=RouteCallable)


class Scaffold:
    """Base class for a Miroslava application.

    :param import_name: Usually the name of the module where this
        object is defined.
    :param static_folder: Path to a folder of static files to serve,
        defaults to `None`.
    :param static_url_path: URL prefix for the static route, defaults
        to `None`.
    :param template_folder: Path to a folder containing template files,
        defaults to `None`.
    :param root_path: Relative path to the static, template, and the
        resources directories, defaults to `None`.

    .. note::

        This class is supposed to be extended to add more
        functionality. However, there's absolutely no need for having
        this base class, but for the sake of simplicity, I'm separating
        it from rest of the implementation.
    """

    name: str

    def __init__(
        self,
        import_name: str,
        static_folder: str | os.PathLike[str] | None = "static",
        static_url_path: str | None = None,
        template_folder: str | os.PathLike[str] | None = "templates",
        root_path: str | None = None,
    ) -> None:
        """Initialise the base scaffolding for the app with paths."""
        self.import_name = import_name
        self.static_folder = static_folder
        self.static_url_path = static_url_path
        self.template_folder = template_folder
        if root_path is None:
            root_path = get_root_path(self.import_name)
        self.root_path = root_path
        self.view_functions: dict[str, RouteCallable] = {}

    def __repr__(self) -> str:
        """Human-readable representation of the application object."""
        return f"<{type(self).__name__} {self.name!r}>"

    def route(
        self,
        rule: str,
        **options: t.Any,
    ) -> t.Callable[[T_route], T_route]:
        """Decorator that is used to register a view function for a
        given URL rule.
        """

        def decorator(f: T_route) -> T_route:
            endpoint = options.pop("endpoint", None)
            self.add_url_rule(rule, endpoint, f, **options)
            return f

        return decorator

    def _method_route(
        self,
        method: str,
        rule: str,
        options: dict[str, t.Any],
    ) -> t.Callable[[T_route], T_route]:
        """Route different protocol methods."""
        return self.route(rule, methods=[method], **options)

    def get(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route `GET` methods."""
        return self._method_route("GET", rule, **options)

    def post(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route `POST` methods."""
        return self._method_route("POST", rule, **options)

    def put(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route `PUT` methods."""
        return self._method_route("PUT", rule, **options)

    def delete(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route `DELETE` methods."""
        return self._method_route("DELETE", rule, **options)

    def patch(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route `PATCH` methods."""
        return self._method_route("PATCH", rule, **options)


class App(Scaffold):
    """Base application object which implements a WSGI application."""

    json_provider_class: type[DefaultJSONProvider] = DefaultJSONProvider
    default_config: t.ClassVar[dict[str, t.Any]] = {}
    response_class: type[Response] = Response

    def __init__(
        self,
        import_name: str,
        static_url_path: str | None = None,
        static_folder: str | os.PathLike[str] | None = "static",
        static_host: str | None = None,
        host_matching: bool = False,
        subdomain_matching: bool = False,
        template_folder: str | os.PathLike[str] | None = "templates",
        instance_path: str | None = None,
        instance_relative_config: bool = False,
        root_path: str | None = None,
    ) -> None:
        """Initialise the application instance."""
        super().__init__(
            import_name=import_name,
            static_folder=static_folder,
            static_url_path=static_url_path,
            template_folder=template_folder,
            root_path=root_path,
        )
        self.instance_path = instance_path
        self.config = self.make_config(instance_relative_config)
        self.json: DefaultJSONProvider = self.json_provider_class
        self.subdomain_matching = subdomain_matching
        self.static_host = static_host
        self.host_matching = host_matching

    @property
    def name(self) -> str:
        """Name of the application."""
        if self.import_name == "__main__":
            fn: str | None = getattr(sys.modules["__main__"], "__file__", None)
            if fn is None:
                return "__main__"
            return os.path.splitext(os.path.basename(fn))[0]
        return self.import_name

    def add_url_rule(
        self,
        rule: str,
        endpoint: str | None = None,
        view_func: RouteCallable | None = None,
        provide_automatic_options: bool | None = None,
        **options: t.Any,
    ) -> None:
        """Register a rule for routing incoming requests and building
        URLs.

        :param rule: URL rule string.
        :param endpoint: The endpoint name to associate the rule and a
            view function, defaults to `None`.
        :param view_func: Function to associate with the endpoint
            name, defaults to `None`.
        :param provide_automatic_options: Ignored in this case, have
            intentionally defaulted to `None`.
        """
        if endpoint is None:
            endpoint = view_func.__name__ or rule
        options["endpoint"] = endpoint
        methods = options.pop("methods", None)
        if methods is None:
            methods = ("GET",)
        methods = {method.upper() for method in methods}
        if provide_automatic_options is None and "OPTIONS" not in methods:
            provide_automatic_options = True
        if view_func is not None:
            self.view_functions[endpoint] = view_func

    def make_config(self, instance_relative: bool = False) -> dict[str, t.Any]:
        """Make configuration to be used by the instance."""
        if instance_relative:
            self.root_path = self.instance_path
        defaults = dict(self.default_config)
        defaults["DEBUG"] = os.environ.get("MIROSLAVA_DEBUG", False)
        return defaults

    @property
    def debug(self) -> bool:
        """Return `True` if the app is running in debug mode."""
        return self.config["DEBUG"]

    @debug.setter
    def debug(self, value: bool) -> None:
        """Set debug value."""
        self.config["DEBUG"] = value


class Miroslava(App):
    """Main class which implements a WSGI application."""

    pass
