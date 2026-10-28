export function Emblem({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="ft-gold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f6d58b" />
          <stop offset="1" stopColor="#b8862f" />
        </linearGradient>
      </defs>
      <path d="M16 2 28 8v8c0 7-5.2 12.3-12 14C9.2 28.3 4 23 4 16V8z" fill="#141c2c" stroke="url(#ft-gold)" strokeWidth="1.6" />
      <path d="M11 9h10M11 9v14M11 15.5h7" stroke="url(#ft-gold)" strokeWidth="2.4" strokeLinecap="round" fill="none" />
      <circle cx="21.5" cy="21.5" r="2" fill="url(#ft-gold)" />
    </svg>
  );
}
