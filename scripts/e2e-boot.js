import plugin from "./index.js";

const init = plugin.default || plugin;
init();
const route = window.__decklingRoute;
if (!route) {
  throw new Error("Deckling did not register the settings route");
}
const root = window.SP_REACTDOM.createRoot(document.getElementById("root"));
root.render(window.SP_JSX.jsx(route, {}));
