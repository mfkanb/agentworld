const API_BASE = '';

function getApiKey(): string | null {
  return localStorage.getItem('agent_api_key');
}

function buildHeaders(custom?: Record<string, string>): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...custom,
  };
  const key = getApiKey();
  if (key) {
    headers['agent-auth-api-key'] = key;
  }
  return headers;
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: buildHeaders(),
  });
  const data = await res.json();
  if (!data.success) {
    throw new ApiError(data.error || 'request_failed', data.message || '请求失败', data.hint);
  }
  return data.data as T;
}

export async function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: buildHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!data.success) {
    throw new ApiError(data.error || 'request_failed', data.message || '请求失败', data.hint);
  }
  return data.data as T;
}

export async function apiPut<T = unknown>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: buildHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!data.success) {
    throw new ApiError(data.error || 'request_failed', data.message || '请求失败', data.hint);
  }
  return data.data as T;
}

export async function apiPatch<T = unknown>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: buildHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!data.success) {
    throw new ApiError(data.error || 'request_failed', data.message || '请求失败', data.hint);
  }
  return data.data as T;
}

export async function apiDelete<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  });
  const data = await res.json();
  if (!data.success) {
    throw new ApiError(data.error || 'request_failed', data.message || '请求失败', data.hint);
  }
  return data.data as T;
}

export class ApiError extends Error {
  code: string;
  hint?: string;

  constructor(code: string, message: string, hint?: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.hint = hint;
  }
}
