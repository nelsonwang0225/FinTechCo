import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Svg({ children, className = "", ...rest }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className={`icon ${className}`.trim()} {...rest}>
      {children}
    </svg>
  );
}

/* Navigation */
export function IconOverview(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </Svg>
  );
}
export function IconPayments(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="2.5" y="5" width="19" height="14" rx="2" />
      <path d="M2.5 10h19" />
      <path d="M6.5 15h4" />
    </Svg>
  );
}
export function IconPaymentHealth(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.5 12h4l2.5-6 4 12 2.5-6h6" />
    </Svg>
  );
}
export function IconPayouts(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 10 12 4l9 6" />
      <path d="M5 10v9M10 10v9M14 10v9M19 10v9" />
      <path d="M3 19h18" />
    </Svg>
  );
}
export function IconCustomers(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6" />
      <path d="M16 4.5a3.5 3.5 0 0 1 0 7" />
      <path d="M17.5 14c2.6.5 4 2.6 4 6" />
    </Svg>
  );
}
export function IconDisputes(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3 4.5 6v5.5c0 4.4 3.1 7.9 7.5 9.5 4.4-1.6 7.5-5.1 7.5-9.5V6L12 3Z" />
      <path d="M12 8.5v4" />
      <path d="M12 15.5h.01" />
    </Svg>
  );
}
export function IconReports(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h6" />
    </Svg>
  );
}
export function IconSettings(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h10M18 7h2" />
      <circle cx="16" cy="7" r="2" />
      <path d="M4 17h2M10 17h10" />
      <circle cx="8" cy="17" r="2" />
    </Svg>
  );
}

/* Controls */
export function IconChevronLeft(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m15 6-6 6 6 6" />
    </Svg>
  );
}
export function IconChevronRight(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m9 6 6 6-6 6" />
    </Svg>
  );
}
export function IconArrowUp(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 19V5" />
      <path d="m6 11 6-6 6 6" />
    </Svg>
  );
}
export function IconArrowDown(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 5v14" />
      <path d="m6 13 6 6 6-6" />
    </Svg>
  );
}
export function IconArrowUpDown(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m8 9 4-4 4 4" />
      <path d="m8 15 4 4 4-4" />
    </Svg>
  );
}
export function IconDownload(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 4v11" />
      <path d="m7 10 5 5 5-5" />
      <path d="M4 19h16" />
    </Svg>
  );
}
export function IconExternal(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 4h6v6" />
      <path d="M20 4 10 14" />
      <path d="M18 13v6H5V6h6" />
    </Svg>
  );
}
