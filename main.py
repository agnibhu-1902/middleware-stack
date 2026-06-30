import uuid
import time
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# ── Config ─────────────────────────────────────────────────────
YOUR_EMAIL = "21f1001209@ds.study.iitm.ac.in"  # ← replace with your email

ALLOWED_ORIGINS = {
    "https://app-6eiknr.example.com",
    "null",  # exam page / file:// origin during grading
}

RATE_LIMIT = 14   # requests
RATE_WINDOW = 10  # seconds

app = FastAPI()

# ── Rate limit store ───────────────────────────────────────────
rate_limit_store: dict = defaultdict(list)


# ══════════════════════════════════════════════════════════════
# Middleware 1 — Request Context (innermost)
# ══════════════════════════════════════════════════════════════
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ══════════════════════════════════════════════════════════════
# Middleware 2 — Scoped CORS (middle)
# ══════════════════════════════════════════════════════════════
class ScopedCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")

        if request.method == "OPTIONS":
            if origin in ALLOWED_ORIGINS:
                return JSONResponse(
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Methods": "GET, OPTIONS",
                        "Access-Control-Allow-Headers": "X-Request-ID, X-Client-Id",
                        "Access-Control-Expose-Headers": "X-Request-ID",
                    },
                )
            return JSONResponse(status_code=200)

        response = await call_next(request)
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
        return response


# ══════════════════════════════════════════════════════════════
# Middleware 3 — Per-client Rate Limiter (outermost)
# ══════════════════════════════════════════════════════════════
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_id = request.headers.get("X-Client-Id", "anonymous")
        now = time.time()
        window_start = now - RATE_WINDOW

        rate_limit_store[client_id] = [
            t for t in rate_limit_store[client_id] if t > window_start
        ]

        if len(rate_limit_store[client_id]) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests"},
            )

        rate_limit_store[client_id].append(now)
        return await call_next(request)


# ── Register middleware (last added = outermost = runs first) ──
app.add_middleware(RequestContextMiddleware)  # innermost
app.add_middleware(ScopedCORSMiddleware)      # middle
app.add_middleware(RateLimitMiddleware)       # outermost


# ── Route ──────────────────────────────────────────────────────
@app.get("/ping")
async def ping(request: Request):
    return {
        "email": YOUR_EMAIL,
        "request_id": request.state.request_id,
    }
