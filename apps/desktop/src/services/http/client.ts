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
  if (Array.isArray(detail)) {
    return detail
      .flatMap((item) =>
        typeof item === "object" && item !== null && "msg" in item
          ? [String(item.msg)]
          : [],
      )
      .join("；");
  }
  return "";
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const { baseUrl, token } = await getSidecarConfig();
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
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

  // OpenAPI types are the compile-time authority; FastAPI validates the runtime payload.
  return response.json() as Promise<T>;
}
