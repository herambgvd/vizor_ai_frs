"""Ready-to-use Jinja2 notification templates + a tiny ``render`` helper.

Notifications shouldn't hardcode HTML strings all over the codebase. Instead a
scenario names a template ("alert", "welcome", ...) and passes a context dict;
``render`` returns the ``(subject, html)`` pair with placeholders filled in.

Templates live in ``DEFAULT_TEMPLATES`` as ``{name: {"subject", "html"}}``. Both
the subject and the body are Jinja2 strings, so ``{{ placeholders }}`` and simple
logic (``{% if %}``) work in either. Keep them small and self-contained — a
scenario can always render its own HTML and pass it straight to ``send_email``.
"""

from __future__ import annotations

from jinja2 import Environment, select_autoescape

from ..core.errors import ValidationError

# Autoescape so context values can't inject markup into the rendered HTML.
_env = Environment(autoescape=select_autoescape(["html", "xml"]))


# The built-in templates. Placeholders are documented inline next to each.
DEFAULT_TEMPLATES: dict[str, dict] = {
    # A generic alert/event notification.
    #   ctx: title, message, [severity], [when]
    "alert": {
        "subject": "Alert: {{ title }}",
        "html": (
            "<h2>{{ title }}</h2>"
            "{% if severity %}<p><strong>Severity:</strong> {{ severity }}</p>{% endif %}"
            "<p>{{ message }}</p>"
            "{% if when %}<p style=\"color:#888\">{{ when }}</p>{% endif %}"
        ),
    },
    # Tells a user an export/report they requested is ready to download.
    #   ctx: name, [download_url]
    "report_ready": {
        "subject": "Your report is ready: {{ name }}",
        "html": (
            "<h2>Report ready</h2>"
            "<p>Your report <strong>{{ name }}</strong> has finished generating.</p>"
            "{% if download_url %}"
            "<p><a href=\"{{ download_url }}\">Download it here</a></p>"
            "{% endif %}"
        ),
    },
    # Onboarding email for a newly created user.
    #   ctx: name, [app_name], [activate_url], [login_url]
    "welcome": {
        "subject": "Welcome{% if app_name %} to {{ app_name }}{% endif %}!",
        "html": (
            "<h2 style=\"margin:0 0 12px\">Welcome, {{ name }}!</h2>"
            "<p>An account has been created for you{% if app_name %} on {{ app_name }}{% endif %}.</p>"
            "{% if activate_url %}"
            "<p style=\"margin:20px 0\"><a href=\"{{ activate_url }}\" "
            "style=\"display:inline-block;background:#111;color:#fff;text-decoration:none;"
            "padding:11px 20px;border-radius:8px;font-weight:600\">Set your password</a></p>"
            "<p style=\"color:#888;font-size:13px\">This secure link activates your account and lets "
            "you choose your password. It expires in 1 hour.</p>"
            "{% elif login_url %}"
            "<p><a href=\"{{ login_url }}\">Sign in to get started</a></p>"
            "{% endif %}"
        ),
    },
}


def render(name: str, ctx: dict) -> tuple[str, str]:
    """Render a named template with ``ctx`` → ``(subject, html)``.

    Raises ``ValidationError`` if ``name`` isn't a known template so a typo in a
    scenario fails loudly instead of silently sending an empty email.
    """
    tpl = DEFAULT_TEMPLATES.get(name)
    if tpl is None:
        known = ", ".join(sorted(DEFAULT_TEMPLATES))
        raise ValidationError(f"unknown template '{name}' (known: {known})")

    ctx = ctx or {}
    subject = _env.from_string(tpl["subject"]).render(**ctx)
    html = _env.from_string(tpl["html"]).render(**ctx)
    return subject, html


def available_template_names() -> list[str]:
    """The built-in template names (the keys admins can override)."""
    return list(DEFAULT_TEMPLATES)


async def render_with_overrides(db, name: str, ctx: dict) -> tuple[str, str]:
    """Render ``name`` preferring a DB override, falling back to the code default.

    If an admin has customised the template (a row in ``email_templates``), its
    subject+html are rendered with the SAME Jinja Environment as the built-ins.
    Otherwise we defer to ``render`` for the code default. Raises ``ValidationError``
    when neither an override nor a built-in exists for ``name``.
    """
    # Local import avoids a circular import (template_store imports nothing here,
    # but keep the module boundary clean and lazy).
    from . import template_store

    override = await template_store.get_override(db, name)
    if override is not None:
        ctx = ctx or {}
        subject = _env.from_string(override.subject).render(**ctx)
        html = _env.from_string(override.html).render(**ctx)
        return subject, html

    # No override — fall back to the built-in (raises if that's unknown too).
    return render(name, ctx)


# --- preview -----------------------------------------------------------------
# Realistic sample values so admins see a rendered email, not raw Jinja tags.
_SAMPLE_CTX = {
    "title": "Perimeter breach detected",
    "message": "A person was detected in a restricted zone (Camera 3, North Gate).",
    "severity": "High",
    "when": "Jul 3, 2026 · 14:22",
    "name": "Jane Doe",
    "download_url": "https://app.example.com/reports/monthly-attendance.pdf",
    "app_name": "Neubit",
    "login_url": "https://app.example.com/login",
}


def wrap_email(app_name: str, body_html: str) -> str:
    """Wrap a rendered template body in a clean, branded email shell."""
    return (
        '<div style="margin:0;padding:24px;background:#f4f4f5;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #eaeaea;'
        'border-radius:12px;overflow:hidden">'
        f'<div style="padding:16px 24px;border-bottom:1px solid #eee;font-weight:600;'
        f'font-size:15px;color:#111">{app_name}</div>'
        f'<div style="padding:24px;color:#333;font-size:15px;line-height:1.6">{body_html}</div>'
        f'<div style="padding:16px 24px;border-top:1px solid #eee;color:#9ca3af;font-size:12px">'
        f'You are receiving this because you have a {app_name} account.</div>'
        '</div></div>'
    )


async def render_preview(db, name: str, app_name: str = "Neubit") -> tuple[str, str]:
    """Render ``name`` with sample data and a branded shell → (subject, html)."""
    ctx = {**_SAMPLE_CTX, "app_name": app_name}
    subject, body = await render_with_overrides(db, name, ctx)
    return subject, wrap_email(app_name, body)
