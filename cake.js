import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

const canvas = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.25;

const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 2.6, 7.4);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.enablePan = false;
controls.minDistance = 3.5;
controls.maxDistance = 16;
controls.minPolarAngle = Math.PI * 0.28;
controls.maxPolarAngle = Math.PI * 0.55;
controls.target.set(0, 1.55, 0);

let userInteracted = false;
renderer.domElement.addEventListener('pointerdown', () => {
  userInteracted = true;
  const hint = document.getElementById('hint');
  if (hint) hint.style.opacity = '0';
});

// mobile-first: pull the camera back on narrow (portrait) viewports
function fitDistance(aspect) {
  if (aspect < 0.62) return 13.0;
  if (aspect < 0.85) return 10.8;
  if (aspect < 1.2) return 8.6;
  return 7.6;
}
function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  if (!userInteracted) {
    const dist = fitDistance(camera.aspect);
    const dir = camera.position.clone().sub(controls.target).normalize();
    camera.position.copy(controls.target).addScaledVector(dir, dist);
  }
}
window.addEventListener('resize', resize);
resize();

controls.autoRotate = true;
controls.autoRotateSpeed = 0.9;
controls.update();

// ---------- Lighting (bright & soft for the pastel PBR model) ----------
scene.add(new THREE.AmbientLight(0xfff0ea, 1.4));
scene.add(new THREE.HemisphereLight(0xfff8ee, 0x8a6070, 0.9));

const key = new THREE.DirectionalLight(0xffffff, 1.6);
key.position.set(-3, 6, 4);
scene.add(key);

const rim = new THREE.DirectionalLight(0xf2a1b8, 0.55);
rim.position.set(4, 3, -4);
scene.add(rim);

const bounce = new THREE.DirectionalLight(0xfff6e0, 0.4);
bounce.position.set(0, -2, 3);
scene.add(bounce);

const flameLight = new THREE.PointLight(0xffab5e, 1.8, 6, 2);
scene.add(flameLight);

// ---------- Load the Meshy cake (hamsters + "4" candle baked in) ----------
const draco = new DRACOLoader();
draco.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/');
const loader = new GLTFLoader();
loader.setDRACOLoader(draco);

const cake = new THREE.Group();
scene.add(cake);

const startBtn = document.getElementById('startBtn');
const startBtnLabel = startBtn.textContent;
startBtn.textContent = 'Preparando el pastel… 🎂';
startBtn.disabled = true;

let flameTip = new THREE.Vector3(0, 3.3, 0); // fallback; refined from the model bbox

loader.load(
  './model/cake.glb',
  (gltf) => {
    const model = gltf.scene;

    // center on origin, rest on y=0, scale to a ~3.4 unit tall centerpiece
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const scale = 3.4 / size.y;
    model.scale.setScalar(scale);
    model.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale);
    cake.add(model);

    // the "4" candle is the tallest point of the model — anchor the glow there
    flameTip.set(0, size.y * scale + 0.02, 0);
    glowSprite.position.copy(flameTip);
    flameLight.position.copy(flameTip);
    controls.target.set(0, size.y * scale * 0.48, 0);
    resize();

    startBtn.textContent = startBtnLabel;
    startBtn.disabled = false;
  },
  undefined,
  (err) => {
    console.error('No se pudo cargar el modelo', err);
    startBtn.textContent = startBtnLabel;
    startBtn.disabled = false;
  }
);

// soft ground shadow disc so the cake doesn't float visually
const shadowTex = (() => {
  const size = 256;
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(30,10,20,0.4)');
  g.addColorStop(0.7, 'rgba(30,10,20,0.15)');
  g.addColorStop(1, 'rgba(30,10,20,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(c);
})();
const shadow = new THREE.Mesh(
  new THREE.PlaneGeometry(5.2, 5.2),
  new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false })
);
shadow.rotation.x = -Math.PI / 2;
shadow.position.y = 0.005;
scene.add(shadow);

// ---------- Flame glow (the model's flame is baked; we add live flicker) ----------
function makeGlowTexture() {
  const size = 128;
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(255,220,150,0.85)');
  g.addColorStop(0.4, 'rgba(255,160,60,0.4)');
  g.addColorStop(1, 'rgba(255,120,40,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(c);
}
const glowSprite = new THREE.Sprite(new THREE.SpriteMaterial({
  map: makeGlowTexture(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending
}));
glowSprite.scale.set(0.9, 0.9, 1);
glowSprite.position.copy(flameTip);
scene.add(glowSprite);

let flameOn = true;
let flameEnergy = 1;

// ---------- Confetti (pastel palette) ----------
const palette = ['#f5b8c8', '#9fd8c2', '#f2d478', '#aacdf0', '#ffffff'];
function burstConfetti(originY = 0.25) {
  const duration = 1400;
  const end = Date.now() + duration;
  (function frame() {
    confetti({
      particleCount: 4,
      startVelocity: 32,
      spread: 70,
      ticks: 200,
      gravity: 0.9,
      scalar: 0.9,
      colors: palette,
      origin: { x: 0.5 + (Math.random() - 0.5) * 0.3, y: originY }
    });
    if (Date.now() < end) requestAnimationFrame(frame);
  })();
  confetti({ particleCount: 90, spread: 100, startVelocity: 45, origin: { x: 0.5, y: originY }, colors: palette, scalar: 1.1 });
}

// ---------- UI wiring ----------
const veil = document.getElementById('veil');
const blowBtn = document.getElementById('blowBtn');
const hint = document.getElementById('hint');

startBtn.addEventListener('click', () => {
  veil.classList.add('hidden');
  setTimeout(() => burstConfetti(0.15), 150);
  setTimeout(() => burstConfetti(0.1), 500);
  if (hint) setTimeout(() => { hint.style.opacity = '1'; }, 900);
});

let relightTimeout = null;
blowBtn.addEventListener('click', () => {
  burstConfetti(0.85);
  if (!flameOn) return;
  flameOn = false;
  blowBtn.textContent = '✨ Deseo pedido';
  clearTimeout(relightTimeout);
  relightTimeout = setTimeout(() => {
    flameOn = true;
    blowBtn.textContent = '🕯️ Soplar la vela';
  }, 3200);
});

// ---------- Animate ----------
const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();

  const targetEnergy = flameOn ? 1 : 0;
  flameEnergy += (targetEnergy - flameEnergy) * 0.15;

  const flicker = 0.8 + Math.sin(t * 9) * 0.1 + Math.sin(t * 23) * 0.06;
  glowSprite.material.opacity = flameEnergy * flicker;
  glowSprite.scale.setScalar(0.9 * (0.9 + flicker * 0.2));
  flameLight.intensity = 1.8 * flameEnergy * flicker;

  if (!userInteracted) cake.rotation.y = Math.sin(t * 0.15) * 0.05;

  controls.update();
  renderer.render(scene, camera);
}
animate();
