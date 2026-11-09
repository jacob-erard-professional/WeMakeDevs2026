// Base URL for the FastAPI backend, read at build time. On the hosted web build it is
// `/api` on the same origin: nginx in frontend/Dockerfile forwards it to Service `backend`
// and strips the prefix, so `${API_BASE_URL}/health` reaches the backend's `/health`.
// Native builds cannot use a relative path and must set EXPO_PUBLIC_API_URL to an absolute URL.
export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? "/api").replace(/\/+$/, "");
