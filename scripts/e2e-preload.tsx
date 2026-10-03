import * as React from "react";
import * as ReactDOM from "react-dom/client";
import * as JSX from "react/jsx-runtime";
import * as DFL from "./mock-decky-ui";

const host = window as unknown as Record<string, unknown>;
host.SP_REACT = React;
host.SP_REACTDOM = ReactDOM;
host.SP_JSX = JSX;
host.DFL = DFL;

host.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit = {
  connect(version: number) {
    return {
      _version: version,
      callable(method: string) {
        return async (...args: unknown[]) => {
          const bridge = window as unknown as {
            __deckyCall?: (name: string, args: unknown[]) => Promise<unknown>;
          };
          if (!bridge.__deckyCall) {
            throw new Error("Test harness did not install __deckyCall");
          }
          const value = await bridge.__deckyCall(method, args);
          if (value && typeof value === "object" && "success" in value && "result" in value) {
            const packet = value as { success: boolean; result: unknown };
            if (!packet.success) {
              throw new Error(typeof packet.result === "string" ? packet.result : `${method} failed`);
            }
            return packet.result;
          }
          return value;
        };
      },
      async call() {
        return {};
      },
      addEventListener() {
        return () => undefined;
      },
      removeEventListener() {
        return undefined;
      },
      routerHook: {
        addRoute(_path: string, component: unknown) {
          (window as unknown as { __decklingRoute?: unknown }).__decklingRoute = component;
        },
        removeRoute() {
          return undefined;
        },
      },
      toaster: {
        toast(notice: { title?: string; body?: string }) {
          const page = window as unknown as { __toasts?: Array<{ title?: string; body?: string }> };
          page.__toasts = page.__toasts || [];
          page.__toasts.push(notice);
        },
      },
    };
  },
};
