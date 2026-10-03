import { PanelSection, PanelSectionRow } from "@decky/ui";
import { retryKitten, saveVoice, testVoice } from "../api";
import { DeckRow } from "../DeckRow";
import { errorMessage } from "../retry";
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
    try {
      const result = await saveVoice(patch);
      if (!result.ok || !result.voice) {
        onError(result.error || "Could not save voice settings");
        return;
      }
      onVoice(result.voice);
    } catch (err) {
      onError(errorMessage(err, "Could not save voice settings"));
    }
  };

  const engine = voice.voice_enabled ? voice.voice_engine : "off";
  const voices = voice.voice_engine === "kittentts" ? voice.kitten_voices : voice.piper_voices;
  const selected = voice.voice_engine === "kittentts" ? voice.kitten_voice : voice.piper_voice;

  return (
    <PanelSection title="Spoken replies">
      <PanelSectionRow>
        <div>Pick an engine. Voice, speed, and the test line show up for that engine only.</div>
      </PanelSectionRow>
      <DeckRow layout="below" onClick={() => void save({ voice_enabled: false })}>
        {engine === "off" ? "Spoken replies: off" : "Turn spoken replies off"}
      </DeckRow>
      <DeckRow layout="below" onClick={() => void save({ voice_enabled: true, voice_engine: "piper" })}>
        {engine === "piper" ? "Engine: Piper" : "Use Piper"}
      </DeckRow>
      <DeckRow
        layout="below"
        onClick={() => void save({ voice_enabled: true, voice_engine: "kittentts" })}
        description={voice.kitten_error || "Smaller neural voices. Piper stays available if this cannot install."}
      >
        {engine === "kittentts" ? "Engine: KittenTTS" : "Use KittenTTS"}
      </DeckRow>
      {engine === "kittentts" && voice.kitten_error ? (
        <DeckRow layout="below" onClick={() => void retry()}>
          Try KittenTTS again
        </DeckRow>
      ) : null}
      {engine !== "off"
        ? voices.map((id) => (
            <DeckRow
              key={id}
              layout="below"
              onClick={() => void save(voice.voice_engine === "kittentts" ? { kitten_voice: id } : { piper_voice: id })}
            >
              {selected === id ? `Voice: ${id}` : id}
            </DeckRow>
          ))
        : null}
      {engine !== "off"
        ? SPEEDS.map((speed) => (
            <DeckRow key={speed} layout="below" onClick={() => void save({ voice_speed: speed })}>
              {voice.voice_speed === speed ? `Speed: ${speed}` : `Speed ${speed}`}
            </DeckRow>
          ))
        : null}
      {engine !== "off" ? (
        <DeckRow layout="below" onClick={() => void test()}>
          Test voice
        </DeckRow>
      ) : null}
    </PanelSection>
  );

  async function test() {
    onNotice("Speaking a test line…");
    try {
      const result = await testVoice();
      if (result.voice) {
        onVoice(result.voice);
      }
      if (!result.ok) {
        onError(result.error || "Could not play the test voice");
        return;
      }
      onNotice(result.warning || "Played the test line.");
    } catch (err) {
      onError(errorMessage(err, "Could not play the test voice"));
    }
  }

  async function retry() {
    try {
      const result = await retryKitten();
      if (result.voice) {
        onVoice(result.voice);
      }
      if (!result.ok) {
        onError(result.error || "KittenTTS could not be installed. Piper is still available.");
        return;
      }
      onNotice("KittenTTS is ready. Pick it as the engine, then test the voice.");
    } catch (err) {
      onError(errorMessage(err, "KittenTTS could not be installed. Piper is still available."));
    }
  }
}
