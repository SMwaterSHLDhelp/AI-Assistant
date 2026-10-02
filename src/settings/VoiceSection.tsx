import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { retryKitten, saveVoice, testVoice } from "../api";
import type { VoiceSettings } from "../types";

const SPEEDS = [0.8, 1, 1.25, 1.5];

export function VoiceSection({
  voice,
  onVoice,
  onError,
  onNotice,
}: {
  voice: VoiceSettings;
  onVoice: (voice: VoiceSettings) => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const save = async (patch: Partial<VoiceSettings>) => {
    const result = await saveVoice(patch);
    if (!result.ok || !result.voice) {
      onError(result.error || "Could not save voice settings");
      return;
    }
    onVoice(result.voice);
  };

  const voices = voice.voice_engine === "kittentts" ? voice.kitten_voices : voice.piper_voices;
  const selected = voice.voice_engine === "kittentts" ? voice.kitten_voice : voice.piper_voice;

  return (
    <PanelSection title="Voice">
      <PanelSectionRow>
        <div>Spoken replies stay off until you turn them on. The voice download waits for the first test or the first reply.</div>
      </PanelSectionRow>
      <ButtonItem layout="below" onClick={() => void save({ voice_enabled: !voice.voice_enabled })}>
        {voice.voice_enabled ? "Voice replies: on" : "Voice replies: off"}
      </ButtonItem>
      <ButtonItem layout="below" onClick={() => void save({ voice_engine: "piper" })}>
        {voice.voice_engine === "piper" ? "Engine: Piper" : "Use Piper"}
      </ButtonItem>
      <ButtonItem
        layout="below"
        onClick={() => void save({ voice_engine: "kittentts" })}
        description={voice.kitten_error || "Smaller neural voices. Piper stays available if this cannot install."}
      >
        {voice.voice_engine === "kittentts" ? "Engine: KittenTTS" : "Use KittenTTS"}
      </ButtonItem>
      {voice.kitten_error ? (
        <ButtonItem layout="below" onClick={() => void retry()}>
          Try KittenTTS again
        </ButtonItem>
      ) : null}
      {voices.map((id) => (
        <ButtonItem
          key={id}
          layout="below"
          onClick={() => void save(voice.voice_engine === "kittentts" ? { kitten_voice: id } : { piper_voice: id })}
        >
          {selected === id ? `Voice: ${id}` : id}
        </ButtonItem>
      ))}
      {SPEEDS.map((speed) => (
        <ButtonItem key={speed} layout="below" onClick={() => void save({ voice_speed: speed })}>
          {voice.voice_speed === speed ? `Speed: ${speed}` : `Speed ${speed}`}
        </ButtonItem>
      ))}
      <ButtonItem layout="below" onClick={() => void test()}>
        Test voice
      </ButtonItem>
      <ButtonItem layout="below" onClick={() => void save({ screen_capture: !voice.screen_capture })}>
        {voice.screen_capture ? "Screen capture: on" : "Screen capture: off"}
      </ButtonItem>
      <PanelSectionRow>
        <div>Screenshots are sent only to the provider you picked, and only when you ask about the screen. They are not saved unless you press Save screenshot.</div>
      </PanelSectionRow>
    </PanelSection>
  );

  async function test() {
    onNotice("Speaking a test line…");
    const result = await testVoice();
    if (result.voice) {
      onVoice(result.voice);
    }
    if (!result.ok) {
      onError(result.error || "Could not play the test voice");
      return;
    }
    onNotice(result.warning || "Played the test line.");
  }

  async function retry() {
    const result = await retryKitten();
    if (result.voice) {
      onVoice(result.voice);
    }
    if (!result.ok) {
      onError(result.error || "KittenTTS could not be installed. Piper is still available.");
      return;
    }
    onNotice("KittenTTS is ready. Pick it as the engine, then test the voice.");
  }
}
