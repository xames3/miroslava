"""\
Miroslava's Utilities
=====================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 27 January, 2026
Last updated on: 01 February, 2026

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

if t.TYPE_CHECKING:
    from miroslava.wrappers import Response

F = t.TypeVar("F", bound=t.Callable[..., object])
type JSONValue = (
    str | int | float | bool | None | dict[str, t.Any] | list[t.Any]
)
type WSGIEnvironment = dict[str, t.Any]

_charset_mimetypes: set[str] = {
    "application/javascript",
    "application/xml",
}


def set_module(module: str | None) -> t.Callable[[F], F]:
    """Decorator for overriding the ``__module__`` on a callable."""

    def inner(func: F) -> F:
        """Decorated function."""
        if module is not None:
            func.__module__ = module
        return func

    return inner


m = set_module


def get_content_type(mimetype: str, charset: str) -> str:
    """Return a content type string with charset when appropriate.

    :param mimetype: Base mimetype value such as ``text/html``.
    :param charset: Charset label appended for textual types.
    :return: Content type.
    """
    if mimetype.startswith("text/") or mimetype in _charset_mimetypes:
        mimetype += f"; charset={charset}"
    return mimetype


@m("miroslava.json.provider")
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


jsonify = m("miroslava.json.provider")(lambda: DefaultJSONProvider().response)


@m("miroslava.templating")
class TemplateNotFoundError(IOError):
    """Error raised when a template file cannot be located on disk."""


@m("miroslava.templating")
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
    :param context: Values to interpolate into the template source.
    :raises TemplateNotFoundError: When no templates are found.
    """
    templates = (
        [template_name_or_list]
        if isinstance(template_name_or_list, str)
        else template_name_or_list
    )
    content: str | None = None
    for template in templates:
        path = os.path.join("templates", template)
        if os.path.exists(path):
            with open(path) as html:
                content = html.read()
            break
    if content is None:
        raise TemplateNotFoundError(f"Template(s) not found: {templates}")
    for key, value in context.items():
        content = content.replace(f"{{{{ {key} }}}}", str(value))
        content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


@m("miroslava.helpers")
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


@m("miroslava.twerkzeug.wsgi")
def _get_server(environ: WSGIEnvironment) -> tuple[str, int] | None:
    """Return value of host and port details from environment."""
    name = environ.get("SERVER_NAME")
    if name is None:
        return None
    return name, int(environ.get("SERVER_PORT", 9001))


@m("miroslava.twerkzeugwsgi")
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
