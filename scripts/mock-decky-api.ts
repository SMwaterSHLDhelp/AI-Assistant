type Call = (name: string, args: unknown[]) => Promise<unknown>;

function backend(): Call {
  const host = window as unknown as { __deckyCall?: Call };
  if (!host.__deckyCall) {
    throw new Error("Test harness did not install __deckyCall");
  }
  return host.__deckyCall;
}

export function callable(name: string): (...args: unknown[]) => Promise<unknown> {
  return async (...args: unknown[]) => {
    const value = await backend()(name, args);
    if (value && typeof value === "object" && "success" in value && "result" in value) {
      const packet = value as { success: boolean; result: unknown };
      if (!packet.success) {
        throw new Error(typeof packet.result === "string" ? packet.result : `${name} failed`);
      }
      return packet.result;
    }
    return value;
  };
}

export const toaster = {
  toast(notice: { title?: string; body?: string }) {
    const host = window as unknown as { __toasts?: Array<{ title?: string; body?: string }> };
    host.__toasts = host.__toasts || [];
    host.__toasts.push(notice);
  },
};

export function addEventListener(): () => void {
  return () => undefined;
}

export function removeEventListener(): void {
  return undefined;
}

export const routerHook = {
  addRoute() {
    return undefined;
  },
  removeRoute() {
    return undefined;
  },
};

export function definePlugin<T>(fn: T): T {
  return fn;
}
