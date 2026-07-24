export type SseEventType = "text_delta" | "tool_call" | "done" | "error";

export interface SseEvent {
  type: SseEventType;
  text?: string | null;
  conversation_id?: string | null;
  tool_name?: string | null;
  tool_use_id?: string | null;
  error?: string | null;
  code?: string | null;
  message?: string | null;
}

/**
 * Reads a `text/event-stream` Response from POST /chat.
 * Each `data:` line is JSON matching docs/4_API_DESIGN.yaml SSE events.
 */
export async function readSseStream(
  response: Response,
  onEvent: (event: SseEvent) => void,
): Promise<void> {
  if (!response.body) {
    throw new Error("SSE response has no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const dataLines = chunk
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());

      if (dataLines.length === 0) continue;

      const payload = dataLines.join("\n");
      if (!payload || payload === "[DONE]") continue;

      try {
        const event = JSON.parse(payload) as SseEvent;
        onEvent(event);
      } catch {
        // Ignore malformed event frames.
      }
    }
  }
}
