"""全局限流中间件 - 基于 API Key / IP 的请求频率限制"""
import time
import uuid
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# 限流配置
GET_LIMIT = 60
POST_LIMIT = 30
WINDOW_SECONDS = 60.0


class RateLimiter:
    """基于滑动窗口的内存限流器"""

    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str) -> None:
        cutoff = time.time() - WINDOW_SECONDS
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

    def check(self, key: str, limit: int) -> tuple[bool, int, int]:
        """检查是否超限，返回 (is_limited, retry_after, remaining)"""
        now = time.time()
        self._cleanup(key)
        self._requests[key].append(now)

        count = len(self._requests[key])
        remaining = max(0, limit - count)
        if count > limit:
            oldest = self._requests[key][0]
            retry_after = int(oldest + WINDOW_SECONDS - now) + 1
            return True, max(retry_after, 1), 0
        return False, 0, remaining

    def reset(self) -> None:
        """重置所有限流状态（测试用）"""
        self._requests.clear()


# 全局单例
limiter = RateLimiter()


def _get_client_id(request: Request) -> str:
    """提取客户端标识：API Key 优先，否则用 IP"""
    api_key = request.headers.get("agent-auth-api-key")
    if not api_key:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            api_key = auth[7:]
    if api_key:
        return f"key:{api_key}"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    client = request.client
    if client:
        return f"ip:{client.host}"
    return "ip:unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 API Key（优先）或 IP 的全局限流中间件"""

    def __init__(self, app, get_limit: int = GET_LIMIT, post_limit: int = POST_LIMIT):
        super().__init__(app)
        self.get_limit = get_limit
        self.post_limit = post_limit

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in ("/", "/health", "/docs", "/openapi.json", "/redoc") or path.startswith("/data/"):
            return await call_next(request)

        method = request.method.upper()
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            limit = self.post_limit
        else:
            limit = self.get_limit

        client_id = _get_client_id(request)
        is_limited, retry_after, remaining = limiter.check(client_id, limit)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "rate_limited",
                    "message": f"请求频率过高，{method} 限制为 {limit} 次/分钟",
                    "hint": f"请 {retry_after} 秒后重试，当前剩余额度: 0/{limit}",
                    "request_id": f"req_{uuid.uuid4().hex[:12]}",
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
