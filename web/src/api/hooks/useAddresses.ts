import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../client";
import type { AddressCreateRequest, AddressOut, AddressUpdateRequest } from "../types";
import { useAuth } from "../../context/AuthContext";

const ADDRESSES_KEY = ["addresses"];

export function useAddresses() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ADDRESSES_KEY,
    queryFn: () => apiRequest<AddressOut[]>("/users/me/addresses"),
    enabled: isAuthenticated,
  });
}

export function useCreateAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AddressCreateRequest) =>
      apiRequest<AddressOut>("/users/me/addresses", { method: "POST", body: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  });
}

export function useUpdateAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ addressId, payload }: { addressId: string; payload: AddressUpdateRequest }) =>
      apiRequest<AddressOut>(`/users/me/addresses/${addressId}`, { method: "PATCH", body: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  });
}

export function useDeleteAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (addressId: string) => apiRequest<void>(`/users/me/addresses/${addressId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ADDRESSES_KEY }),
  });
}
