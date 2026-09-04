/**
 * CreditDB - Static Web App Client Logic
 * Loads precalculated JSON data and renders fast, interactive tables & modals.
 */

// Global State
const state = {
  summary: null,
  works: [],
  filteredWorks: [],
  leaderboards: {},
  profiles: {},
  staffIndex: {}, // Fast lookup: name -> { all: compactItem, roles: { [role]: compactItem } }
  
  // Works table state
  worksPage: 1,
  worksPageSize: 50,
  worksSortField: "deviation_score",
  worksSortAsc: false,
  worksSearch: "",
  worksTier: "all",
  worksEra: "all",

  // Staff leaderboard state
  currentRole: "all",
  staffSort: "rating", // 'rating' or 'cumulative'
  staffSearch: "",
  staffPage: 1,
  staffPageSize: 50,
  filteredStaff: [],
};

// Japanese Text Normalization for Search
function normalizeText(text) {
  if (!text) return "";
  let s = String(text).toLowerCase();
  // Zenkaku to Hankaku alphanumeric
  s = s.replace(/[！-～]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));
  // Katakana to Hiragana
  s = s.replace(/[\u30a1-\u30f6]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60));
  // Historical / variation kana
  s = s.replace(/ゑ/g, "え").replace(/ゐ/g, "い").replace(/を/g, "お").replace(/ゔ/g, "ぶ");
  // Remove punctuation & whitespaces
  s = s.replace(/[\s\-_・:：,，.．!！?？/／★☆♪〜~]/g, "");
  return s;
}

// Role display names
const ROLE_NAMES = {
  all: "全役職",
  director: "監督",
  series_comp: "シリーズ構成 / 脚本",
  char_design: "キャラクターデザイン",
  sakkan: "作画監督",
  genga: "原画",
  unit_director: "演出 / 絵コンテ",
  music: "音楽",
  art_dir: "美術監督",
  studio: "アニメーション制作",
};

// Tier descriptions
const TIER_DESCS = {
  "S+": "同年代の全アニメの中で極めて突出した、歴史的メガヒット・超名作水準（上位約 2.3% 以内）。",
  "S": "その時代を代表する大傑作。高いクオリティと広範な支持を獲得した作品（上位約 6.7% 以内）。",
  "A+": "同年代の上位15%に位置する、確かな完成度と魅力を誇る秀作（上位約 15.9% 以内）。",
  "A": "平均を明確に上回り、ファン層から根強く支持される良作水準（上位約 30.9% 以内）。",
  "B+": "年代の平均水準以上を堅実に維持している安定作。",
  "B": "年代の平均的ボリュームゾーンに位置する標準的な作品。",
  "C": "同年代の平均的な評価を下回った作品群。",
  "D": "同年代の平均的な評価を大きく下回った作品群。",
};

// Initialize Application
document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupEventListeners();
  await loadStaticData();
});

// Setup Navigation Tabs
function setupTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      const targetId = tab.getAttribute("data-tab");
      document.querySelectorAll(".tab-pane").forEach((pane) => {
        pane.classList.remove("active");
      });
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }
    });
  });
}

// Fetch Static Data
async function loadStaticData() {
  try {
    const [sumRes, worksRes, lbRes, profRes] = await Promise.all([
      fetch("data/summary.json").then((r) => r.json()).catch(() => null),
      fetch("data/works.json").then((r) => r.json()),
      fetch("data/leaderboards.json").then((r) => r.json()),
      fetch("data/profiles.json").then((r) => r.json()).catch(() => ({})),
    ]);

    state.summary = sumRes;
    state.works = worksRes || [];
    state.leaderboards = lbRes || {};
    state.profiles = profRes || {};

    // Update Header stats
    if (state.summary) {
      const elWorks = document.getElementById("statTotalWorks");
      const elRange = document.getElementById("statYearRange");
      if (elWorks) elWorks.textContent = state.summary.total_works.toLocaleString();
      if (elRange) elRange.textContent = `${state.summary.year_min} - ${state.summary.year_max}`;
    }

    // Build fast lookup index across all staff
    state.staffIndex = {};
    for (const [roleKey, roleObj] of Object.entries(state.leaderboards || {})) {
      const items = roleObj.items || [];
      for (const it of items) {
        if (!state.staffIndex[it.n]) {
          state.staffIndex[it.n] = { all: null, roles: {} };
        }
        if (roleKey === "all") {
          state.staffIndex[it.n].all = it;
        } else {
          state.staffIndex[it.n].roles[roleKey] = it;
        }
      }
    }

    applyWorksFilters();
    applyStaffFilters();
  } catch (err) {
    console.error("Failed to load static datasets:", err);
    const tbody = document.getElementById("worksTableBody");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" class="loading-td" style="color:var(--color-rose);">データの読み込みに失敗しました。ローカルサーバー経由（http://...）でアクセスしてください。</td></tr>`;
    }
  }
}

// Setup Event Listeners
function setupEventListeners() {
  // Works Search
  const searchInput = document.getElementById("workSearchInput");
  const searchClear = document.getElementById("workSearchClear");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      state.worksSearch = e.target.value.trim();
      state.worksPage = 1;
      applyWorksFilters();
    });
  }
  if (searchClear) {
    searchClear.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      state.worksSearch = "";
      state.worksPage = 1;
      applyWorksFilters();
    });
  }

  // Tier Filter
  const filterTier = document.getElementById("filterTier");
  if (filterTier) {
    filterTier.addEventListener("change", (e) => {
      state.worksTier = e.target.value;
      state.worksPage = 1;
      applyWorksFilters();
    });
  }

  // Era Filter
  const filterEra = document.getElementById("filterYearEra");
  if (filterEra) {
    filterEra.addEventListener("change", (e) => {
      state.worksEra = e.target.value;
      state.worksPage = 1;
      applyWorksFilters();
    });
  }

  // Sort Select
  const sortSelect = document.getElementById("sortWorksSelect");
  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val === "deviation_desc") {
        state.worksSortField = "deviation_score";
        state.worksSortAsc = false;
      } else if (val === "deviation_asc") {
        state.worksSortField = "deviation_score";
        state.worksSortAsc = true;
      } else if (val === "raw_desc") {
        state.worksSortField = "anilist_raw_score";
        state.worksSortAsc = false;
      } else if (val === "raw_asc") {
        state.worksSortField = "anilist_raw_score";
        state.worksSortAsc = true;
      } else if (val === "year_desc") {
        state.worksSortField = "year";
        state.worksSortAsc = false;
      } else if (val === "year_asc") {
        state.worksSortField = "year";
        state.worksSortAsc = true;
      }
      applyWorksSorting();
      renderWorksTable();
    });
  }

  // Table Header Click Sorting
  const sortableThs = document.querySelectorAll("#worksTable th.sortable");
  sortableThs.forEach((th) => {
    th.addEventListener("click", () => {
      const field = th.getAttribute("data-sort");
      if (state.worksSortField === field) {
        state.worksSortAsc = !state.worksSortAsc;
      } else {
        state.worksSortField = field;
        state.worksSortAsc = field === "title"; // title defaults to asc, numbers to desc
      }

      // Update Header styles
      sortableThs.forEach((t) => t.classList.remove("active-sort"));
      th.classList.add("active-sort");
      const icon = th.querySelector(".sort-icon");
      if (icon) {
        icon.textContent = state.worksSortAsc ? "▲" : "▼";
      }

      applyWorksSorting();
      renderWorksTable();
    });
  });

  // Pagination
  const btnPrev = document.getElementById("btnPrevPage");
  const btnNext = document.getElementById("btnNextPage");
  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (state.worksPage > 1) {
        state.worksPage--;
        renderWorksTable();
      }
    });
  }
  if (btnNext) {
    btnNext.addEventListener("click", () => {
      const maxPage = Math.ceil(state.filteredWorks.length / state.worksPageSize);
      if (state.worksPage < maxPage) {
        state.worksPage++;
        renderWorksTable();
      }
    });
  }

  // Staff Pagination
  const btnPrevStaff = document.getElementById("btnPrevStaffPage");
  const btnNextStaff = document.getElementById("btnNextStaffPage");
  if (btnPrevStaff) {
    btnPrevStaff.addEventListener("click", () => {
      if (state.staffPage > 1) {
        state.staffPage--;
        renderLeaderboard();
      }
    });
  }
  if (btnNextStaff) {
    btnNextStaff.addEventListener("click", () => {
      const maxPage = Math.ceil(state.filteredStaff.length / state.staffPageSize);
      if (state.staffPage < maxPage) {
        state.staffPage++;
        renderLeaderboard();
      }
    });
  }

  // Staff Role Pills
  const rolePills = document.querySelectorAll(".role-pill");
  rolePills.forEach((pill) => {
    pill.addEventListener("click", () => {
      rolePills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.currentRole = pill.getAttribute("data-role");
      state.staffPage = 1;
      applyStaffFilters();
    });
  });

  // Staff Search & Sort
  const staffSearchInput = document.getElementById("staffSearchInput");
  const staffSearchClear = document.getElementById("staffSearchClear");
  if (staffSearchInput) {
    staffSearchInput.addEventListener("input", (e) => {
      state.staffSearch = e.target.value.trim();
      state.staffPage = 1;
      applyStaffFilters();
    });
  }
  if (staffSearchClear) {
    staffSearchClear.addEventListener("click", () => {
      if (staffSearchInput) staffSearchInput.value = "";
      state.staffSearch = "";
      state.staffPage = 1;
      applyStaffFilters();
    });
  }

  const sortStaffSelect = document.getElementById("sortStaffSelect");
  if (sortStaffSelect) {
    sortStaffSelect.addEventListener("change", (e) => {
      state.staffSort = e.target.value;
      state.staffPage = 1;
      applyStaffFilters();
    });
  }

  // Modals close
  const animeClose = document.getElementById("modalAnimeClose");
  const staffClose = document.getElementById("modalStaffClose");
  const animeModal = document.getElementById("animeModal");
  const staffModal = document.getElementById("staffModal");

  if (animeClose) animeClose.addEventListener("click", () => animeModal.classList.remove("open"));
  if (staffClose) staffClose.addEventListener("click", () => staffModal.classList.remove("open"));

  window.addEventListener("click", (e) => {
    if (e.target === animeModal) animeModal.classList.remove("open");
    if (e.target === staffModal) staffModal.classList.remove("open");
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      animeModal.classList.remove("open");
      staffModal.classList.remove("open");
    }
  });
}

// Filter Works
function applyWorksFilters() {
  let list = state.works;

  // Search filter
  if (state.worksSearch) {
    const qNorm = normalizeText(state.worksSearch);
    list = list.filter((w) => {
      if (normalizeText(w.title).includes(qNorm)) return true;
      if (normalizeText(w.title_en).includes(qNorm)) return true;
      // Search in staff names
      for (const [r, members] of Object.entries(w.staff || {})) {
        for (const n of members) {
          const nameStr = typeof n === "object" ? n.name : n;
          if (normalizeText(nameStr).includes(qNorm)) return true;
        }
      }
      return false;
    });
  }

  // Tier filter
  if (state.worksTier !== "all") {
    list = list.filter((w) => w.tier === state.worksTier);
  }

  // Era filter
  if (state.worksEra !== "all") {
    if (state.worksEra === "2020s") {
      list = list.filter((w) => w.year >= 2020);
    } else if (state.worksEra === "2010s") {
      list = list.filter((w) => w.year >= 2010 && w.year < 2020);
    } else if (state.worksEra === "2000s") {
      list = list.filter((w) => w.year >= 2000 && w.year < 2010);
    } else if (state.worksEra === "1990s") {
      list = list.filter((w) => w.year >= 1990 && w.year < 2000);
    } else if (state.worksEra === "1980s") {
      list = list.filter((w) => w.year < 1990);
    }
  }

  state.filteredWorks = list;
  applyWorksSorting();
  renderWorksTable();
}

// Sort Works
function applyWorksSorting() {
  const f = state.worksSortField;
  const asc = state.worksSortAsc;

  state.filteredWorks.sort((a, b) => {
    let va = a[f];
    let vb = b[f];
    if (typeof va === "string") {
      return asc ? va.localeCompare(vb, "ja") : vb.localeCompare(va, "ja");
    }
    return asc ? va - vb : vb - va;
  });
}

// Render Works Table
function renderWorksTable() {
  const tbody = document.getElementById("worksTableBody");
  if (!tbody) return;

  const total = state.filteredWorks.length;
  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-td">条件に一致する作品が見つかりませんでした。</td></tr>`;
    updatePagination(0, 0, 0);
    return;
  }

  const startIdx = (state.worksPage - 1) * state.worksPageSize;
  const endIdx = Math.min(startIdx + state.worksPageSize, total);
  const pageItems = state.filteredWorks.slice(startIdx, endIdx);

  const formatStaffList = (arr) => {
    if (!arr || !arr.length) return "";
    return arr.map((s) => (typeof s === "object" ? s.name : s)).join(", ");
  };

  let html = "";
  pageItems.forEach((w, idx) => {
    const globalIdx = startIdx + idx + 1;
    const tierClass = `tier-${w.tier.replace("+", "-plus")}`;

    // Format main staff string
    const staffParts = [];
    if (w.staff?.director?.length) staffParts.push(`監督: ${formatStaffList(w.staff.director)}`);
    if (w.staff?.series_comp?.length) staffParts.push(`構成: ${formatStaffList(w.staff.series_comp)}`);
    if (w.staff?.char_design?.length) staffParts.push(`キャラ: ${formatStaffList(w.staff.char_design)}`);
    if (w.staff?.studio?.length) staffParts.push(`制作: ${formatStaffList(w.staff.studio)}`);
    const staffStr = staffParts.join(" / ") || "-";

    html += `
      <tr onclick="openAnimeModal('${w.id}')">
        <td style="text-align: center; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">#${globalIdx}</td>
        <td>
          <span class="work-title-cell">${escapeHtml(w.title)}</span>
          ${w.title_en ? `<span class="work-title-en">${escapeHtml(w.title_en)}</span>` : ""}
        </td>
        <td style="text-align: center; font-family: 'JetBrains Mono', monospace; color: var(--text-secondary);">${w.year}</td>
        <td style="text-align: right;">
          <span class="score-num deviation-val">${w.deviation_score.toFixed(1)}</span>
        </td>
        <td style="text-align: right;">
          <span class="score-num raw-score-val">${w.anilist_raw_score.toFixed(1)}点</span>
        </td>
        <td style="text-align: center;">
          <span class="tier-badge ${tierClass}">${w.tier}</span>
        </td>
        <td>
          <div class="staff-summary-cell" title="${escapeHtml(staffStr)}">${escapeHtml(staffStr)}</div>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
  updatePagination(startIdx + 1, endIdx, total);
}

// Update Pagination Bar
function updatePagination(start, end, total) {
  const pageInfo = document.getElementById("pageInfo");
  const curPageNum = document.getElementById("currentPageNum");
  const btnPrev = document.getElementById("btnPrevPage");
  const btnNext = document.getElementById("btnNextPage");

  if (pageInfo) pageInfo.textContent = `${start} - ${end} / ${total.toLocaleString()} 作品`;
  if (curPageNum) curPageNum.textContent = state.worksPage;

  const maxPage = Math.ceil(total / state.worksPageSize);
  if (btnPrev) btnPrev.disabled = state.worksPage <= 1;
  if (btnNext) btnNext.disabled = state.worksPage >= maxPage;
}

// Filter & Sort Staff Leaderboard
function applyStaffFilters() {
  const roleData = state.leaderboards[state.currentRole];
  let list = roleData?.items ? [...roleData.items] : [];

  if (state.staffSearch) {
    const qNorm = normalizeText(state.staffSearch);
    list = list.filter((item) => normalizeText(item.n).includes(qNorm));
  }

  // Sort list
  if (state.staffSort === "cumulative") {
    list.sort((a, b) => a.ck - b.ck);
  } else {
    list.sort((a, b) => a.rk - b.rk);
  }

  state.filteredStaff = list;
  renderLeaderboard();
}

// Render Leaderboard
function renderLeaderboard() {
  const tbody = document.getElementById("leaderboardTableBody");
  if (!tbody) return;

  const total = state.filteredStaff.length;
  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-td">該当するスタッフが見つかりませんでした。</td></tr>`;
    updateStaffPagination(0, 0, 0);
    return;
  }

  const startIdx = (state.staffPage - 1) * state.staffPageSize;
  const endIdx = Math.min(startIdx + state.staffPageSize, total);
  const pageItems = state.filteredStaff.slice(startIdx, endIdx);

  const isCum = state.staffSort === "cumulative";

  let html = "";
  pageItems.forEach((item, idx) => {
    const rankNum = state.staffSearch ? (startIdx + idx + 1) : (isCum ? item.ck : item.rk);
    const tier = isCum ? (item.ct || "B") : (item.rt || "B");
    const tierClass = `tier-${tier.replace("+", "-plus")}`;
    const bestWorkStr = item.bt
      ? `${item.bt} (${item.by} / Z=+${item.bz.toFixed(2)})`
      : "-";

    html += `
      <tr onclick="openStaffModal('${escapeJsStr(item.n)}')">
        <td style="text-align: center; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">#${rankNum}</td>
        <td>
          <span style="font-weight: 700; color: #ffffff;">${escapeHtml(item.n)}</span>
        </td>
        <td style="text-align: center;">
          <span class="tier-badge ${tierClass}">Tier ${tier}</span>
        </td>
        <td style="text-align: center; font-family: 'JetBrains Mono', monospace; color: var(--text-secondary);">${item.w} 作</td>
        <td style="text-align: right;">
          <span class="score-num" style="color: var(--color-cyan); font-size: 0.95rem;">${item.r.toFixed(3)}</span>
        </td>
        <td style="text-align: right;">
          <span class="score-num" style="color: var(--color-green); font-size: 0.95rem;">${item.z >= 0 ? "+" : ""}${item.z.toFixed(2)}</span>
        </td>
        <td>
          <span style="font-size: 0.82rem; color: var(--text-secondary);">${escapeHtml(bestWorkStr)}</span>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
  updateStaffPagination(startIdx + 1, endIdx, total);
}

// Update Staff Pagination Bar
function updateStaffPagination(start, end, total) {
  const pageInfo = document.getElementById("staffPageInfo");
  const curPageNum = document.getElementById("currentStaffPageNum");
  const btnPrev = document.getElementById("btnPrevStaffPage");
  const btnNext = document.getElementById("btnNextStaffPage");

  if (pageInfo) pageInfo.textContent = `${start} - ${end} / ${total.toLocaleString()} 名`;
  if (curPageNum) curPageNum.textContent = state.staffPage;

  const maxPage = Math.ceil(total / state.staffPageSize);
  if (btnPrev) btnPrev.disabled = state.staffPage <= 1;
  if (btnNext) btnNext.disabled = state.staffPage >= maxPage;
}

// Open Anime Detail Modal
window.openAnimeModal = function (workId) {
  const work = state.works.find((w) => w.id === workId);
  if (!work) return;

  // Close staffModal so animeModal never opens behind it
  const staffModal = document.getElementById("staffModal");
  if (staffModal) {
    staffModal.classList.remove("open");
  }

  const modal = document.getElementById("animeModal");
  if (!modal) return;
  modal.style.zIndex = "250";

  document.getElementById("modalAnimeTitle").textContent = work.title;
  document.getElementById("modalAnimeSub").textContent = `${work.year}年公開 ${work.title_en ? `/ ${work.title_en}` : ""}`;

  // Card 1: 偏差値
  document.getElementById("modalAnimeDeviation").textContent = work.deviation_score.toFixed(1);
  document.getElementById("modalAnimeDevRank").textContent = `🏆 年代補正順位: 第 #${work.deviation_rank} 位 / ${state.works.length.toLocaleString()} 作品`;
  const tierClass = `tier-${work.tier.replace("+", "-plus")}`;
  document.getElementById("modalAnimeDevTier").innerHTML = `
    <span class="tier-badge ${tierClass}">${work.tier}</span>
    <span class="percentile-text">上位 ${work.percentile.toFixed(2)}%</span>
  `;

  // Card 2: AniList 素点
  document.getElementById("modalAnimeRawScore").textContent = `${work.anilist_raw_score.toFixed(1)}点`;
  document.getElementById("modalAnimeRawRank").textContent = `素点順位: 第 #${work.raw_rank} 位 / ${state.works.length.toLocaleString()} 作品`;

  // Card 3: Tier 判定
  const tierBadge = document.getElementById("modalAnimeTierBadge");
  tierBadge.className = `tier-badge ${tierClass}`;
  tierBadge.textContent = `Tier ${work.tier}`;
  document.getElementById("modalAnimeTierDesc").textContent = TIER_DESCS[work.tier] || "";

  // Staff Credits with Color-Coded [総合実力Tier / 生涯累積Tier]
  const staffGrid = document.getElementById("modalAnimeStaffGrid");
  let staffHtml = "";

  const roleOrder = ["director", "series_comp", "char_design", "sakkan", "genga", "unit_director", "music", "art_dir", "studio"];
  roleOrder.forEach((roleKey) => {
    const members = work.staff?.[roleKey] || [];
    if (members.length > 0) {
      staffHtml += `
        <div class="staff-credit-box">
          <div class="staff-role-title">${ROLE_NAMES[roleKey] || roleKey} (${members.length}名)</div>
          <div style="display: flex; flex-direction: column; gap: 4px;">
            ${members
              .map((m) => {
                if (typeof m === "object") {
                  const rtClass = (m.rt || "B").replace("+", "-plus");
                  const ctClass = (m.ct || "B").replace("+", "-plus");
                  return `
                    <div class="staff-credit-item">
                      <span class="staff-tier-pill" title="総合実力Tier: ${m.rt} / 生涯累積Tier: ${m.ct}">
                        <span class="tier-tag tier-tag-${rtClass}">${m.rt}</span>
                        <span class="tier-divider">/</span>
                        <span class="tier-tag tier-tag-${ctClass}">${m.ct}</span>
                      </span>
                      <span class="staff-name-link" onclick="event.stopPropagation(); openStaffModal('${escapeJsStr(m.name)}')">${escapeHtml(m.name)}</span>
                    </div>
                  `;
                } else {
                  return `
                    <div class="staff-credit-item">
                      <span style="color: #ffffff; font-size: 0.84rem; font-weight: 500;">${escapeHtml(m)}</span>
                    </div>
                  `;
                }
              })
              .join("")}
          </div>
        </div>
      `;
    }
  });

  staffGrid.innerHTML = staffHtml || `<div style="color:var(--text-muted); font-size:0.84rem;">制作陣情報なし</div>`;

  modal.classList.add("open");
};

// Open Staff Detail Modal
window.openStaffModal = function (staffName) {
  const prof = state.profiles[staffName];
  const modal = document.getElementById("staffModal");
  if (!modal) return;
  modal.style.zIndex = "250";

  if (!prof) {
    openBasicStaffModal(staffName);
    return;
  }

  const totalStaff = state.summary?.total_staff ? state.summary.total_staff.toLocaleString() : "22,896";

  document.getElementById("modalStaffName").textContent = prof.name;
  document.getElementById("modalStaffRole").textContent = `主役職: ${ROLE_NAMES[prof.primary_role] || prof.primary_role} / 参加本数: ${prof.total_works} 作品`;

  // Card 1: 総合実力 S(a)
  document.getElementById("modalStaffRating").textContent = prof.bayesian_rating.toFixed(3);
  const ratingTierBadge = document.getElementById("modalStaffRatingTierBadge");
  if (ratingTierBadge) {
    const rTier = prof.overall_rating_tier || "B";
    ratingTierBadge.className = `tier-badge tier-${rTier.replace("+", "-plus")}`;
    ratingTierBadge.textContent = `Tier ${rTier}`;
  }
  document.getElementById("modalStaffRank").textContent = `全スタッフ中 第 #${prof.overall_rank.toLocaleString()} 位 / ${totalStaff} 名`;

  // Card 2: 生涯累積実績 ΣZ
  document.getElementById("modalStaffCumZ").textContent = `${prof.career_cumulative_z >= 0 ? "+" : ""}${prof.career_cumulative_z.toFixed(2)}`;
  const cumTierBadge = document.getElementById("modalStaffCumTierBadge");
  if (cumTierBadge) {
    const cTier = prof.overall_cum_tier || "B";
    cumTierBadge.className = `tier-badge tier-${cTier.replace("+", "-plus")}`;
    cumTierBadge.textContent = `Tier ${cTier}`;
  }
  document.getElementById("modalStaffCumRank").textContent = `通算貢献順: 第 #${prof.cumulative_rank.toLocaleString()} 位 / ${totalStaff} 名`;

  // Department Grid (Side-by-side rating & cumulative sub-boxes with Tiers, scores, and rankings)
  const deptGrid = document.getElementById("modalStaffDeptGrid");
  let deptHtml = "";
  (prof.all_role_stats || []).forEach((st) => {
    const rTier = st.rating_tier || "B";
    const cTier = st.cum_tier || "B";
    const rTierClass = `tier-${rTier.replace("+", "-plus")}`;
    const cTierClass = `tier-${cTier.replace("+", "-plus")}`;
    const cumSign = st.career_cumulative_z >= 0 ? "+" : "";
    const cumScoreClass = st.career_cumulative_z >= 0 ? "score-green" : "score-rose";

    deptHtml += `
      <div class="dept-stat-card">
        <div class="dept-card-header">
          <span class="dept-title">${ROLE_NAMES[st.role] || st.role}</span>
          <span class="dept-meta">参加 ${st.works_count} 作 / 部門母数 ${st.role_total.toLocaleString()} 名</span>
        </div>
        <div class="dept-dual-columns">
          <!-- 総合実力区画 -->
          <div class="dept-subbox">
            <div class="dept-subbox-title">総合実力 S(a)</div>
            <div>
              <span class="tier-badge ${rTierClass}">Tier ${rTier}</span>
            </div>
            <div class="dept-subbox-score score-cyan">${st.bayesian_rating.toFixed(3)}</div>
            <div class="dept-subbox-rank">部門 #${st.rating_rank.toLocaleString()} 位</div>
          </div>

          <!-- 生涯累積実績区画 -->
          <div class="dept-subbox">
            <div class="dept-subbox-title">生涯累積 ΣZ</div>
            <div>
              <span class="tier-badge ${cTierClass}">Tier ${cTier}</span>
            </div>
            <div class="dept-subbox-score ${cumScoreClass}">${cumSign}${st.career_cumulative_z.toFixed(2)}</div>
            <div class="dept-subbox-rank">部門 #${st.cumulative_rank.toLocaleString()} 位</div>
          </div>
        </div>
      </div>
    `;
  });
  deptGrid.innerHTML = deptHtml || `<div style="color:var(--text-muted);">部門情報なし</div>`;

  // Timeline
  const timelineBody = document.getElementById("modalStaffTimelineBody");
  let timelineHtml = "";
  (prof.career_trajectory || []).forEach((t) => {
    timelineHtml += `
      <tr onclick="openAnimeModal('${escapeJsStr(t.work_id)}')" style="cursor: pointer;">
        <td style="text-align: center; font-family: 'JetBrains Mono', monospace; color: var(--text-secondary);">${t.year}</td>
        <td><span style="font-weight: 600; color: #ffffff;">${escapeHtml(t.work_title)}</span></td>
        <td style="color: var(--text-secondary);">${ROLE_NAMES[t.role] || t.role}</td>
        <td style="text-align: right; font-family: 'JetBrains Mono', monospace; font-weight: 700; color: ${t.z_score >= 0 ? "var(--color-green)" : "var(--color-rose)"};">
          ${t.z_score >= 0 ? "+" : ""}${t.z_score.toFixed(2)}
        </td>
      </tr>
    `;
  });
  timelineBody.innerHTML = timelineHtml || `<tr><td colspan="4" class="loading-td">年表データなし</td></tr>`;

  modal.classList.add("open");
};

// Fallback for staff not in precomputed top profiles (uses full leaderboards index + works dataset)
function openBasicStaffModal(staffName) {
  const modal = document.getElementById("staffModal");
  if (!modal) return;
  modal.style.zIndex = "250";
  document.getElementById("modalStaffName").textContent = staffName;

  const totalStaff = state.summary?.total_staff ? state.summary.total_staff.toLocaleString() : "22,896";
  const sIdx = state.staffIndex ? state.staffIndex[staffName] : null;

  // Find all works featuring this staff member
  const matchedWorks = [];
  for (const w of state.works || []) {
    let matchedRoles = [];
    for (const [r, members] of Object.entries(w.staff || {})) {
      for (const m of members) {
        const nameStr = typeof m === "object" ? m.name : m;
        if (nameStr === staffName) {
          matchedRoles.push(ROLE_NAMES[r] || r);
        }
      }
    }
    if (matchedRoles.length > 0) {
      matchedWorks.push({
        id: w.id,
        year: w.year,
        title: w.title,
        roles: matchedRoles.join(", "),
        dev: w.deviation_score,
      });
    }
  }

  // Determine primary role & total works
  let primaryRoleName = "制作スタッフ";
  let maxW = 0;
  if (sIdx && sIdx.roles) {
    for (const [rKey, rItem] of Object.entries(sIdx.roles)) {
      if (rItem.w > maxW) {
        maxW = rItem.w;
        primaryRoleName = ROLE_NAMES[rKey] || rKey;
      }
    }
  }
  const worksCount = (sIdx && sIdx.all) ? sIdx.all.w : matchedWorks.length;
  document.getElementById("modalStaffRole").textContent = `主役職: ${primaryRoleName} / 参加本数: ${worksCount} 作品`;

  // Stats: Rating & Cumulative
  const allItem = sIdx ? sIdx.all : null;
  const ratingEl = document.getElementById("modalStaffRating");
  const rBadge = document.getElementById("modalStaffRatingTierBadge");
  const rankEl = document.getElementById("modalStaffRank");
  const cumZEl = document.getElementById("modalStaffCumZ");
  const cBadge = document.getElementById("modalStaffCumTierBadge");
  const cumRankEl = document.getElementById("modalStaffCumRank");

  if (allItem) {
    ratingEl.textContent = allItem.r.toFixed(3);
    const rTier = allItem.rt || "B";
    if (rBadge) {
      rBadge.className = `tier-badge tier-${rTier.replace("+", "-plus")}`;
      rBadge.textContent = `Tier ${rTier}`;
    }
    rankEl.textContent = `全スタッフ中 第 #${allItem.rk.toLocaleString()} 位 / ${totalStaff} 名`;

    const cumSign = allItem.z >= 0 ? "+" : "";
    cumZEl.textContent = `${cumSign}${allItem.z.toFixed(2)}`;
    const cTier = allItem.ct || "B";
    if (cBadge) {
      cBadge.className = `tier-badge tier-${cTier.replace("+", "-plus")}`;
      cBadge.textContent = `Tier ${cTier}`;
    }
    cumRankEl.textContent = `通算貢献順: 第 #${allItem.ck.toLocaleString()} 位 / ${totalStaff} 名`;
  } else {
    ratingEl.textContent = "-";
    if (rBadge) {
      rBadge.className = "tier-badge tier-B";
      rBadge.textContent = "Tier -";
    }
    rankEl.textContent = `参加確認数: ${matchedWorks.length} 作品`;

    cumZEl.textContent = "-";
    if (cBadge) {
      cBadge.className = "tier-badge tier-B";
      cBadge.textContent = "Tier -";
    }
    cumRankEl.textContent = "集計枠外";
  }

  // Department Grid (Dual-columns for each role in sIdx.roles)
  const deptGrid = document.getElementById("modalStaffDeptGrid");
  let deptHtml = "";
  if (sIdx && sIdx.roles && Object.keys(sIdx.roles).length > 0) {
    for (const [rKey, rItem] of Object.entries(sIdx.roles)) {
      const roleTotal = state.leaderboards[rKey]?.total_count || 0;
      const rTier = rItem.rt || "B";
      const cTier = rItem.ct || "B";
      const rTierClass = `tier-${rTier.replace("+", "-plus")}`;
      const cTierClass = `tier-${cTier.replace("+", "-plus")}`;
      const cumSign = rItem.z >= 0 ? "+" : "";
      const cumScoreClass = rItem.z >= 0 ? "score-green" : "score-rose";

      deptHtml += `
        <div class="dept-stat-card">
          <div class="dept-card-header">
            <span class="dept-title">${ROLE_NAMES[rKey] || rKey}</span>
            <span class="dept-meta">参加 ${rItem.w} 作 / 部門母数 ${roleTotal.toLocaleString()} 名</span>
          </div>
          <div class="dept-dual-columns">
            <!-- 総合実力区画 -->
            <div class="dept-subbox">
              <div class="dept-subbox-title">総合実力 S(a)</div>
              <div>
                <span class="tier-badge ${rTierClass}">Tier ${rTier}</span>
              </div>
              <div class="dept-subbox-score score-cyan">${rItem.r.toFixed(3)}</div>
              <div class="dept-subbox-rank">部門 #${rItem.rk.toLocaleString()} 位</div>
            </div>

            <!-- 生涯累積実績区画 -->
            <div class="dept-subbox">
              <div class="dept-subbox-title">生涯累積 ΣZ</div>
              <div>
                <span class="tier-badge ${cTierClass}">Tier ${cTier}</span>
              </div>
              <div class="dept-subbox-score ${cumScoreClass}">${cumSign}${rItem.z.toFixed(2)}</div>
              <div class="dept-subbox-rank">部門 #${rItem.ck.toLocaleString()} 位</div>
            </div>
          </div>
        </div>
      `;
    }
  }
  deptGrid.innerHTML = deptHtml || `<div style="color:var(--text-muted); font-size:0.84rem;">部門統計集計外（参加本数少数等）</div>`;

  // Timeline
  const timelineBody = document.getElementById("modalStaffTimelineBody");
  let timelineHtml = "";
  matchedWorks.sort((a, b) => a.year - b.year);
  matchedWorks.forEach((w) => {
    const zScore = (w.dev - 50) / 10;
    const zSign = zScore >= 0 ? "+" : "";
    const zColor = zScore >= 0 ? "var(--color-green)" : "var(--color-rose)";
    timelineHtml += `
      <tr onclick="openAnimeModal('${escapeJsStr(w.id)}')" style="cursor: pointer;">
        <td style="text-align: center; font-family: 'JetBrains Mono', monospace; color: var(--text-secondary);">${w.year}</td>
        <td><span style="font-weight: 600; color: #ffffff;">${escapeHtml(w.title)}</span></td>
        <td style="color: var(--text-secondary);">${escapeHtml(w.roles)}</td>
        <td style="text-align: right; font-family: 'JetBrains Mono', monospace; font-weight: 700; color: ${zColor};">
          ${zSign}${zScore.toFixed(2)}
        </td>
      </tr>
    `;
  });
  timelineBody.innerHTML = timelineHtml || `<tr><td colspan="4" class="loading-td">作品データなし</td></tr>`;

  modal.classList.add("open");
}

// Utility: Escape HTML
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Utility: Escape JS string for inline event handlers
function escapeJsStr(str) {
  if (!str) return "";
  return String(str)
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/"/g, "&quot;");
}
