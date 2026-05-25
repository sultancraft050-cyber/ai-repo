export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/80 focus-visible:ring-offset-2 focus-visible:ring-offset-[#080f1f]";

export const interactiveButton =
  "cursor-pointer transition-colors duration-150 motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-60";

export const motionSafeSpin = "motion-safe:animate-spin motion-reduce:animate-none";
