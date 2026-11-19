// A flat crest in the interface gold with an F cut into it.
export function Emblem({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={`text-primary ${className}`} aria-hidden="true">
      <path d="M16 2.5 27 6.6V15c0 7-4.8 12.4-11 14.5C9.8 27.4 5 22 5 15V6.6z" fill="currentColor" />
      <path
        d="M12.2 9.8h7.8M12.2 9.8v12.4M12.2 15.6h5.8"
        style={{ stroke: "var(--background)" }}
        strokeWidth="2.6"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}
