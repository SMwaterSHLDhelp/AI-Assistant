import { useEffect, useRef, useState, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

export function ButtonItem({
  children,
  onClick,
  disabled,
}: {
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

export function PanelSection({ title, children }: { title?: string; children?: ReactNode }) {
  return (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function PanelSectionRow({ children }: { children?: ReactNode }) {
  return <div>{children}</div>;
}

type MountWindow = Window & {
  __fieldSeq?: number;
  __fieldMounts?: Record<string, number>;
};

export function TextField({
  label,
  value,
  onChange,
}: {
  label?: string;
  value?: string;
  onChange?: (event: { target: { value: string } }) => void;
}) {
  const keyRef = useRef("");
  if (!keyRef.current) {
    const win = window as MountWindow;
    win.__fieldSeq = (win.__fieldSeq || 0) + 1;
    keyRef.current = `${label || "field"}#${win.__fieldSeq}`;
  }
  useEffect(() => {
    const win = window as MountWindow;
    const mounts = (win.__fieldMounts = win.__fieldMounts || {});
    mounts[keyRef.current] = (mounts[keyRef.current] || 0) + 1;
  }, []);
  return (
    <label>
      {label}
      <input
        aria-label={label || ""}
        data-mount-key={keyRef.current}
        value={value ?? ""}
        onChange={(event) => onChange?.({ target: { value: event.target.value } })}
      />
    </label>
  );
}

export function Focusable({
  children,
  onActivate,
  onOKButton,
}: {
  children?: ReactNode;
  onActivate?: () => void;
  onOKButton?: () => void;
}) {
  return (
    <div
      tabIndex={0}
      data-deck-row="1"
      onKeyDown={(event) => {
        if (event.key !== "Enter") {
          return;
        }
        event.preventDefault();
        onActivate?.();
        onOKButton?.();
      }}
    >
      {children}
    </div>
  );
}

export function ConfirmModal() {
  return null;
}

export function ModalRoot({
  children,
  onCancel,
}: {
  children?: ReactNode;
  onCancel?: () => void;
}) {
  return (
    <div role="dialog" className="deckling-dialog">
      {children}
      <button type="button" onClick={onCancel}>
        Close
      </button>
    </div>
  );
}

export function DialogHeader({ children }: { children?: ReactNode }) {
  return <h1>{children}</h1>;
}

export function DialogBody({ children }: { children?: ReactNode }) {
  return <div>{children}</div>;
}

export function DialogFooter({ children }: { children?: ReactNode }) {
  return <footer>{children}</footer>;
}

export function DialogButton({
  children,
  onClick,
  disabled,
}: {
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

export function SidebarNavigation({
  children,
  pages,
  title,
}: {
  children?: ReactNode;
  pages?: ({ title?: ReactNode; content?: ReactNode } | "separator")[];
  title?: ReactNode;
}) {
  const real = (pages || []).filter((page): page is { title?: ReactNode; content?: ReactNode } => page !== "separator");
  const [index, setIndex] = useState(0);
  const current = Math.min(index, Math.max(real.length - 1, 0));
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }
      if (event.key === "ArrowRight" || event.key === "PageDown") {
        setIndex((value) => Math.min(real.length - 1, value + 1));
      }
      if (event.key === "ArrowLeft" || event.key === "PageUp") {
        setIndex((value) => Math.max(0, value - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [real.length]);
  return (
    <div>
      <div role="tablist" aria-label={typeof title === "string" ? title : "Settings"}>
        {real.map((page, pageIndex) => (
          <button
            key={pageIndex}
            type="button"
            role="tab"
            aria-selected={pageIndex === current}
            onClick={() => setIndex(pageIndex)}
          >
            {page.title}
          </button>
        ))}
      </div>
      <div>{real[current]?.content}</div>
      {children}
    </div>
  );
}

export function DropdownItem() {
  return null;
}

let modalRoot: Root | null = null;

export function showModal(node: ReactNode) {
  let host = document.getElementById("deckling-modal");
  if (!host) {
    host = document.createElement("div");
    host.id = "deckling-modal";
    document.body.appendChild(host);
  }
  modalRoot ??= createRoot(host);
  const close = () => {
    modalRoot?.render(null);
  };
  modalRoot.render(node);
  return {
    Close: close,
    Update: (next: ReactNode) => {
      modalRoot?.render(next);
    },
  };
}

export const Navigation = {
  NavigateBack() {
    return undefined;
  },
  Navigate() {
    return undefined;
  },
  NavigateToExternalWeb() {
    return undefined;
  },
  CloseSideMenus() {
    return undefined;
  },
};

export const staticClasses = { Title: "title" };
export const Router = { MainRunningApp: null };
