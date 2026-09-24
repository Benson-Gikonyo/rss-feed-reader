"""Session-bound CSRF tokens for browser forms; no protection bypass in tests."""
import secrets

from flask import abort, request, session


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def protect_request():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected.encode(), supplied.encode()):
        abort(400, description="This form is no longer valid. Reload the page and try again.")


def init_app(app):
    app.before_request(protect_request)
    app.context_processor(lambda: {"csrf_token": csrf_token})

    @app.after_request
    def prevent_form_caching(response):
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response
