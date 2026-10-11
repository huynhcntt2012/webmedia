import re

from starlette.responses import JSONResponse


class AuthBodyLimit:
    """Bound request buffering before JSON validation, including chunked bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(
            ("/auth/", "/admin/", "/playback/", "/reader/", "/payments/", "/content/")
        ):
            return await self.app(scope, receive, send)
        limit = 32768 if scope["path"].startswith("/admin/") else 8192
        if scope["path"] == "/payments/sepay/webhook":
            limit = 16384
        if scope["method"] == "POST" and re.fullmatch(
            r"/admin/comics/[a-fA-F0-9-]{36}/chapters/[a-fA-F0-9-]{36}/pages", scope["path"]
        ):
            limit = 8 * 1024 * 1024
        if scope["method"] == "PUT" and re.fullmatch(
            r"/admin/media-jobs/[a-fA-F0-9-]{36}/subtitles/[a-zA-Z-]{2,12}", scope["path"]
        ):
            limit = 256 * 1024  # JSON escaping overhead; decoded VTT separately limited to 128 KiB.
        if scope["method"] == "PUT" and re.fullmatch(
            r"/admin/uploads/[a-fA-F0-9-]{36}/chunks", scope["path"]
        ):
            limit = 4 * 1024 * 1024
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await JSONResponse({"detail": "Request too large"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
