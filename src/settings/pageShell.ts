/**
 * The settings route is a full-screen Steam page. On a Deck, that page was
 * painted in a box that ended mid-screen, so the action bar (STEAM / A SELECT /
 * B BACK) sat on top of the provider list. Stretch those short boxes to the
 * window and pin the bar to the bottom while this route is open.
 */

export function isShortShell(height: number, bottom: number, viewHeight: number): boolean {
  if (viewHeight < 200) {
    return false;
  }
  return height > 160 && height < viewHeight - 40 && bottom <= viewHeight - 40;
}

export function looksLikeActionBar(text: string, className: string, height: number, width: number): boolean {
  const clipped = text.trim();
  if (clipped.length > 160) {
    return false;
  }
  if (height < 20 || height > 80 || width < 180) {
    return false;
  }
  const label = clipped.toUpperCase();
  if (label.includes("SELECT") && (label.includes("BACK") || label.includes("STEAM"))) {
    return true;
  }
  const name = className.toLowerCase();
  return name.includes("footer") && !name.includes("dialog");
}

/**
 * Stretching ancestor shells and pinning a guessed footer covered the dialog
 * Save button and other rows. Steam's SidebarNavigation already places the
 * action bar. Do not rewrite those nodes.
 */
export function mountPageShell(_root: HTMLElement): () => void {
  return () => undefined;
}
