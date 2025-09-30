import axios, { AxiosError } from "axios";
import type { ApiResult } from "./types";

export const API_BASE_DEFAULT = "http://ai-ui-test.qa.fortinet-us.com:8090";

type HttpMethod = "get" | "post" | "delete" | "patch";

function normaliseBaseUrl(baseUrl: string): string {
  const trimmed = baseUrl.trim();
  if (!trimmed) {
    return "";
  }

  const hasScheme = /^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(trimmed);
  if (hasScheme) {
    return trimmed;
  }
  return `http://${trimmed}`;
}

export async function apiRequest<T = unknown>(
  baseUrl: string,
  method: HttpMethod,
  path: string,
  payload?: unknown,
  token?: string | null
): Promise<ApiResult<T>> {
  const baseURL = normaliseBaseUrl(baseUrl).replace(/\/$/, "");
  const client = axios.create({
    baseURL,
    headers: { "Content-Type": "application/json" }
  });

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  try {
    const response = await client.request<T>({
      url: path,
      method,
      data: payload,
      headers
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
