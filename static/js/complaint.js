// Location button
const btn = document.getElementById('location-button');
if (btn) {
  btn.addEventListener('click', () => {
    if (!navigator.geolocation) {
      alert('Location is not supported by this browser.');
      return;
    }
    btn.textContent = '⏳ Getting location...';
    btn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      pos => {
        document.getElementById('latitude').value = pos.coords.latitude.toFixed(6);
        document.getElementById('longitude').value = pos.coords.longitude.toFixed(6);
        btn.textContent = '✓ Location captured';
        btn.style.borderColor = 'var(--success)';
        btn.style.color = 'var(--success)';
      },
      () => {
        btn.textContent = '📍 Use My Current Location';
        btn.disabled = false;
        alert('Could not retrieve location. You can still submit without it, but a geo-tagged photo is required.');
      }
    );
  });
}

// Photo preview & feedback
const photoInput = document.getElementById('photo-input');
const photoStatus = document.getElementById('photo-status');
if (photoInput) {
  photoInput.addEventListener('change', () => {
    const file = photoInput.files[0];
    if (!file) { photoStatus.textContent = ''; return; }
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'jpg' && ext !== 'jpeg') {
      photoStatus.innerHTML = '<span style="color:var(--danger)">⚠ Only JPG/JPEG photos are accepted. PNG and WEBP are not supported.</span>';
      photoInput.value = '';
      return;
    }
    photoStatus.innerHTML = '<span style="color:var(--success)">✓ Photo selected: ' + file.name + '</span>';
  });
}
