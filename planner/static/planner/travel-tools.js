(() => {
  const root = document.getElementById('travel-tools');
  if (!root) return;
  const endpoint = root.dataset.apiBase.replace(/destinations\/$/, '');
  function node(tag, text, className) {
    const el = document.createElement(tag); el.textContent = text;
    if (className) el.className = className; return el;
  }
  async function load(provider, params, target, button, display) {
    const originalLabel = button.textContent;
    button.disabled = true; button.textContent = 'Loading…';
    target.replaceChildren(node('p', 'Checking the latest information…', 'muted'));
    target.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(endpoint + provider + '/?' + new URLSearchParams(params), {headers: {'Accept': 'application/json'}});
      if (response.redirected) throw new Error('Please log in again to continue.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Service unavailable. Please try again.');
      target.replaceChildren(); display(data, target);
    } catch (error) {
      const friendly = error.message?.includes('not configured') ? 'This travel tool is unavailable right now. Your trip is saved, and you can still manage your budget. Please try again later.' : (error.message || 'Unable to connect. Please try again.');
      target.replaceChildren(node('p', friendly, 'error'));
    } finally {button.disabled = false; button.textContent = originalLabel; target.setAttribute('aria-busy', 'false');}
  }
  document.getElementById('destination-search').addEventListener('submit', event => {
    event.preventDefault();
    load('destinations', {q: document.getElementById('place-query').value}, document.getElementById('destination-results'), event.currentTarget.querySelector('button'), (data, target) => {
      if (!data.results.length) target.append(node('p', 'No matching places found. Try a nearby city and include the country.'));
      else target.append(node('p', 'Choose the correct location to save it to this trip.', 'muted'));
      data.results.forEach(place => {
        const button = node('button', place.label + ' — Select location', 'place-option'); button.type = 'button';
        button.addEventListener('click', () => {document.getElementById('location-token').value = place.token; document.getElementById('select-location').requestSubmit();});
        target.append(button);
      });
    });
  });
  document.getElementById('weather-load').addEventListener('click', event => {
    load('weather', {}, document.getElementById('weather-results'), event.currentTarget, (data, target) => {
      if (data.partial) target.append(node('p', 'Showing only trip dates within the current forecast window.', 'muted'));
      const table = document.createElement('table'); table.className = 'forecast-table';
      const head = document.createElement('thead'); const row = document.createElement('tr');
      ['Date', 'Low / High', 'Rain chance'].forEach(text => {const th = node('th', text); th.scope = 'col'; row.append(th);});
      head.append(row); table.append(head); const body = document.createElement('tbody');
      data.days.forEach(day => {
        const row = document.createElement('tr');
        [new Date(day.date + 'T12:00:00').toLocaleDateString(undefined, {month: 'short', day: 'numeric'}), `${day.low ?? '—'} / ${day.high ?? '—'} °C`, day.rain == null ? '—' : day.rain + '%'].forEach(text => row.append(node('td', text)));
        body.append(row);
      }); table.append(body); target.append(table, node('small', 'Local timezone: ' + data.timezone));
    });
  });
  document.getElementById('currency-form').addEventListener('submit', event => {
    event.preventDefault(); load('currency', {currency: document.getElementById('currency').value}, document.getElementById('currency-results'), event.currentTarget.querySelector('button'), (data, target) => {
      target.append(node('strong', data.currency + ' ' + Number(data.amount).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}), 'conversion-amount'), node('p', `1 PHP = ${data.rate} ${data.currency} · Rate dated ${data.date}`, 'muted'));
    });
  });
  document.getElementById('wiki-load').addEventListener('click', event => {
    load('wikipedia', {}, document.getElementById('wiki-results'), event.currentTarget, (data, target) => {
      target.append(node('h3', data.title), node('p', data.extract));
      const link = node('a', 'Read full article and attribution on Wikipedia ↗');
      link.href = data.url; link.target = '_blank'; link.rel = 'noopener'; target.append(link);
    });
  });
})();
