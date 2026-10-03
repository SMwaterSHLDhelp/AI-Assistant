/** Small markdown for chat bubbles. HTML is escaped before any markup is added. */

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inline(value: string): string {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderBlocks(chunk: string): string {
  const html: string[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length === 0) {
      return;
    }
    html.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`);
    list = [];
  };
  for (const line of chunk.split("\n")) {
    const item = /^(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
    if (item) {
      list.push(item[1]);
      continue;
    }
    flush();
    if (!line.trim()) {
      continue;
    }
    html.push(`<p>${inline(line)}</p>`);
  }
  flush();
  return html.join("");
}

export function renderMarkdown(source: string): string {
  const text = String(source || "").replace(/\r\n/g, "\n");
  return text
    .split("```")
    .map((chunk, index) => {
      if (index % 2 === 1) {
        const newline = chunk.indexOf("\n");
        const body = newline === -1 ? chunk : chunk.slice(newline + 1);
        return `<pre><code>${escapeHtml(body.replace(/\n$/, ""))}</code></pre>`;
      }
      return renderBlocks(chunk);
    })
    .join("");
}
