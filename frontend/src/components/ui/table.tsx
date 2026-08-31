import * as React from "react";
import { cn } from "@/lib/utils";

export function Table({
  className,
  scrollLabel = "Table",
  ...props
}: React.HTMLAttributes<HTMLTableElement> & { scrollLabel?: string }) {
  return (
    // tabIndex + role make the horizontally-scrollable region reachable by keyboard
    <div
      role="region"
      aria-label={scrollLabel}
      tabIndex={0}
      className="w-full overflow-x-auto rounded-lg border border-border focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
    >
      <table className={cn("w-full border-collapse text-sm", className)} {...props} />
    </div>
  );
}
export function THead(props: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className="bg-bg-subtle text-xs uppercase tracking-wide text-text-faint" {...props} />;
}
export function TBody(props: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className="divide-y divide-border" {...props} />;
}
export function TR({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors", className)} {...props} />;
}
export function TH({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("whitespace-nowrap px-3 py-2.5 text-left font-medium", className)} {...props} />;
}
export function TD({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("whitespace-nowrap px-3 py-2.5 align-middle", className)} {...props} />;
}
