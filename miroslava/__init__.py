"""\
Miroslava
=========

Author: Akshay Mestry <xa@mes3.dev>
Created on: 26 January, 2026
Last updated on: 03 February, 2026

Miroslava is a ultra-lightweight, risky, and non-production ready WSGI
(micro) web framework modelled after ``Flask`` and ``Werkzeug``.

This reinactment of ``Flask`` is something I wrote to challenge myself
and a means to teach how a web framework works behind the scenes to my
students.
"""

from __future__ import annotations

from miroslava.app import Miroslava as Miroslava
from miroslava.globals import current_app as current_app
from miroslava.globals import g as g
from miroslava.globals import request as request
from miroslava.globals import session as session
from miroslava.utils import jsonify as jsonify
from miroslava.utils import render_template as render_template
from miroslava.wrappers import Request as Request
from miroslava.wrappers import Response as Response

version: str = "01.02.2026"
