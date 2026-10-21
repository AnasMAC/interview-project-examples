// Atlas dashboard: small progressive enhancements. Every page works without this file.
document.addEventListener("DOMContentLoaded", () => {
  document.documentElement.classList.add("js");

  // Org switcher: submit as soon as another org is picked (the button is the no-JS fallback).
  for (const select of document.querySelectorAll("select[data-autosubmit]")) {
    select.addEventListener("change", () => select.form.requestSubmit());
  }

  // Destructive forms ask first.
  for (const form of document.querySelectorAll("form[data-confirm]")) {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  }
});
