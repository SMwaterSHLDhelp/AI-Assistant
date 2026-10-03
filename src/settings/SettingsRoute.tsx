import { SidebarNavigation } from "@decky/ui";
import { SettingsPage } from "./SettingsPage";

/**
 * Steam's settings shell keeps the action bar at the bottom of the window
 * and scrolls the page above it.
 */
export function SettingsRoute() {
  return (
    <SidebarNavigation
      title="Deckling"
      showTitle
      disableRouteReporting
      pages={[{ title: "Deckling", content: <SettingsPage />, hideTitle: true }]}
    />
  );
}
