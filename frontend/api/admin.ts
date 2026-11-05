import type {
  BookingSeason,
  Cabin,
  CabinUpdate,
  Document as CabinDocument,
  Rate,
  RateUpdate,
  Shareholder,
  ShareholderUpdate,
} from "../types";
import { ApiError, apiRequest, jsonRequest } from "./client";

export const adminApi = {
  currentSeason: async (signal?: AbortSignal) => {
    try {
      return await apiRequest<BookingSeason>("/api/booking-seasons/current", { signal });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  seasons: (signal?: AbortSignal) =>
    apiRequest<BookingSeason[]>("/api/booking-seasons", { signal }),
  createSeason: <T>(input: T) =>
    apiRequest<BookingSeason>("/api/booking-seasons", jsonRequest("POST", input)),
  updateSeason: <T>(id: number, input: T) =>
    apiRequest<BookingSeason>(`/api/booking-seasons/${id}`, jsonRequest("PUT", input)),
  deleteSeason: (id: number) =>
    apiRequest<void>(`/api/booking-seasons/${id}`, { method: "DELETE" }),
  shareholders: (signal?: AbortSignal) =>
    apiRequest<Shareholder[]>("/api/shareholders", { signal }),
  updateShareholder: (id: number, update: ShareholderUpdate) =>
    apiRequest<Shareholder>(`/api/shareholders/${id}`, jsonRequest("PUT", update)),
  deleteShareholder: (id: number) =>
    apiRequest<void>(`/api/shareholders/${id}`, { method: "DELETE" }),
  cabins: (signal?: AbortSignal) => apiRequest<Cabin[]>("/api/cabins", { signal }),
  createCabin: <T>(input: T) => apiRequest<Cabin>("/api/cabins", jsonRequest("POST", input)),
  updateCabin: (id: string, update: CabinUpdate) =>
    apiRequest<Cabin>(`/api/cabins/${id}`, jsonRequest("PUT", update)),
  deleteCabin: (id: string) => apiRequest<void>(`/api/cabins/${id}`, { method: "DELETE" }),
  rates: (signal?: AbortSignal) => apiRequest<Rate[]>("/api/rates", { signal }),
  createRate: <T>(input: T) => apiRequest<Rate>("/api/rates", jsonRequest("POST", input)),
  updateRate: (id: number, update: RateUpdate) =>
    apiRequest<Rate>(`/api/rates/${id}`, jsonRequest("PUT", update)),
  deleteRate: (id: number) => apiRequest<void>(`/api/rates/${id}`, { method: "DELETE" }),
  documents: (signal?: AbortSignal) => apiRequest<CabinDocument[]>("/api/documents", { signal }),
  createDocument: <T>(input: T) => apiRequest<CabinDocument>("/api/documents", jsonRequest("POST", input)),
  updateDocument: <T>(id: number, input: T) =>
    apiRequest<CabinDocument>(`/api/documents/${id}`, jsonRequest("PUT", input)),
  deleteDocument: (id: number) => apiRequest<void>(`/api/documents/${id}`, { method: "DELETE" }),
  timeTravelStatus: (signal?: AbortSignal) => apiRequest<{
    active: boolean;
    simulated_date: string | null;
    real_date: string | null;
  }>("/api/time-travel", { signal }),
  setTimeTravel: (date: string) => apiRequest<{
    active: boolean;
    simulated_date: string | null;
    real_date: string | null;
  }>("/api/time-travel", jsonRequest("POST", { date })),
  resetTimeTravel: () => apiRequest<{
    active: boolean;
    simulated_date: string | null;
    real_date: string | null;
  }>("/api/time-travel", { method: "DELETE" }),
};
