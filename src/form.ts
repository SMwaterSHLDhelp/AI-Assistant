/** Steam's text and dropdown controls do not always pass a DOM event. */

export function componentReady(value: unknown): boolean {
  return typeof value === "function" || (typeof value === "object" && value !== null);
}

export function fieldValue(event: unknown): string {
  if (typeof event === "string") {
    return event;
  }
  if (event && typeof event === "object" && "target" in event) {
    const value = (event as { target?: { value?: unknown } }).target?.value;
    if (typeof value === "string") {
      return value;
    }
  }
  return "";
}

export function optionData(option: unknown): string {
  if (typeof option === "string" || typeof option === "number") {
    return String(option);
  }
  if (option && typeof option === "object" && "data" in option) {
    const data = (option as { data?: unknown }).data;
    if (data != null) {
      return String(data);
    }
  }
  return "";
}
