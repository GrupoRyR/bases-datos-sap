// Theme choice per viewer: "system" (no attribute), "light" or "dark" in
// <html data-theme>. The inline script in
// resources/views/components/layouts/partials/head.blade.php applies the
// stored choice before the first paint; keep STORAGE_KEY in sync with it.
// Without JavaScript the page follows the system preference.

const STORAGE_KEY = 'bases-sap-theme';
const CYCLE = ['system', 'light', 'dark'];
const NAMES = { system: 'sistema', light: 'claro', dark: 'oscuro' };

function readTheme() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);

        return stored === 'light' || stored === 'dark' ? stored : 'system';
    } catch {
        return 'system';
    }
}

function storeTheme(theme) {
    try {
        if (theme === 'system') {
            localStorage.removeItem(STORAGE_KEY);
        } else {
            localStorage.setItem(STORAGE_KEY, theme);
        }
    } catch {
        // Storage can be blocked (private windows); the choice lasts for this page.
    }
}

function applyTheme(theme) {
    if (theme === 'system') {
        delete document.documentElement.dataset.theme;
    } else {
        document.documentElement.dataset.theme = theme;
    }
}

function renderToggle(button, theme) {
    const name = NAMES[theme];
    const label = button.querySelector('[data-theme-toggle-label]');

    button.setAttribute('aria-label', `Tema: ${name}`);
    button.title = `Tema: ${name}`;

    if (label) {
        label.textContent = name.charAt(0).toUpperCase() + name.slice(1);
    }
}

// Shows every [data-theme-toggle] button (rendered hidden for no-JS
// visitors) and cycles system → light → dark on each click.
export function initThemeToggle() {
    const buttons = document.querySelectorAll('[data-theme-toggle]');
    let theme = readTheme();

    buttons.forEach((button) => {
        renderToggle(button, theme);
        button.hidden = false;

        button.addEventListener('click', () => {
            theme = CYCLE[(CYCLE.indexOf(theme) + 1) % CYCLE.length];
            applyTheme(theme);
            storeTheme(theme);
            buttons.forEach((other) => renderToggle(other, theme));
        });
    });
}
