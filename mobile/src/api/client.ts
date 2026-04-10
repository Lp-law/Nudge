import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { BACKEND_URL } from "../config";
import { getAccessToken } from "../store/secureStorage";

/**
 * Pre-configured Axios instance that automatically attaches the
 * Bearer access token to every outgoing request.
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: BACKEND_URL,
  timeout: 60_000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response) {
      const detail = error.response.data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : typeof detail === "object" && detail?.message
            ? detail.message
            : error.message;
      return Promise.reject(new Error(message));
    }
    return Promise.reject(error);
  },
);

export default apiClient;
