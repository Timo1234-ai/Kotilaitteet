/* ─── Device Controls ─────────────────────────────────────────────────── */

/**
 * Toggle a device on/off via the REST API and update the UI.
 * @param {number} deviceId
 * @param {HTMLElement} btn - The button element that was clicked
 */
async function toggleDevice(deviceId, btn) {
  try {
    const res = await fetch(`/api/devices/${deviceId}/toggle`, { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    const device = await res.json();

    // Update button
    btn.textContent = device.state ? 'PÄÄLLÄ' : 'POIS';
    btn.classList.toggle('active', device.state);

    // Update card class (dashboard)
    const card = document.getElementById(`card-${deviceId}`);
    if (card) {
      card.classList.toggle('on', device.state);
      card.classList.toggle('off', !device.state);
    }
  } catch (e) {
    console.error('toggleDevice error:', e);
    alert('Virhe laitteen ohjauksessa: ' + e.message);
  }
}

/**
 * Set the auto-mode for a device.
 * @param {number} deviceId
 * @param {boolean} enabled
 */
async function setAuto(deviceId, enabled) {
  try {
    await fetch(`/api/devices/${deviceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto: enabled }),
    });
  } catch (e) {
    console.error('setAuto error:', e);
  }
}

/**
 * Set the maximum electricity price for a device.
 * @param {number} deviceId
 * @param {string|number} price
 */
async function setMaxPrice(deviceId, price) {
  try {
    await fetch(`/api/devices/${deviceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_price: parseFloat(price) }),
    });
  } catch (e) {
    console.error('setMaxPrice error:', e);
  }
}

/**
 * Add a new device.
 * @param {Event} event
 */
async function addDevice(event) {
  event.preventDefault();
  const name = document.getElementById('new-device-name').value.trim();
  const type = document.getElementById('new-device-type').value;
  const icon = document.getElementById('new-device-icon').value;
  if (!name) return;
  try {
    const res = await fetch('/api/devices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, type, icon }),
    });
    if (!res.ok) throw new Error(await res.text());
    location.reload();
  } catch (e) {
    alert('Virhe lisättäessä laitetta: ' + e.message);
  }
}

/**
 * Delete a device after confirmation.
 * @param {number} deviceId
 */
async function deleteDevice(deviceId) {
  if (!confirm('Poistetaanko laite?')) return;
  try {
    const res = await fetch(`/api/devices/${deviceId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    const row = document.getElementById(`row-${deviceId}`);
    if (row) row.remove();
  } catch (e) {
    alert('Virhe poistettaessa laitetta: ' + e.message);
  }
}

/* ─── Modal helpers ─────────────────────────────────────────────────────── */

function showAddDeviceModal() {
  document.getElementById('addDeviceModal').classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// Close modal when clicking outside
document.addEventListener('click', function (e) {
  document.querySelectorAll('.modal.open').forEach(function (modal) {
    if (e.target === modal) modal.classList.remove('open');
  });
});

/* ─── Price Chart ───────────────────────────────────────────────────────── */

/**
 * Draw a bar chart of hourly electricity prices.
 * @param {string} canvasId - ID of the canvas element
 * @param {Array} prices    - Array of price objects from the API
 * @param {Array} cheapHours - Array of cheap hour numbers
 * @param {number|null} currentHour - Highlight this hour
 */
function drawPriceChart(canvasId, prices, cheapHours, currentHour) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  // Resolve CSS variables
  const style = getComputedStyle(document.documentElement);
  const green = style.getPropertyValue('--green').trim() || '#2ecc71';
  const red   = style.getPropertyValue('--red').trim()   || '#e74c3c';
  const blue  = style.getPropertyValue('--accent').trim() || '#4f8ef7';
  const muted = style.getPropertyValue('--text-muted').trim() || '#8a93a8';

  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.clientWidth  || canvas.parentElement.clientWidth;
  const H   = canvas.clientHeight || 200;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);

  const PAD = { top: 20, right: 15, bottom: 40, left: 50 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top  - PAD.bottom;

  if (!prices || prices.length === 0) {
    ctx.fillStyle = muted;
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Ei hintatietoja', W / 2, H / 2);
    return;
  }

  const maxPrice = Math.max(...prices.map(p => p.price_kwh), 0.01);
  const barW     = chartW / prices.length;
  const cheapSet = new Set(cheapHours);

  // Draw bars
  prices.forEach((p, i) => {
    const barH  = (p.price_kwh / maxPrice) * chartH;
    const x     = PAD.left + i * barW + 1;
    const y     = PAD.top  + chartH - barH;
    const isCur = (p.hour === currentHour);
    ctx.fillStyle = isCur ? blue : cheapSet.has(p.hour) ? green : red;
    ctx.globalAlpha = isCur ? 1 : 0.75;
    ctx.fillRect(x, y, barW - 2, barH);
  });
  ctx.globalAlpha = 1;

  // X-axis labels (every 3 hours)
  ctx.fillStyle = muted;
  ctx.font = '11px sans-serif';
  ctx.textAlign = 'center';
  prices.forEach((p, i) => {
    if (p.hour % 3 === 0) {
      const x = PAD.left + i * barW + barW / 2;
      ctx.fillText(`${String(p.hour).padStart(2, '0')}`, x, H - PAD.bottom + 15);
    }
  });

  // Y-axis labels
  ctx.textAlign = 'right';
  const ySteps = 4;
  for (let s = 0; s <= ySteps; s++) {
    const val = (maxPrice * s) / ySteps;
    const y   = PAD.top + chartH - (val / maxPrice) * chartH;
    ctx.fillStyle = muted;
    ctx.fillText(val.toFixed(1), PAD.left - 5, y + 4);
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(PAD.left + chartW, y);
    ctx.stroke();
  }

  // Y-axis unit label
  ctx.save();
  ctx.translate(12, PAD.top + chartH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = muted;
  ctx.textAlign = 'center';
  ctx.fillText('snt/kWh', 0, 0);
  ctx.restore();
}
