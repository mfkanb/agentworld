"""统一响应工具"""
import secrets
import uuid


def generate_api_key() -> str:
    """生成 API Key: agent-world- + 48位随机字符"""
    return "agent-world-" + secrets.token_hex(24)


def success_response(data: dict, message: str = "操作成功") -> dict:
    return {
        "success": True,
        "data": data,
        "message": message,
        "request_id": f"req_{uuid.uuid4().hex[:12]}",
    }


def error_response(error: str, message: str, hint: str = "") -> dict:
    resp = {
        "success": False,
        "error": error,
        "message": message,
        "hint": hint,
        "request_id": f"req_{uuid.uuid4().hex[:12]}",
    }
    return resp
