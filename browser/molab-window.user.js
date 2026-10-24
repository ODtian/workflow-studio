// ==UserScript==
// @name         Workflow Studio 窗口内铺满
// @namespace    workflow-studio
// @version      1.0.0
// @match        https://molab.marimo.io/notebooks/*
// @run-at       document-start
// @grant        none
// @noframes
// ==/UserScript==

(() => {
  const style = document.createElement('style');
  style.textContent = `
    html.workflow-studio-expanded header { display: none !important; }
    html.workflow-studio-expanded iframe[title="Workflow Studio"] {
      position: fixed !important;
      inset: 0 !important;
      width: 100% !important;
      height: 100dvh !important;
      max-height: none !important;
      z-index: 1000 !important;
    }
  `;
  document.documentElement.append(style);
  const apply = expanded => document.documentElement.classList.toggle('workflow-studio-expanded', expanded);
  window.addEventListener('message', event => {
    const frame = document.querySelector('iframe[title="Workflow Studio"]');
    if (event.source === frame?.contentWindow && event.data?.type === 'workflow-studio:expanded') {
      apply(event.data.expanded);
    }
  });
  if (document.querySelector('iframe[title="Workflow Studio"]')) apply(true);
})();
