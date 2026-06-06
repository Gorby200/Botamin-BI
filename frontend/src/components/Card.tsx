import type { ReactNode } from "react";

interface Props {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
  noPad?: boolean;
}

export default function Card({ title, subtitle, children, action, icon, className = "", noPad }: Props) {
  return (
    <div
      className={`rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-[var(--shadow-card)] ${className}`}
    >
      <div className="flex items-start justify-between px-5 pt-5 pb-3">
        <div className="flex items-start gap-2.5">
          {icon && <div className="mt-0.5">{icon}</div>}
          <div>
            <h3
              className="text-base font-medium text-[var(--color-ink)]"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {title}
            </h3>
            {subtitle && (
              <p className="mt-0.5 text-xs text-[var(--color-ink-tertiary)]">{subtitle}</p>
            )}
          </div>
        </div>
        {action}
      </div>
      <div className={noPad ? "" : "px-5 pb-5"}>{children}</div>
    </div>
  );
}
