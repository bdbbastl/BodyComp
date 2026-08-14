import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Schützt alle verschachtelten Routen - ohne gültige Session geht's
 * zurück zu /login. Während des ersten Ladens (noch kein isError/isSuccess)
 * wird nichts gerendert, um kein Flackern der Login-Seite zu erzeugen. */
export default function RequireAuth() {
  const { data: user, isLoading, isError } = useCurrentUser();

  if (isLoading) return null;
  if (isError || !user) return <Navigate to="/login" replace />;

  return <Outlet />;
}
