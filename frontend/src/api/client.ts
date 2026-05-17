const API_PREFIX = "/api/v1";
const ACCESS_TOKEN_KEY = "autolearning_access_token";
const MODEL_CONFIG_KEY = "autolearning_model_config";

export function getAccessToken() {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

function buildHeaders() {
  const token = getAccessToken();
  return token ? ({ Authorization: `Bearer ${token}` } as Record<string, string>) : {};
}

function getModelOverrides(): Record<string, string | number | null> | null {
  try {
    const raw = localStorage.getItem(MODEL_CONFIG_KEY);
    if (!raw) return null;
    const config = JSON.parse(raw);
    if (!config.useCustom) return null;
    return {
      model_provider: config.provider === "spark" ? "spark" : "openai_compatible",
      model_api_base: config.apiBase || null,
      model_api_key: config.apiKey || null,
      model_name: config.modelName || null,
      model_temperature: config.temperature ?? null,
    };
  } catch {
    return null;
  }
}

function injectModelOverrides(body: unknown): unknown {
  const overrides = getModelOverrides();
  if (!overrides || !body || typeof body !== "object") return body;
  return { ...overrides, ...(body as Record<string, unknown>) };
}

const REQUEST_TIMEOUT_MS = 60_000;

const FRIENDLY_ERRORS: Record<string, string> = {
  LLM_TIMEOUT: "AI 服务响应超时，请稍后重试",
  LLM_RATE_LIMITED: "AI 服务繁忙，请稍后再试",
  LLM_AUTH_FAILED: "AI 服务认证失败，请检查模型配置",
  LLM_CIRCUIT_OPEN: "AI 服务暂时不可用，请稍后重试",
  LLM_GENERATION_FAILED: "AI 生成失败，请重试",
  KNOWLEDGE_BASE_EMPTY: "知识库尚未导入，部分功能受限",
  RESOURCE_GENERATION_FAILED: "资源生成失败，请重试",
  PROFILE_NOT_FOUND: "学习档案未找到，请先完成入学诊断",
  GRADING_FAILED: "评分服务暂时不可用，请重试",
  INTERNAL_ERROR: "服务器内部错误，请稍后重试",
};

export function getFriendlyError(detail: string, errorCode?: string): string {
  if (errorCode && FRIENDLY_ERRORS[errorCode]) return FRIENDLY_ERRORS[errorCode];
  // Check if detail itself is a known error code
  if (FRIENDLY_ERRORS[detail]) return FRIENDLY_ERRORS[detail];
  // Filter out technical messages
  if (detail.includes("circuit breaker")) return FRIENDLY_ERRORS.LLM_CIRCUIT_OPEN;
  if (detail.includes("timed out") || detail.includes("timeout")) return FRIENDLY_ERRORS.LLM_TIMEOUT;
  if (detail.includes("API key")) return FRIENDLY_ERRORS.LLM_AUTH_FAILED;
  // Return original if it looks user-friendly (Chinese, short)
  if (/[一-鿿]/.test(detail) && detail.length < 100) return detail;
  return "请求失败，请重试";
}

function timeoutSignal(existing?: AbortSignal): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  if (existing) {
    existing.addEventListener("abort", () => { clearTimeout(timer); controller.abort(); });
  }
  return { signal: controller.signal, cleanup: () => clearTimeout(timer) };
}

async function handleResponse<T>(response: Response, path: string): Promise<T> {
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      clearAccessToken();
    }
    let detail = `${response.status} ${path}`;
    let errorCode: string | undefined;
    try {
      const body = await response.json();
      if (body?.detail) {
        if (Array.isArray(body.detail)) {
          detail = body.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ");
        } else {
          detail = String(body.detail);
        }
      }
      errorCode = body?.error_code;
    } catch { /* ignore */ }
    throw new Error(getFriendlyError(detail, errorCode));
  }
  const json = await response.json();
  return json.data as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const { signal, cleanup } = timeoutSignal();
  try {
    const response = await fetch(`${API_PREFIX}${path}`, {
      headers: buildHeaders(),
      signal,
    });
    return handleResponse<T>(response, `GET ${path}`);
  } finally {
    cleanup();
  }
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const { signal, cleanup } = timeoutSignal();
  try {
    const response = await fetch(`${API_PREFIX}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...buildHeaders()
      },
      body: JSON.stringify(injectModelOverrides(body)),
      signal,
    });
    return handleResponse<T>(response, `POST ${path}`);
  } finally {
    cleanup();
  }
}

export async function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  const { signal, cleanup } = timeoutSignal();
  try {
    const response = await fetch(`${API_PREFIX}${path}`, {
      method: "POST",
      headers: buildHeaders(),
      body: formData,
      signal,
    });
    return handleResponse<T>(response, `POST ${path}`);
  } finally {
    cleanup();
  }
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const { signal, cleanup } = timeoutSignal();
  try {
    const response = await fetch(`${API_PREFIX}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...buildHeaders() },
      body: JSON.stringify(body),
      signal,
    });
    return handleResponse<T>(response, `PATCH ${path}`);
  } finally {
    cleanup();
  }
}

export async function apiDelete<T>(path: string): Promise<T> {
  const { signal, cleanup } = timeoutSignal();
  try {
    const response = await fetch(`${API_PREFIX}${path}`, {
      method: "DELETE",
      headers: buildHeaders(),
      signal,
    });
    return handleResponse<T>(response, `DELETE ${path}`);
  } finally {
    cleanup();
  }
}

export async function apiPostStream(
  path: string,
  body: unknown,
  onEvent: (event: { type: string; data: unknown }) => void,
  signal?: AbortSignal
) {
  const STREAM_READ_TIMEOUT_MS = 120_000; // 2 minutes per-read timeout

  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildHeaders()
    },
    body: JSON.stringify(injectModelOverrides(body)),
    signal,
  });
  if (!response.ok || !response.body) {
    let detail = `POST ${path} failed: ${response.status}`;
    let errorCode: string | undefined;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
      errorCode = body?.error_code;
    } catch { /* ignore */ }
    throw new Error(getFriendlyError(detail, errorCode));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let eventName = "message";

  const flush = () => {
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let currentEvent = eventName;
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (dataLines.length) {
        const raw = dataLines.join("\n");
        try {
          onEvent({ type: currentEvent, data: JSON.parse(raw) as unknown });
        } catch {
          onEvent({ type: currentEvent, data: raw });
        }
      }
    }
  };

  while (true) {
    const readPromise = reader.read();
    const timeoutPromise = new Promise<never>((_, reject) => {
      const id = setTimeout(() => reject(new Error("SSE read timeout")), STREAM_READ_TIMEOUT_MS);
      signal?.addEventListener("abort", () => { clearTimeout(id); reject(new Error("aborted")); }, { once: true });
    });
    const { value, done } = await Promise.race([readPromise, timeoutPromise]);
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    flush();
  }

  buffer += decoder.decode();
  flush();
}

export async function apiTTS(text: string, voice?: string): Promise<Blob> {
  const token = getAccessToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_PREFIX}/tts/synthesize`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text, voice }),
  });
  if (!res.ok) {
    const detail = res.headers.get("X-Error") || "";
    if (res.status === 503 && detail.includes("Key")) {
      throw new Error("TTS_NOT_CONFIGURED");
    }
    throw new Error(detail || `TTS 请求失败: ${res.status}`);
  }
  return res.blob();
}
