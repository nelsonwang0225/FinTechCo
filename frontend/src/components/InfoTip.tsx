import { useId, useState } from "react";

/**
 * A small round "i" button that reveals a short definition. The definition is always in the DOM (role="tooltip",
 * referenced by aria-describedby), so assistive technology and tests can read it. Showing is a real open state rather
 * than a CSS :hover rule: it opens on hover, keyboard focus or a click (touch devices do not reliably focus a tapped
 * button), stays open while the pointer is over the text, and closes on Escape, blur or leaving the control, which is
 * what WCAG 1.4.13 asks of content shown on hover or focus.
 */
export function InfoTip({ text, label }: { text: string; label: string }) {
  const id = useId();
  const tipId = `${id}-tip`;
  const [open, setOpen] = useState(false);
  return (
    <span
      className={open ? "infotip infotip-open" : "infotip"}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      <button type="button" className="infotip-button" aria-label={label} aria-describedby={tipId} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <svg className="infotip-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <circle cx="8" cy="8" r="6.75" />
          <path d="M8 7.25v4" />
          <circle cx="8" cy="4.9" r="0.75" className="infotip-icon-dot" />
        </svg>
      </button>
      <span role="tooltip" id={tipId} className="infotip-text">
        {text}
      </span>
    </span>
  );
}
