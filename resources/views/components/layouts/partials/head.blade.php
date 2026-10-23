{{-- Shared <head> content of the layouts; title is the page name without the app name. --}}
@props([
    'title' => null,
])

<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{{ filled($title) ? $title.' · Bases de datos SAP' : 'Bases de datos SAP' }}</title>
<script>
    // Applies the stored theme choice before the first paint (resources/js/theme.js).
    try {
        var theme = localStorage.getItem('bases-sap-theme');

        if (theme === 'light' || theme === 'dark') {
            document.documentElement.dataset.theme = theme;
        }
    } catch (error) {}
</script>
@vite(['resources/css/app.css', 'resources/js/app.js'])
