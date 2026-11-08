(() => {
  document.querySelectorAll('.dismiss-message').forEach(button => button.addEventListener('click', () => button.closest('.message').remove()));
  document.querySelectorAll('input[type="password"]').forEach(input => {
    const wrapper = document.createElement('div'); wrapper.className = 'password-input';
    input.parentNode.insertBefore(wrapper, input); wrapper.append(input);
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.textContent = 'Show';
    toggle.setAttribute('aria-label', 'Show ' + (input.labels[0]?.textContent.replace('*', '').trim().toLowerCase() || 'password'));
    toggle.setAttribute('aria-pressed', 'false'); toggle.setAttribute('aria-controls', input.id);
    toggle.addEventListener('click', () => {
      const show = input.type === 'password'; input.type = show ? 'text' : 'password';
      toggle.textContent = show ? 'Hide' : 'Show'; toggle.setAttribute('aria-pressed', String(show));
      toggle.setAttribute('aria-label', (show ? 'Hide ' : 'Show ') + (input.labels[0]?.textContent.replace('*', '').trim().toLowerCase() || 'password'));
    }); wrapper.append(toggle);
  });
  const start = document.getElementById('id_start_date'), end = document.getElementById('id_end_date');
  if (start && end) {
    const validate = () => {end.min = start.value; end.setCustomValidity(start.value && end.value && end.value < start.value ? 'Choose an end date on or after your start date.' : '');};
    start.addEventListener('input', validate); end.addEventListener('input', validate); validate();
  }
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));
  const preview = document.getElementById('photo-preview');
  const photoInput = document.querySelector('.photo-form input[type="file"]');
  let previewUrl;
  if (photoInput && preview) photoInput.addEventListener('change', () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    preview.hidden = true; photoInput.setCustomValidity('');
    const file = photoInput.files[0]; if (!file) return;
    if (file.size > 5 * 1024 * 1024) {photoInput.setCustomValidity('Choose a photo smaller than 5 MB.'); photoInput.reportValidity(); return;}
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {photoInput.setCustomValidity('Choose a JPEG, PNG, or WebP photo.'); photoInput.reportValidity(); return;}
    previewUrl = URL.createObjectURL(file); preview.querySelector('img').src = previewUrl;
    document.getElementById('photo-filename').textContent = file.name; preview.hidden = false;
  });
  const photoForm = document.querySelector('.photo-form');
  if (photoForm) photoForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (photoForm.dataset.uploading === 'true') return;
    const status = document.getElementById('photo-upload-status');
    const button = photoForm.querySelector('button[type="submit"], button.button');
    const label = button.textContent;
    photoForm.dataset.uploading = 'true'; button.disabled = true; button.textContent = 'Uploading…';
    status.textContent = 'Uploading your photo. Please keep this page open.'; status.className = 'info-hint';
    status.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(photoForm.action, {
        method: 'POST', body: new FormData(photoForm),
        headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
      });
      if (response.redirected) throw new Error('Your session expired. Open the login page in another tab, sign in, then retry here.');
      let data;
      try {data = await response.json();} catch {throw new Error('The server could not finish the upload. Please try again.');}
      if (!response.ok) throw new Error(data.error || 'Your photo could not be saved. Please try again.');
      window.location.hash = 'trip-photos'; window.location.reload();
    } catch (error) {
      status.className = 'error-summary';
      status.textContent = error instanceof TypeError ? 'Could not connect. Check your connection, then click Save photo to retry.' : error.message;
      status.focus();
    } finally {
      photoForm.dataset.uploading = 'false'; button.disabled = false; button.textContent = label;
      status.setAttribute('aria-busy', 'false');
    }
  });
  const summary = document.querySelector('.form-error-summary'); if (summary) summary.focus();
  document.querySelectorAll('form[method="post"]').forEach(form => form.addEventListener('submit', event => {
    if (event.defaultPrevented) return;
    const button = event.submitter;
    if (button) {button.disabled = true; button.textContent = 'Saving…';}
  }));
  window.addEventListener('pageshow', event => {if (event.persisted) window.location.reload();});
})();
