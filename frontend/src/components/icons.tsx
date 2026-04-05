import type { SVGProps } from "react";

/**
 * The raw book shapes as a <g> element, reused by both LabBook and LabBookPlus.
 * Expects to live inside a viewBox of "0 0 24 24" (or wider).
 */
function LabBookGlyph() {
  return (
    <g>
      {/* Book body */}
      <rect x="3" y="1" width="20" height="22" rx="1" />
      {/* Spine */}
      <line x1="5" y1="1" x2="5" y2="23" strokeWidth="6" strokeLinecap="butt" />
      {/* Title label */}
      <rect x="11" y="12" width="6" height="5" rx="0.5" />
    </g>
  );
}

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
      <LabBookGlyph />
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
      viewBox="0 0 28 28"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <defs>
        <mask id="book-mask">
          <rect width="28" height="28" fill="white" />
          {/* Cut out a square behind the plus badge */}
          <rect x="18" y="-1" width="12" height="12" rx="1" fill="black" />
        </mask>
      </defs>
      {/* Book body, masked to clear space for the badge */}
      <g mask="url(#book-mask)">
        <LabBookGlyph />
      </g>
      {/* Plus badge (upper right) */}
      <line x1="24" y1="1" x2="24" y2="9" />
      <line x1="20" y1="5" x2="28" y2="5" />
    </svg>
  );
}
