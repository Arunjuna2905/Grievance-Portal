// Mobile navigation menu
(() => {
  const menuToggle = document.getElementById('mobile-menu-toggle');
  const mainNav = document.getElementById('main-navigation');
  if (!menuToggle || !mainNav) return;

  function closeMenu() {
    mainNav.classList.remove('is-open');
    menuToggle.classList.remove('is-open');
    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-label', 'Open navigation menu');
  }

  menuToggle.addEventListener('click', () => {
    const isOpen = mainNav.classList.toggle('is-open');
    menuToggle.classList.toggle('is-open', isOpen);
    menuToggle.setAttribute('aria-expanded', String(isOpen));
    menuToggle.setAttribute('aria-label', isOpen ? 'Close navigation menu' : 'Open navigation menu');
  });

  mainNav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', closeMenu);
  });

  document.addEventListener('click', (event) => {
    if (mainNav.classList.contains('is-open') && !mainNav.contains(event.target) && !menuToggle.contains(event.target)) {
      closeMenu();
    }
  });
})();

// Theme preference
(() => {
  const themeToggle = document.querySelector('.theme-toggle');
  const themeLabel = document.querySelector('.theme-toggle-label');

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('smartgov_theme', theme);
    const isDark = theme === 'dark';
    if (themeToggle) themeToggle.setAttribute('aria-pressed', String(isDark));
    if (themeLabel) themeLabel.textContent = isDark ? 'Light' : 'Dark';
  }

  const currentTheme = document.documentElement.dataset.theme || 'light';
  setTheme(currentTheme);
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    });
  }
})();

// Save the profile notification choice immediately, so it remains correct after refresh.
(() => {
  const notificationToggle = document.getElementById('status-notifications-toggle');
  if (!notificationToggle) return;
  const notificationLabel = notificationToggle.parentElement.querySelector('.switch-label');

  notificationToggle.addEventListener('change', async () => {
    const enabled = notificationToggle.checked;
    const previousState = !enabled;
    notificationToggle.disabled = true;
    if (notificationLabel) notificationLabel.textContent = enabled ? 'On' : 'Off';

    try {
      const response = await fetch(notificationToggle.dataset.preferenceUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
      });
      if (!response.ok) throw new Error('Unable to save notification preference');
    } catch (error) {
      notificationToggle.checked = previousState;
      if (notificationLabel) notificationLabel.textContent = previousState ? 'On' : 'Off';
      window.alert('Your notification preference could not be saved. Please try again.');
    } finally {
      notificationToggle.disabled = false;
    }
  });
})();

// Auto-dismiss alerts
document.querySelectorAll('.alert').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity .3s, transform .3s';
    el.style.opacity = '0';
    el.style.transform = 'translateY(-8px)';
    setTimeout(() => el.remove(), 320);
  }, 6000);
});



