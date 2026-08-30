import { getSidecarConfig } from "@/services/tauri/sidecar";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(formatApiDetail(detail) || `HTTP ${status}`);
  }
}

function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  return "";
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
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? body.detail
        : response.statusText;
    throw new ApiError(response.status, detail);
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
