/** Read the running game from Steam. Missing client methods are skipped. */

export interface GameSnapshot {
  appid: number;
  name: string;
  shortcut: boolean;
  exe: string;
  launch_options: string;
  playtime_minutes: number | null;
  session_started: number | null;
  last_played: number | null;
  rich_presence: string;
  achievements_unlocked: number | null;
  achievements_total: number | null;
  recent_achievements: string[];
  next_achievement: string;
  compat_tool: string;
  recent_screenshot: boolean;
  sources: string[];
}

type Bag = Record<string, unknown>;

const SHORTCUT_TYPE = 1073741824;
const sessionStart = new Map<number, number>();

export function emptySnapshot(): GameSnapshot {
  return {
    appid: 0,
    name: "",
    shortcut: false,
    exe: "",
    launch_options: "",
    playtime_minutes: null,
    session_started: null,
    last_played: null,
    rich_presence: "",
    achievements_unlocked: null,
    achievements_total: null,
    recent_achievements: [],
    next_achievement: "",
    compat_tool: "",
    recent_screenshot: false,
    sources: [],
  };
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function numberOf(value: unknown): number | null {
  const number = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(number) || number < 0) {
    return null;
  }
  return Math.floor(number);
}

function firstText(app: Bag, keys: string[]): string {
  for (const key of keys) {
    const value = textOf(app[key]);
    if (value) {
      return value;
    }
  }
  return "";
}

function presenceText(value: unknown): string {
  if (typeof value === "string") {
    return value.trim().slice(0, 160);
  }
  if (!value || typeof value !== "object") {
    return "";
  }
  const record = value as Bag;
  for (const key of ["status", "steam_display", "richPresence", "localized"]) {
    const text = textOf(record[key]);
    if (text) {
      return text.slice(0, 160);
    }
  }
  const parts = Object.values(record)
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .slice(0, 3);
  return parts.join(" · ").slice(0, 160);
}

function achievementName(item: Bag): string {
  return firstText(item, ["name", "strName", "displayName", "apiName", "strID"]);
}

export function achievementsFrom(value: unknown): {
  unlocked: number | null;
  total: number | null;
  recent: string[];
  next: string;
} {
  if (Array.isArray(value)) {
    const rows = value.filter((item): item is Bag => Boolean(item) && typeof item === "object");
    const unlocked = rows.filter((item) => Boolean(item.achieved || item.unlocked || item.bAchieved));
    const locked = rows.filter((item) => !item.achieved && !item.unlocked && !item.bAchieved);
    return {
      unlocked: unlocked.length,
      total: rows.length,
      recent: unlocked
        .slice(-3)
        .map(achievementName)
        .filter(Boolean),
      next: locked[0] ? achievementName(locked[0]) : "",
    };
  }
  if (value && typeof value === "object") {
    const record = value as Bag;
    const recent = Array.isArray(record.recent) ? record.recent.map((item) => textOf(item)).filter(Boolean) : [];
    return {
      unlocked: numberOf(record.unlocked ?? record.nAchieved ?? record.unlockedCount),
      total: numberOf(record.total ?? record.nTotal ?? record.totalCount),
      recent: recent.slice(0, 3),
      next: textOf(record.next || record.nextName),
    };
  }
  return { unlocked: null, total: null, recent: [], next: "" };
}

export function collectGame(
  input: {
    app?: Bag | null;
    richPresence?: unknown;
    achievements?: unknown;
    compat?: unknown;
    recentScreenshot?: boolean;
    now?: number;
  },
): GameSnapshot {
  const app = input.app || {};
  const appid = numberOf(app.appid ?? app.unAppID ?? app.nAppId) ?? 0;
  const appType = numberOf(app.app_type ?? app.appType);
  const shortcut = Boolean(app.shortcut || app.BIsShortcut || appType === SHORTCUT_TYPE || appid >= 2_000_000_000);
  const name = firstText(app, ["display_name", "strDisplayName", "app_name", "name"]);
  const playtime = numberOf(app.minutes_playtime_forever ?? app.nPlaytimeForever ?? app.minutes_played);
  const lastPlayed = numberOf(app.rt_last_time_played ?? app.rtLastPlayed ?? app.last_played);
  const achievements = achievementsFrom(input.achievements);
  const compat =
    textOf(input.compat) ||
    (input.compat && typeof input.compat === "object"
      ? firstText(input.compat as Bag, ["name", "strToolName", "version"])
      : "") ||
    firstText(app, ["compat_tool_name", "selected_compat_tool"]);
  const now = input.now ?? Date.now();
  let started: number | null = null;
  if (appid && name) {
    if (!sessionStart.has(appid)) {
      sessionStart.set(appid, Math.floor(now / 1000));
    }
    started = sessionStart.get(appid) ?? null;
  }
  const sources = ["router"];
  const rich = presenceText(input.richPresence);
  if (rich) {
    sources.push("rich-presence");
  }
  if (achievements.total) {
    sources.push("achievements");
  }
  if (compat) {
    sources.push("compat");
  }
  if (input.recentScreenshot) {
    sources.push("screenshot");
  }
  return {
    appid,
    name,
    shortcut,
    exe: firstText(app, ["strShortcutExe", "executable", "strExePath", "exe"]),
    launch_options: firstText(app, ["strShortcutLaunchOptions", "launch_options", "strLaunchOptions"]),
    playtime_minutes: playtime,
    session_started: started,
    last_played: lastPlayed,
    rich_presence: rich,
    achievements_unlocked: achievements.unlocked,
    achievements_total: achievements.total,
    recent_achievements: achievements.recent,
    next_achievement: achievements.next,
    compat_tool: compat,
    recent_screenshot: Boolean(input.recentScreenshot),
    sources,
  };
}

async function tryCall(owner: Bag | undefined, names: string[], args: unknown[]): Promise<unknown> {
  if (!owner) {
    return undefined;
  }
  for (const name of names) {
    const fn = owner[name];
    if (typeof fn !== "function") {
      continue;
    }
    try {
      const result = (fn as (...values: unknown[]) => unknown).apply(owner, args);
      if (result && typeof (result as Promise<unknown>).then === "function") {
        return await Promise.race([
          result as Promise<unknown>,
          new Promise((resolve) => {
            window.setTimeout(() => resolve(undefined), 400);
          }),
        ]);
      }
      return result;
    } catch {
      // This Steam build uses a different method name.
    }
  }
  return undefined;
}

export async function readLiveGame(now = Date.now()): Promise<GameSnapshot> {
  try {
    const steam = (window as unknown as { SteamClient?: Bag }).SteamClient;
    const router = (window as unknown as { SteamUIStore?: { MainRunningApp?: Bag } }).SteamUIStore;
    const deckyRouter = (await import("@decky/ui")).Router as { MainRunningApp?: Bag | null };
    const app = (deckyRouter?.MainRunningApp || router?.MainRunningApp || null) as Bag | null;
    if (!app) {
      return emptySnapshot();
    }
    const appid = numberOf(app.appid ?? app.unAppID ?? app.nAppId) ?? 0;
    const apps = steam?.Apps as Bag | undefined;
    const [richPresence, achievements, compat, screenshot] = await Promise.all([
      tryCall(apps, ["GetRichPresence", "GetAppRichPresence"], [appid]),
      tryCall(apps, ["GetMyAchievementsForApp", "GetAchievements", "GetAchievementProgress"], [appid]),
      tryCall(apps, ["GetCompatToolInfo", "GetCompatTool"], [appid]),
      tryCall(steam?.Screenshots as Bag | undefined, ["GetLastScreenshot", "GetRecentScreenshot"], [appid]),
    ]);
    return collectGame({
      app,
      richPresence,
      achievements,
      compat,
      recentScreenshot: Boolean(screenshot),
      now,
    });
  } catch {
    return emptySnapshot();
  }
}
