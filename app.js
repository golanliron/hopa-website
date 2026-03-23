/* ===========================
   HOPA — App JavaScript
   =========================== */

'use strict';

// ===========================
// HEADER — Scroll Shadow
// ===========================
const header = document.getElementById('header');

window.addEventListener('scroll', () => {
  if (window.scrollY > 10) {
    header.classList.add('scrolled');
  } else {
    header.classList.remove('scrolled');
  }
}, { passive: true });

// ===========================
// SEARCH BAR TOGGLE
// ===========================
const searchBar = document.getElementById('search-bar');
let searchOpen = false;

function toggleSearch() {
  searchOpen = !searchOpen;
  if (searchOpen) {
    searchBar.classList.add('open');
    setTimeout(() => {
      const input = document.getElementById('search-input');
      if (input) input.focus();
    }, 100);
  } else {
    searchBar.classList.remove('open');
    clearFilter();
  }
}

// ===========================
// MOBILE MENU TOGGLE
// ===========================
const mobileMenu = document.getElementById('mobile-menu');
let menuOpen = false;

function toggleMobileMenu() {
  menuOpen = !menuOpen;
  if (menuOpen) {
    mobileMenu.classList.add('open');
  } else {
    mobileMenu.classList.remove('open');
  }
}

function closeMobileMenu() {
  menuOpen = false;
  mobileMenu.classList.remove('open');
}

// Close menu on outside click
document.addEventListener('click', (e) => {
  if (menuOpen && !header.contains(e.target)) {
    closeMobileMenu();
  }
});

// ===========================
// SEARCH / FILTER LOGIC
// ===========================
let activeCategory = 'הכל';
let searchQuery = '';
let _searchDebounce;

function filterCards(query) {
  clearTimeout(_searchDebounce);
  _searchDebounce = setTimeout(() => {
    searchQuery = query.toLowerCase().trim();
    applyFilters();
  }, 200);
}

function filterByCategory(cat) {
  activeCategory = cat;

  // Update category item active state
  document.querySelectorAll('.category-item').forEach(item => {
    if (item.dataset.cat === cat || (cat === 'הכל' && item.dataset.cat === 'הכל')) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Update chip buttons
  document.querySelectorAll('.chip-btn').forEach(btn => {
    btn.classList.remove('active');
  });

  // Update filter info
  updateFilterInfo(cat);

  applyFilters();

  // Scroll to services section
  const servicesSection = document.getElementById('all-services');
  if (servicesSection) {
    setTimeout(() => {
      servicesSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  }
}

function applyFilters() {
  const cards = document.querySelectorAll('.service-card');
  let visibleCount = 0;

  cards.forEach(card => {
    const category = (card.dataset.category || '').toLowerCase();
    const text = card.innerText.toLowerCase();

    const matchesCategory = activeCategory === 'הכל' || category.includes(activeCategory.toLowerCase());
    const matchesSearch = searchQuery === '' || text.includes(searchQuery);

    if (matchesCategory && matchesSearch) {
      card.classList.remove('hidden-by-filter');
      card.style.display = '';
      visibleCount++;
    } else {
      card.classList.add('hidden-by-filter');
      card.style.display = 'none';
    }
  });

  // Show/hide no results
  const noResults = document.getElementById('no-results');
  if (noResults) {
    // Only count cards in the main grid
    const gridCards = document.querySelectorAll('#services-grid .service-card');
    const gridVisible = Array.from(gridCards).filter(c => c.style.display !== 'none').length;
    noResults.classList.toggle('hidden', gridVisible > 0);
  }
}

function clearFilter() {
  activeCategory = 'הכל';
  searchQuery = '';

  const searchInput = document.getElementById('search-input');
  if (searchInput) searchInput.value = '';

  document.querySelectorAll('.category-item').forEach(item => {
    item.classList.remove('active');
    if (item.dataset.cat === 'הכל') item.classList.add('active');
  });

  updateFilterInfo('הכל');
  applyFilters();
}

function updateFilterInfo(cat) {
  const filterInfo = document.getElementById('filter-info');
  const activeFilterTag = document.getElementById('active-filter-tag');

  if (cat === 'הכל') {
    filterInfo.classList.add('hidden');
  } else {
    filterInfo.classList.remove('hidden');
    // Update tag text (keep the × button)
    if (activeFilterTag) {
      activeFilterTag.childNodes[0].textContent = cat + ' ';
    }
  }
}

// ===========================
// SMOOTH SCROLL — anchor links
// ===========================
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', (e) => {
    const href = anchor.getAttribute('href');
    if (href === '#') return;

    const target = document.querySelector(href);
    if (target) {
      e.preventDefault();
      const headerHeight = header.offsetHeight;
      const targetTop = target.getBoundingClientRect().top + window.scrollY - headerHeight - 16;
      window.scrollTo({ top: targetTop, behavior: 'smooth' });
    }
  });
});

// ===========================
// INTERSECTION OBSERVER
// Animate sections on scroll
// ===========================
const observerOptions = {
  threshold: 0.1,
  rootMargin: '0px 0px -50px 0px'
};

const sectionObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      sectionObserver.unobserve(entry.target);
    }
  });
}, observerOptions);

// Add animate class to major sections and observe
document.querySelectorAll('section').forEach((section, index) => {
  if (index > 0) { // skip hero
    section.classList.add('section-animate');
    sectionObserver.observe(section);
  }
});

// ===========================
// CARD STAGGER ANIMATION
// ===========================
const cardObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('cards-visible');
      cardObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.05 });

document.querySelectorAll('.grid').forEach(grid => {
  const cards = grid.querySelectorAll('.service-card, .stat-card');
  if (cards.length > 0) {
    cards.forEach((card, i) => {
      card.style.opacity = '0';
      card.style.transform = 'translateY(16px)';
      card.style.transition = 'opacity 0.4s ease, transform 0.4s ease, box-shadow 0.25s ease';
      card.style.transitionDelay = (i * 80) + 'ms';
    });
    cardObserver.observe(grid);
  }
});

// ===========================
// KEYBOARD NAVIGATION
// ===========================
document.addEventListener('keydown', (e) => {
  // ESC closes search and mobile menu
  if (e.key === 'Escape') {
    if (searchOpen) {
      toggleSearch();
    }
    if (menuOpen) {
      closeMobileMenu();
    }
  }
});

// ===========================
// DYNAMIC SEO — meta tags per subcategory
// ===========================
const SEO_MAP = {
  'מלגות-לימודים': {
    title: 'מלגות לסטודנטים וצעירים 2026 | הופה',
    description: 'מאגר מלגות לסטודנטים וצעירים בישראל — מלגות לימודים, מלגות מחיה, מלגות לחיילים משוחררים ועוד. חינם ונגיש. מצאו את המלגה שלכם.',
  },
  'מכינות-ושנת-שירות': {
    title: 'מכינות קדם צבאיות ושנת שירות לאומי 2026 | הופה',
    description: 'רשימת מכינות קדם צבאיות ותוכניות שנת שירות לאומי בכל הארץ. השוו בין מכינות, בדקו מיקום ותנאים. חינם.',
  },
  'זכויות-חיילים-משוחררים': {
    title: 'מענק שחרור וזכויות חיילים משוחררים 2026 | הופה',
    description: 'כל הזכויות לחיילים משוחררים — מענק שחרור, מלגות, דיור, הטבות והכוונה תעסוקתית. ריכוז מלא במקום אחד.',
  },
  'חיילים-בודדים': {
    title: 'זכויות חיילים בודדים 2026 | הופה',
    description: 'כל הזכויות וההטבות לחיילים בודדים — מלגות, דיור, סיוע כלכלי וליווי. מדריך מלא ומעודכן.',
  },
  'הכוונה-תעסוקתית': {
    title: 'הכוונה תעסוקתית לצעירים | הופה',
    description: 'שירותי הכוונה תעסוקתית לצעירים — ייעוץ קריירה, כתיבת קורות חיים, הכנה לראיון עבודה. חינם.',
  },
  'הכשרות-תעסוקה': {
    title: 'הכשרות מקצועיות וקורסים לצעירים | הופה',
    description: 'קורסים והכשרות מקצועיות ממומנות לצעירים — טכנולוגיה, עיצוב, מלאכה ועוד. חינם ונגיש.',
  },
  'סיוע-רפואי-ורגשי': {
    title: 'סיוע רגשי ותמיכה נפשית לצעירים | הופה',
    description: 'קווי סיוע, ייעוץ רגשי וקבוצות תמיכה לצעירים. שירותים מקצועיים, חינמיים וסודיים.',
  },
  'הלנת-חירום': {
    title: 'דיור חירום ומגורים זמניים לצעירים | הופה',
    description: 'פתרונות דיור חירום ומגורים זמניים לצעירים בכל הארץ. סיוע מיידי וחינמי.',
  },
  'סיוע-כלכלי-ודיור': {
    title: 'סיוע כלכלי ודיור לצעירים | הופה',
    description: 'מענים כלכליים, מלגות מחיה, סיוע בשכר דירה ופתרונות דיור לצעירים בישראל.',
  },
  'סיוע-משפטי-ומיצוי-זכויות': {
    title: 'מיצוי זכויות וסיוע משפטי לצעירים | הופה',
    description: 'גלו אילו זכויות מגיעות לכם — סיוע משפטי, מיצוי זכויות, הטבות ומענקים לצעירים. חינם.',
  },
};

function updateSEO() {
  const params = new URLSearchParams(window.location.search);
  const sub = params.get('subcategory');
  if (!sub) return;

  const seo = SEO_MAP[sub];
  if (!seo) return;

  // Update title
  document.title = seo.title;

  // Update meta description
  let metaDesc = document.querySelector('meta[name="description"]');
  if (metaDesc) metaDesc.setAttribute('content', seo.description);

  // Update canonical
  let canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) {
    canonical.setAttribute('href', 'https://hopa.org.il/?subcategory=' + encodeURIComponent(sub));
  }

  // Update OG tags
  let ogTitle = document.querySelector('meta[property="og:title"]');
  if (ogTitle) ogTitle.setAttribute('content', seo.title);

  let ogDesc = document.querySelector('meta[property="og:description"]');
  if (ogDesc) ogDesc.setAttribute('content', seo.description);

  let ogUrl = document.querySelector('meta[property="og:url"]');
  if (ogUrl) ogUrl.setAttribute('content', 'https://hopa.org.il/?subcategory=' + encodeURIComponent(sub));
}

// Run SEO update immediately
updateSEO();

// ===========================
// INIT
// ===========================
document.addEventListener('DOMContentLoaded', () => {
  // Set first category as active
  const firstCat = document.querySelector('.category-item[data-cat="הכל"]');
  if (firstCat) firstCat.classList.add('active');

  // Make search-bar hidden initially via CSS class approach
  const sb = document.getElementById('search-bar');
  if (sb) {
    sb.style.display = 'block';
    sb.classList.remove('hidden');
  }

  // Make mobile-menu hidden initially
  const mm = document.getElementById('mobile-menu');
  if (mm) {
    mm.style.display = 'block';
    mm.classList.remove('hidden');
  }
});
