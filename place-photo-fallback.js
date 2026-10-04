/* Local reviewed photographs and resilient image loading for recommendation cards. */
(function () {
  'use strict';
  function normalize(name) {
    return String(name || '').trim().replace(/[（(](?:东|東|西|南|北)?(?:门|門|入口|出入口)[）)]$/, '')
      .replace(/[\s·•,，()（）_-]/g, '').toLowerCase();
  }
  const records = window.CURRENT_HK_PHOTOS || [];
  const aliases = new Map(), byUrl = new Map();
  records.forEach(record => {
    record.aliases.forEach(alias => aliases.set(normalize(alias), record));
    record.photos.forEach(photo => byUrl.set(photo.url, photo));
  });
  function lookup(place) {
    const city = String(place.city || '').toLowerCase();
    const hongKongNames = ['香港', '香港特别行政区', '香港特別行政區', 'hong kong', 'hong kong sar'];
    if (city && !hongKongNames.includes(city)) return null;
    const lat = place.latitude, lng = place.longitude;
    const hasCoordinates = lat != null && lng != null;
    const inHongKong = hasCoordinates
      ? Number(lat) >= 22.14 && Number(lat) <= 22.57 && Number(lng) >= 113.82 && Number(lng) <= 114.46
      : hongKongNames.includes(city);
    return inHongKong ? aliases.get(normalize(place.placeName)) : null;
  }
  function credit(url) { return byUrl.get(url) || null; }
  function updateCredit(img, url) {
    const link = img.parentNode.querySelector('.photo-credit');
    if (!link) return;
    const photo = credit(url);
    link.hidden = !photo;
    if (photo) {
      link.href = photo.credit_url;
      link.textContent = '© ' + photo.author;
    }
  }
  function onError(img) {
    let candidates;
    try { candidates = JSON.parse(img.dataset.photoCandidates); }
    catch (_) { candidates = []; }
    const index = Number(img.dataset.photoIndex || 0) + 1;
    if (index < candidates.length) {
      img.dataset.photoIndex = String(index);
      updateCredit(img, candidates[index]);
      img.src = candidates[index];
      return;
    }
    const parent = img.parentNode;
    const badge = document.createElement('span');
    badge.className = 'photo-demo-badge';
    badge.textContent = document.documentElement.lang === 'en' ? 'No place photo yet' : '暂无地点实景图';
    const link = parent.querySelector('.photo-credit');
    if (link) link.hidden = true;
    img.remove();
    parent.appendChild(badge);
  }
  window.CurrentPlacePhotos = { lookup, credit, onError };
})();
