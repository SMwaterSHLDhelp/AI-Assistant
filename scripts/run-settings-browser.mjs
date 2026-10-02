import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(here);
const outDir = "/tmp/ai-assistant-settings-browser";
const require = createRequire("/tmp/ui-harness/package.json");

const esbuild = require("/tmp/ui-harness/node_modules/esbuild");
const puppeteer = require("/tmp/ui-harness/node_modules/puppeteer-core");

await mkdir(outDir, { recursive: true });
await esbuild.build({
  absWorkingDir: root,
  entryPoints: [join(root, "scripts/settings-harness.tsx")],
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

function pageHtml() {
  return `<!doctype html><html><body><div id="root"></div><script src="app.js"></script></body></html>`;
}

await writeFile(join(outDir, "index.html"), pageHtml());

function installBackend(mode) {
  const savedProvider = {
    id: "p1",
    kind: "llamacpp",
    name: "llama.cpp server",
    base_url: "http://127.0.0.1:8080/v1",
    default_model: "",
    max_tokens: 1024,
    has_api_key: false,
    api_key_last4: "",
    oauth_client_id: "",
    has_oauth_secret: false,
    oauth_connected: false,
    oauth_expires_at: 0,
  };
  const calls = [];
  window.__toasts = [];
  window.__deckyCall = async (name, args) => {
    calls.push(name);
    window.__calls = calls;
    if (name === "get_state") {
      if (mode === "hang") {
        return new Promise(() => {});
      }
      if (mode === "fail") {
        return { ok: false, error: "Deckling is still starting." };
      }
      return {
        ok: true,
        catalog: [],
        providers: [],
        default_provider_id: "",
        default_model: "",
        system_prompt: "",
        current_session_id: "",
        sessions: [],
        messages: [],
      };
    }
    if (name === "save_provider") {
      return { ok: true, provider: { ...savedProvider, ...(args[0] || {}) , id: "p1" } };
    }
    if (name === "list_models") {
      return { ok: true, models: ["qwen-test", "tiny"] };
    }
    return { ok: true };
  };
}

async function textOf(page) {
  return page.evaluate(() => document.body.innerText);
}

async function typeInto(page, label, text) {
  const input = await page.waitForSelector(`input[aria-label="${label}"]`, { timeout: 4000 });
  const before = await input.evaluate((node) => ({
    key: node.dataset.mountKey,
    mounts: window.__fieldMounts?.[node.dataset.mountKey] || 0,
  }));
  await input.evaluate((node) => {
    node.focus();
    node.setSelectionRange(0, node.value.length);
  });
  await page.keyboard.press("Backspace");
  await page.keyboard.type(text, { delay: 8 });
  const after = await page.evaluate((mountKey) => {
    const node = document.querySelector(`[data-mount-key="${mountKey}"]`);
    return {
      value: node?.value ?? "",
      focused: document.activeElement === node,
      connected: Boolean(node?.isConnected),
      mounts: window.__fieldMounts?.[mountKey] || 0,
    };
  }, before.key);
  if (!after.connected || !after.focused || after.value !== text || after.mounts !== before.mounts) {
    throw new Error(
      `Field ${label} lost focus or remounted. before=${JSON.stringify(before)} after=${JSON.stringify(after)}\n${await textOf(page)}`,
    );
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
    throw new Error(`Could not find button: ${label}\n${await textOf(page)}`);
  }
}

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

try {
  const failPage = await browser.newPage();
  await failPage.evaluateOnNewDocument(installBackend, "fail");
  await failPage.goto(`file://${join(outDir, "index.html")}`, { waitUntil: "networkidle0" });
  await failPage.waitForFunction(() => document.body.innerText.includes("still starting"), { timeout: 8000 });
  const beforeAdd = await textOf(failPage);
  if (!beforeAdd.includes("Deckling is still starting.")) {
    throw new Error(`Real backend error was not shown:\n${beforeAdd}`);
  }
  await clickButton(failPage, "Add provider");
  await failPage.waitForFunction(() => document.body.innerText.includes("llama.cpp server"), { timeout: 4000 });
  const failedText = await textOf(failPage);
  if (failedText.includes("have not loaded yet")) {
    throw new Error(`Add provider still blocked:\n${failedText}`);
  }
  if (!failedText.includes("Selected: OpenAI / ChatGPT")) {
    throw new Error(`Add provider did not open the type list:\n${failedText}`);
  }

  const hangPage = await browser.newPage();
  await hangPage.evaluateOnNewDocument(installBackend, "hang");
  await hangPage.goto(`file://${join(outDir, "index.html")}`, { waitUntil: "domcontentloaded" });
  await hangPage.waitForFunction(() => document.body.innerText.includes("Loading settings"), { timeout: 4000 });
  await clickButton(hangPage, "Add provider");
  await hangPage.waitForFunction(() => document.body.innerText.includes("Selected: OpenAI / ChatGPT"), { timeout: 4000 });
  const hungText = await textOf(hangPage);
  if (hungText.includes("have not loaded yet")) {
    throw new Error(`Add provider blocked while settings were still loading:\n${hungText}`);
  }

  const savePage = await browser.newPage();
  await savePage.evaluateOnNewDocument(installBackend, "save");
  await savePage.goto(`file://${join(outDir, "index.html")}`, { waitUntil: "networkidle0" });
  await savePage.waitForFunction(() => document.body.innerText.includes("Add provider"), { timeout: 4000 });
  await typeInto(savePage, "System prompt", "Stay with this field while I type a long prompt.");
  await typeInto(savePage, "Default model", "local-model-id-that-stays-focused");
  await clickButton(savePage, "Add provider");
  await savePage.waitForSelector("#deckling-modal input[aria-label='Name']", { timeout: 4000 });
  await typeInto(savePage, "Name", "Home llama server");
  await typeInto(savePage, "Base URL", "http://192.168.1.20:8080/v1");
  await typeInto(savePage, "Model", "qwen-local-typed-by-hand");
  await typeInto(savePage, "Max tokens", "2048");
  await typeInto(savePage, "API key", "secret-key-that-must-stay-put");
  const callsWhileTyping = await savePage.evaluate(() => window.__calls || []);
  if (callsWhileTyping.includes("list_models") || callsWhileTyping.includes("save_provider")) {
    throw new Error(`Typing called the backend: ${callsWhileTyping.join(",")}`);
  }
  await clickButton(savePage, "llama.cpp server");
  await clickButton(savePage, "Save provider");
  await savePage.waitForFunction(() => document.body.innerText.includes("qwen-test"), { timeout: 8000 });
  await clickButton(savePage, "qwen-test");
  const modelValue = await savePage.evaluate(() => {
    const inputs = [...document.querySelectorAll('input[aria-label="Model"]')];
    return inputs.at(-1)?.value ?? "";
  });
  if (modelValue !== "qwen-test") {
    throw new Error(`Model picker did not select qwen-test, got ${modelValue}\n${await textOf(savePage)}`);
  }
  const calls = await savePage.evaluate(() => window.__calls || []);
  if (!calls.includes("list_models")) {
    throw new Error(`Saving a provider did not list models: ${calls.join(",")}`);
  }
  console.log("settings browser check passed");
} finally {
  await browser.close();
}
