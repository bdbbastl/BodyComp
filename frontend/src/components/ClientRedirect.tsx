import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

/**
 * Root-Route ("/") für eingeloggte Accounts: `single` geht direkt in das
 * eine automatisch angelegte Client-Profil, `coach` sieht das Dashboard
 * (siehe Design-Spec Abschnitt "Kontotyp").
 */
export default function ClientRedirect() {
  const { data: user } = useCurrentUser();
  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.clients.list });

  if (user?.account_type === "coach") {
    return <Navigate to="/dashboard" replace />;
  }

  if (clientsQuery.isLoading) return null;
  const firstClient = clientsQuery.data?.[0];
  if (!firstClient) return null; // sollte nie passieren - jeder Account hat mind. einen Client

  return <Navigate to={`/clients/${firstClient.id}/timeline`} replace />;
}
