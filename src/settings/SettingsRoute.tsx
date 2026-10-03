import { SidebarNavigation } from "@decky/ui";
import { useEffect, useRef } from "react";
import { mountPageShell } from "./pageShell";
import { SettingsPage } from "./SettingsPage";

/**
 * Steam's settings shell keeps the action bar at the bottom of the window
 * and scrolls the page above it. A bare route did neither, so the bar was
 * drawn across the middle of the provider list.
 */
export function SettingsRoute() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) {
      return undefined;
    }
    return mountPageShell(node);
  }, []);
  return (
    <div ref={ref} style={{ width: "100%", minHeight: "100%", boxSizing: "border-box" }}>
      <SidebarNavigation
        title="Deckling"
        showTitle
        disableRouteReporting
        pages={[{ title: "Deckling", content: <SettingsPage />, hideTitle: true }]}
      />
    </div>
  );
}
