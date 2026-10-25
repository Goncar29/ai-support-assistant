import type { ChatMessage } from "./useChat";

export const CONVERSATION_STORAGE_KEY = "chat-conversation";
/** Enough to pick a conversation back up; only the last few messages go to the model anyway. */
export const MAX_STORED_MESSAGES = 50;

function isChatMessage(value: unknown): value is ChatMessage {
  if (typeof value !== "object" || value === null) return false;
  const { id, role, text } = value as Record<string, unknown>;
  return typeof id === "string" && (role === "user" || role === "assistant") && typeof text === "string" && text !== "";
}

/** The conversation saved in this browser, or an empty one when there is none or it cannot be read. */
export function loadConversation(): ChatMessage[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(CONVERSATION_STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isChatMessage).slice(-MAX_STORED_MESSAGES) : [];
  } catch {
    return []; // storage blocked or data unreadable: start a new conversation
  }
}

/** Keeps the conversation for the next visit; an empty one is forgotten. */
export function saveConversation(messages: ChatMessage[]): void {
  try {
    if (messages.length === 0) window.localStorage.removeItem(CONVERSATION_STORAGE_KEY);
    else window.localStorage.setItem(CONVERSATION_STORAGE_KEY, JSON.stringify(messages.slice(-MAX_STORED_MESSAGES)));
  } catch {
    // storage blocked or full: the conversation still works for this visit
  }
}
