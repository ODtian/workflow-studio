const storageKey = 'workflow-studio-color-theme';
const themes = {
  light: {
    background:'#ffffff', foreground:'#242b35', primary:'#29313d', 'primary-foreground':'#ffffff',
    secondary:'#eef1f4', muted:'#f6f7f9', 'muted-foreground':'#85909f', border:'#e5e9ee',
    ring:'#85909f', destructive:'#c94a4a', sidebar:'#f8f9fb', 'surface-subtle':'#fafbfc',
    'preview-background':'#f2f4f7', 'preview-dot':'#d6dde6', 'text-secondary':'#58677b',
    'code-background':'#edf2f8', 'notice-background':'#faf7ef', 'notice-foreground':'#97815b',
    success:'#397453', warning:'#ae662f', 'timeline-clip':'#edf2f6', 'timeline-selected':'#e7eff5',
  },
  dark: {
    background:'#14181e', foreground:'#e5eaf0', primary:'#d9e3ee', 'primary-foreground':'#14181e',
    secondary:'#29313b', muted:'#1d232b', 'muted-foreground':'#a1acba', border:'#343e4b',
    ring:'#8ea4bc', destructive:'#f18b8b', sidebar:'#10141a', 'surface-subtle':'#191f27',
    'preview-background':'#10151b', 'preview-dot':'#2e3844', 'text-secondary':'#bec8d5',
    'code-background':'#252e3a', 'notice-background':'#332b1d', 'notice-foreground':'#dfc18d',
    success:'#88cba5', warning:'#e3b97b', 'timeline-clip':'#25313d', 'timeline-selected':'#273c4b',
  },
};

export const readColorTheme = () => localStorage.getItem(storageKey) || 'dark';

export function setColorTheme(theme) {
  localStorage.setItem(storageKey, theme);
  window.dispatchEvent(new Event('studio-theme-change'));
}

export function watchColorTheme(target, onChange = () => {}) {
  const apply = () => {
    const theme = readColorTheme();
    for (const [name, value] of Object.entries(themes[theme])) target.style.setProperty('--' + name, value);
    target.style.colorScheme = theme;
    target.style.color = 'var(--foreground)';
    target.classList.toggle('studio-dark', theme === 'dark');
    onChange(theme);
  };
  apply();
  window.addEventListener('studio-theme-change', apply);
  window.addEventListener('storage', apply);
  return () => {
    window.removeEventListener('studio-theme-change', apply);
    window.removeEventListener('storage', apply);
  };
}
