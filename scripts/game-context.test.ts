import assert from "node:assert/strict";
import { collectGame, achievementsFrom } from "../src/gameContext.ts";

const steamApp = {
  appid: 1245620,
  display_name: "Elden Ring",
  minutes_playtime_forever: 400,
  rt_last_time_played: 1_700_000_000,
  compat_tool_name: "proton-9.0-4",
};

const collected = collectGame({
  app: steamApp,
  richPresence: { status: "Act 2 - The Forest" },
  achievements: [
    { name: "First Blood", achieved: true },
    { name: "The Forest", achieved: false },
  ],
  recentScreenshot: true,
  now: 1_700_000_000_000,
});

assert.equal(collected.name, "Elden Ring");
assert.equal(collected.appid, 1245620);
assert.equal(collected.shortcut, false);
assert.equal(collected.rich_presence, "Act 2 - The Forest");
assert.equal(collected.achievements_unlocked, 1);
assert.equal(collected.achievements_total, 2);
assert.deepEqual(collected.recent_achievements, ["First Blood"]);
assert.equal(collected.next_achievement, "The Forest");
assert.equal(collected.compat_tool, "proton-9.0-4");
assert.equal(collected.recent_screenshot, true);
assert.ok(collected.sources.includes("rich-presence"));
assert.ok(collected.sources.includes("achievements"));
assert.ok(collected.sources.includes("compat"));
assert.ok(collected.sources.includes("screenshot"));

const shortcut = collectGame({
  app: {
    appid: 2147483648,
    app_type: 1073741824,
    display_name: "RetroArch",
    strShortcutExe: "/usr/bin/retroarch",
    strShortcutLaunchOptions: '"/home/deck/Emulation/roms/gba/Pokemon_Emerald.gba"',
  },
  now: 1_700_000_000_000,
});
assert.equal(shortcut.shortcut, true);
assert.equal(shortcut.exe, "/usr/bin/retroarch");
assert.match(shortcut.launch_options, /Pokemon_Emerald\.gba/);

const summary = achievementsFrom({ unlocked: 3, total: 9, recent: ["A"], next: "B" });
assert.equal(summary.unlocked, 3);
assert.equal(summary.total, 9);
assert.equal(summary.next, "B");

console.log("game context client check passed");
