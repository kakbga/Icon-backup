const categories = { apps: 'Apps', flags: 'Flags', groups: 'Groups' };
const search = document.querySelector('#search');
const filters = document.querySelectorAll('[data-category]');
const results = document.querySelector('#results');
const gallery = document.querySelector('#gallery');
const copyStatus = document.querySelector('#copy-status');
const copyDialog = document.querySelector('#copy-dialog');
const manualUrl = document.querySelector('#manual-url');
let icons = [];
let category = 'all';

function setupTheme() {
  const toggle = document.querySelector('#theme-toggle');
  if (!toggle) return;
  const symbol = toggle.querySelector('.theme-symbol');
  const label = toggle.querySelector('.theme-label');
  const root = document.documentElement;

  function updateThemeToggle() {
    const isLight = root.dataset.theme === 'light';
    symbol.textContent = isLight ? '☾' : '☀︎';
    label.textContent = isLight ? 'Dark' : 'Light';
    toggle.setAttribute('aria-label', `Switch to ${isLight ? 'dark' : 'light'} mode`);
  }

  updateThemeToggle();
  toggle.hidden = false;
  toggle.addEventListener('click', () => {
    const theme = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = theme;
    updateThemeToggle();
    try {
      localStorage.setItem('netkit-theme', theme);
    } catch {
      // The theme still works for this page when storage is unavailable.
    }
  });
}

function copyWithSelection(url) {
  const previouslyFocused = document.activeElement;
  const field = document.createElement('textarea');
  field.className = 'visually-hidden';
  field.value = url;
  field.readOnly = true;
  field.tabIndex = -1;
  document.body.append(field);
  field.select();
  field.setSelectionRange(0, url.length);
  try {
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    field.remove();
    previouslyFocused.focus({ preventScroll: true });
  }
}

async function copyUrl(url, button, announcement, label = 'Copy URL', status = copyStatus) {
  let copied = false;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(url);
      copied = true;
    } catch {
      copied = copyWithSelection(url);
    }
  } else {
    copied = copyWithSelection(url);
  }

  if (!copied) {
    manualUrl.value = url;
    if (!copyDialog.open) copyDialog.showModal();
    manualUrl.select();
    manualUrl.setSelectionRange(0, manualUrl.value.length);
    return;
  }

  status.textContent = announcement;
  if (label === null) return true;
  button.textContent = 'Copied!';
  button.setAttribute('data-copied', '');
  clearTimeout(button.feedbackTimer);
  button.feedbackTimer = setTimeout(() => {
    button.textContent = label;
    button.removeAttribute('data-copied');
  }, 1600);
}

function createCard(icon) {
  const card = document.createElement('li');
  card.className = 'card';

  const link = document.createElement('a');
  link.className = 'icon-link';
  link.href = icon.rawUrl;
  link.target = '_blank';
  link.rel = 'noopener';
  link.setAttribute('aria-label', `Open ${icon.filename} on GitHub Raw (new tab)`);

  const image = document.createElement('img');
  image.src = icon.image;
  image.alt = '';
  image.loading = 'lazy';
  image.decoding = 'async';
  link.append(image);

  const name = document.createElement('p');
  name.className = 'name';
  name.textContent = icon.name;

  const label = document.createElement('p');
  label.className = 'category';
  label.textContent = categories[icon.category];

  const button = document.createElement('button');
  button.className = 'copy';
  button.type = 'button';
  button.textContent = 'Copy URL';
  button.setAttribute('aria-label', `Copy URL for ${icon.name} (${label.textContent})`);
  button.addEventListener('click', () => copyUrl(icon.rawUrl, button, `Copied URL for ${icon.name}.`));

  card.append(link, name, label, button);
  return card;
}

function render() {
  const query = search.value.trim().normalize('NFC').toLowerCase();
  const visible = icons.filter(icon => (
    (category === 'all' || icon.category === category) &&
    icon.filename.normalize('NFC').toLowerCase().includes(query)
  ));

  gallery.replaceChildren(...visible.map(createCard));
  results.textContent = visible.length
    ? `${visible.length} ${visible.length === 1 ? 'icon' : 'icons'}`
    : 'No matching icons.';
}

async function loadIcons() {
  try {
    const response = await fetch('./icons.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    icons = await response.json();

    const counts = { all: icons.length, apps: 0, flags: 0, groups: 0 };
    for (const icon of icons) counts[icon.category]++;

    for (const filter of filters) {
      filter.querySelector('span').textContent = counts[filter.dataset.category];
      filter.addEventListener('click', () => {
        category = filter.dataset.category;
        for (const button of filters) {
          button.setAttribute('aria-pressed', String(button === filter));
        }
        render();
      });
    }
    search.addEventListener('input', render);
    render();
  } catch (error) {
    results.textContent = 'Could not load icons. Refresh to try again.';
    console.error(error);
  }
}

function setupIconSubscription() {
  const url = new URL('./surge-icons.json', document.baseURI).href;
  const button = document.querySelector('#copy-icon-set');
  const status = document.querySelector('#subscription-copy-status');
  let clearStatus;
  button.addEventListener('click', async () => {
    clearTimeout(clearStatus);
    status.textContent = '';
    if (await copyUrl(url, button, 'Subscription URL copied', null, status)) {
      clearTimeout(clearStatus);
      clearStatus = setTimeout(() => { status.textContent = ''; }, 2000);
    }
  });
  button.hidden = false;

  const encodedUrl = encodeURIComponent(url);
  const imports = {
    loon: `loon://import?iconset=${encodedUrl}`,
    quantumult: `quantumult-x:///ui?module=gallery&type=icon&action=add&content=${encodeURIComponent(JSON.stringify([url]))}`,
    stash: `stash://install-icon-set?url=${encodedUrl}`,
  };
  for (const appLink of document.querySelectorAll('[data-icon-app]')) {
    appLink.href = imports[appLink.dataset.iconApp];
    appLink.hidden = false;
  }
}

setupTheme();
setupIconSubscription();
loadIcons();
