import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaRobot } from "react-icons/fa";
import { ChatPanel } from "./chat/ChatPanel";
import { SettingsRoute } from "./settings/SettingsRoute";

export default definePlugin(() => {
  routerHook.addRoute("/deckling/settings", SettingsRoute, { exact: true });
  const content = <ChatPanel />;
  if (typeof window !== "undefined") {
    (window as unknown as { __decklingQAM?: typeof content }).__decklingQAM = content;
  }

  return {
    name: "Deckling",
    titleView: <div className={staticClasses.Title}>Deckling</div>,
    content,
    icon: <FaRobot />,
    onDismount() {
      routerHook.removeRoute("/deckling/settings");
    },
  };
});
