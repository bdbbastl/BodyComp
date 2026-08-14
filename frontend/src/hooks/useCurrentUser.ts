import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/** Lädt den eingeloggten Account. `enabled` steuert React Query's
 * Retry-Verhalten nicht direkt - ein 401 wird hier bewusst NICHT als
 * Query-Error behandelt, sondern über `isError`/`data === undefined`
 * geprüft, damit die aufrufende Seite entscheiden kann, ob sie zum
 * Login redirected. */
export function useCurrentUser() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.auth.me,
    retry: false,
  });
}
