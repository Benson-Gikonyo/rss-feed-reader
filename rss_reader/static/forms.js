"use strict";

document.querySelectorAll("form[data-busy-label]").forEach((form) => {
    const button = form.querySelector('button[type="submit"]');
    const status = form.querySelector("[data-submit-status]");
    const label = button.textContent;
    form.addEventListener("submit", (event) => {
        if (form.dataset.submitting === "true") {
            event.preventDefault();
            return;
        }
        form.dataset.submitting = "true";
        form.setAttribute("aria-busy", "true");
        button.disabled = true;
        button.textContent = form.dataset.busyLabel;
        status.textContent = `${form.dataset.busyLabel} Please wait.`;
    });
    // Browsers may restore disabled controls when returning through history.
    window.addEventListener("pageshow", () => {
        delete form.dataset.submitting;
        form.removeAttribute("aria-busy");
        button.disabled = false;
        button.textContent = label;
        status.textContent = "";
    });
});
