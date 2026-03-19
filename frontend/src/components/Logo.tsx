/**
 * Inline version of public/logo.svg.
 *
 * Only difference from the asset: the "Lab" text fill and the large-bubble
 * stroke use `currentColor` so the logo adapts to light/dark mode.
 * Bubble gradient fills are identical to the SVG asset.
 *
 * If you change the logo, update both this file and public/logo.svg.
 */
import type { SVGProps } from "react";

export function Logo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 222.136 79.563"
      xmlns="http://www.w3.org/2000/svg"
      xmlnsXlink="http://www.w3.org/1999/xlink"
      {...props}
    >
      <defs>
        <radialGradient
          id="b1" cx="284.2" cy="54.2" r="31.2"
          gradientUnits="userSpaceOnUse"
          gradientTransform="matrix(.8668 0 0 .8668 -78.395 -6.309)"
        >
          <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.9} />
          <stop offset="100%" stopColor="#7c3aed" stopOpacity={0.85} />
        </radialGradient>

        <radialGradient
          id="b2" cx="314.6" cy="28.6" r="21.6"
          gradientUnits="userSpaceOnUse"
          gradientTransform="matrix(.8668 0 0 .8668 -78.395 -6.309)"
        >
          <stop offset="0%" stopColor="#67e8f9" stopOpacity={0.9} />
          <stop offset="100%" stopColor="#06b6d4" stopOpacity={0.85} />
        </radialGradient>

        <radialGradient
          id="b3" cx="264.4" cy="24.4" r="14.4"
          gradientUnits="userSpaceOnUse"
          gradientTransform="matrix(.8668 0 0 .8668 -78.395 -6.309)"
        >
          <stop offset="0%" stopColor="#86efac" stopOpacity={0.9} />
          <stop offset="100%" stopColor="#22c55e" stopOpacity={0.85} />
        </radialGradient>

        <radialGradient id="sh" cx="0.3" cy="0.25" r="0.3">
          <stop offset="0%" stopColor="white" stopOpacity={0.7} />
          <stop offset="100%" stopColor="white" stopOpacity={0} />
        </radialGradient>

        <radialGradient
          xlinkHref="#sh" id="sh1"
          cx="281.6" cy="49" r="15.6"
          gradientUnits="userSpaceOnUse"
          gradientTransform="matrix(.8668 0 0 .8668 -78.395 -6.309)"
        />
        <radialGradient
          xlinkHref="#sh" id="sh2"
          cx="312.8" cy="25" r="10.8"
          gradientUnits="userSpaceOnUse"
          gradientTransform="matrix(.8668 0 0 .8668 -78.395 -6.309)"
        />
        <radialGradient
          xlinkHref="#sh" id="sh3"
          cx="263.2" cy="22" r="7.2"
          gradientUnits="userSpaceOnUse"
          gradientTransform="matrix(.8668 0 0 .8668 -78.395 -6.309)"
        />
      </defs>

      {/* "Lab" text */}
      <text
        x="2.039" y="66.988"
        fontFamily="'Helvetica Neue', Arial, sans-serif"
        fontSize="80px" fontWeight={700}
        fill="currentColor"
        letterSpacing={-1}
      >
        Lab
      </text>

      {/* Large bubble */}
      <circle cx="174.705" cy="47.431" r="22.536" fill="url(#b1)" />
      <circle
        cx="174.705" cy="47.431" r="22.536"
        fill="url(#sh1)"
        stroke="currentColor" strokeWidth={4.074}
        paintOrder="fill markers stroke"
      />

      {/* Medium bubble */}
      <circle cx="198.975" cy="23.161" r="15.602" fill="url(#b2)" />
      <circle cx="198.975" cy="23.161" r="15.602" fill="url(#sh2)" />

      {/* Small bubble */}
      <circle cx="153.902" cy="17.96" r="10.401" fill="url(#b3)" />
      <circle cx="153.902" cy="17.96" r="10.401" fill="url(#sh3)" />
    </svg>
  );
}
