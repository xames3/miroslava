"""\
Miroslava's Miscellaneous Utilities
===================================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 27 January, 2026
Last updated on: 31 January, 2026

This module implements a few things besides the usual miscellaneous
utilities which are used throughout the project.

It implements:

    [1] a basic rendering engine compatible with Jinja2 syntax for
        variable substitution. While `Flask` uses the powerful Jinja2
        engine, Miroslava implements a lightweight version, and I mean
        very lightweight version that handles basic `{{ variable }}`
        replacement, which is good enough for simple pedagogical
        purpose.
    [2] a json-ifying utility.
"""

from __future__ import annotations

import json
import os
import sys
import typing as t

if t.TYPE_CHECKING:
    from miroslava.wrappers import Response

type WSGIEnvironment = dict[str, t.Any]

_charset_mimetypes: set[str] = {
    "application/ecmascript",
    "application/javascript",
    "application/sql",
    "application/xml",
}


def set_module(mod: str) -> t.Callable[..., t.Any]:
    """Decorator for overriding `__module__` on a function or class."""

    def decorator(func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        """Inner function."""
        if mod is not None:
            func.__module__ = mod
        return func

    return decorator


def get_content_type(mimetype: str, charset: str) -> str:
    """Return the full content type string with charset.

    :param mimetype: Mimetype to be used as content type.
    :param charset: Charset to be appended for mimetype.
    :return: Content type.
    """
    if mimetype.startswith("text/") or mimetype in _charset_mimetypes:
        mimetype += f", charset={charset}"
    return mimetype


@set_module("miroslava.wsgi")
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


@set_module("miroslava.wsgi")
def _get_server(environ: WSGIEnvironment) -> tuple[str, int] | None:
    """Return value of host and port details from environment."""
    name = environ.get("SERVER_NAME")
    if name is None:
        return None
    return name, int(environ.get("SERVER_PORT", 9001))


@set_module("miroslava.json")
class DefaultJSONProvider:
    """Base class which provides abstractions for JSON operations."""

    mimetype: t.ClassVar[str] = "application/json"
    compact: t.ClassVar[bool | None] = None

    def loads(self, s: str | bytes, **kwargs: t.Any) -> t.Any:
        """Deserialise data as JSON."""
        return json.loads(s, **kwargs)

    def load(self, fp: t.IO[t.AnyStr], **kwargs: t.Any) -> t.Any:
        """Deserialise data as JSON, but from a file."""
        return self.loads(fp.read(), **kwargs)

    def dumps(self, obj: t.Any, **kwargs: t.Any) -> str:
        """Serialise data as JSON."""
        return json.dumps(obj, **kwargs)

    def dump(self, obj: t.Any, fp: t.IO[str], **kwargs: t.Any) -> None:
        """Serialise data as JSON, but write to a file."""
        fp.write(self.dumps(obj, **kwargs))

    def _prepare_response_obj(self, *args: t.Any, **kwargs: t.Any) -> t.Any:
        """Return valid keyword/arguments for the response."""
        if args and kwargs:
            raise TypeError("Response takes either args or kwargs, not both")
        if len(args) == 1:
            return args[0]
        return args or kwargs

    def response(self, *args: t.Any, **kwargs: t.Any) -> Response:
        """Serialise provided arguments as JSON and return a
        `Response`.
        """
        from miroslava.wrappers import Response

        obj = self._prepare_response_obj(*args, **kwargs)
        if self.compact:
            kwargs.setdefault("separators", (",", ":"))
        else:
            kwargs.setdefault("indent", 2)
        return Response(self.dumps(obj), mimetype=self.mimetype)


jsonify = set_module("miroslava.json")(lambda: DefaultJSONProvider().response)


@set_module("miroslava.templating")
class TemplateNotFoundError(IOError):
    """Raise exception if template isn't found."""

    def __init__(self, message: str | None = None) -> None:
        """Initialise exception with an optional message."""
        super.__init__(message)

    @property
    def message(self) -> str | None:
        """Return an exception message, if any."""
        return self.args[0] if self.args else None


@set_module("miroslava.templating")
def render_template(
    template_name_or_list: str | list[str],
    **context: t.Any,
) -> str:
    """Render a template by name with the given context.

    Example::

        render_template("index.html", name="Mikasa")  # normal usage

        # Tries `custom.html` first, if that doesn't exist, it'll
        # fallback to `default.html`.
        render_template(["custom.html", "default.html"], name="Eren")

    :param template_name_or_list: The name of the template to render.
        If a list is provided instead, the first object will be
        rendered.
    :param context: Keyword arguments to make available in the
        templates.
    """
    content: str | None = None
    if isinstance(template_name_or_list, str):
        templates = [template_name_or_list]
    else:
        templates = template_name_or_list
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


@set_module("miroslava.helpers")
def get_root_path(import_name: str) -> str:
    """Find the root path of a package or a module."""
    module = sys.modules[import_name]
    path = getattr(module, "__file__", None)
    if path is None:
        raise RuntimeError("No root path found")
    return os.path.dirname(os.path.abspath(path))
