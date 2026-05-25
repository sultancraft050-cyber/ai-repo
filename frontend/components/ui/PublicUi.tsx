import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cx, focusRing, interactiveButton, motionSafeSpin } from "@/lib/uiClasses";

type NoticeTone = "info" | "success" | "caution" | "danger";
type BadgeTone = "neutral" | "success" | "info" | "caution" | "danger";

const noticeToneClasses: Record<NoticeTone, string> = {
  info: "border-line bg-panel text-muted",
  success: "border-teal-200 bg-teal-50 text-signal",
  caution: "border-amber-200 bg-amber-50 text-caution",
  danger: "border-danger/40 bg-danger/10 text-danger"
};

const badgeToneClasses: Record<BadgeTone, string> = {
  neutral: "border-line bg-panel text-muted",
  success: "border-teal-200 bg-teal-50 text-signal",
  info: "border-sky-300/30 bg-sky-400/10 text-sky-200",
  caution: "border-amber-200 bg-amber-50 text-caution",
  danger: "border-danger/40 bg-danger/10 text-danger"
};

const noticeIcons: Record<NoticeTone, ReactNode> = {
  info: <Info size={16} aria-hidden />,
  success: <CheckCircle2 size={16} aria-hidden />,
  caution: <AlertTriangle size={16} aria-hidden />,
  danger: <XCircle size={16} aria-hidden />
};

export function CalmNotice({
  title,
  children,
  details,
  tone = "info",
  className
}: {
  title: string;
  children?: ReactNode;
  details?: ReactNode;
  tone?: NoticeTone;
  className?: string;
}) {
  return (
    <div className={cx("rounded-md border px-3 py-2 text-sm leading-6", noticeToneClasses[tone], className)}>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0">{noticeIcons[tone]}</span>
        <div className="min-w-0">
          <div className="font-semibold">{title}</div>
          {children ? <div className="mt-0.5 opacity-90">{children}</div> : null}
          {details ? (
            <details className="mt-2">
              <summary className={cx("w-fit text-xs font-semibold", interactiveButton, focusRing)}>Details</summary>
              <div className="mt-2 text-xs leading-5 opacity-80">{details}</div>
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function StateBadge({ children, tone = "neutral", className }: { children: ReactNode; tone?: BadgeTone; className?: string }) {
  return (
    <span className={cx("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold", badgeToneClasses[tone], className)}>
      {children}
    </span>
  );
}

export function SkeletonBlock({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <div
      className={cx("rounded-md border border-line bg-panel motion-safe:animate-pulse motion-reduce:animate-none", className)}
      role="status"
      aria-label={label}
    />
  );
}

export function IconButton({
  label,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        "inline-grid h-9 w-9 place-items-center rounded-md border border-line bg-panel text-muted hover:border-signal hover:text-ink active:bg-[#101827]",
        interactiveButton,
        focusRing,
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export { focusRing, interactiveButton, motionSafeSpin, cx };
