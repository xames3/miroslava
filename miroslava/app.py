"""\
Miroslava's Application
=======================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 31 January, 2026
Last updated on: 03 February, 2026

The primary application classes which ties together routing, configs,
and the server loop.

The ``Scaffold`` class exposes the routing decorators and URL rule
registration. The ``App`` extends the base scaffold with configuration,
JSON support, and response construction.

Miroslava provides a lightweight development server that accepts TCP
connections, parses HTTP requests into ``Request`` objects, applies
routing, and emits ``Response`` objects with minimal dependencies.
"""

from __future__ import annotations

import mimetypes
import os
import re
import socket
import sys
import threading
import typing as t
from collections.abc import Mapping
from datetime import datetime
from http import HTTPStatus
from urllib.parse import unquote

from miroslava.globals import AppContext
from miroslava.globals import RequestContext
from miroslava.utils import DefaultJSONProvider
from miroslava.utils import HTTPExceptionError
from miroslava.utils import Map
from miroslava.utils import Rule
from miroslava.utils import get_root_path
from miroslava.wrappers import Request
from miroslava.wrappers import Response

if t.TYPE_CHECKING:
    from collections.abc import Sequence

    from miroslava.wrappers import Headers

type HeaderValue = str | list[str] | tuple[str, ...]
type HeadersValue = (
    "Headers" | Mapping[str, HeaderValue] | Sequence[tuple[str, HeaderValue]]
)
type ResponseValue = Response | str | bytes | list[t.Any] | Mapping[str, t.Any]
type ResponseReturnValue = (
    ResponseValue
    | tuple[ResponseValue, HeadersValue]
    | tuple[ResponseValue, int]
    | tuple[ResponseValue, int, HeadersValue]
)
type WSGIEnvironment = dict[str, t.Any]
RouteCallable = t.Callable[..., ResponseReturnValue]
T_route = t.TypeVar("T_route", bound=RouteCallable)


class Scaffold:
    """Base class for a Miroslava application.

    :param import_name: Usually the name of the module where this
        object is defined.
    :param static_folder: Path to a folder of static files to serve,
        defaults to ``static``.
    :param static_url_path: URL prefix for the static route, defaults
        to ``None``.
    :param template_folder: Path to a folder containing template files,
        defaults to ``templates``.
    :param root_path: Relative path to the static, template, and the
        resources directories, defaults to ``None``.
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
        """Route ``GET`` methods."""
        return self._method_route("GET", rule, options)

    def post(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route ``POST`` methods."""
        return self._method_route("POST", rule, options)

    def put(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route ``PUT`` methods."""
        return self._method_route("PUT", rule, options)

    def delete(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route ``DELETE`` methods."""
        return self._method_route("DELETE", rule, options)

    def patch(
        self, rule: str, **options: t.Any
    ) -> t.Callable[[T_route], T_route]:
        """Route ``PATCH`` methods."""
        return self._method_route("PATCH", rule, options)

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
            view function, defaults to ``None``.
        :param view_func: Function to associate with the endpoint
            name, defaults to ``None``.
        :param provide_automatic_options: Add ``OPTIONS`` method,
            defaults to ``None``.
        """
        raise NotImplementedError


class App(Scaffold):
    """Base application object which implements a WSGI application.

    :param import_name: Name of the application package.
    :param static_url_path:  URL prefix for the static route, defaults
        to ``None``.
    :param static_folder: Path to a folder of static files to serve,
        defaults to ``static``.
    :param static_host: Host to use for adding static routes, defaults
        to ``None``.
    :param host_matching: Set the ``host_matching`` attribute, defaults
        to ``False``.
    :param subdomain_matching: Consider a subdomain when matching
        routes, defaults to ``False``.
    :param template_folder: Path to the folder containing templates,
        defaults to ``templates``.
    :param instance_path: Alternative instance path to the application,
        defaults to ``None``.
    :param instance_relative_config: If ``True``, use relative instance
        path instead of the application path, defaults to ``False``.
    :param root_path: Path to the root of application files, defaults
        to ``None``.
    """

    json_provider_class: type[DefaultJSONProvider] = DefaultJSONProvider
    default_config: t.ClassVar[dict[str, t.Any]]
    url_rule_class: Rule = Rule
    url_map_class: Map = Map
    response_class: type[Response]

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
        self.json = self.json_provider_class()
        self.subdomain_matching = subdomain_matching
        self.static_host = static_host
        self.host_matching = host_matching
        self.url_map = self.url_map_class()
        self.response_class: type[Response] = Response

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
        :param provide_automatic_options: Add ``OPTIONS`` method,
            defaults to ``None``.
        """
        converters: dict[str, t.Callable[[str], t.Any]] = {}
        if endpoint is None:
            endpoint = view_func.__name__ or rule
        methods = options.pop("methods", None)
        if methods is None:
            methods = ("GET",)
        methods = {method.upper() for method in methods}
        if provide_automatic_options is None and "OPTIONS" not in methods:
            provide_automatic_options = True
        defaults = options.pop("defaults", {}) or {}
        pattern = None
        if "<" in rule and ">" in rule:
            type_map = {"int": int, None: str}

            def _replace(match: re.Match[str]) -> str:
                type_name = match.group("type")
                name = match.group("name")
                converters[name] = type_map.get(type_name, str)
                if type_name == "int":
                    return f"(?P<{name}>\\d+)"
                return f"(?P<{name}>[^/]+)"

            pattern = re.compile(
                "^"
                + re.sub(
                    r"<(?:(?P<type>[a-zA-Z_][a-zA-Z0-9_]*)?:)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)>",
                    _replace,
                    rule,
                )
                + "$"
            )
        rule_obj = self.url_rule_class(rule, defaults, methods, endpoint)
        rule_obj.pattern = pattern
        rule_obj.converters = converters
        self.url_map.add(rule_obj)
        if view_func is not None:
            self.view_functions[endpoint] = view_func

    def make_response(self, rv: ResponseReturnValue) -> Response:
        """Convert a view return value into a ``Response`` instance.

        :param rv: Return value from a view function.
        :raises TypeError: If the return value shape cannot be
            understood.
        """
        status: int | str | HTTPStatus | None = None
        headers: HeadersValue | None = None
        body: ResponseValue = rv
        if isinstance(rv, tuple):
            if len(rv) == 3:
                body, status, headers = rv
            elif len(rv) == 2:
                body, second = rv
                if isinstance(second, (int, str, HTTPStatus)):
                    status = second
                else:
                    headers = second
            else:
                raise TypeError("A response tuple must be of length 2 or 3")
        if isinstance(body, self.response_class):
            response = body
            if status is not None:
                response.status_code, response.status_phrase = (
                    response._parse_status(status)
                )
        elif isinstance(body, (dict, list)):
            response = self.json.response(body)
            if status is not None:
                response.status_code, response.status_phrase = (
                    response._parse_status(status)
                )
        elif isinstance(body, (str, bytes)):
            response = self.response_class(body, status=status or 200)
        else:
            response = self.response_class(str(body), status=status or 200)
        if headers:
            if isinstance(headers, Mapping):
                for key, value in headers.items():
                    response.headers[key] = (
                        ", ".join(value)
                        if isinstance(value, (list, tuple))
                        else value
                    )
            else:
                for key, value in headers:
                    response.headers[key] = (
                        ", ".join(value)
                        if isinstance(value, (list, tuple))
                        else value
                    )
        return response

    def make_config(self, instance_relative: bool = False) -> dict[str, t.Any]:
        """Make configuration to be used by the instance."""
        if instance_relative:
            self.root_path = self.instance_path
        defaults = dict(self.default_config)
        defaults["DEBUG"] = os.environ.get("MIROSLAVA_DEBUG", False)
        return defaults

    @property
    def debug(self) -> bool:
        """Return ``True`` if the app is running in debug mode."""
        return self.config["DEBUG"]

    @debug.setter
    def debug(self, value: bool) -> None:
        """Set debug value."""
        self.config["DEBUG"] = value


class Miroslava(App):
    """Main class which implements a WSGI application.

    :param import_name: Name of the application package.
    :param static_url_path:  URL prefix for the static route, defaults
        to ``None``.
    :param static_folder: Path to a folder of static files to serve,
        defaults to ``static``.
    :param static_host: Host to use for adding static routes, defaults
        to ``None``.
    :param host_matching: Set the ``host_matching`` attribute, defaults
        to ``False``.
    :param subdomain_matching: Consider a subdomain when matching
        routes, defaults to ``False``.
    :param template_folder: Path to the folder containing templates,
        defaults to ``templates``.
    :param instance_path: Alternative instance path to the application,
        defaults to ``None``.
    :param instance_relative_config: If ``True``, use relative instance
        path instead of the application path, defaults to ``False``.
    :param root_path: Path to the root of application files, defaults
        to ``None``.
    """

    default_config: t.ClassVar[dict[str, t.Any]] = {
        "DEBUG": False,
        "APPLICATION_ROOT": "/",
        "SERVER_NAME": None,
    }
    request_class: type[Request] = Request
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
            static_url_path=static_url_path,
            static_folder=static_folder,
            static_host=static_host,
            host_matching=host_matching,
            subdomain_matching=subdomain_matching,
            template_folder=template_folder,
            instance_path=instance_path,
            instance_relative_config=instance_relative_config,
            root_path=root_path,
        )

    def run(
        self,
        host: str | None = None,
        port: int | None = None,
        debug: bool | None = None,
        load_dotenv: bool = False,
        **options: t.Any,
    ) -> None:
        """Run the application on a local development server.

        The method binds a TCP socket, listens for incoming HTTP
        requests, and delegates each connection to a worker thread.

        :param host: Hostname to bind to; falls back to ``SERVER_NAME``
            or ``127.0.0.1`` when omitted, defaults to ``None``.
        :param port: Port for the webserver; defaults to ``9001`` when
            not provided or derived from ``SERVER_NAME``, defaults
            to ``None``.
        :param debug: When ``True``, exceptions print full tracebacks
            and the debug flag is set in the configuration, defaults
            to ``None``.
        :param load_dotenv: Included for API compatibility; unused but
            retained, defaults to ``False``.
        """
        _ = load_dotenv
        _ = options
        if debug is not None:
            self.debug = bool(debug)
        server_name = self.config.get("SERVER_NAME")
        sn_host = None
        sn_port = None
        if server_name:
            sn_host, _, sn_port = server_name.partition(":")

        if not host:
            host = sn_host if sn_host else "127.0.0.1"

        if port or port == 0:
            port = int(port)
        elif sn_port:
            port = int(sn_port)
        else:
            port = 9001

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((host, port))
        except OSError as err:
            print(f"Couldn't bind to {host}:{port} due to {err}")
            return
        server.listen(5)
        print(f" * Serving Miroslava app {self.name!r}")
        print(f" * Debug mode: {'on' if debug else 'off'}")
        print(f" * Running on http://{host}:{port}/\nPress CTRL+C to quit")
        try:
            while True:
                client, client_address = server.accept()
                threading.Thread(
                    target=self.handle_client,
                    args=(client, client_address),
                    daemon=True,
                ).start()
        except KeyboardInterrupt:
            pass
        finally:
            server.close()

    def handle_client(
        self,
        client: socket.socket,
        client_address: tuple[str, int],
    ) -> None:
        """Handle incoming request by dispatching.

        This method reads the raw request bytes from the socket,
        constructs a WSGI-style environment mapping, and instantiates a
        Request object. It then sets up the application and request
        contexts, dispatches the request to a view function, logs the
        outcome, and finally sends the resulting Response back to the
        client. Errors are reported to stdout, and tracebacks are shown
        when debug mode is enabled.

        :param client: The client socket connection.
        :param client_address: The client address tuple (host, port).
        """
        try:
            buffer = b""
            while b"\r\n\r\n" not in buffer:
                chunk = client.recv(1024)
                if not chunk:
                    break
                buffer += chunk
            if b"\r\n\r\n" not in buffer:
                return
            headers_data, body_data = buffer.split(b"\r\n\r\n", 1)
            environ = self.make_environ(headers_data)
            cl = environ.get("CONTENT_LENGTH")
            if cl:
                length = int(cl)
                while len(body_data) < length:
                    chunk = client.recv(1024)
                    if not chunk:
                        break
                    body_data += chunk
                environ["miroslava.request_body"] = body_data

            request = self.request_class(environ)
            request_ctx = RequestContext(self, environ, request=request)
            app_ctx = AppContext(self)

            app_ctx.push()
            request_ctx.push()
            try:
                response = self.dispatch_request(request)
                self.log_request(client_address, request, response)
                self.send_response(client, response)
            finally:
                request_ctx.pop()
                app_ctx.pop()
        except Exception as err:
            print(f"Internal Server Error: {err}")
            if self.config["DEBUG"]:
                import traceback

                traceback.print_exc()
        finally:
            client.close()

    def make_environ(self, headers: bytes) -> WSGIEnvironment:
        """Convert raw header bytes into a WSGI-like environment
        dictionary.

        The parser extracts the request line, path, query string, and
        maps headers to CGI-style keys. The ``Content-Length`` and
        ``Content-Type`` are stored without the ``HTTP_`` prefix while
        all other headers are namespaced with ``HTTP_`` to mirror the
        WSGI standard.

        :param headers: Raw bytes containing the request line and
            header block.
        """
        lines = headers.decode("utf-8", "ignore").split("\r\n")
        request_url = lines[0].split()
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/",
            "QUERY_STRING": "",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "9001",
            "wsgi.url_scheme": "http",
        }
        if len(request_url) >= 2:
            environ["REQUEST_METHOD"] = request_url[0]
            path = request_url[1]
            if "?" in path:
                path, query = path.split("?", 1)
                environ["QUERY_STRING"] = query
            environ["PATH_INFO"] = unquote(path)
        for line in lines[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                key = key.upper().replace("-", "_")
                if key in ("CONTENT_LENGTH", "CONTENT_TYPE"):
                    environ[key] = value.strip()
                else:
                    environ[f"HTTP_{key}"] = value.strip()
        return environ

    def dispatch_request(self, request: Request) -> Response:
        """Match route and return a response object.

        The dispatcher matches the incoming path against the
        ``url_map``, validates the HTTP method, and invokes the
        registered view function.

        View return values are normalised with make_response so tuples,
        mappings, and ``Response`` objects are handled consistently.

        Static file requests containing a period in the path are served
        from the configured ``static_folder``. Missing routes yield a
        ``404`` response.

        :param request: The request object to dispatch.
        :return: Response object.
        """
        if "." in request.path and not request.path.endswith("/"):
            return self.send_static_file(request.path)
        for rule in self.url_map:
            if rule.pattern is not None:
                continue
            if request.path != rule.rule:
                continue
            if request.method not in rule.methods:
                return self.response_class("Method Not Allowed", status=405)
            view_func = self.view_functions[rule.endpoint]
            kwargs = dict(rule.defaults)
            try:
                rv = view_func(**kwargs)
            except HTTPExceptionError as err:
                return err.response
            return self.make_response(rv)
        for rule in self.url_map:
            if rule.pattern is None:
                continue
            match = rule.pattern.match(request.path)
            if not match:
                continue
            if request.method not in rule.methods:
                return self.response_class("Method Not Allowed", status=405)
            view_func = self.view_functions[rule.endpoint]
            kwargs = dict(rule.defaults)
            for key, value in match.groupdict().items():
                try:
                    kwargs[key] = rule.converters.get(key, str)(value)
                except Exception:
                    return self.response_class("Not Found", status=404)
            try:
                rv = view_func(**kwargs)
            except HTTPExceptionError as err:
                return err.response
            return self.make_response(rv)
        return self.response_class("Not Found", status=404)

    def send_static_file(self, path: str) -> Response:
        """Serve static files.

        :param path: The path to the static file including the leading
            slash.
        :return: A Response object containing the file data or a 404
            response when the file is missing.
        """
        path = path.lstrip("/")
        static_prefix = (self.static_url_path or "static").lstrip("/")
        if path.startswith((f"{static_prefix}/", "static/")):
            path = path.split("/", 1)[1]
        if self.static_folder:
            path_str = os.path.join(self.root_path, self.static_folder, path)
        else:
            path_str = os.path.join(self.root_path, path)
        if os.path.exists(path_str) and os.path.isfile(path_str):
            with open(path_str, "rb") as f:
                data = f.read()
            mimetype, _ = mimetypes.guess_type(path_str)
            return self.response_class(
                data, mimetype=mimetype or "application/octet-stream"
            )
        return self.response_class("Not Found", status=404)

    def log_request(
        self,
        client_address: tuple[str, int],
        request: Request,
        response: Response,
    ) -> None:
        """Log the incoming request details to stdout.

        The format mimics the default access logs::

            ``host - - [Date] "METHOD Path HTTP/1.1" Status -``

        :param client_address: The client address tuple (host, port).
        :param request: The request object.
        :param response: The response object.
        """
        now = datetime.now().strftime("%d/%b/%Y %H:%M:%S")
        print(
            f'{client_address[0]} - - [{now}] "{request.method} {request.path} '
            f'{request.environ.get("SERVER_PROTOCOL", "HTTP/1.1")}" '
            f"{response.status_code} -"
        )

    def send_response(self, client: socket.socket, response: Response) -> None:
        """Send a Response object to the client socket.

        :param client: The client socket.
        :param response: The response object to send.
        """
        status_line = f"HTTP/1.1 {response.status}\r\n"
        headers = "".join(f"{k}: {v}\r\n" for k, v in response.headers.items())
        full_response = (
            status_line.encode("latin-1")
            + headers.encode("latin-1")
            + f"Content-Length: {len(response.data)}\r\n\r\n".encode("latin-1")
            + response.data
        )
        client.sendall(full_response)
