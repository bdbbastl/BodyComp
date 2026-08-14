import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";

export default function Settings() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const queryClient = useQueryClient();
  const [newPoseName, setNewPoseName] = useState("");
  const [editing, setEditing] = useState<Record<number, string>>({});

  const posesQuery = useQuery({
    queryKey: ["poses", clientIdNum],
    queryFn: () => api.poses.list(clientIdNum),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["poses", clientIdNum] });

  const createMutation = useMutation({
    mutationFn: (name: string) => api.poses.create(clientIdNum, name),
    onSuccess: () => {
      setNewPoseName("");
      invalidate();
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      api.poses.update(clientIdNum, id, { name }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.poses.remove(clientIdNum, id),
    onSuccess: invalidate,
  });

  const poses = posesQuery.data ?? [];
  const MAX_POSES = 20;

  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="Settings" />

      <div className="rounded-xl border border-white/5 bg-surface p-4">
        <ul className="divide-y divide-white/5">
          {poses.map((pose, index) => {
            const editValue = editing[pose.id] ?? pose.name;
            const isDirty = editValue !== pose.name;
            return (
              <li key={pose.id} className="flex items-center gap-2 py-2">
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-accent"
                  title={`Position ${index + 1} - erscheint so in allen Pose-Dropdowns`}
                >
                  {index + 1}
                </span>
                <input
                  value={editValue}
                  onChange={(e) => setEditing((s) => ({ ...s, [pose.id]: e.target.value }))}
                  className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white focus:border-accent focus:outline-none"
                />
                {isDirty && (
                  <button
                    onClick={() =>
                      renameMutation.mutate({ id: pose.id, name: editValue.trim() })
                    }
                    disabled={!editValue.trim()}
                    className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
                  >
                    Speichern
                  </button>
                )}
                <button
                  onClick={() => {
                    if (confirm(`Pose "${pose.name}" wirklich löschen?`)) {
                      deleteMutation.mutate(pose.id);
                    }
                  }}
                  className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/10"
                >
                  Löschen
                </button>
              </li>
            );
          })}
        </ul>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (newPoseName.trim()) createMutation.mutate(newPoseName.trim());
          }}
          className="mt-4 flex gap-2 border-t border-white/5 pt-4"
        >
          <input
            value={newPoseName}
            onChange={(e) => setNewPoseName(e.target.value)}
            placeholder="Neue Pose, z.B. Vacuum Pose"
            disabled={poses.length >= MAX_POSES}
            className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none disabled:opacity-40"
          />
          <button
            type="submit"
            disabled={!newPoseName.trim() || poses.length >= MAX_POSES}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Hinzufügen
          </button>
        </form>
        {poses.length >= MAX_POSES && (
          <p className="mt-2 text-xs text-slate-500">Maximale Anzahl von {MAX_POSES} Posen erreicht.</p>
        )}
      </div>
    </div>
  );
}
