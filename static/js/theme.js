document.addEventListener('DOMContentLoaded', () => {
    const themeToggler = document.getElementById('themeToggler');
    const themeIcon = document.getElementById('themeIcon');
    const html = document.documentElement;

    // Cargar preferencia
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);

    themeToggler.addEventListener('click', () => {
        const currentTheme = html.getAttribute('data-bs-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
    });

    function setTheme(theme) {
        html.setAttribute('data-bs-theme', theme);
        localStorage.setItem('theme', theme);
        
        if (theme === 'dark') {
            themeIcon.classList.replace('bi-sun-fill', 'bi-moon-stars-fill');
        } else {
            themeIcon.classList.replace('bi-moon-stars-fill', 'bi-sun-fill');
        }
    }
});