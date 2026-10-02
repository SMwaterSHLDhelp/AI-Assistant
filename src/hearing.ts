/** Steam + X holds the microphone when the controller API exists. Steam + Y stays the screen chord. */

type SteamRecord = Record<string, unknown>;

type SteamClient = {
  Input?: SteamRecord;
  Controller?: SteamRecord;
  System?: SteamRecord;
};

export function bindHearingChord(onFire: () => void): () => void {
  return bindChord(["guide", "face_x"], "Push to talk", onFire);
}

export function bindSleep(onChange: (sleeping: boolean) => void): () => void {
  const system = steamClient()?.System;
  if (!system) {
    return () => {};
  }
  const offs: Array<() => void> = [];
  const pairs: Array<[string, boolean]> = [
    ["RegisterForOnSuspendRequest", true],
    ["RegisterForOnSuspend", true],
    ["RegisterForOnResume", false],
  ];
  for (const [name, sleeping] of pairs) {
    const register = system[name];
    if (typeof register !== "function") {
      continue;
    }
    try {
      const token = (register as (this: SteamRecord, cb: () => void) => unknown).call(system, () => onChange(sleeping));
      offs.push(() => {
        const unregister = system.UnregisterForOnSuspendRequest || system.UnregisterForOnResume;
        if (typeof unregister === "function") {
          try {
            (unregister as (this: SteamRecord, value: unknown) => void).call(system, token);
          } catch {
            // The registration is already gone.
          }
        }
      });
    } catch {
      // This Steam build does not expose that sleep hook.
    }
  }
  return () => {
    for (const off of offs) {
      off();
    }
  };
}

function bindChord(buttons: string[], description: string, onFire: () => void): () => void {
  const steam = steamClient();
  const owners = [steam?.Input, steam?.Controller];
  for (const owner of owners) {
    if (!owner) {
      continue;
    }
    const register = owner.RegisterForControllerAction || owner.RegisterForControllerChord;
    if (typeof register !== "function") {
      continue;
    }
    try {
      const token = (register as (this: SteamRecord, spec: unknown, cb: () => void) => unknown).call(
        owner,
        { buttons, description },
        onFire,
      );
      return () => {
        const unregister = owner.UnregisterForControllerAction || owner.UnregisterForControllerChord;
        if (typeof unregister === "function") {
          try {
            (unregister as (this: SteamRecord, value: unknown) => void).call(owner, token);
          } catch {
            // The chord registration is already gone.
          }
        }
      };
    } catch {
      // This Steam build does not expose that registration call.
    }
  }
  return () => {};
}

function steamClient(): SteamClient | undefined {
  return (window as unknown as { SteamClient?: SteamClient }).SteamClient;
}
