"""Minimal CORS middleware so the static front-end can call the API in dev.

For production use django-cors-headers with an explicit allow-list instead.
"""


class SimpleCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS":
            from django.http import HttpResponse

            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        # Telegram Web loads a Mini App inside an <iframe> on *.telegram.org, so the
        # default X-Frame-Options: DENY blocks it. Drop that header and instead use a
        # CSP frame-ancestors allow-list (still blocks every other origin → keeps
        # clickjacking protection) so the game embeds inside Telegram.
        if "X-Frame-Options" in response:
            del response["X-Frame-Options"]
        response["Content-Security-Policy"] = (
            "frame-ancestors 'self' https://telegram.org https://*.telegram.org "
            "https://web.telegram.org"
        )
        return response
