import assert from "node:assert/strict";
import { isShortShell, looksLikeActionBar } from "../src/settings/pageShell.ts";

const view = 800;
assert.equal(isShortShell(420, 420, view), true);
assert.equal(isShortShell(800, 800, view), false);
assert.equal(isShortShell(760, 790, view), false);
assert.equal(isShortShell(100, 100, view), false);

assert.equal(looksLikeActionBar("STEAM MENU A SELECT B BACK", "", 42, 640), true);
assert.equal(looksLikeActionBar("OpenAI", "footer_bar", 42, 640), true);
assert.equal(looksLikeActionBar("Save provider", "deckling-dialog", 48, 400), false);
assert.equal(looksLikeActionBar("A SELECT B BACK and a very long page of provider buttons ".repeat(8), "", 42, 640), false);

console.log("page shell check passed");
