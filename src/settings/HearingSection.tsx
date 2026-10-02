import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { saveHearing } from "../api";
import type { HearingSettings } from "../types";

export function HearingSection({
  hearing,
  onHearing,
  onError,
}: {
  hearing: HearingSettings;
  onHearing: (hearing: HearingSettings) => void;
  onError: (message: string) => void;
}) {
  const save = async (patch: Partial<HearingSettings>) => {
    const result = await saveHearing(patch);
    if (!result.ok || !result.hearing) {
      onError(result.error || "Could not save listening settings");
      return;
    }
    onHearing(result.hearing);
  };

  const percent = Math.round(hearing.sensitivity * 100);

  return (
    <PanelSection title="Listening">
      <PanelSectionRow>
        <div>
          Wake word and speech recognition run on this Deck. Audio is not saved unless debug capture is on. Models
          download into the plugin data folder the first time you turn listening on.
        </div>
      </PanelSectionRow>
      <ButtonItem layout="below" onClick={() => void save({ wake_enabled: !hearing.wake_enabled })}>
        {hearing.wake_enabled ? "Wake word: on" : "Wake word: off"}
      </ButtonItem>
      <PanelSectionRow>
        <label>
          {`Sensitivity ${percent}%`}
          <input
            aria-label="Wake word sensitivity"
            type="range"
            min={0}
            max={100}
            value={percent}
            onChange={(event) => void save({ sensitivity: Number(event.target.value) / 100 })}
            style={{ width: "100%" }}
          />
        </label>
      </PanelSectionRow>
      {hearing.wake_models.map((item) => (
        <ButtonItem key={item.id} layout="below" onClick={() => void save({ wake_model: item.id })}>
          {hearing.wake_model === item.id ? `Wake word: ${item.label}` : item.label}
        </ButtonItem>
      ))}
      {hearing.stt_models.map((model) => (
        <ButtonItem key={model} layout="below" onClick={() => void save({ stt_model: model })}>
          {hearing.stt_model === model ? `Speech model: ${model}` : model}
        </ButtonItem>
      ))}
      <ButtonItem layout="below" onClick={() => void save({ ptt_enabled: !hearing.ptt_enabled })}>
        {hearing.ptt_enabled ? "Push to talk: on" : "Push to talk: off"}
      </ButtonItem>
      <ButtonItem layout="below" onClick={() => void save({ battery_saver: !hearing.battery_saver })}>
        {hearing.battery_saver ? "Pause while a game is running" : "Keep listening during games"}
      </ButtonItem>
      <ButtonItem layout="below" onClick={() => void save({ debug_audio: !hearing.debug_audio })}>
        {hearing.debug_audio ? "Debug audio: on" : "Debug audio: off"}
      </ButtonItem>
      {hearing.install_message ? (
        <PanelSectionRow>
          <div>{hearing.install_message}</div>
        </PanelSectionRow>
      ) : null}
      {hearing.wake_error ? (
        <PanelSectionRow>
          <div style={{ color: "#f2b8b5", whiteSpace: "pre-wrap" }}>{hearing.wake_error}</div>
        </PanelSectionRow>
      ) : null}
      <PanelSectionRow>
        <div>
          A custom “hey deckling” model is not bundled. Pick one of the openWakeWord models above. hey jarvis is the
          default. {hearing.idle_note}
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
}
