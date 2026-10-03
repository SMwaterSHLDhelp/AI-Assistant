import { SettingsPage } from "./SettingsPage";

/** Full-screen Steam page. SidebarNavigation switches tabs with L1/R1. */
export function SettingsRoute() {
  return <SettingsPage layout="tabs" />;
}
