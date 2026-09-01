import { useState } from "react";
import { Copy, KeyRound, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { Badge, Button, Card, Input } from "@/components/ui/primitives";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/overlays";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/States";
import { useToast } from "@/hooks/useToast";
import { useCreateProject, useProjects, useRevokeProject, useRotateKey } from "@/api/queries";
import type { CreatedProject } from "@/api/types";
import { fmtInt, fmtRelative, fmtUsd } from "@/lib/utils";

export function ProjectsPage() {
  const q = useProjects();
  const [revealed, setRevealed] = useState<CreatedProject | null>(null);

  return (
    <div>
      <PageHeader
        title="API Keys / Projects"
        description="One key per project. The full key is shown once, at creation — it cannot be retrieved again."
        actions={<CreateProjectDialog onCreated={setRevealed} />}
      />

      {q.isLoading ? (
        <LoadingBlock />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data?.projects.length ? (
        <EmptyState title="No projects yet" hint="Create your first API key to start routing traffic." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Project</TH>
              <TH>API key</TH>
              <TH className="text-right">Requests</TH>
              <TH className="text-right">Cost</TH>
              <TH className="text-right">Rate limit</TH>
              <TH>Last used</TH>
              <TH>Status</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {q.data.projects.map((p) => (
              <TR key={p.id}>
                <TD className="font-medium">{p.name}</TD>
                <TD className="font-mono text-xs text-text-muted">{p.key_prefix}••••</TD>
                <TD className="text-right tabular-nums">{fmtInt(p.requests)}</TD>
                <TD className="text-right tabular-nums">{fmtUsd(p.cost_usd)}</TD>
                <TD className="text-right tabular-nums">{p.rate_limit_per_minute}/min</TD>
                <TD className="text-text-muted">{fmtRelative(p.last_used_at)}</TD>
                <TD>
                  <Badge tone={p.status === "active" ? "ok" : "err"}>{p.status}</Badge>
                </TD>
                <TD>
                  <RowActions id={p.id} name={p.name} disabled={p.status !== "active"} onRotated={setRevealed} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <RevealKeyDialog project={revealed} onClose={() => setRevealed(null)} />
    </div>
  );
}

function CreateProjectDialog({ onCreated }: { onCreated: (p: CreatedProject) => void }) {
  const create = useCreateProject();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [limit, setLimit] = useState(60);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <KeyRound className="size-4" /> New API key
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create project</DialogTitle>
          <DialogDescription>A new API key is generated and shown once.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(
              { name, rate_limit_per_minute: limit },
              {
                onSuccess: (p) => {
                  setOpen(false);
                  setName("");
                  onCreated(p);
                  toast({ tone: "ok", title: "Project created", description: p.name });
                },
                onError: () =>
                  toast({ tone: "err", title: "Couldn't create the project" }),
              },
            );
          }}
        >
          <div className="space-y-1">
            <label className="text-xs font-medium text-text-muted" htmlFor="new-project-name">
              Project name
            </label>
            <Input
              id="new-project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-text-muted" htmlFor="new-project-limit">
              Rate limit (req/min)
            </label>
            <Input
              id="new-project-limit"
              type="number"
              min={1}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            />
          </div>
          {create.isError && (
            <div className="rounded bg-err-bg px-3 py-2 text-xs text-err">Could not create project.</div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <DialogClose asChild>
              <Button type="button" variant="outline" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={create.isPending || !name}>
              {create.isPending && <Loader2 className="size-4 animate-spin" />}
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RowActions({
  id,
  name,
  disabled,
  onRotated,
}: {
  id: string;
  name: string;
  disabled: boolean;
  onRotated: (p: CreatedProject) => void;
}) {
  const rotate = useRotateKey();
  const revoke = useRevokeProject();
  const { toast } = useToast();
  const [confirm, setConfirm] = useState<null | "rotate" | "revoke">(null);

  return (
    <div className="flex justify-end gap-1">
      <Dialog open={confirm === "rotate"} onOpenChange={(v) => setConfirm(v ? "rotate" : null)}>
        <DialogTrigger asChild>
          <Button size="icon" variant="ghost" disabled={disabled} title="Rotate key">
            <RotateCcw className="size-4" />
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rotate key for “{name}”?</DialogTitle>
            <DialogDescription>
              The current key stops working immediately. A new key is shown once.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button
              size="sm"
              disabled={rotate.isPending}
              onClick={() =>
                rotate.mutate(id, {
                  onSuccess: (p) => {
                    setConfirm(null);
                    onRotated(p);
                    toast({ tone: "ok", title: "Key rotated", description: name });
                  },
                  onError: () => toast({ tone: "err", title: "Couldn't rotate the key" }),
                })
              }
            >
              {rotate.isPending && <Loader2 className="size-4 animate-spin" />}
              Rotate
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={confirm === "revoke"} onOpenChange={(v) => setConfirm(v ? "revoke" : null)}>
        <DialogTrigger asChild>
          <Button size="icon" variant="ghost" disabled={disabled} title="Revoke">
            <Trash2 className="size-4 text-err" />
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke “{name}”?</DialogTitle>
            <DialogDescription>
              This permanently disables the key. Requests using it will be rejected with 401.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button
              size="sm"
              variant="danger"
              disabled={revoke.isPending}
              onClick={() =>
                revoke.mutate(id, {
                  onSuccess: () => {
                    setConfirm(null);
                    toast({ tone: "ok", title: "Project revoked", description: name });
                  },
                  onError: () => toast({ tone: "err", title: "Couldn't revoke the project" }),
                })
              }
            >
              {revoke.isPending && <Loader2 className="size-4 animate-spin" />}
              Revoke
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RevealKeyDialog({
  project,
  onClose,
}: {
  project: CreatedProject | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Dialog open={!!project} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Copy this key now</DialogTitle>
          <DialogDescription>
            It won’t be shown again. Store it somewhere safe.
          </DialogDescription>
        </DialogHeader>
        <Card className="flex items-center gap-2 bg-bg-subtle p-3">
          <code className="flex-1 break-all font-mono text-xs">{project?.api_key}</code>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => {
              if (project) navigator.clipboard?.writeText(project.api_key);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            <Copy className="size-4" />
          </Button>
        </Card>
        {copied && <div className="text-xs text-ok">Copied to clipboard.</div>}
        <div className="flex justify-end pt-2">
          <Button size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
