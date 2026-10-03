import { Focusable } from "@decky/ui";
import { useRef, type ReactNode } from "react";

/**
 * Steam's A button calls onActivate / onOKButton on the focused row.
 * Touch calls the inner button's onClick. One guard covers both so a single
 * press cannot fire twice.
 */
export function DeckRow({
  children,
  onClick,
  disabled,
  description,
}: {
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  description?: ReactNode;
  layout?: string;
}) {
  const last = useRef(0);
  const run = () => {
    if (disabled || !onClick) {
      return;
    }
    const now = Date.now();
    if (now - last.current < 300) {
      return;
    }
    last.current = now;
    onClick();
  };
  return (
    <Focusable onActivate={run} onOKButton={run}>
      <button type="button" disabled={disabled} onClick={run} style={{ width: "100%", textAlign: "left" }}>
        <div>{children}</div>
        {description ? <div style={{ opacity: 0.8, fontSize: "14px" }}>{description}</div> : null}
      </button>
    </Focusable>
  );
}
