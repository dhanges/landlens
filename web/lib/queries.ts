"use client";

/** TanStack Query hooks over lib/api.ts. Query keys live here so invalidation stays in one place. */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "@/lib/api";

export const keys = {
  me: ["me"] as const,
  summary: (id: number) => ["parcel", id, "summary"] as const,
  report: (id: number) => ["parcel", id, "report"] as const,
  options: ["screener", "options"] as const,
  screener: (f: api.ScreenerFilters, sort: api.SortKey, order?: "asc" | "desc") =>
    ["screener", "page", f, sort, order ?? null] as const,
  count: (f: api.ScreenerFilters) => ["screener", "count", f] as const,
  ledger: ["ledger"] as const,
  villageTrend: (id: number, lt?: api.LandType) => ["trend", "village", id, lt ?? null] as const,
  mandalTrend: (id: number, lt?: api.LandType) => ["trend", "mandal", id, lt ?? null] as const,
  search: (q: string) => ["search", q] as const,
};

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: api.me, staleTime: 60_000 });

/** After anything that changes the balance or unlocks: refresh me, the ledger and parcel queries. */
export function useInvalidateAccount() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.me });
    qc.invalidateQueries({ queryKey: keys.ledger });
    qc.invalidateQueries({ queryKey: ["parcel"] });
  };
}

export function useAuth(kind: "login" | "signup") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      kind === "login" ? api.login(email, password) : api.signup(email, password),
    onSuccess: (user) => {
      qc.setQueryData(keys.me, user);
      qc.invalidateQueries({ queryKey: ["parcel"] });
      qc.invalidateQueries({ queryKey: keys.ledger });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      qc.setQueryData(keys.me, null);
      qc.removeQueries({ queryKey: keys.ledger });
      qc.invalidateQueries({ queryKey: ["parcel"] });
    },
  });
}

export const useSummary = (id: number | null) =>
  useQuery({ queryKey: keys.summary(id ?? 0), queryFn: () => api.parcelSummary(id!), enabled: id != null });

export const useReport = (id: number, enabled: boolean) =>
  useQuery({ queryKey: keys.report(id), queryFn: () => api.parcelReport(id), enabled, staleTime: 5 * 60_000 });

export const useScreenerOptions = () =>
  useQuery({ queryKey: keys.options, queryFn: api.screenerOptions, staleTime: 10 * 60_000 });

export function useScreener(filters: api.ScreenerFilters, sort: api.SortKey, order?: "asc" | "desc") {
  return useInfiniteQuery({
    queryKey: keys.screener(filters, sort, order),
    queryFn: ({ pageParam, signal }) =>
      api.screener({ filters, sort, order, cursor: pageParam, limit: 50 }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

/** Match count for the pending (not yet applied) filters: page 1 with limit 1 carries approx_total. */
export const useScreenerCount = (filters: api.ScreenerFilters) =>
  useQuery({
    queryKey: keys.count(filters),
    queryFn: ({ signal }) => api.screener({ filters, limit: 1 }, signal).then((p) => p.approx_total),
    placeholderData: (prev) => prev,
  });

export function useLedger(enabled: boolean) {
  return useInfiniteQuery({
    queryKey: keys.ledger,
    queryFn: ({ pageParam }) => api.ledger(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled,
  });
}

export const useVillageTrend = (id: number | null, lt?: api.LandType) =>
  useQuery({
    queryKey: keys.villageTrend(id ?? 0, lt),
    queryFn: () => api.villageTrend(id!, lt),
    enabled: id != null,
  });

export const useMandalTrend = (id: number | null, lt?: api.LandType) =>
  useQuery({
    queryKey: keys.mandalTrend(id ?? 0, lt),
    queryFn: () => api.mandalTrend(id!, lt),
    enabled: id != null,
  });

export const useSearch = (q: string) =>
  useQuery({
    queryKey: keys.search(q),
    queryFn: ({ signal }) => api.search(q, signal),
    enabled: q.trim().length >= 2,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });
