/**
 * InferMesh brand mark — a gateway hub linked to three provider nodes (the
 * "inference mesh"). Pure `currentColor` so it takes the colour of its context:
 * drop it in the accent tile (`text-accent-fg`) or use it standalone
 * (`text-accent`).
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" aria-hidden="true">
      <g stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" opacity="0.85">
        <path d="M16 16.6 16 7.6" />
        <path d="M16 16.6 8 23" />
        <path d="M16 16.6 24 23" />
      </g>
      <g fill="currentColor">
        <circle cx="16" cy="16.6" r="3.4" />
        <circle cx="16" cy="7.6" r="2.7" />
        <circle cx="8" cy="23" r="2.7" />
        <circle cx="24" cy="23" r="2.7" />
      </g>
    </svg>
  );
}
