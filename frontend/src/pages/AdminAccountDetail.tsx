import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { Card } from "../components/Card";

export default function AdminAccountDetail() {
  const { userId } = useParams<{ userId: string }>();
  const userIdNum = Number(userId);
  const queryClient = useQueryClient();

  const accountQuery = useQuery({
    queryKey: ["admin", "accounts", userIdNum],
    queryFn: () => api.admin.getAccount(userIdNum),
    enabled: !Number.isNaN(userIdNum),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (isActive: boolean) => api.admin.setAccountActive(userIdNum, isActive),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "accounts", userIdNum] });
      queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] });
    },
  });

  if (accountQuery.isLoading) {
    return <div className="min-h-screen bg-background px-6 py-8 text-slate-400">Loading…</div>;
  }
  if (accountQuery.isError) {
    // Unterscheidet einen echten Fehler (Netzwerk/500) von "existiert
    // nicht" (404, siehe unten) - beides mit "Account not found." zu
    // beschriften wäre irreführend (Code-Review nach Task 5).
    return (
      <div className="min-h-screen bg-background px-6 py-8 text-slate-400">
        Could not load this account. Please try again.
      </div>
    );
  }
  if (!accountQuery.data) {
    return <div className="min-h-screen bg-background px-6 py-8 text-slate-400">Account not found.</div>;
  }

  const account = accountQuery.data;

  return (
    <div className="min-h-screen bg-background px-6 py-8 text-slate-100">
      <div className="mx-auto max-w-3xl space-y-6">
        <Link to="/admin" className="text-sm text-accent hover:underline">
          ← Back to accounts
        </Link>
        <h1 className="text-2xl font-semibold text-white">{account.email}</h1>

        <Card title="Account">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-slate-400">Type</dt>
            <dd className="text-white">{account.account_type}</dd>
            <dt className="text-slate-400">Signup</dt>
            <dd className="text-white">{new Date(account.created_at).toLocaleDateString("en-US")}</dd>
            <dt className="text-slate-400">Subscription</dt>
            <dd className="text-white">
              {account.subscription_tier ?? "—"} ({account.subscription_status ?? "none"})
            </dd>
            <dt className="text-slate-400">Status</dt>
            <dd className={account.is_active ? "text-green-400" : "text-red-400"}>
              {account.is_active ? "Active" : "Disabled"}
            </dd>
          </dl>
          <button
            onClick={() => toggleActiveMutation.mutate(!account.is_active)}
            disabled={toggleActiveMutation.isPending}
            className={`mt-4 rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50 ${
              account.is_active
                ? "bg-red-900/40 text-red-300 hover:bg-red-900/60"
                : "bg-accent text-slate-900 hover:opacity-90"
            }`}
          >
            {toggleActiveMutation.isPending
              ? "Saving…"
              : account.is_active
                ? "Deactivate account"
                : "Reactivate account"}
          </button>
        </Card>

        <Card title="Clients">
          {account.clients.length === 0 && <p className="text-sm text-slate-500">No clients.</p>}
          <ul className="space-y-2">
            {account.clients.map((c) => (
              <li key={c.id} className="flex items-center justify-between text-sm">
                <span className="text-white">{c.name}</span>
                <span className="text-slate-400">
                  {c.photo_count} photos ·{" "}
                  {c.last_activity_at
                    ? new Date(c.last_activity_at).toLocaleDateString("en-US")
                    : "no activity"}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
