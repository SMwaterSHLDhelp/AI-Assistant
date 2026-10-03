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

export function mountPageShell(root: HTMLElement): () => void {
  const viewHeight = window.innerHeight || 0;
  const touched: { el: HTMLElement; style: string | null }[] = [];
  const remember = (el: HTMLElement) => {
    touched.push({ el, style: el.getAttribute("style") });
  };

  const parent = root.parentElement;
  const parentHeight = parent?.getBoundingClientRect().height ?? 0;
  remember(root);
  if (parentHeight > 0) {
    root.style.position = "absolute";
    root.style.top = "0";
    root.style.right = "0";
    root.style.bottom = "0";
    root.style.left = "0";
    root.style.overflow = "hidden";
    root.style.boxSizing = "border-box";
    root.style.paddingBottom = "64px";
  }

  let node = root.parentElement;
  for (let depth = 0; node && node !== document.body && depth < 8; depth += 1) {
    const rect = node.getBoundingClientRect();
    if (isShortShell(rect.height, rect.bottom, viewHeight)) {
      remember(node);
      node.style.setProperty("height", `${viewHeight}px`, "important");
      node.style.setProperty("min-height", `${viewHeight}px`, "important");
      node.style.setProperty("overflow", "hidden", "important");
    }
    node = node.parentElement;
  }

  const footer = findActionBar();
  if (footer) {
    remember(footer);
    footer.style.setProperty("position", "fixed", "important");
    footer.style.setProperty("left", "0", "important");
    footer.style.setProperty("right", "0", "important");
    footer.style.setProperty("bottom", "0", "important");
    footer.style.setProperty("top", "auto", "important");
    footer.style.setProperty("transform", "none", "important");
  }

  return () => {
    for (let index = touched.length - 1; index >= 0; index -= 1) {
      const item = touched[index];
      if (item.style === null) {
        item.el.removeAttribute("style");
      } else {
        item.el.setAttribute("style", item.style);
      }
    }
  };
}

function findActionBar(): HTMLElement | null {
  const nodes = document.querySelectorAll("div, footer");
  for (const node of nodes) {
    if (!(node instanceof HTMLElement)) {
      continue;
    }
    const rect = node.getBoundingClientRect();
    if (looksLikeActionBar(node.textContent || "", node.className || "", rect.height, rect.width)) {
      return node;
    }
  }
  return null;
}
