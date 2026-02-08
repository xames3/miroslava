"""\
Simple use cases
================

Author: Akshay Mestry <xa@mes3.dev>
Created on: 04 February, 2026
Last updated on: 04 February, 2026

These (simple) examples showcase what Miroslava can do in its current
state. Since, it's supposed to be a Temu like rip-off of Flask, it has
same API signature.
"""

from datetime import datetime as dt

from miroslava import (
    Miroslava,
    abort,
    jsonify,
    make_response,
    render_template,
    request,
)

now = dt.now().hour
time = "morning" if 0 <= now < 12 else "day" if 12 <= now < 16 else "evening"

app = Miroslava(__name__)


# Use case 01: Basic application using the ``route`` decorator
@app.route("/")
def index():
    return f"<h1>Hello hello, good {time}!!</h1>"


# Use case 02: URL stacking for a single view (function)
@app.route("/hi")
@app.route("/hello")
@app.route("/hola")
@app.route("/bonjour")
def greet():
    return "<p>I can't speak other languages, I'll greet in English</p>"


# Use case 03: Dynamic URL routes
@app.route("/wish", defaults={"to": "to you"})
@app.route("/wish/<to>")
def birthday(to):
    return f"<h1>Good {time}!</h1><h2>Happy birthday {to}!! 🥳</<h2>"


@app.route("/brew/<drink>")
def beverages(drink):
    if drink == "coffee":
        return f"<h2>{abort(418)} 🫖</h2>"
    return f"<h2>Let's have some {drink}! ☕️</h2>"


if __name__ == "__main__":
    app.run(debug=True)
