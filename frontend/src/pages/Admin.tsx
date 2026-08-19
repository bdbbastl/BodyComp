import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card } from "../components/Card";

const ACTIVITY_LABEL: Record<string, string> = {
  active: "🟢 Active",
  inactive: "⚪ Inactive",
  never: "— Never",
};

export default function Admin() {
  const [search, setSearch] = useState("");

  const overviewQuery = useQuery({ queryKey: ["admin", "overview"], queryFn: api.admin.overview });
  const accountsQuery = useQuery({ queryKey: ["admin", "accounts"], queryFn: api.admin.listAccounts });

  const filteredAccounts = (accountsQuery.data ?? []).filter((a) =>
    a.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-background px-6 py-8 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <h1 className="text-2xl font-semibold text-white">Admin</h1>

        {overviewQuery.data && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <Card title="Total Accounts">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.total_accounts}</p>
            </Card>
            <Card title="Single">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.single_accounts}</p>
            </Card>
            <Card title="Coach">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.coach_accounts}</p>
            </Card>
            <Card title="Active Subs">
              <p className="text-2xl font-semibold text-white">{overviewQuery.data.active_subscriptions}</p>
            </Card>
            <Card title="Signups (7d / 30d)">
              <p className="text-2xl font-semibold text-white">
                {overviewQuery.data.signups_this_week} / {overviewQuery.data.signups_this_month}
              </p>
            </Card>
          </div>
        )}

        <Card title="Accounts">
          <input
            type="text"
            placeholder="Search by email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mb-4 w-full max-w-sm rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-400">
                <tr>
                  <th className="pb-2 pr-4">Email</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Signup</th>
                  <th className="pb-2 pr-4">Subscription</th>
                  <th className="pb-2 pr-4">Clients</th>
                  <th className="pb-2 pr-4">Activity</th>
                  <th className="pb-2 pr-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredAccounts.map((a) => (
                  <tr key={a.id} className="border-t border-white/5">
                    <td className="py-2 pr-4">
                      <Link to={`/admin/accounts/${a.id}`} className="text-accent hover:underline">
                        {a.email}
                      </Link>
                    </td>
                    <td className="py-2 pr-4">{a.account_type}</td>
                    <td className="py-2 pr-4">{new Date(a.created_at).toLocaleDateString("en-US")}</td>
                    <td className="py-2 pr-4">{a.subscription_tier ?? "—"}</td>
                    <td className="py-2 pr-4">{a.client_count}</td>
                    <td className="py-2 pr-4">{ACTIVITY_LABEL[a.activity_status]}</td>
                    <td className="py-2 pr-4">
                      {a.is_active ? (
                        <span className="text-green-400">Active</span>
                      ) : (
                        <span className="text-red-400">Disabled</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
