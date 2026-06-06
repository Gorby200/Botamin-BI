interface Props {
  variant?: "default" | "positive" | "negative" | "warning" | "accent";
  children: React.ReactNode;
  className?: string;
}

const VARIANT_STYLES: Record<string, string> = {
  default: "bg-[var(--color-bg-card-hover)] text-[var(--color-ink-secondary)]",
  positive: "bg-[oklch(0.92_0.05_145)] text-[oklch(0.35_0.12_145)]",
  negative: "bg-[oklch(0.92_0.04_25)] text-[oklch(0.40_0.12_25)]",
  warning: "bg-[var(--color-secondary-subtle)] text-[var(--color-secondary)]",
  accent: "bg-[var(--color-accent-subtle)] text-[var(--color-accent)]",
};

export default function Badge({ variant = "default", children, className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${VARIANT_STYLES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
