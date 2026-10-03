import { DialogBody, DialogFooter, DialogHeader, ModalRoot } from "@decky/ui";
import { useEffect, type ReactNode } from "react";

const STYLE_ID = "deckling-dialog-style";

/**
 * Provider dialogs scroll inside the dialog. Save stays in the dialog footer,
 * above Steam's action bar, instead of at the end of an unbounded list.
 */
export function SettingsDialog({
  title,
  onClose,
  footer,
  children,
}: {
  title: string;
  onClose: () => void;
  footer: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    if (document.getElementById(STYLE_ID)) {
      return;
    }
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      ".deckling-dialog {",
      "  max-height: calc(100vh - 96px) !important;",
      "  display: flex !important;",
      "  flex-direction: column !important;",
      "  box-sizing: border-box !important;",
      "  margin-bottom: 72px !important;",
      "}",
    ].join("\n");
    document.head.appendChild(style);
  }, []);
  return (
    <ModalRoot onCancel={onClose} bDisableBackgroundDismiss modalClassName="deckling-dialog">
      <DialogHeader>{title}</DialogHeader>
      <DialogBody style={{ overflowY: "auto", maxHeight: "calc(100vh - 220px)" }}>{children}</DialogBody>
      <DialogFooter>{footer}</DialogFooter>
    </ModalRoot>
  );
}
