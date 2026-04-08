"use client";

interface Props {
  notice: string;
  error: string;
}

export function LiveFeedbackBanner({ notice, error }: Props) {
  if (!notice && !error) {
    return null;
  }

  return (
    <div
      className={
        error
          ? "rounded-lg bg-red-600/20 px-4 py-3 text-sm text-red-200"
          : "rounded-lg bg-emerald-600/20 px-4 py-3 text-sm text-emerald-200"
      }
    >
      {error || notice}
    </div>
  );
}
