interface Props {
  h?: number;
  w?: number | string;
  className?: string;
}

export default function Skeleton({ h = 20, w, className = "" }: Props) {
  return (
    <div
      className={`animate-pulse rounded-[var(--radius-md)] bg-[var(--color-border)] ${className}`}
      style={{ height: h, width: w ?? "100%" }}
    />
  );
}
