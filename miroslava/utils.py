"""\
Miroslava's Utilities
=====================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 27 January, 2026
Last updated on: 04 February, 2026

This module provides small helper functions that are used throughout
the project. It includes some JSON serialisation helpers, a simple
template renderer for demonstration purposes, and path helpers for
locating application roots.

The intent is to keep behaviour familiar while remaining easy to follow
for pedagogical purposes.
"""

from __future__ import annotations

import json
import os
import sys
import typing as t
from http import HTTPStatus

if t.TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping
    from collections.abc import Sequence

    from miroslava.wrappers import Headers
    from miroslava.wrappers import Response

F = t.TypeVar("F", bound=t.Callable[..., object])
type HeaderValue = str | list[str] | tuple[str, ...]
type HeadersValue = (
    "Headers" | Mapping[str, HeaderValue] | Sequence[tuple[str, HeaderValue]]
)
type JSONValue = (
    str | int | float | bool | None | dict[str, t.Any] | list[t.Any]
)
type ResponseValue = Response | str | bytes | list[t.Any] | Mapping[str, t.Any]
type WSGIEnvironment = dict[str, t.Any]

_charset_mimetypes: set[str] = {
    "application/javascript",
    "application/xml",
}


def get_content_type(mimetype: str, charset: str) -> str:
    """Return a content type string with charset when appropriate.

    :param mimetype: Base mimetype value such as ``text/html``.
    :param charset: Charset label appended for textual types.
    :return: Content type.
    """
    if mimetype.startswith("text/") or mimetype in _charset_mimetypes:
        mimetype += f"; charset={charset}"
    return mimetype


class DefaultJSONProvider:
    """Base class which provides JSON serialisation."""

    mimetype: t.ClassVar[str] = "application/json"
    compact: t.ClassVar[bool | None] = None

    def loads(self, s: str | bytes, **kwargs: t.Any) -> t.Any:
        """Deserialise a Python object as JSON."""
        return json.loads(s, **kwargs)

    def load(self, fp: t.IO[t.AnyStr], **kwargs: t.Any) -> t.Any:
        """Deserialise data as JSON, but from a file."""
        return self.loads(fp.read(), **kwargs)

    def dumps(self, obj: t.Any, **kwargs: t.Any) -> str:
        """Serialise a Python object to a JSON string."""
        if "ensure_ascii" not in kwargs:
            kwargs["ensure_ascii"] = False
        return json.dumps(obj, **kwargs)

    def _prepare_response_obj(self, *args: t.Any, **kwargs: t.Any) -> t.Any:
        """Return valid keywords/arguments for the response."""
        if args and kwargs:
            raise TypeError("Response takes either args or kwargs, not both")
        if len(args) == 1:
            return args[0]
        return args or kwargs

    def response(self, *args: t.Any, **kwargs: t.Any) -> Response:
        """Create a JSON Response using the configured provider."""
        from miroslava.wrappers import Response

        obj = self._prepare_response_obj(*args, **kwargs)
        if self.compact:
            kwargs.setdefault("separators", (",", ":"))
        else:
            kwargs.setdefault("indent", 2)
        return Response(self.dumps(obj), mimetype=self.mimetype)


def jsonify(*args: t.Any, **kwargs: t.Any) -> Response:
    """Create a JSON response using the default provider."""
    return DefaultJSONProvider().response(*args, **kwargs)


class TemplateNotFoundError(IOError):
    """Error raised when a template file cannot be located on disk."""


def render_template(
    template_name_or_list: str | list[str],
    **context: t.Any,
) -> str:
    """Render a template string by naive substitution.

    The function walks a list of possible template names, picking the
    first file present under a templates directory. It then performs a
    simple string replacement for context variables of the form {{ key }}.
    This is intentionally minimal and intended for teaching rather than
    production use.

    :param template_name_or_list: Template filename or list of fallback
        names to try in order.
    :raises TemplateNotFoundError: When no templates are found.
    """
    templates = (
        [template_name_or_list]
        if isinstance(template_name_or_list, str)
        else template_name_or_list
    )
    content: str | None = None
    try:
        from miroslava.globals import current_app

        root_dir = current_app.root_path
        template_dir = current_app.template_folder or "templates"
    except Exception:
        root_dir = os.getcwd()
        template_dir = "templates"

    for template in templates:
        candidates = [
            os.path.join(root_dir, template_dir, template),
            os.path.join("templates", template),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                with open(candidate) as html:
                    content = html.read()
                break
        if content is not None:
            break
    if content is None:
        raise TemplateNotFoundError(f"Template(s) not found: {templates}")
    for key, value in context.items():
        content = content.replace(f"{{{{ {key} }}}}", str(value))
        content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


def get_root_path(import_name: str) -> str:
    """Return the filesystem directory for the given import name.

    :param import_name: Module import path whose ``__file__`` location
        is used to determine the root directory.
    """
    try:
        module = sys.modules[import_name]
        return os.path.dirname(os.path.abspath(module.__file__ or "."))
    except (KeyError, AttributeError):
        return os.getcwd()


def get_current_url(
    scheme: str,
    host: str,
    root_path: str | None = None,
    path: str | None = None,
    query_string: str | None = None,
) -> str:
    """Recreate the URL for a request.

    :param scheme: Protocol of the request used.
    :param host: The host the request was made to.
    :param root_path: Prefix that the application is mounted under,
        defaults to `None`.
    :param path: The path part of the URL after `root_path`, defaults
        to `None`.
    :param query_string: The portion of the URL after the `?`, defaults
        to `None`.
    """
    url = [scheme, "://", host]
    if root_path is None:
        return f"{''.join(url)}/"
    url.append(root_path.rstrip("/"))
    if path is None:
        return f"{''.join(url)}/"
    url.append(path.lstrip("/"))
    if query_string:
        url.extend(["?", query_string])
    return "".join(url)


class Rule:
    """Represent a single URL mapping.

    The rule stores the original pattern string, any default values for
    variable parts, compiled regular expression for dynamic segments,
    and converters that coerce matched strings into typed Python
    objects.

    :param string: Normal URL string.
    :param defaults: Optional dictionary with defaults for other rules
        with same endpoints, defaults to ``None``.
    :param methods: Sequence of http methods this rule applied to,
        defaults to ``None``.
    :param endpoint: Endpoint for this rule, defaults to ``None``.
    """

    def __init__(
        self,
        string: str,
        defaults: Mapping[str, t.Any] | None = None,
        methods: Iterable[str] | None = None,
        endpoint: str | None = None,
    ) -> None:
        """Initialise a rule with URL string."""
        if not string.startswith("/"):
            raise ValueError(f"URL rule {string!r} must start with a slash")
        self.rule = string
        self.endpoint = endpoint or string
        self.methods = set(methods or [])
        self.defaults = dict(defaults or {})

    def __repr__(self) -> str:
        """Human-readable representation of the rule object."""
        methods = ", ".join(sorted(self.methods)) if self.methods else ""
        return f"<Rule {self.rule!r} ({methods}) -> {self.endpoint}>"


class Map:
    """Container class for storing all the URL rules.

    The map maintains insertion order, exposes iteration, and supports
    length queries to mirror the behaviour expected by the dispatcher.

    :param rules: Sequence of URL rules for this map, defaults to
        ``None``.
    """

    def __init__(self, rules: Iterable[Rule] | None = None) -> None:
        """Initialise mapping with some rules."""
        self._rules: Iterable[Rule] = rules or []

    def __repr__(self) -> str:
        """Human-readable representation of mapping object."""
        return f"<Map {len(self._rules)} rules>"

    def __iter__(self) -> t.Iterator[Rule]:
        """Iterate over all rules of an endpoint."""
        return iter(self._rules)

    def __len__(self) -> int:
        """Return count of rules."""
        return len(self._rules)

    def add(self, rule: Rule) -> None:
        """Add new rule to the map."""
        self._rules.append(rule)


def make_response(*args: t.Any) -> Response:
    """Make a response to return."""
    from miroslava.globals import current_app

    if not args:
        return current_app.response_class()
    if len(args) == 1:
        args = args[0]
    return current_app.make_response(args)


class HTTPExceptionError(Exception):
    """Signal a prepared response should short-circuit dispatch."""

    def __init__(self, response: Response) -> None:
        """Initialise an HTTP exception."""
        super().__init__()
        self.response = response


def abort(
    status: int | HTTPStatus | Response,
    description: str | None = None,
    headers: HeadersValue | None = None,
) -> t.NoReturn:
    """Raise an HTTP error response.

    When provided a ``Response`` or a response tuple, that value is
    wrapped via ``current_app.make_response``. Otherwise a fresh
    ``Response`` is created using the current application's response
    class and the HTTP status phrase as the default body.

    :param status: Status code for the exception.
    :param description: Error description, defaults to ``None``.
    :para headers: List of headers while sending response, defaults to
        ``None``.
    """
    from miroslava.globals import current_app
    from miroslava.wrappers import Response

    if isinstance(status, Response):
        response = status
    else:
        code = int(status)
        body: ResponseValue = description or HTTPStatus(code).phrase
        if headers:
            response = current_app.make_response((body, code, headers))
        else:
            response = current_app.make_response((body, code))
    raise HTTPExceptionError(response)


def show_server_banner(
    debug: bool, app_import_path: str | None, **options: t.Any
) -> None:
    """Show startup message when running the main application."""
    message = ""
    if app_import_path is not None:
        message += f" * Serving Miroslava app {app_import_path!r}\n"
    if options:
        host = options.get("host", "127.0.0.1")
        port = options.get("port", 90001)
        info = f" * Running on http://{host}:{port}/\nPress CTRL+C to quit\n"
    if debug is not None:
        message += f" * Debug mode: {'on' if debug else 'off'}\n"
        message += info
        if debug:
            message += " * Debugger is active!\n * Debugger PIN: 299-792-458"
    print(message)
