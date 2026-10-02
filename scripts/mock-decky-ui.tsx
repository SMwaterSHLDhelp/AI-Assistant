import type { ReactNode } from "react";

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

export function TextField({
  label,
  value,
  onChange,
}: {
  label?: string;
  value?: string;
  onChange?: (event: { target: { value: string } }) => void;
}) {
  return (
    <label>
      {label}
      <input
        aria-label={label || ""}
        value={value ?? ""}
        onChange={(event) => onChange?.({ target: { value: event.target.value } })}
      />
    </label>
  );
}

export function Focusable({ children }: { children?: ReactNode }) {
  return <div>{children}</div>;
}

export function ConfirmModal() {
  return null;
}

export function DropdownItem() {
  return null;
}

export function showModal(): void {
  return undefined;
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
