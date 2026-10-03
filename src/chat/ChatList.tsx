import { ButtonItem, ModalRoot, PanelSection, PanelSectionRow, TextField } from "@decky/ui";
import { useState } from "react";
import { deleteSession, moveSession, pinSession, renameSession, switchSession } from "../api";
import { fieldValue } from "../form";
import type { SessionSummary } from "../types";

export interface SessionResult {
  ok: boolean;
  error?: string;
  current_session_id?: string;
  messages?: { id: string; role: string; content: string; created_at: number }[];
  sessions?: SessionSummary[];
  provider_id?: string;
  model?: string;
  remember_model?: boolean;
}

export function ChatList({
  sessions,
  currentId,
  activeKey,
  activeLabel,
  onApply,
  onClose,
}: {
  sessions: SessionSummary[];
  currentId: string;
  activeKey: string;
  activeLabel: string;
  onApply: (result: SessionResult) => void;
  onClose: () => void;
}) {
  const [rows, setRows] = useState(sessions);
  const [selected, setSelected] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [moving, setMoving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const chat = rows.find((item) => item.id === selected);

  const apply = (result: SessionResult) => {
    if (!result.ok) {
      setError(result.error || "Could not update that chat");
      return false;
    }
    if (result.sessions) {
      setRows(result.sessions);
    }
    onApply(result);
    return true;
  };

  if (renaming && chat) {
    return (
      <ModalRoot onCancel={() => setRenaming(false)} bDisableBackgroundDismiss>
        <PanelSection title="Rename chat">
          <PanelSectionRow>
            <TextField
              key="chat-rename"
              label="Chat name"
              description="Opens the on-screen keyboard"
              value={draft}
              onChange={(event) => setDraft(fieldValue(event))}
            />
          </PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              void renameSession(chat.id, draft).then((result) => {
                if (apply(result)) {
                  setRenaming(false);
                }
              });
            }}
          >
            Save name
          </ButtonItem>
          <ButtonItem layout="below" onClick={() => setRenaming(false)}>
            Cancel
          </ButtonItem>
        </PanelSection>
      </ModalRoot>
    );
  }

  if (moving && chat) {
    const destinations = destinationsFor(rows, activeKey, activeLabel).filter((item) => item.key !== chat.game_key);
    return (
      <ModalRoot onCancel={() => setMoving(false)}>
        <PanelSection title="Move chat">
          {destinations.map((item) => (
            <ButtonItem
              key={item.key}
              layout="below"
              onClick={() => {
                void moveSession(chat.id, item.key, item.label).then((result) => {
                  if (apply(result)) {
                    setMoving(false);
                    setSelected("");
                  }
                });
              }}
            >
              {item.label}
            </ButtonItem>
          ))}
          <ButtonItem layout="below" onClick={() => setMoving(false)}>
            Back
          </ButtonItem>
        </PanelSection>
      </ModalRoot>
    );
  }

  if (chat && confirming) {
    return (
      <ModalRoot onCancel={() => setConfirming(false)}>
        <PanelSection title="Delete this chat?">
          <PanelSectionRow>
            <div>{`${chat.title || "New chat"} will be removed from this Deck.`}</div>
          </PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              void deleteSession(chat.id).then((result) => {
                if (apply(result)) {
                  setConfirming(false);
                  setSelected("");
                }
              });
            }}
          >
            Delete
          </ButtonItem>
          <ButtonItem layout="below" onClick={() => setConfirming(false)}>
            Keep chat
          </ButtonItem>
        </PanelSection>
      </ModalRoot>
    );
  }

  if (chat) {
    return (
      <ModalRoot onCancel={() => setSelected("")}>
        <PanelSection title={chat.title || "New chat"}>
          <PanelSectionRow>
            <div>{`${chat.game_label || "General"} · ${when(chat.updated_at)}`}</div>
          </PanelSectionRow>
          {error ? (
            <PanelSectionRow>
              <div style={{ color: "#f2b8b5" }}>{error}</div>
            </PanelSectionRow>
          ) : null}
          <ButtonItem
            layout="below"
            onClick={() => {
              void switchSession(chat.id).then((result) => {
                if (apply(result)) {
                  onClose();
                }
              });
            }}
          >
            Open
          </ButtonItem>
          <ButtonItem
            layout="below"
            onClick={() => {
              setDraft(chat.title === "New chat" ? "" : chat.title);
              setRenaming(true);
            }}
          >
            Rename
          </ButtonItem>
          <ButtonItem
            layout="below"
            onClick={() => {
              void pinSession(chat.id, !chat.pinned).then((result) => {
                apply(result);
              });
            }}
          >
            {chat.pinned ? "Unpin" : "Pin"}
          </ButtonItem>
          <ButtonItem layout="below" onClick={() => setMoving(true)}>
            Move to another game
          </ButtonItem>
          <ButtonItem layout="below" onClick={() => setConfirming(true)}>
            Delete
          </ButtonItem>
          <ButtonItem layout="below" onClick={() => setSelected("")}>
            Back
          </ButtonItem>
        </PanelSection>
      </ModalRoot>
    );
  }

  const groups = groupRows(rows, activeKey);
  return (
    <ModalRoot onCancel={onClose}>
      {groups.map((group) => (
        <PanelSection key={group.key} title={group.key === activeKey ? `${group.label} · now` : group.label}>
          {group.rows.map((item) => (
            <ButtonItem
              key={item.id}
              layout="below"
              description={`${item.preview || "No messages yet"} · ${when(item.updated_at)}`}
              onClick={() => setSelected(item.id)}
            >
              {`${item.pinned ? "Pinned · " : ""}${item.id === currentId ? "Open · " : ""}${item.title || "New chat"}`}
            </ButtonItem>
          ))}
        </PanelSection>
      ))}
      <PanelSection title="Chats">
        <ButtonItem layout="below" onClick={onClose}>
          Close
        </ButtonItem>
      </PanelSection>
    </ModalRoot>
  );
}

function when(stamp: number): string {
  if (!stamp) {
    return "";
  }
  const date = new Date(stamp * 1000);
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function groupRows(rows: SessionSummary[], activeKey: string): { key: string; label: string; rows: SessionSummary[] }[] {
  const groups: { key: string; label: string; rows: SessionSummary[] }[] = [];
  for (const item of rows) {
    const key = item.game_key || "general";
    const found = groups.find((group) => group.key === key);
    if (found) {
      found.rows.push(item);
    } else {
      groups.push({ key, label: item.game_label || "General", rows: [item] });
    }
  }
  groups.sort((left, right) => rank(left.key, activeKey) - rank(right.key, activeKey));
  return groups;
}

function rank(key: string, activeKey: string): number {
  if (key === activeKey) {
    return 0;
  }
  if (key === "general") {
    return 2;
  }
  return 1;
}

function destinationsFor(
  rows: SessionSummary[],
  activeKey: string,
  activeLabel: string,
): { key: string; label: string }[] {
  const found = new Map<string, string>();
  found.set("general", "General");
  if (activeKey) {
    found.set(activeKey, activeLabel || "This game");
  }
  for (const item of rows) {
    if (item.game_key && !found.has(item.game_key)) {
      found.set(item.game_key, item.game_label || item.game_key);
    }
  }
  return [...found.entries()].map(([key, label]) => ({ key, label }));
}
