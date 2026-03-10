import type { SVGProps } from "react";

/**
 * A symbolic lab-notebook icon: hardbound book with spine and title label.
 * Designed to sit alongside Lucide icons at the same sizes (14, 16, etc.).
 */
export function LabBook({
  size = 16,
  className,
  ...props
}: { size?: number; className?: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Book body */}
      <rect x="3" y="1" width="20" height="22" rx="1" />
      {/* Spine */}
      <line x1="5" y1="1" x2="5" y2="23" strokeWidth="6" strokeLinecap="butt"/>
      {/* Title label */}
      <rect x="11" y="12" width="6" height="5" rx="0.5" />
    </svg>
  );
}

/**
 * Lab-notebook with a small "+" badge — used for "New Notebook" actions.
 */
export function LabBookPlus({
  size = 16,
  className,
  ...props
}: { size?: number; className?: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Book body */}
      <rect x="5" y="2" width="14" height="20" rx="1" />
      {/* Spine */}
      <line x1="8" y1="2" x2="8" y2="22" />
      {/* Title label */}
      <rect x="11" y="6" width="6" height="5" rx="0.5" />
      {/* Plus sign */}
      <line x1="14" y1="16" x2="14" y2="20" />
      <line x1="12" y1="18" x2="16" y2="18" />
    </svg>
  );
}
