import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Schützt /admin/* - dieselbe Logik wie RequireAuth, zusätzlich muss
 * is_admin true sein. Bewusst KEIN Unterschied in der Fehlerbehandlung
 * zwischen "nicht eingeloggt" und "kein Admin" - beides landet auf
 * /login, um die Existenz des Admin-Bereichs nicht zu verraten (siehe
 * Design-Spec "Master-Admin-Dashboard"). */
export default function AdminGuard() {
  const { data: user, isLoading, isError } = useCurrentUser();

  if (isLoading) return null;
  if (isError || !user || !user.is_admin) return <Navigate to="/login" replace />;

  return <Outlet />;
}
