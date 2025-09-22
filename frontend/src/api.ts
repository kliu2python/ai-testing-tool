import axios, { AxiosError } from "axios";
import type { ApiResult } from "./types";

export const API_BASE_DEFAULT = "http://localhost:8090";

export async function apiRequest<T = unknown>(
  baseUrl: string,
  method: "get" | "post",
  path: string,
  payload?: unknown
): Promise<ApiResult<T>> {
  const client = axios.create({
    baseURL: baseUrl.replace(/\/$/, ""),
    headers: { "Content-Type": "application/json" }
  });

  try {
    const response = await client.request<T>({
      url: path,
      method,
      data: payload
    });
    return {
      ok: true,
      status: response.status,
      data: response.data ?? null
    };
  } catch (error) {
    if (error instanceof AxiosError && error.response) {
      const { status, data } = error.response;
      const detail =
        typeof data === "object" && data !== null && "detail" in data
          ? String((data as { detail: unknown }).detail)
          : error.message;
      return { ok: false, status, data: data ?? null, error: detail };
    }
    const message =
      error instanceof Error ? error.message : "Unknown network error";
    return { ok: false, status: 0, data: null, error: message };
  }
}

export function formatPayload(payload: unknown): string {
  if (payload === null || payload === undefined) {
    return "";
  }
  try {
    return JSON.stringify(payload, null, 2);
  } catch (error) {
    return String(payload);
  }
}
