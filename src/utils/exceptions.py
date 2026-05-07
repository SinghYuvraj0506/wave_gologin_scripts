"""
Exception tree:
    InstagramScrapingBaseError          ← root for all custom errors
    ├── UIChangeError                   ← DOM/XPath/selector no longer valid
    ├── ScriptError                     ← JS execution failure inside browser
    ├── GologinError                    ← Browser/profile launch issues
    └── InstagramServerError            ← Instagram returned an error banner

    RuntimeError  (Python built-in)     ← re-used as "server says stop NOW"
                                          (NOT subclassed — propagates as-is)
"""


class InstagramScrapingBaseError(Exception):
    """Root for every custom scraping exception.  Carries a `context` dict
    so callers can log structured data without string-parsing the message."""

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message)
        self.context: dict = context or {}

    def __str__(self) -> str:
        base = super().__str__()
        if self.context:
            ctx_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{base} [{ctx_str}]"
        return base


# ── UI / DOM ──────────────────────────────────────────────────────────────────

class UIChangeError(InstagramScrapingBaseError):
    """Instagram changed its DOM — a selector or XPath is no longer valid.
    Signals that a developer must update the locator."""


class ScriptError(InstagramScrapingBaseError):
    """A JavaScript snippet executed via driver.execute_script() failed or
    returned an unexpected value."""


class NavigationError(InstagramScrapingBaseError):
    """Failed to navigate to a required page (e.g. Inbox)."""


# ── Search ────────────────────────────────────────────────────────────────────
 
class UserSearchError(InstagramScrapingBaseError):
    """Username search flow failed after all retries.
    Carries `username` and `attempt` in context."""
 

 # ── Messaging ─────────────────────────────────────────────────────────────────
 
class MessageSendError(InstagramScrapingBaseError):
    """DM send/verify flow failed after all retries.
    Carries `username` and `reason` in context."""
 
 
class MessageRejectedError(MessageSendError):
    """Instagram explicitly showed 'Failed to send' SVG — hard stop for this
    user, do not retry."""

# ── Browser / Session ─────────────────────────────────────────────────────────

class GologinError(InstagramScrapingBaseError):
    """Gologin browser profile could not be launched, connected to, or
    kept alive.  Treat as a fatal session error."""


class GologinConnectionError(GologinError):
    """Gologin browser connection failed (e.g. timeout, refuse)."""


class GologinProfileNotFoundError(GologinError):
    """Gologin profile not found."""



# ── Instagram Server ──────────────────────────────────────────────────────────

class InstagramServerError(InstagramScrapingBaseError):
    """Instagram returned an on-page error banner (e.g. 'Something isn't
    working.').  Carries `page` and `error_count` in context."""