/* ═══════════════════════════════════════════════════════════════════
   animations.js — BookTale Animation Engine
   Uses Web Animations API & IntersectionObserver.
   All functions respect prefers-reduced-motion.
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ── Motion guard ────────────────────────────────────────────────
  function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  // ── 1. Staggered reveal (IntersectionObserver) ──────────────────
  function staggerReveal(selector, opts) {
    if (prefersReducedMotion()) return;
    opts = opts || {};
    const rootMargin = opts.rootMargin || '0px 0px -60px 0px';
    const threshold = opts.threshold || 0.05;

    const els = document.querySelectorAll(selector);
    if (!els.length) return;

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const delay = parseFloat(el.dataset.staggerDelay) ||
                      (parseFloat(el.style.getPropertyValue('--i')) || 0) * 40;
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition =
          'opacity 500ms cubic-bezier(0.16,1,0.3,1) ' + delay + 'ms, ' +
          'transform 500ms cubic-bezier(0.16,1,0.3,1) ' + delay + 'ms';
        requestAnimationFrame(function () {
          el.style.opacity = '1';
          el.style.transform = 'translateY(0)';
        });
        observer.unobserve(el);
      });
    }, { rootMargin: rootMargin, threshold: threshold });

    els.forEach(function (el) { observer.observe(el); });
    return observer;
  }

  // ── 2. Animate counter ──────────────────────────────────────────
  function animateCounter(el, from, to, duration) {
    if (prefersReducedMotion()) {
      el.textContent = to;
      return;
    }
    duration = duration || 1200;
    from = from || 0;
    const start = performance.now();
    const isFloat = (to % 1 !== 0) || (from % 1 !== 0);

    function tick(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = from + (to - from) * eased;
      el.textContent = isFloat ? current.toFixed(1) : Math.round(current);
      if (progress < 1) {
        requestAnimationFrame(tick);
      }
    }
    requestAnimationFrame(tick);
  }

  // ── 3. Init parallax ────────────────────────────────────────────
  function initParallax(selector, speed) {
    if (prefersReducedMotion()) return;
    speed = speed || 0.3;
    const el = document.querySelector(selector);
    if (!el) return;

    function onScroll() {
      const rect = el.getBoundingClientRect();
      const scrollY = window.scrollY || window.pageYOffset;
      const offset = rect.top - scrollY;
      el.style.transform = 'translateY(' + (offset * speed * 0.1) + 'px)';
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return function cleanup() { window.removeEventListener('scroll', onScroll); };
  }

  // ── 4. Confetti burst (Canvas) ──────────────────────────────────
  function burstConfetti(x, y, colors) {
    if (prefersReducedMotion()) return;
    colors = colors || ['#7c6af7', '#e8507a', '#0D9488', '#D97706', '#3B82F6'];

    const canvas = document.createElement('canvas');
    canvas.style.cssText =
      'position:fixed;inset:0;z-index:99998;pointer-events:none;width:100vw;height:100vh;';
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    const particles = [];
    const count = 80;

    for (let i = 0; i < count; i++) {
      particles.push({
        x: x || window.innerWidth / 2,
        y: y || window.innerHeight / 2,
        vx: (Math.random() - 0.5) * 14,
        vy: (Math.random() - 0.8) * 16 - 4,
        size: Math.random() * 8 + 4,
        color: colors[Math.floor(Math.random() * colors.length)],
        rotation: Math.random() * 360,
        rotSpeed: (Math.random() - 0.5) * 10,
        life: 1,
        decay: 0.01 + Math.random() * 0.015,
        shape: Math.random() > 0.5 ? 'rect' : 'circle',
      });
    }

    let frame;

    function animate() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      let alive = false;

      for (const p of particles) {
        if (p.life <= 0) continue;
        alive = true;
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.25; // gravity
        p.rotation += p.rotSpeed;
        p.life -= p.decay;

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.globalAlpha = Math.max(0, p.life);
        ctx.fillStyle = p.color;

        if (p.shape === 'rect') {
          ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
        } else {
          ctx.beginPath();
          ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }

      if (alive) {
        frame = requestAnimationFrame(animate);
      } else {
        canvas.remove();
      }
    }

    animate();

    // Cleanup after 4 seconds
    setTimeout(function () {
      cancelAnimationFrame(frame);
      if (canvas.parentNode) canvas.remove();
    }, 4000);
  }

  // ── 5. Magnetic hover ───────────────────────────────────────────
  function magneticHover(selector, strength) {
    if (prefersReducedMotion()) return;
    strength = strength || 0.3;
    const els = document.querySelectorAll(selector);
    if (!els.length) return;

    els.forEach(function (el) {
      el.addEventListener('mousemove', function (e) {
        const rect = el.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dx = (e.clientX - cx) * strength;
        const dy = (e.clientY - cy) * strength;
        el.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
      });

      el.addEventListener('mouseleave', function () {
        el.style.transform = 'translate(0, 0)';
      });
    });
  }

  // ── 6. Ripple effect ────────────────────────────────────────────
  function addRipple(el) {
    if (prefersReducedMotion()) return;
    // One-time setup: ensure position:relative for ripple containment
    if (!el._btRippleReady) {
      if (getComputedStyle(el).position === 'static') {
        el.style.position = 'relative';
      }
      el.style.overflow = 'hidden';
      el._btRippleReady = true;
    }
    el.addEventListener('click', function (e) {
      const rect = el.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const x = e.clientX - rect.left - size / 2;
      const y = e.clientY - rect.top - size / 2;

      const ripple = document.createElement('span');
      ripple.style.cssText =
        'position:absolute;border-radius:50%;width:' + size + 'px;height:' + size + 'px;' +
        'left:' + x + 'px;top:' + y + 'px;' +
        'background:rgba(255,255,255,0.35);transform:scale(0);' +
        'animation:bt-ripple-effect 600ms ease-out forwards;pointer-events:none;';
      el.appendChild(ripple);
      setTimeout(function () { if (ripple.parentNode) ripple.remove(); }, 700);
    });
  }

  // ── 7. Page transitions ─────────────────────────────────────────
  function initPageTransitions() {
    if (prefersReducedMotion()) return;

    // Add bt-page class to main content for entrance animation
    const main = document.querySelector('.main-content');
    if (main) {
      main.classList.add('bt-page');
    }

    // Reading progress bar
    let progressBar = document.getElementById('bt-progress-bar');
    if (!progressBar) {
      progressBar = document.createElement('div');
      progressBar.id = 'bt-progress-bar';
      document.body.appendChild(progressBar);
    }

    function updateProgress() {
      const scrollTop = window.scrollY || window.pageYOffset;
      const docHeight = Math.max(
        document.body.scrollHeight, document.documentElement.scrollHeight,
        document.body.offsetHeight, document.documentElement.offsetHeight,
        document.body.clientHeight, document.documentElement.clientHeight
      );
      const winHeight = window.innerHeight;
      const scrollable = docHeight - winHeight;
      const pct = scrollable > 0 ? Math.min((scrollTop / scrollable) * 100, 100) : 0;
      progressBar.style.width = pct + '%';
      progressBar.style.opacity = pct > 0 ? '1' : '0';
    }

    window.addEventListener('scroll', updateProgress, { passive: true });
    updateProgress();
  }

  // ── 8. Tilt effect ──────────────────────────────────────────────
  function initTilt(selector, maxTilt) {
    if (prefersReducedMotion()) return;
    maxTilt = maxTilt || 8;
    const els = document.querySelectorAll(selector);
    if (!els.length) return;

    els.forEach(function (el) {
      el.addEventListener('mousemove', function (e) {
        const rect = el.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;
        const tiltX = (y - 0.5) * maxTilt;
        const tiltY = (x - 0.5) * -maxTilt;
        el.style.transform =
          'perspective(800px) rotateX(' + tiltX + 'deg) rotateY(' + tiltY + 'deg) scale3d(1.02,1.02,1.02)';
      });

      el.addEventListener('mouseleave', function () {
        el.style.transform = 'perspective(800px) rotateX(0) rotateY(0) scale3d(1,1,1)';
        el.style.transition = 'transform 400ms cubic-bezier(0.16,1,0.3,1)';
        setTimeout(function () { el.style.transition = ''; }, 400);
      });
    });
  }

  // ── 9. Typewriter ───────────────────────────────────────────────
  function typewriter(el, text, speed) {
    if (prefersReducedMotion()) {
      el.textContent = text;
      return;
    }
    speed = speed || 50;
    el.textContent = '';
    el.style.visibility = 'visible';

    let i = 0;
    function type() {
      if (i < text.length) {
        el.textContent += text.charAt(i);
        i++;
        setTimeout(type, speed + Math.random() * 30);
      }
    }
    type();
  }

  // ── Auto-init on DOMContentLoaded ───────────────────────────────
  function autoInit() {
    // Page transitions + progress bar
    initPageTransitions();

    // Staggered reveal on any element with .bt-reveal class
    const revealObserver = staggerReveal('.bt-reveal');

    // Tilt on cover cards
    initTilt('.bt-cover-card', 6);

    // Ripple on primary buttons
    document.querySelectorAll('.btn-primary, .sidebar-post-btn').forEach(function (btn) {
      addRipple(btn);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  // ── Export to global BookTale namespace ──────────────────────────
  window.BookTale = window.BookTale || {};
  window.BookTale.animations = {
    staggerReveal: staggerReveal,
    animateCounter: animateCounter,
    initParallax: initParallax,
    burstConfetti: burstConfetti,
    magneticHover: magneticHover,
    addRipple: addRipple,
    initPageTransitions: initPageTransitions,
    initTilt: initTilt,
    typewriter: typewriter,
  };

})();
