import { spawn } from "node:child_process";
import { mkdir, copyFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(here);
const outDir = "/tmp/deckling-settings-e2e";
const require = createRequire("/tmp/ui-harness/package.json");
const esbuild = require("/tmp/ui-harness/node_modules/esbuild");
const puppeteer = require("/tmp/ui-harness/node_modules/puppeteer-core");

await new Promise((resolve, reject) => {
  const child = spawn("pnpm", ["exec", "rollup", "-c"], { cwd: root, stdio: "inherit" });
  child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`rollup exited ${code}`))));
});

await mkdir(outDir, { recursive: true });
await esbuild.build({
  absWorkingDir: root,
  entryPoints: [join(root, "scripts/e2e-preload.tsx")],
  bundle: true,
  format: "iife",
  platform: "browser",
  outfile: join(outDir, "preload.js"),
  jsx: "automatic",
  alias: {
    "@decky/ui": join(root, "scripts/mock-decky-ui.tsx"),
  },
  nodePaths: ["/tmp/ui-harness/node_modules"],
});
await copyFile(join(root, "dist/index.js"), join(outDir, "index.js"));
await copyFile(join(root, "scripts/e2e-boot.js"), join(outDir, "boot.js"));
await writeFile(
  join(outDir, "index.html"),
  `<!doctype html><html><body><div id="root"></div><script src="preload.js"></script><script type="module" src="boot.js"></script></body></html>`,
);

function installBackend() {
  const calls = [];
  const state = {
    providers: [],
    voice: {
      voice_enabled: false,
      voice_engine: "piper",
      piper_voice: "en_US-lessac-medium",
      kitten_voice: "Jasper",
      voice_speed: 1,
      screen_capture: true,
      kitten_error: "",
      piper_voices: ["en_US-lessac-medium", "en_US-amy-medium"],
      kitten_voices: ["Jasper", "Bella"],
    },
    hearing: {
      wake_enabled: false,
      sensitivity: 0.5,
      wake_model: "hey_jarvis",
      stt_model: "tiny.en",
      ptt_enabled: true,
      battery_saver: false,
      debug_audio: false,
      wake_error: "",
      stt_backend: "",
      install_message: "",
      phase: "off",
      wake_models: [{ id: "hey_jarvis", label: "hey jarvis" }],
      stt_models: ["tiny.en"],
      idle_note: "The speech model closes after each line.",
    },
  };
  window.__toasts = [];
  window.__calls = calls;
  window.__deckyCall = async (name, args) => {
    calls.push(name);
    if (name === "get_state") {
      return { ok: true, providers: state.providers, voice: state.voice, hearing: state.hearing };
    }
    if (name === "health") {
      return { ok: true, version: "0.1.0-rc.10", error: "" };
    }
    if (name === "diagnostics") {
      return { ok: true, lines: ["INFO Deckling ready"] };
    }
    if (name === "save_provider") {
      const saved = {
        id: "p1",
        kind: "llamacpp",
        name: "llama.cpp on my PC",
        base_url: "http://127.0.0.1:8080/v1",
        default_model: "",
        max_tokens: 1024,
        has_api_key: false,
        api_key_last4: "",
        oauth_client_id: "",
        has_oauth_secret: false,
        oauth_connected: false,
        oauth_expires_at: 0,
        connection_status: "",
        connection_detail: "",
        ...(args[0] || {}),
        id: "p1",
      };
      state.providers = [saved];
      return { ok: true, provider: saved };
    }
    if (name === "list_models") {
      return { ok: true, models: ["qwen-test"] };
    }
    if (name === "save_hearing") {
      state.hearing = { ...state.hearing, ...(args[0] || {}) };
      return { ok: true, hearing: state.hearing };
    }
    if (name === "save_voice") {
      state.voice = { ...state.voice, ...(args[0] || {}) };
      return { ok: true, voice: state.voice };
    }
    if (name === "test_voice") {
      return { success: false, result: "speaker is missing" };
    }
    return { ok: true };
  };
}

async function textOf(page) {
  return page.evaluate(() => document.body.innerText);
}

async function modalText(page) {
  return page.evaluate(() => document.querySelector("#deckling-modal")?.innerText || "");
}

async function typeInto(page, label, text) {
  const input = await page.waitForSelector(`#deckling-modal input[aria-label="${label}"]`, { timeout: 4000 });
  await input.evaluate((node) => {
    node.focus();
    node.setSelectionRange(0, node.value.length);
  });
  await page.keyboard.press("Backspace");
  await page.keyboard.type(text, { delay: 8 });
}

async function activateRow(page, label) {
  const clicked = await page.evaluate((wanted) => {
    const row = [...document.querySelectorAll("[data-deck-row]")].find((item) => item.textContent?.includes(wanted));
    if (!row) {
      return false;
    }
    row.focus();
    row.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    return true;
  }, label);
  if (!clicked) {
    throw new Error(`Could not activate row: ${label}\n${await textOf(page)}`);
  }
}

async function clickButton(page, label) {
  const clicked = await page.evaluate((wanted) => {
    const button = [...document.querySelectorAll("button")].find((item) => item.textContent?.includes(wanted));
    if (!button) {
      return false;
    }
    button.click();
    return true;
  }, label);
  if (!clicked) {
    throw new Error(`Could not click button: ${label}\n${await textOf(page)}`);
  }
}

const server = spawn("python3", ["-m", "http.server", "8765", "--bind", "127.0.0.1"], {
  cwd: outDir,
  stdio: "ignore",
});

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

try {
  const page = await browser.newPage();
  page.on("pageerror", (err) => {
    console.error("pageerror", err);
  });
  await page.evaluateOnNewDocument(installBackend);
  await page.goto("http://127.0.0.1:8765/", { waitUntil: "networkidle0" });
  await page.waitForFunction(() => document.body.innerText.includes("Backend: connected v0.1.0-rc.10"), {
    timeout: 8000,
  });
  await page.waitForFunction(() => document.body.innerText.includes("llama.cpp on my PC"), { timeout: 4000 });

  await activateRow(page, "llama.cpp on my PC");
  await page.waitForSelector("#deckling-modal input[aria-label='Base URL']", { timeout: 4000 });
  const opened = await modalText(page);
  if (opened.includes("Selected:") || opened.includes("OpenAI / ChatGPT")) {
    throw new Error(`Preset opened the type list again:\n${opened}`);
  }
  if (!opened.includes("Change type") || !opened.includes("Save provider")) {
    throw new Error(`Preset form is missing the locked type or Save:\n${opened}`);
  }
  const saveInFooter = await page.evaluate(() => {
    const footer = document.querySelector("#deckling-modal footer");
    return Boolean(footer && footer.textContent && footer.textContent.includes("Save provider"));
  });
  if (!saveInFooter) {
    throw new Error(`Save provider is not in the dialog footer:\n${opened}`);
  }
  await typeInto(page, "Base URL", "http://192.168.1.40:8080/v1");
  await activateRow(page, "Save provider");
  await page.waitForFunction(() => document.body.innerText.includes("qwen-test"), { timeout: 8000 });
  await page.waitForFunction(() => document.body.innerText.includes("Edit llama.cpp on my PC"), { timeout: 4000 });
  const callsAfterSave = await page.evaluate(() => window.__calls || []);
  if (!callsAfterSave.includes("save_provider") || !callsAfterSave.includes("list_models")) {
    throw new Error(`Save did not store the provider and load models: ${callsAfterSave.join(",")}`);
  }
  if (callsAfterSave.filter((name) => name === "save_provider").length !== 1) {
    throw new Error(`Save provider fired more than once: ${callsAfterSave.join(",")}`);
  }
  await clickButton(page, "Cancel");

  const wakeOptionsVisible = await page.evaluate(
    () => Boolean(document.querySelector("input[aria-label='Wake word sensitivity']")),
  );
  if (wakeOptionsVisible) {
    throw new Error("Wake options showed before it was enabled");
  }
  await activateRow(page, "Wake word: off");
  await page.waitForFunction(() => document.body.innerText.includes("Wake word: on"), { timeout: 4000 });
  await page.waitForSelector("input[aria-label='Wake word sensitivity']", { timeout: 4000 });
  const hearingCalls = await page.evaluate(
    () => (window.__calls || []).filter((name) => name === "save_hearing").length,
  );
  if (hearingCalls !== 1) {
    throw new Error(`Wake word activate called save_hearing ${hearingCalls} times`);
  }
  await new Promise((resolve) => setTimeout(resolve, 350));
  await clickButton(page, "Wake word: on");
  await page.waitForFunction(() => document.body.innerText.includes("Wake word: off"), { timeout: 4000 });
  const sensitivityGone = await page.evaluate(
    () => !document.querySelector("input[aria-label='Wake word sensitivity']"),
  );
  if (!sensitivityGone) {
    throw new Error("Sensitivity stayed on screen after wake word was turned off");
  }

  if ((await textOf(page)).includes("en_US-lessac-medium")) {
    throw new Error("Piper voices were shown before an engine was picked");
  }
  await activateRow(page, "Use Piper");
  await page.waitForFunction(() => document.body.innerText.includes("Engine: Piper"), { timeout: 4000 });
  await page.waitForFunction(() => document.body.innerText.includes("en_US-lessac-medium"), { timeout: 4000 });
  if ((await textOf(page)).includes("Jasper")) {
    throw new Error("Kitten voices showed while Piper was selected");
  }
  await activateRow(page, "Use KittenTTS");
  await page.waitForFunction(() => document.body.innerText.includes("Engine: KittenTTS"), { timeout: 4000 });
  await page.waitForFunction(() => document.body.innerText.includes("Jasper"), { timeout: 4000 });
  if ((await textOf(page)).includes("en_US-lessac-medium")) {
    throw new Error("Piper voices stayed on screen after switching to KittenTTS");
  }
  const voiceCalls = await page.evaluate(() => (window.__calls || []).filter((name) => name === "save_voice"));
  if (voiceCalls.length !== 2) {
    throw new Error(`Expected two engine saves, got ${voiceCalls.join(",")}`);
  }

  await activateRow(page, "Test voice");
  await page.waitForFunction(
    () => (window.__toasts || []).some((item) => String(item.body || "").includes("speaker is missing")),
    { timeout: 4000 },
  );
  await page.waitForFunction(() => document.body.innerText.includes("speaker is missing"), { timeout: 4000 });
  console.log("settings e2e passed");
} finally {
  await browser.close();
  server.kill();
}
