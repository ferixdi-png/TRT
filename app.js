async function loadTextImages() {
  const images = [...document.querySelectorAll('img[data-src-text]')];
  const cache = new Map();
  await Promise.all(images.map(async (img) => {
    const url = img.dataset.srcText;
    try {
      let data = cache.get(url);
      if (!data) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        data = (await response.text()).trim();
        cache.set(url, data);
      }
      img.src = data;
    } catch (error) {
      img.alt = `${img.alt} — изображение временно недоступно`;
      console.error('Не удалось загрузить изображение', url, error);
    }
  }));
}
loadTextImages();
const track = document.getElementById('track');
const slides = [...document.querySelectorAll('.slide')];
const current = document.getElementById('current');
const dotsWrap = document.getElementById('dots');
let index = 0;
let touchStart = 0;

slides.forEach((_, i) => {
  const dot = document.createElement('button');
  dot.className = `dot${i === 0 ? ' active' : ''}`;
  dot.setAttribute('aria-label', `Открыть слайд ${i + 1}`);
  dot.addEventListener('click', () => go(i));
  dotsWrap.appendChild(dot);
});
const dots = [...document.querySelectorAll('.dot')];

function go(nextIndex) {
  index = (nextIndex + slides.length) % slides.length;
  track.style.transform = `translateX(-${index * 100}%)`;
  current.textContent = String(index + 1).padStart(2, '0');
  dots.forEach((dot, i) => dot.classList.toggle('active', i === index));
  slides.forEach((slide, i) => slide.classList.toggle('active', i === index));
}

document.getElementById('prev').addEventListener('click', () => go(index - 1));
document.getElementById('next').addEventListener('click', () => go(index + 1));

document.getElementById('carousel').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowLeft') go(index - 1);
  if (e.key === 'ArrowRight') go(index + 1);
});
track.addEventListener('touchstart', (e) => { touchStart = e.changedTouches[0].clientX; }, {passive: true});
track.addEventListener('touchend', (e) => {
  const delta = e.changedTouches[0].clientX - touchStart;
  if (Math.abs(delta) > 45) go(index + (delta < 0 ? 1 : -1));
}, {passive: true});

const gate = document.getElementById('ageGate');
if (localStorage.getItem('seedream-age-ok') === 'yes') gate.classList.add('hidden');
document.getElementById('confirmAge').addEventListener('click', () => {
  localStorage.setItem('seedream-age-ok', 'yes');
  gate.classList.add('hidden');
});
