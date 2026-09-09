import { apiErrorMessage } from "@/services/http/apiErrorMessage";
import { getSidecarConfig } from "@/services/tauri/sidecar";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
    public readonly code?: string,
    public readonly params?: Record<string, unknown>,
  ) {
    super(
      apiErrorMessage(code, typeof detail === "string" ? detail : "", params) ||
        `HTTP ${status}`,
    );
  }
}

export async function apiRequest(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const { baseUrl, token } = await getSidecarConfig();
  const headers = new Headers(init?.headers);
  // FormData 自带分隔符 Content-Type；二进制体（头像字节）不是 JSON，均不强加 JSON 头。
  const isRawBody =
    init?.body instanceof FormData ||
    init?.body instanceof Blob ||
    init?.body instanceof ArrayBuffer ||
    ArrayBuffer.isView(init?.body);
  if (!isRawBody) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-KnowRealm-Token", token);
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const record = isRecord(body) ? body : undefined;
    const detail =
      record && "detail" in record ? record.detail : response.statusText;
    const code = typeof record?.code === "string" ? record.code : undefined;
    const params = isRecord(record?.params) ? record.params : undefined;
    throw new ApiError(response.status, detail, code, params);
  }

  return response;
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  // OpenAPI types are the compile-time authority; FastAPI validates the runtime payload.
  return (await apiRequest(path, init)).json() as Promise<T>;
}

export async function apiFetchNoContent(
  path: string,
  init?: RequestInit,
): Promise<void> {
  await apiRequest(path, init);
}
