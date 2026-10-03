/** Turn a backend error into a sentence that says what to try next. */

export function nextStep(error: string): string {
  const text = error.trim();
  if (!text) {
    return "";
  }
  if (/still starting/i.test(text)) {
    return `${text} Wait a few seconds, then open Deckling again.`;
  }
  if (/add a provider/i.test(text)) {
    return `${text} Open Provider settings and add one.`;
  }
  if (/screen capture is turned off/i.test(text)) {
    return `${text} Turn it on under Screen help in settings.`;
  }
  if (/timed out|connection|refused|unreachable|could not connect/i.test(text)) {
    return `${text} Check the address, and allow that port through the PC firewall.`;
  }
  return text;
}
