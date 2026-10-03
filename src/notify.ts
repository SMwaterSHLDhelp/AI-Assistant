import { toaster } from "@decky/api";
import { logClient } from "./api";

export function reportFailure(message: string): void {
  toaster.toast({ title: "Deckling", body: message, duration: 5000 });
  void logClient(message).catch(() => undefined);
}

export function reportSaved(message: string): void {
  toaster.toast({ title: "Deckling", body: message, duration: 3000 });
}
