import { addEventListener, definePlugin, removeEventListener, routerHook, toaster } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaRobot } from "react-icons/fa";
import { ChatPanel } from "./chat/ChatPanel";
import { SettingsRoute } from "./settings/SettingsRoute";
import type { BackendEvent } from "./types";

export default definePlugin(() => {
  routerHook.addRoute("/deckling/settings", SettingsRoute, { exact: true });
  const content = <ChatPanel />;
  if (typeof window !== "undefined") {
    (window as unknown as { __decklingQAM?: typeof content }).__decklingQAM = content;
  }
  const onEvent = addEventListener<[BackendEvent]>("deckling_event", (event) => {
    if (event.type === "toast" && event.message) {
      toaster.toast({ title: "Deckling", body: event.message, duration: 3000 });
    }
  });

  return {
    name: "Deckling",
    titleView: <div className={staticClasses.Title}>Deckling</div>,
    content,
    icon: <FaRobot />,
    onDismount() {
      removeEventListener("deckling_event", onEvent);
      routerHook.removeRoute("/deckling/settings");
    },
  };
});
