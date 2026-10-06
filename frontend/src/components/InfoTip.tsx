import { useId } from "react";

/**
 * A small round "i" button that reveals a short definition on hover or keyboard focus. The definition is always in
 * the DOM (role="tooltip", referenced by aria-describedby), so assistive technology and tests can read it; CSS does
 * the showing and hiding (.infotip:hover / .infotip:focus-within).
 */
export function InfoTip({ text, label }: { text: string; label: string }) {
  const id = useId();
  const tipId = `${id}-tip`;
  return (
    <span className="infotip">
      <button type="button" className="infotip-button" aria-label={label} aria-describedby={tipId}>
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
