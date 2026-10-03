import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(here);
const label = process.argv[2] || "before";
const outDir = "/tmp/deckling-preview";
const shots = join(root, "docs", "screenshots");
const require = createRequire("/tmp/ui-harness/package.json");
const esbuild = require("/tmp/ui-harness/node_modules/esbuild");
const puppeteer = require("/tmp/ui-harness/node_modules/puppeteer-core");

await mkdir(outDir, { recursive: true });
await mkdir(shots, { recursive: true });
await esbuild.build({
  absWorkingDir: root,
  entryPoints: [join(root, "scripts/deck-preview.tsx")],
  bundle: true,
  format: "iife",
  platform: "browser",
  outfile: join(outDir, "app.js"),
  jsx: "automatic",
  alias: {
    "@decky/api": join(root, "scripts/mock-decky-api.ts"),
    "@decky/ui": join(root, "scripts/mock-decky-ui.tsx"),
  },
  nodePaths: ["/tmp/ui-harness/node_modules"],
});

function installBackend() {
  const provider = {
    id: "p1",
    kind: "llamacpp",
    name: "llama.cpp server",
    base_url: "http://192.168.1.20:8080/v1",
    default_model: "qwen-test",
    max_tokens: 1024,
    has_api_key: false,
    api_key_last4: "",
    oauth_client_id: "",
    has_oauth_secret: false,
    oauth_connected: false,
    oauth_expires_at: 0,
    connection_status: "connected",
    connection_detail: "Connected. 1 model available.",
  };
  window.__calls = [];
  window.__deckyCall = async (name) => {
    window.__calls.push(name);
    if (name === "get_state") {
      return {
        ok: true,
        catalog: [],
        providers: [provider],
        default_provider_id: "p1",
        default_model: "qwen-test",
        system_prompt: "",
        current_session_id: "s1",
        sessions: [{ id: "s1", title: "Boss fight", updated_at: 1 }],
        messages: [
          { id: "m1", role: "user", content: "How do I beat this boss?", created_at: 1 },
          {
            id: "m2",
            role: "assistant",
            content: "Stay behind the pillar.\n\n- Dodge the slam\n- `roll` when it glows\n\n```\nthen hit\n```",
            created_at: 2,
          },
        ],
        voice: { voice_enabled: false, voice_engine: "piper", screen_capture: true, piper_voices: [], kitten_voices: [] },
        hearing: { wake_enabled: false, phase: "off", ptt_enabled: true, wake_models: [], stt_models: [] },
      };
    }
    if (name === "list_models") {
      return { ok: true, models: ["qwen-test"], vision_models: ["qwen-test"] };
    }
    return { ok: true, messages: [], sessions: [], hearing: { phase: "off", ptt_enabled: true } };
  };
}

await writeFile(join(outDir, "index.html"), `<!doctype html><html><body><div id="root"></div><script src="app.js"></script></body></html>`);

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
try {
  for (const screen of ["settings", "chat"]) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });
    await page.evaluateOnNewDocument(installBackend);
    await page.goto(`file://${join(outDir, "index.html")}?screen=${screen}`, { waitUntil: "networkidle0" });
    await page.waitForFunction(
      (which) => document.body.innerText.includes(which === "chat" ? "Deckling" : "Deckling"),
      { timeout: 8000 },
      screen,
    );
    await new Promise((resolve) => setTimeout(resolve, 300));
    const file = join(shots, `${label}-${screen}.png`);
    await page.screenshot({ path: file });
    console.log(file);
    if (screen === "chat") {
      const list = await page.evaluate(() => document.querySelector(".deckling-bubble ul li")?.textContent || "");
      if (!list.includes("Dodge the slam")) {
        throw new Error(`Markdown list was not rendered: ${list}`);
      }
      const input = await page.waitForSelector('input[aria-label="Ask"]');
      const before = await input.evaluate((node) => ({
        key: node.dataset.mountKey,
        mounts: window.__fieldMounts?.[node.dataset.mountKey] || 0,
      }));
      await input.evaluate((node) => {
        node.focus();
        node.setSelectionRange(0, node.value.length);
      });
      await page.keyboard.type("stay focused while I type", { delay: 5 });
      const after = await page.evaluate((mountKey) => {
        const node = document.querySelector(`[data-mount-key="${mountKey}"]`);
        return {
          value: node?.value ?? "",
          focused: document.activeElement === node,
          mounts: window.__fieldMounts?.[mountKey] || 0,
        };
      }, before.key);
      if (!after.focused || after.mounts !== before.mounts || after.value !== "stay focused while I type") {
        throw new Error(`Ask field lost focus: ${JSON.stringify(before)} ${JSON.stringify(after)}`);
      }
    }
    await page.close();
  }
} finally {
  await browser.close();
}
