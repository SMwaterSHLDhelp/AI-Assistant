import { ButtonItem, PanelSectionRow, TextField } from "@decky/ui";
import { fieldValue } from "./form";

const VISIBLE_MODELS = 40;

export function ModelPicker({
  label,
  models,
  value,
  onChange,
  onRefresh,
  loading,
  error,
}: {
  label: string;
  models: string[];
  value: string;
  onChange: (model: string) => void;
  onRefresh: () => void;
  loading: boolean;
  error: string;
}) {
  const shown = models.slice(0, VISIBLE_MODELS);
  let status = "No models loaded yet. Type an id, or press Refresh models.";
  if (loading) {
    status = "Loading models…";
  } else if (models.length > 0) {
    status = "Pick a model below, or type an id.";
  }
  return (
    <>
      <PanelSectionRow>
        <div>{status}</div>
      </PanelSectionRow>
      {error ? (
        <PanelSectionRow>
          <div style={{ color: "#f2b8b5", whiteSpace: "pre-wrap" }}>{error}</div>
        </PanelSectionRow>
      ) : null}
      {shown.map((id) => (
        <ButtonItem key={id} layout="below" onClick={() => onChange(id)}>
          {value === id ? `Selected: ${id}` : id}
        </ButtonItem>
      ))}
      {models.length > shown.length ? (
        <PanelSectionRow>
          <div>{`${models.length - shown.length} more models are not listed. Type the id below.`}</div>
        </PanelSectionRow>
      ) : null}
      <PanelSectionRow>
        <TextField label={label} value={value} onChange={(event) => onChange(fieldValue(event))} />
      </PanelSectionRow>
      <ButtonItem layout="below" onClick={onRefresh}>
        {loading ? "Refreshing models…" : "Refresh models"}
      </ButtonItem>
    </>
  );
}
