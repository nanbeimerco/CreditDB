/**
 * Anime Latent Quality & Staff Evaluator Dashboard Controller
 */

let shapChartInstance = null;
let comparisonData = [];
let currentFilteredComparison = [];
let compareCurrentPage = 1;
const COMPARE_PAGE_SIZE = 30;

let staffData = [];
let currentFilteredStaff = [];
let staffCurrentPage = 1;
const STAFF_PAGE_SIZE = 30;

// Presets data
const PRESETS = {
  eizouken: {
    title: "映像研には手を出すな！",
    year: 2020,
    director: "湯浅政明",
    series_comp: "木戸雄一郎",
    char_design: "浅野直之",
    music: "オオルタイチ",
    art_dir: "野原愛",
    studio: "サイエンスSARU",
    genga: "村上泉, 榎本柊斗, 松本憲生, 堀裕津, 田口愛梨",
  },
  bocchi: {
    title: "ぼっち・ざ・ろっく！",
    year: 2022,
    director: "斎藤圭一郎",
    series_comp: "吉田恵里香",
    char_design: "けろりら",
    music: "菊谷知樹",
    art_dir: "taracod",
    studio: "CloverWorks",
    genga: "けろりら, 榎本柊斗, 川上雄介, MYOUN",
  },
  frieren: {
    title: "葬送のフリーレン",
    year: 2023,
    director: "斎藤圭一郎",
    series_comp: "鈴木智尋",
    char_design: "長澤礼子",
    music: "Evan Call",
    art_dir: "高木佐和子",
    studio: "マッドハウス",
    genga: "榎本柊斗, 岩澤亨, 亀田祥倫, 松本憲生",
  },
  shingeki: {
    title: "進撃の巨人 Season 1",
    year: 2013,
    director: "荒木哲郎",
    series_comp: "小林靖子",
    char_design: "浅野恭司",
    music: "澤野弘之",
    art_dir: "吉原俊一郎",
    studio: "WIT STUDIO",
    genga: "今井有文, 世良悠子, 田中宏紀, 胡拓磨",
  },
  mob: {
    title: "モブサイコ100 II",
    year: 2019,
    director: "立川譲",
    series_comp: "瀬古浩司",
    char_design: "亀田祥倫",
    music: "川井憲次",
    art_dir: "河野羚",
    studio: "ボンズ",
    genga: "亀田祥倫, 榎本柊斗, 五十嵐祐貴, 田中宏紀",
  },
  new_sci: {
    title: "【仮想2025新作】サイエンスSARU × 湯浅監督",
    year: 2025,
    director: "湯浅政明",
    series_comp: "上田誠",
    char_design: "浅野直之",
    music: "牛尾憲輔",
    art_dir: "水谷利春",
    studio: "サイエンスSARU",
    genga: "榎本柊斗, 松本憲生, 伊東伸高, 井上俊之",
  },
  new_bones: {
    title: "【仮想2025新作】ボンズ アクション特化企画",
    year: 2025,
    director: "立川譲",
    series_comp: "瀬古浩司",
    char_design: "亀田祥倫",
    music: "林ゆうき",
    art_dir: "近藤由美子",
    studio: "ボンズ",
    genga: "中村豊, 亀田祥倫, 今井有文, 田中宏紀",
  },
};

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initPresetDropdown();
  initPredictForm();
  initComparisonFilters();
  initStaffFilters();
  initModal();
  initBulkCollectButton();
  initGlobalSearch();

  // Fast initial paint: load metrics and run prediction only
  loadStatusMetrics();
  applyPreset("eizouken");
  document.getElementById("predictForm").dispatchEvent(new Event("submit"));

  // Defer background fetch of large comparison data so UI remains snappy
  setTimeout(() => {
    if (comparisonData.length === 0) loadComparisonData();
  }, 400);
});

/* Tabs Switching with on-demand data load */
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");

      // On-demand lazy load
      if (targetId === "tab-compare" && comparisonData.length === 0) {
        loadComparisonData();
      } else if (targetId === "tab-staff" && staffData.length === 0) {
        loadStaffLeaderboard("all");
      }
    });
  });
}

/* Load Header Status Metrics */
async function loadStatusMetrics() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    document.getElementById("chipWorks").textContent = `${data.works_count} 作品`;
    if (data.metrics) {
      document.getElementById("chipRmse").textContent = data.metrics.rmse.toFixed(3);
      document.getElementById("chipPearson").textContent = data.metrics.pearson_r.toFixed(3);
    }
  } catch (err) {
    console.error("Status fetch error:", err);
  }
}

/* Presets */
function initPresetDropdown() {
  const select = document.getElementById("presetSelect");
  select.addEventListener("change", (e) => {
    const key = e.target.value;
    if (key && PRESETS[key]) {
      applyPreset(key);
      document.getElementById("predictForm").dispatchEvent(new Event("submit"));
    }
  });
}

function applyPreset(key) {
  const p = PRESETS[key];
  if (!p) return;
  document.getElementById("inputTitle").value = p.title;
  document.getElementById("inputYear").value = p.year;
  document.getElementById("inputDirector").value = p.director;
  document.getElementById("inputSeriesComp").value = p.series_comp;
  document.getElementById("inputCharDesign").value = p.char_design;
  const musicElem = document.getElementById("inputMusic");
  if (musicElem) musicElem.value = p.music || "";
  const artElem = document.getElementById("inputArtDir");
  if (artElem) artElem.value = p.art_dir || "";
  document.getElementById("inputStudio").value = p.studio;
  document.getElementById("inputGenga").value = p.genga;
}

/* Prediction Form & SHAP */
function initPredictForm() {
  const form = document.getElementById("predictForm");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btnPredict");
    btn.disabled = true;
    btn.innerHTML = "<span>⏳ 計算中...</span>";

    const title = document.getElementById("inputTitle").value;
    const year = parseInt(document.getElementById("inputYear").value, 10);
    const director = document.getElementById("inputDirector").value;
    const series_comp = document.getElementById("inputSeriesComp").value;
    const char_design = document.getElementById("inputCharDesign").value;
    const music = document.getElementById("inputMusic") ? document.getElementById("inputMusic").value : "";
    const art_dir = document.getElementById("inputArtDir") ? document.getElementById("inputArtDir").value : "";
    const studio = document.getElementById("inputStudio").value;
    const gengaStr = document.getElementById("inputGenga").value;

    const gengaList = gengaStr
      .split(/[,、\n]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const payload = {
      title,
      year,
      director,
      series_comp,
      char_design,
      music,
      art_dir,
      studio,
      genga: gengaList,
    };

    try {
      const res = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      renderPredictionResult(data);
    } catch (err) {
      console.error("Predict error:", err);
      alert("予測エラーが発生しました。");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "<span>⚡ 潜在クオリティを予測 & SHAP分析</span>";
    }
  });
}

function renderPredictionResult(data) {
  const badge = document.getElementById("badgeResultStatus");
  badge.textContent = `予測完了 (${data.release_year}年基準)`;
  badge.className = "badge badge-success";

  const zVal = data.predicted_z;
  const zElem = document.getElementById("valPredZ");
  zElem.textContent = (zVal >= 0 ? "+" : "") + zVal.toFixed(2);
  zElem.style.color = zVal >= 0.5 ? "var(--accent-green)" : (zVal < -0.3 ? "var(--accent-red)" : "var(--accent-blue)");

  document.getElementById("valPredScore").textContent = data.predicted_anilist_score.toFixed(1);

  const zTier = getZTierInfo(zVal);
  const tierContainer = document.getElementById("valPredTier");
  if (tierContainer) {
    tierContainer.innerHTML = `
      <div style="display:flex; justify-content:center; align-items:center; gap:0.4rem;">
        ${zTier.badgeHtml}
        <span style="font-size:0.75rem; font-weight:600; color:var(--text-secondary);">上位 ${zTier.pctStr}</span>
      </div>
    `;
  }

  const baseElem = document.getElementById("valBaseZ");
  baseElem.textContent = (data.base_z >= 0 ? "+" : "") + data.base_z.toFixed(2);

  // Render SHAP Chart
  renderShapChart(data.all_contributions, data.base_z);

  // Render Factor Bullets
  const posList = document.getElementById("listPosFactors");
  const negList = document.getElementById("listNegFactors");
  posList.innerHTML = "";
  negList.innerHTML = "";

  if (data.top_positive_factors.length === 0) {
    posList.innerHTML = `<li class="factor-item" style="color:var(--text-muted)">特筆すべき押し上げ要因なし</li>`;
  } else {
    data.top_positive_factors.forEach((f) => {
      posList.innerHTML += `
        <li class="factor-item">
          <span>${f.label_ja}</span>
          <span class="factor-val pos">+${f.shap_value.toFixed(3)}</span>
        </li>
      `;
    });
  }

  if (data.top_negative_factors.length === 0) {
    negList.innerHTML = `<li class="factor-item" style="color:var(--text-muted)">特筆すべき押し下げ要因なし</li>`;
  } else {
    data.top_negative_factors.forEach((f) => {
      negList.innerHTML += `
        <li class="factor-item">
          <span>${f.label_ja}</span>
          <span class="factor-val neg">${f.shap_value.toFixed(3)}</span>
        </li>
      `;
    });
  }
}

function renderShapChart(contributions, baseZ) {
  const sorted = [...(contributions || [])].sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value));
  const topContributions = sorted.filter((c) => Math.abs(c.shap_value) > 0.003).slice(0, 6);
  topContributions.sort((a, b) => b.shap_value - a.shap_value);

  const labels = topContributions.map((c) => c.label_ja.split("(")[0].trim());
  const values = topContributions.map((c) => c.shap_value);
  const colors = values.map((v) => (v >= 0 ? "#34d399" : "#f43f5e"));

  const canvas = document.getElementById("shapChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (shapChartInstance) {
    shapChartInstance.destroy();
  }

  shapChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "SHAP寄与度",
          data: values,
          backgroundColor: colors,
          borderRadius: 4,
          barThickness: 16,
          maxBarThickness: 20,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `寄与度: ${ctx.raw >= 0 ? "+" : ""}${ctx.raw.toFixed(3)}`,
          },
        },
      },
      scales: {
        x: {
          grid: {
            color: (c) => (c.tick.value === 0 ? "rgba(255, 255, 255, 0.35)" : "rgba(255, 255, 255, 0.05)"),
            lineWidth: (c) => (c.tick.value === 0 ? 1.5 : 1),
          },
          ticks: { color: "#a1a1aa", font: { family: "'Fira Code', monospace", size: 11 } },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#ffffff", font: { family: "'Inter', 'Noto Sans JP', sans-serif", size: 12, weight: "500" } },
        },
      },
    },
  });
}

/* Side-by-side Comparison Table with Pagination */
async function loadComparisonData() {
  try {
    const res = await fetch("/api/comparison");
    comparisonData = await res.json();
    currentFilteredComparison = comparisonData;
    sortComparisonData();
    updateHeaderSortIcons();
    compareCurrentPage = 1;
    renderComparisonTable();
  } catch (err) {
    console.error("Comparison fetch error:", err);
  }
}

let compareSortKey = "residual";
let compareSortDir = "desc";

function sortComparisonData() {
  currentFilteredComparison.sort((a, b) => {
    let va = a[compareSortKey];
    let vb = b[compareSortKey];
    if (typeof va === "string") {
      va = (va || "").toLowerCase();
      vb = (vb || "").toLowerCase();
      return compareSortDir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    va = va ?? 0;
    vb = vb ?? 0;
    return compareSortDir === "asc" ? va - vb : vb - va;
  });
}

function updateHeaderSortIcons() {
  const sortableHeaders = document.querySelectorAll("#compareTable th.sortable");
  sortableHeaders.forEach((th) => {
    const col = th.getAttribute("data-sort");
    const icon = th.querySelector(".sort-icon");
    if (col === compareSortKey) {
      th.classList.add("sorted");
      if (icon) icon.textContent = compareSortDir === "desc" ? "▼" : "▲";
    } else {
      th.classList.remove("sorted");
      if (icon) icon.textContent = "↕";
    }
  });
}

function initComparisonFilters() {
  const search = document.getElementById("filterCompareTitle");
  const verdict = document.getElementById("filterCompareVerdict");
  const sortSelect = document.getElementById("filterCompareSort");
  const btnPrev = document.getElementById("btnComparePrev");
  const btnNext = document.getElementById("btnCompareNext");

  let debounceTimer = null;
  const filterFn = () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const q = search.value.trim().toLowerCase();
      const v = verdict.value;

      currentFilteredComparison = comparisonData.filter((row) => {
        const matchTitle = !q || row.title.toLowerCase().includes(q);
        const matchVerdict = v === "all" || row.performance_verdict.includes(v);
        return matchTitle && matchVerdict;
      });
      sortComparisonData();
      compareCurrentPage = 1;
      renderComparisonTable();
    }, 120);
  };

  search.addEventListener("input", filterFn);
  verdict.addEventListener("change", filterFn);

  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      const lastUnderscore = val.lastIndexOf("_");
      compareSortKey = val.slice(0, lastUnderscore);
      compareSortDir = val.slice(lastUnderscore + 1);
      updateHeaderSortIcons();
      sortComparisonData();
      compareCurrentPage = 1;
      renderComparisonTable();
    });
  }

  const sortableHeaders = document.querySelectorAll("#compareTable th.sortable");
  sortableHeaders.forEach((th) => {
    th.addEventListener("click", () => {
      const col = th.getAttribute("data-sort");
      if (compareSortKey === col) {
        compareSortDir = compareSortDir === "desc" ? "asc" : "desc";
      } else {
        compareSortKey = col;
        compareSortDir = "desc";
      }
      if (sortSelect) {
        const matchingOpt = `${compareSortKey}_${compareSortDir}`;
        if (Array.from(sortSelect.options).some((o) => o.value === matchingOpt)) {
          sortSelect.value = matchingOpt;
        }
      }
      updateHeaderSortIcons();
      sortComparisonData();
      compareCurrentPage = 1;
      renderComparisonTable();
    });
  });

  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (compareCurrentPage > 1) {
        compareCurrentPage--;
        renderComparisonTable();
      }
    });
  }
  if (btnNext) {
    btnNext.addEventListener("click", () => {
      const maxPage = Math.ceil(currentFilteredComparison.length / COMPARE_PAGE_SIZE);
      if (compareCurrentPage < maxPage) {
        compareCurrentPage++;
        renderComparisonTable();
      }
    });
  }
}

function renderComparisonTable() {
  const tbody = document.getElementById("compareTableBody");
  const total = currentFilteredComparison.length;
  const pageInfo = document.getElementById("comparePageInfo");
  const btnPrev = document.getElementById("btnComparePrev");
  const btnNext = document.getElementById("btnCompareNext");

  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:var(--text-muted);">該当する作品が見つかりません</td></tr>`;
    if (pageInfo) pageInfo.textContent = "全 0 件中 0 件を表示";
    if (btnPrev) btnPrev.disabled = true;
    if (btnNext) btnNext.disabled = true;
    return;
  }

  const maxPage = Math.max(1, Math.ceil(total / COMPARE_PAGE_SIZE));
  if (compareCurrentPage > maxPage) compareCurrentPage = maxPage;

  const startIdx = (compareCurrentPage - 1) * COMPARE_PAGE_SIZE;
  const endIdx = Math.min(startIdx + COMPARE_PAGE_SIZE, total);
  const pageRows = currentFilteredComparison.slice(startIdx, endIdx);

  if (pageInfo) {
    pageInfo.textContent = `全 ${total.toLocaleString()} 作品中 ${startIdx + 1}〜${endIdx} 件を表示 (ページ ${compareCurrentPage} / ${maxPage})`;
  }
  if (btnPrev) btnPrev.disabled = compareCurrentPage <= 1;
  if (btnNext) btnNext.disabled = compareCurrentPage >= maxPage;

  tbody.innerHTML = pageRows
    .map((r) => {
      const residualColor =
        r.residual > 0.4
          ? "color:var(--accent-green);font-weight:600;"
          : r.residual < -0.4
          ? "color:var(--accent-red);font-weight:600;"
          : "color:var(--text-secondary);";

      let badgeClass = "badge-info";
      if (r.performance_verdict.includes("サプライズ")) badgeClass = "badge-success";
      else if (r.performance_verdict.includes("期待外れ")) badgeClass = "badge-danger";
      else badgeClass = "badge-warning";

      const totalWorks = r.total_works || comparisonData.length || 1624;
      const predRank = r.pred_score_rank || 0;
      const predTier = getTierInfo(predRank, totalWorks);

      return `
      <tr>
        <td style="font-weight:600;">
          <a class="action-link" onclick="openAnimeModal('${r.work_id}')" title="クリックで作品詳細・全スタッフ・SHAP分析を表示">${r.title}</a>
        </td>
        <td>${r.year}</td>
        <td style="font-family:'Fira Code'; font-weight:700; color:var(--neon-cyan);">
          ${(r.deviation_score !== undefined ? r.deviation_score : (50 + 10 * r.true_z_score)).toFixed(1)}
        </td>
        <td style="font-family:'Fira Code'; font-weight:600;">${r.anilist_raw_score.toFixed(1)}</td>
        <td style="font-family:'Fira Code';">${(r.debiased_b_i >= 0 ? "+" : "") + r.debiased_b_i.toFixed(2)}</td>
        <td style="font-family:'Fira Code'; font-weight:600; color:var(--accent-blue);">${(r.true_z_score >= 0 ? "+" : "") + r.true_z_score.toFixed(2)}</td>
        <td style="font-family:'Fira Code';">${(r.predicted_z_score >= 0 ? "+" : "") + r.predicted_z_score.toFixed(2)}</td>
        <td style="font-family:'Fira Code'; font-weight:700; color:var(--accent-blue);">
          <div>${r.predicted_score.toFixed(1)}点</div>
          <div style="margin-top:0.25rem; display:flex; align-items:center; gap:0.35rem;">
            ${predTier.badgeHtml}
            <span style="font-size:0.72rem; font-weight:600; color:var(--text-muted); font-family:inherit;">上位 ${predTier.pctStr}</span>
          </div>
        </td>
        <td style="${residualColor};font-family:'Fira Code';">${(r.residual >= 0 ? "+" : "") + r.residual.toFixed(2)}</td>
        <td><span class="badge ${badgeClass}">${r.performance_verdict}</span></td>
        <td style="font-size:0.8rem; color:var(--text-secondary);">${r.top_factor || "-"}</td>
      </tr>
    `;
    })
    .join("");
}

/* Staff Leaderboard with Pagination */
let currentStaffRole = "all";
let currentStaffSort = "rating";

async function loadStaffLeaderboard(role = currentStaffRole, sortBy = currentStaffSort) {
  currentStaffRole = role;
  currentStaffSort = sortBy;
  const roleQuery = role === "all" ? "" : `&role=${encodeURIComponent(role)}`;
  const url = `/api/leaderboard?sort_by=${encodeURIComponent(sortBy)}${roleQuery}&limit=1000`;
  try {
    const res = await fetch(url);
    staffData = await res.json();
    currentFilteredStaff = staffData;
    staffCurrentPage = 1;
    renderStaffTable();
  } catch (err) {
    console.error("Staff fetch error:", err);
  }
}

function initStaffFilters() {
  const pills = document.querySelectorAll(".role-pill");
  pills.forEach((p) => {
    p.addEventListener("click", () => {
      pills.forEach((x) => x.classList.remove("active"));
      p.classList.add("active");
      const role = p.getAttribute("data-role");
      loadStaffLeaderboard(role, currentStaffSort);
    });
  });

  const sortSelect = document.getElementById("staffSortOrder");
  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => {
      loadStaffLeaderboard(currentStaffRole, e.target.value);
    });
  }

  const searchInput = document.getElementById("searchStaffInput");
  let debounceTimer = null;
  searchInput.addEventListener("input", (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      const q = e.target.value.trim();
      if (!q) {
        const activeRole = document.querySelector(".role-pill.active").getAttribute("data-role");
        loadStaffLeaderboard(activeRole);
        return;
      }
      try {
        const res = await fetch(`/api/staff-search?q=${encodeURIComponent(q)}`);
        const results = await res.json();
        currentFilteredStaff = results.map((m) => ({
          name: m.name,
          role: m.roles[0] || "all",
          works_count: m.works_count,
          bayesian_rating: m.rating,
          mean_z: m.rating,
          peak_z: m.rating,
          best_work_title: "-",
          best_work_year: "",
        }));
        staffCurrentPage = 1;
        renderStaffTable();
      } catch (err) {
        console.error(err);
      }
    }, 150);
  });

  const btnPrev = document.getElementById("btnStaffPrev");
  const btnNext = document.getElementById("btnStaffNext");
  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (staffCurrentPage > 1) {
        staffCurrentPage--;
        renderStaffTable();
      }
    });
  }
  if (btnNext) {
    btnNext.addEventListener("click", () => {
      const maxPage = Math.ceil(currentFilteredStaff.length / STAFF_PAGE_SIZE);
      if (staffCurrentPage < maxPage) {
        staffCurrentPage++;
        renderStaffTable();
      }
    });
  }
}

function renderStaffTable() {
  const tbody = document.getElementById("staffTableBody");
  const total = currentFilteredStaff.length;
  const pageInfo = document.getElementById("staffPageInfo");
  const btnPrev = document.getElementById("btnStaffPrev");
  const btnNext = document.getElementById("btnStaffNext");

  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:2rem; color:var(--text-muted);">該当スタッフが見つかりません</td></tr>`;
    if (pageInfo) pageInfo.textContent = "全 0 件中 0 件を表示";
    if (btnPrev) btnPrev.disabled = true;
    if (btnNext) btnNext.disabled = true;
    return;
  }

  const maxPage = Math.max(1, Math.ceil(total / STAFF_PAGE_SIZE));
  if (staffCurrentPage > maxPage) staffCurrentPage = maxPage;

  const startIdx = (staffCurrentPage - 1) * STAFF_PAGE_SIZE;
  const endIdx = Math.min(startIdx + STAFF_PAGE_SIZE, total);
  const pageRows = currentFilteredStaff.slice(startIdx, endIdx);

  if (pageInfo) {
    pageInfo.textContent = `全 ${total.toLocaleString()} 名中 ${startIdx + 1}〜${endIdx} 件を表示 (ページ ${staffCurrentPage} / ${maxPage})`;
  }
  if (btnPrev) btnPrev.disabled = staffCurrentPage <= 1;
  if (btnNext) btnNext.disabled = staffCurrentPage >= maxPage;

  tbody.innerHTML = pageRows
    .map((r, idx) => {
      const rankNum = r.rank || (startIdx + idx + 1);
      const totalCount = r.total_count || total;
      const tierInfo = getTierInfo(rankNum, totalCount);
      const roleBadge = getRoleBadgeJa(r.role);
      const cumZ = (r.career_cumulative_z !== undefined ? r.career_cumulative_z : (r.bayesian_rating * (r.works_count + 3.0)));
      const cumStr = (cumZ >= 0 ? "+" : "") + cumZ.toFixed(2);
      const cumColor = cumZ >= 20.0 ? "var(--accent-green); font-weight:700;" : (cumZ >= 10.0 ? "var(--accent-blue); font-weight:700;" : (cumZ < 0 ? "var(--accent-red);" : "var(--text-primary);"));

      return `
      <tr>
        <td style="font-family:'Fira Code'; font-weight:700;">
          <div style="display:flex; align-items:center; gap:0.4rem;">
            <span>#${rankNum}</span>
            ${tierInfo.badgeHtml}
          </div>
          <div style="font-size:0.72rem; font-weight:normal; color:var(--text-muted); margin-top:0.2rem; font-family:inherit;">上位 ${tierInfo.pctStr}</div>
        </td>
        <td style="font-weight:600;">
          <a class="action-link" onclick="openStaffModal('${r.name}')">${r.name}</a>
        </td>
        <td>${roleBadge}</td>
        <td>${r.works_count} 作</td>
        <td style="font-family:'Fira Code'; color:${cumColor};">${cumStr}</td>
        <td style="font-family:'Fira Code'; font-weight:700; color:var(--accent-blue);">${(r.bayesian_rating >= 0 ? "+" : "") + r.bayesian_rating.toFixed(2)}</td>
        <td style="font-family:'Fira Code';">${(r.mean_z >= 0 ? "+" : "") + r.mean_z.toFixed(2)}</td>
        <td style="font-family:'Fira Code'; color:var(--accent-green);">${(r.peak_z >= 0 ? "+" : "") + r.peak_z.toFixed(2)}</td>
        <td style="font-size:0.85rem;">${r.best_work_title} ${r.best_work_year ? `(${r.best_work_year})` : ""}</td>
        <td>
          <button class="btn btn-primary" style="padding:0.25rem 0.6rem;font-size:0.75rem;" onclick="openStaffModal('${r.name}')">詳細</button>
        </td>
      </tr>
    `;
    })
    .join("");
}

function renderStaffSearchResults(matches) {
  const tbody = document.getElementById("staffTableBody");
  if (matches.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:2rem; color:var(--text-muted);">一致するスタッフが見つかりません</td></tr>`;
    return;
  }
  tbody.innerHTML = matches
    .map(
      (m, idx) => `
    <tr>
      <td>#</td>
      <td style="font-weight:600;"><a class="action-link" onclick="openStaffModal('${m.name}')">${m.name}</a></td>
      <td>${m.roles.map(getRoleBadgeJa).join(" ")}</td>
      <td>${m.works_count} 作</td>
      <td style="font-family:'Fira Code'; font-weight:700; color:var(--accent-blue);">${(m.rating >= 0 ? "+" : "") + m.rating.toFixed(2)}</td>
      <td colspan="3">-</td>
      <td><button class="btn btn-primary" style="padding:0.25rem 0.6rem;font-size:0.75rem;" onclick="openStaffModal('${m.name}')">詳細</button></td>
    </tr>
  `
    )
    .join("");
}

function getRoleBadgeJa(role) {
  const map = {
    director: "監督",
    genga: "原画",
    char_design: "キャラデザ",
    series_comp: "構成/脚本",
    studio: "制作",
    unit_director: "演出",
    sakkan: "作監",
    music: "音楽",
    art_dir: "美術監督",
    all: "全体",
  };
  return `<span class="badge badge-info">${map[role] || role}</span>`;
}

function getTierInfo(rank, total) {
  if (!rank || !total || total <= 0) {
    return { pct: 100, pctStr: "-", tier: "-", className: "tier-d", badgeHtml: "" };
  }
  const pct = (rank / total) * 100;
  const pctStr = pct < 0.1 ? "< 0.1%" : `${pct.toFixed(1)}%`;

  let tier = "Tier D";
  let className = "tier-d";

  if (pct <= 1.0) {
    tier = "Tier S+";
    className = "tier-s-plus";
  } else if (pct <= 5.0) {
    tier = "Tier S";
    className = "tier-s";
  } else if (pct <= 15.0) {
    tier = "Tier A+";
    className = "tier-a-plus";
  } else if (pct <= 30.0) {
    tier = "Tier A";
    className = "tier-a";
  } else if (pct <= 50.0) {
    tier = "Tier B";
    className = "tier-b";
  } else if (pct <= 75.0) {
    tier = "Tier C";
    className = "tier-c";
  } else {
    tier = "Tier D";
    className = "tier-d";
  }

  const badgeHtml = `<span class="tier-badge ${className}">${tier}</span>`;
  return { pct, pctStr, tier, className, badgeHtml };
}

function getZTierInfo(zVal) {
  const sign = zVal < 0 ? -1 : 1;
  const x = Math.abs(zVal) / Math.SQRT2;
  const a = 0.147;
  const x2 = x * x;
  const erf = sign * Math.sqrt(1 - Math.exp(-x2 * (4 / Math.PI + a * x2) / (1 + a * x2)));
  const cdf = 0.5 * (1 + erf);
  const topPct = Math.max(0.01, Math.min(99.99, (1 - cdf) * 100));
  const pctStr = topPct < 0.1 ? "< 0.1%" : `${topPct.toFixed(1)}%`;

  let tier = "Tier D";
  let className = "tier-d";

  if (topPct <= 1.0) {
    tier = "Tier S+";
    className = "tier-s-plus";
  } else if (topPct <= 5.0) {
    tier = "Tier S";
    className = "tier-s";
  } else if (topPct <= 15.0) {
    tier = "Tier A+";
    className = "tier-a-plus";
  } else if (topPct <= 30.0) {
    tier = "Tier A";
    className = "tier-a";
  } else if (topPct <= 50.0) {
    tier = "Tier B";
    className = "tier-b";
  } else if (topPct <= 75.0) {
    tier = "Tier C";
    className = "tier-c";
  } else {
    tier = "Tier D";
    className = "tier-d";
  }

  const badgeHtml = `<span class="tier-badge ${className}">${tier}</span>`;
  return { pct: topPct, pctStr, tier, className, badgeHtml };
}

/* Modal */
function initModal() {
  const staffModal = document.getElementById("staffModal");
  const staffCloseBtn = document.getElementById("modalCloseBtn");
  staffCloseBtn.addEventListener("click", () => staffModal.classList.remove("open"));
  staffModal.addEventListener("click", (e) => {
    if (e.target === staffModal) staffModal.classList.remove("open");
  });

  const animeModal = document.getElementById("animeModal");
  const animeCloseBtn = document.getElementById("modalAnimeCloseBtn");
  if (animeCloseBtn) {
    animeCloseBtn.addEventListener("click", () => animeModal.classList.remove("open"));
  }
  if (animeModal) {
    animeModal.addEventListener("click", (e) => {
      if (e.target === animeModal) animeModal.classList.remove("open");
    });
  }
}

async function openStaffModal(staffName) {
  const modal = document.getElementById("staffModal");
  document.getElementById("modalStaffName").innerHTML = `
    <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap;">
      <span>${staffName} - 能力プロファイル</span>
      <span class="badge badge-info" style="font-size:0.75rem; font-weight:normal;">Bangumi API 構造化データ</span>
    </div>
  `;
  const content = document.getElementById("modalStaffContent");
  content.innerHTML = `<p style="color:var(--text-muted);text-align:center;">読込中...</p>`;
  modal.classList.add("open");

  try {
    const res = await fetch(`/api/staff/${encodeURIComponent(staffName)}`);
    const p = await res.json();

    const rolesHtml = Object.entries(p.roles)
      .map(([r, c]) => `${getRoleBadgeJa(r)} × ${c}回`)
      .join("  ");

    // Top works (代表作)
    const bestWorks = p.best_works || [];
    let bestWorksHtml = "";
    if (bestWorks.length > 0) {
      bestWorksHtml = `
        <div style="margin-bottom:1.2rem;">
          <h4 style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:0.4rem;">🏆 代表作 (Top Works - クリックで作品詳細):</h4>
          <div class="best-works-grid">
            ${bestWorks
              .map(
                (w) => `
              <a class="best-work-card" onclick="openAnimeModal('${w.work_id}'); document.getElementById('staffModal').classList.remove('open');" title="クリックで作品詳細を表示">
                🎬 <strong>${w.work_title}</strong> (${w.year}年)
                <span style="color:var(--accent-green); font-family:'Fira Code'; font-size:0.75rem;">Z = ${(w.z_score >= 0 ? "+" : "") + w.z_score.toFixed(2)}</span>
              </a>
            `
              )
              .join("")}
          </div>
        </div>
      `;
    }

    // Career trajectory (タイムライン)
    const trajHtml = p.career_trajectory
      .map(
        (t) => `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:0.45rem 0; border-bottom:1px solid rgba(255,255,255,0.05); font-size:0.85rem;">
          <div>
            <span style="color:var(--text-muted); font-size:0.8rem; margin-right:0.4rem;">${t.year}年</span>
            <a class="work-link" onclick="openAnimeModal('${t.work_id}'); document.getElementById('staffModal').classList.remove('open');" title="クリックで作品詳細・全スタッフ・SHAP分析を表示">
              🎬 ${t.work_title}
            </a>
            <span style="margin-left:0.3rem;">[${getRoleBadgeJa(t.role)}]</span>
          </div>
          <span style="font-family:'Fira Code'; font-weight:600; color:${t.z_score >= 0 ? "var(--accent-green)" : "var(--accent-red)"}">
            Z = ${(t.z_score >= 0 ? "+" : "") + t.z_score.toFixed(2)}
          </span>
        </div>
      `
      )
      .join("");

    const totalStaff = p.total_staff || 33961;
    const overallTier = getTierInfo(p.overall_rank, totalStaff);
    const cumTier = getTierInfo(p.cumulative_rank, totalStaff);
    const cumZ = (p.career_cumulative_z !== undefined ? p.career_cumulative_z : (p.bayesian_rating * (p.total_works + 3.0)));
    const cumStr = (cumZ >= 0 ? "+" : "") + cumZ.toFixed(2);

    // Department Breakdown Cards (各部門での生涯累積実績・総合実力・ランキング)
    let deptBreakdownHtml = "";
    if (p.all_role_stats && p.all_role_stats.length > 0) {
      deptBreakdownHtml = `
        <div style="margin-bottom:1.4rem;">
          <h4 style="font-size:0.86rem; color:#ffffff; font-weight:700; margin-bottom:0.65rem; display:flex; align-items:center; gap:0.4rem;">
            <span>📊 部門別実績 & ランキング (Department Stats)</span>
          </h4>
          <div class="dept-cards-grid">
            ${p.all_role_stats.map(st => {
              const rTier = getTierInfo(st.rating_rank, st.role_total);
              const cTier = getTierInfo(st.cumulative_rank, st.role_total);
              const rCumStr = (st.cumulative_z >= 0 ? "+" : "") + st.cumulative_z.toFixed(2);
              const rRatStr = (st.bayesian_rating >= 0 ? "+" : "") + st.bayesian_rating.toFixed(2);
              return `
                <div class="dept-card">
                  <div class="dept-card-header">
                    <span class="dept-card-title">${getRoleBadgeJa(st.role)} 部門</span>
                    <span class="dept-card-works">${st.works_count} 作品参加</span>
                  </div>
                  <div class="dept-metrics-row">
                    <div class="dept-metric-subbox">
                      <span class="dept-metric-label" style="color:var(--neon-cyan);">🎯 総合実力 S(a)</span>
                      <span class="dept-metric-val" style="color:var(--neon-cyan);">${rRatStr}</span>
                      <span class="dept-metric-rank">第 #${st.rating_rank} 位 / ${st.role_total} 名</span>
                      <div style="margin-top:0.2rem;">${rTier.badgeHtml} <span style="font-size:0.7rem; color:var(--neon-cyan); font-weight:700;">上位 ${rTier.pctStr}</span></div>
                    </div>
                    <div class="dept-metric-subbox">
                      <span class="dept-metric-label" style="color:var(--neon-green);">🏛️ 生涯累積 ΣZ</span>
                      <span class="dept-metric-val" style="color:var(--neon-green);">${rCumStr}</span>
                      <span class="dept-metric-rank">第 #${st.cumulative_rank} 位 / ${st.role_total} 名</span>
                      <div style="margin-top:0.2rem;">${cTier.badgeHtml} <span style="font-size:0.7rem; color:var(--neon-green); font-weight:700;">上位 ${cTier.pctStr}</span></div>
                    </div>
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    }

    content.innerHTML = `
      <!-- TOP 3 STATS: 総合実力、生涯累積実績、最高実績 -->
      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:0.75rem; margin-bottom:1.3rem; text-align:center;">
        <div class="summary-box" style="border-color:var(--neon-cyan);">
          <span class="box-label" style="color:var(--neon-cyan);">🏆 総合実力 S(a) (期待値)</span>
          <span class="box-val highlight-val" style="font-size:1.6rem;">${(p.bayesian_rating >= 0 ? "+" : "") + p.bayesian_rating.toFixed(2)}</span>
          <span class="box-sub" style="font-size:0.74rem; color:var(--neon-cyan); font-weight:bold;">全スタッフ第 #${p.overall_rank || "-"} 位 / ${totalStaff} 名</span>
          <div style="margin-top:0.35rem; display:flex; justify-content:center; align-items:center; gap:0.35rem;">
            ${overallTier.badgeHtml}
            <span style="font-size:0.74rem; font-weight:700; color:var(--neon-cyan);">上位 ${overallTier.pctStr}</span>
          </div>
        </div>
        <div class="summary-box" style="border-color:var(--neon-green);">
          <span class="box-label" style="color:var(--neon-green);">🏛️ 生涯累積実績 ΣZ (通算貢献)</span>
          <span class="box-val highlight-val" style="font-size:1.6rem; color:var(--neon-green); font-weight:800;">${cumStr}</span>
          <span class="box-sub" style="font-size:0.74rem; color:var(--neon-green); font-weight:bold;">全スタッフ第 #${p.cumulative_rank || "-"} 位 / ${totalStaff} 名</span>
          <div style="margin-top:0.35rem; display:flex; justify-content:center; align-items:center; gap:0.35rem;">
            ${cumTier.badgeHtml}
            <span style="font-size:0.74rem; font-weight:700; color:var(--neon-green);">上位 ${cumTier.pctStr}</span>
          </div>
        </div>
        <div class="summary-box" style="border-color:var(--neon-yellow);">
          <span class="box-label" style="color:var(--neon-yellow);">🌟 最高実績 Peak(Z)</span>
          <span class="box-val highlight-val" style="font-size:1.6rem; color:var(--neon-yellow);">${(p.peak_z >= 0 ? "+" : "") + p.peak_z.toFixed(2)}</span>
          <span class="box-sub" style="font-size:0.74rem; color:var(--text-secondary); margin-top:0.15rem;">参加 ${p.total_works} 作品中</span>
        </div>
      </div>
      ${deptBreakdownHtml}
      <div style="margin-bottom:1rem;">
        <h4 style="font-size:0.84rem; color:var(--text-secondary); margin-bottom:0.4rem;">担当役職分布:</h4>
        <div>${rolesHtml}</div>
      </div>
      ${bestWorksHtml}
      <div>
        <h4 style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:0.6rem;">参加作品タイムライン (${p.total_works}作品 - 作品名クリックで詳細):</h4>
        <div style="display:flex; flex-direction:column; gap:0.2rem;">${trajHtml}</div>
      </div>
    `;
  } catch (err) {
    console.error(err);
    content.innerHTML = `<p style="color:var(--accent-red);">プロファイル読込に失敗しました。</p>`;
  }
}

/* Bulk Collector Handler */
function initBulkCollectButton() {
  const btn = document.getElementById("btnBulkCollect");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    if (!confirm("Bangumi APIとAniList APIから人気アニメ約50〜100作品のスタッフ情報・評価を一括収集し、モデルを再学習します。開始しますか？\n（約30秒〜1分程度かかります）")) {
      return;
    }

    btn.disabled = true;
    btn.innerHTML = "<span>⏳ 収集&再学習中...</span>";

    try {
      const res = await fetch("/api/collect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_works: 80 }),
      });
      const data = await res.json();
      alert(`収集完了！\n新規登録: ${data.new_collected}作品\n全登録数: ${data.total_works}作品\n最新RMSE: ${data.metrics.rmse.toFixed(3)}`);

      // Reload all views
      await loadStatusMetrics();
      await loadComparisonData();
      await loadStaffLeaderboard("all");
    } catch (err) {
      console.error(err);
      alert("データ収集中にエラーが発生しました。");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "<span>📥 Bangumi一括収集</span>";
    }
  });
}

/* Global Instant Search */
function initGlobalSearch() {
  const searchInput = document.getElementById("globalSearchInput");
  const dropdown = document.getElementById("searchDropdown");
  if (!searchInput || !dropdown) return;

  let debounceTimer = null;

  // Keyboard shortcuts: Ctrl+K or Cmd+K to focus search, Escape to close
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    } else if (e.key === "Escape") {
      dropdown.classList.remove("open");
    }
  });

  searchInput.addEventListener("input", (e) => {
    clearTimeout(debounceTimer);
    const q = e.target.value.trim();
    if (!q) {
      dropdown.classList.remove("open");
      dropdown.innerHTML = "";
      return;
    }

    debounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        renderSearchDropdown(data);
      } catch (err) {
        console.error(err);
      }
    }, 200);
  });

  document.addEventListener("click", (e) => {
    if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.remove("open");
    }
  });
}

function renderSearchDropdown(data) {
  const dropdown = document.getElementById("searchDropdown");
  const works = data.works || [];
  const staff = data.staff || [];

  if (works.length === 0 && staff.length === 0) {
    dropdown.innerHTML = `<div style="padding:1rem; text-align:center; color:var(--text-muted); font-size:0.85rem;">「${data.query}」に一致する作品またはスタッフは見つかりませんでした</div>`;
    dropdown.classList.add("open");
    return;
  }

  let html = "";

  if (works.length > 0) {
    html += `<div class="dropdown-section-title">🎬 アニメ作品 (${works.length}件)</div>`;
    works.forEach((w) => {
      const directorStr = (w.director || []).join(", ") || "監督未詳";
      const studioStr = (w.studio || []).join(", ") || "";
      const zStr = (w.true_z_score >= 0 ? "+" : "") + w.true_z_score.toFixed(2);
      html += `
        <div class="dropdown-item" onclick="openAnimeModal('${w.work_id}'); document.getElementById('searchDropdown').classList.remove('open');">
          <div>
            <div class="dropdown-item-title">${w.title} <span style="font-size:0.75rem; color:var(--text-muted);">(${w.year}年)</span></div>
            <div class="dropdown-item-sub">監督: ${directorStr} ${studioStr ? " / " + studioStr : ""} | AniList: ${w.anilist_raw_score.toFixed(1)}点</div>
          </div>
          <div style="font-family:'Fira Code'; font-weight:700; color:var(--accent-blue); font-size:0.9rem;">
            Z = ${zStr}
          </div>
        </div>
      `;
    });
  }

  if (staff.length > 0) {
    html += `<div class="dropdown-section-title">👤 制作陣・スタッフ (${staff.length}件)</div>`;
    staff.forEach((s) => {
      const rolesStr = (s.roles || []).map(getRoleBadgeJa).join(" ");
      const ratingStr = (s.rating >= 0 ? "+" : "") + s.rating.toFixed(2);
      html += `
        <div class="dropdown-item" onclick="openStaffModal('${s.name}'); document.getElementById('searchDropdown').classList.remove('open');">
          <div>
            <div class="dropdown-item-title">${s.name} ${rolesStr}</div>
            <div class="dropdown-item-sub">参加作品数: ${s.works_count}作</div>
          </div>
          <div style="font-family:'Fira Code'; font-weight:700; color:var(--accent-green); font-size:0.9rem;">
            S(a) = ${ratingStr}
          </div>
        </div>
      `;
    });
  }

  dropdown.innerHTML = html;
  dropdown.classList.add("open");
}

/* Anime Detail Modal */
let animeShapChartInstance = null;

async function openAnimeModal(workId) {
  const modal = document.getElementById("animeModal");
  const content = document.getElementById("modalAnimeContent");
  modal.classList.add("open");
  content.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:2rem;">作品情報・スタッフクレジット・SHAP寄与度を解析中...</p>`;

  try {
    const res = await fetch(`/api/anime/${encodeURIComponent(workId)}`);
    if (!res.ok) throw new Error("Not found");
    const d = await res.json();

    document.getElementById("modalAnimeTitle").textContent = d.title;
    document.getElementById("modalAnimeSub").textContent = `${d.title_en || ""} (${d.year}年公開 / ${d.performance_verdict})`;

    const staff = d.staff || {};
    const directors = (staff.director || []).map((n) => `<a class="staff-tag" onclick="openStaffModal('${n}')">🎬 監督: ${n}</a>`).join(" ") || "-";
    const seriesComp = (staff.series_comp || []).map((n) => `<a class="staff-tag" onclick="openStaffModal('${n}')">📝 構成/脚本: ${n}</a>`).join(" ") || "-";
    const charDesign = (staff.char_design || []).map((n) => `<a class="staff-tag" onclick="openStaffModal('${n}')">🎨 キャラデザ: ${n}</a>`).join(" ") || "-";
    const music = (staff.music || []).map((n) => `<a class="staff-tag" onclick="openStaffModal('${n}')">🎵 音楽: ${n}</a>`).join(" ") || "-";
    const artDir = (staff.art_dir || []).map((n) => `<a class="staff-tag" onclick="openStaffModal('${n}')">🖼️ 美術監督: ${n}</a>`).join(" ") || "-";
    const studio = (staff.studio || []).map((n) => `<a class="staff-tag" onclick="openStaffModal('${n}')">🏢 制作: ${n}</a>`).join(" ") || "-";
    const sakkan = (staff.sakkan || []).map((n) => `<a class="staff-tag" onclick="openStaffModal('${n}')">✏️ 作監: ${n}</a>`).join(" ") || "-";

    const gengaList = staff.genga || [];
    let gengaHtml = "";
    if (gengaList.length === 0) {
      gengaHtml = `<span style="color:var(--text-muted); font-size:0.85rem;">原画クレジット情報なし</span>`;
    } else {
      gengaHtml = gengaList
        .map((g) => {
          const name = typeof g === "string" ? g : g.name;
          const rank = g.rank ? `(順位:${g.rank})` : "";
          return `<a class="staff-tag" onclick="openStaffModal('${name}')">🖌️ ${name} ${rank}</a>`;
        })
        .join(" ");
    }

    const totalWorks = d.total_works || 1624;
    const predTier = getTierInfo(d.pred_score_rank, totalWorks);
    const rawTier = getTierInfo(d.raw_score_rank, totalWorks);
    const devScore = d.deviation_score !== undefined ? d.deviation_score : Number((50.0 + 10.0 * (d.true_z_score || 0)).toFixed(1));
    const zRank = d.z_score_rank || "-";
    const devTier = getTierInfo(d.z_score_rank, totalWorks);

    content.innerHTML = `
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:0.7rem; margin-bottom:1.5rem; text-align:center;">
        <!-- 1. 偏差値カード (左端) -->
        <div class="summary-box" style="border-color:var(--neon-cyan);">
          <span class="box-label" style="color:var(--neon-cyan);">📊 偏差値 (年代相対クオリティ)</span>
          <span class="box-val highlight-val" style="font-size:1.6rem; font-weight:800; color:var(--neon-cyan);">${devScore.toFixed(1)}</span>
          <span class="box-sub" style="font-size:0.75rem; color:var(--neon-cyan); font-weight:bold; margin-top:0.2rem;">🏆 順位: 第 #${zRank} 位 / ${totalWorks} 作品</span>
          <div style="margin-top:0.35rem; display:flex; justify-content:center; align-items:center; gap:0.35rem;">
            ${devTier.badgeHtml}
            <span style="font-size:0.75rem; font-weight:700; color:var(--neon-cyan);">上位 ${devTier.pctStr}</span>
          </div>
        </div>

        <!-- 2. AniList 素点 (実績) カード -->
        <div class="summary-box">
          <span class="box-label">AniList 素点 (実績)</span>
          <span class="box-val" style="font-size:1.5rem;">${d.anilist_raw_score.toFixed(1)}点</span>
          <span class="box-sub" style="font-size:0.75rem; color:var(--text-secondary); margin-top:0.2rem;">順位: 第 #${d.raw_score_rank || "-"} 位 / ${totalWorks} 作品</span>
          <div style="margin-top:0.35rem; display:flex; justify-content:center; align-items:center; gap:0.35rem;">
            ${rawTier.badgeHtml}
            <span style="font-size:0.75rem; font-weight:600; color:var(--text-secondary);">上位 ${rawTier.pctStr}</span>
          </div>
        </div>

        <!-- 3. 予測換算点 (期待値) カード -->
        <div class="summary-box" style="border-color:var(--accent-blue);">
          <span class="box-label" style="color:var(--accent-blue);">🎯 予測換算点 (期待値)</span>
          <span class="box-val highlight-val" style="font-size:1.5rem; font-weight:800;">${(d.predicted_score || 0).toFixed(1)}点</span>
          <span class="box-sub" style="font-size:0.75rem; color:var(--accent-blue); font-weight:bold; margin-top:0.2rem;">🏆 予測順位: 第 #${d.pred_score_rank || "-"} 位 / ${totalWorks} 作品</span>
          <div style="margin-top:0.35rem; display:flex; justify-content:center; align-items:center; gap:0.35rem;">
            ${predTier.badgeHtml}
            <span style="font-size:0.75rem; font-weight:700; color:var(--accent-blue);">上位 ${predTier.pctStr}</span>
          </div>
        </div>

        <!-- 4. 詳細指標統合カード（乖離残差・年代補正真値・モデル予測値） -->
        <div class="summary-box" style="padding:0.6rem 0.8rem; display:flex; flex-direction:column; justify-content:center; text-align:left;">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:0.3rem; margin-bottom:0.3rem;">
            <span style="font-size:0.74rem; color:var(--text-secondary);">乖離残差 (判定):</span>
            <div style="text-align:right;">
              <span style="font-family:'Fira Code'; font-weight:700; font-size:0.95rem; color:${d.residual >= 0.4 ? "var(--accent-green)" : (d.residual < -0.4 ? "var(--accent-red)" : "var(--text-primary)")};">
                ${(d.residual >= 0 ? "+" : "") + d.residual.toFixed(2)}
              </span>
              <span style="font-size:0.68rem; color:var(--text-muted); display:block;">${d.performance_verdict}</span>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:0.25rem; margin-bottom:0.25rem;">
            <span style="font-size:0.74rem; color:var(--text-secondary);">年代補正真値 (Z_i):</span>
            <span style="font-family:'Fira Code'; font-weight:700; font-size:0.9rem;">${(d.true_z_score >= 0 ? "+" : "") + d.true_z_score.toFixed(2)}</span>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:0.74rem; color:var(--text-secondary);">モデル予測値 (Ẑ_i):</span>
            <span style="font-family:'Fira Code'; font-weight:700; font-size:0.9rem; color:${d.predicted_z_score >= 0 ? "var(--accent-green)" : "var(--accent-red)"};">
              ${(d.predicted_z_score >= 0 ? "+" : "") + d.predicted_z_score.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      <div style="margin-bottom:1.2rem; background-color:var(--bg-card); padding:1rem; border-radius:8px; border:1px solid var(--border-color);">
        <h4 style="font-size:0.95rem; color:var(--accent-blue); margin-bottom:0.8rem;">👥 制作陣スタッフ情報 (Bangumi API構造化データ - クリックでスタッフ詳細)</h4>
        <div style="display:flex; flex-direction:column; gap:0.6rem; font-size:0.85rem;">
          <div><strong>🎬 監督:</strong> ${directors}</div>
          <div><strong>📝 シリーズ構成/脚本:</strong> ${seriesComp}</div>
          <div><strong>🎨 キャラクターデザイン:</strong> ${charDesign}</div>
          <div><strong>🎵 音楽 (劇伴):</strong> ${music}</div>
          <div><strong>🖼️ 美術監督 (背景美術):</strong> ${artDir}</div>
          <div><strong>🏢 制作スタジオ:</strong> ${studio}</div>
          <div><strong>✏️ 作画監督:</strong> ${sakkan}</div>
          <div>
            <strong>🖌️ 原画 (${gengaList.length}名):</strong>
            <div style="max-height:140px; overflow-y:auto; margin-top:0.4rem;" class="staff-badge-group">
              ${gengaHtml}
            </div>
          </div>
        </div>
      </div>

      <div class="chart-container" style="margin-bottom:0;">
        <h4 class="chart-title">TreeSHAP この作品におけるスタッフ寄与度分析 (+押し上げ / -押し下げ)</h4>
        <div class="chart-canvas-wrapper-modal">
          <canvas id="animeShapChart"></canvas>
        </div>
      </div>
    `;

    // Render SHAP in modal
    renderAnimeShapChart(d.all_contributions);
  } catch (err) {
    console.error(err);
    content.innerHTML = `<p style="color:var(--accent-red);text-align:center;">作品情報の読込に失敗しました。</p>`;
  }
}

function renderAnimeShapChart(contributions) {
  const sorted = [...(contributions || [])].sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value));
  const topContributions = sorted.filter((c) => Math.abs(c.shap_value) > 0.003).slice(0, 6);
  topContributions.sort((a, b) => b.shap_value - a.shap_value);

  const labels = topContributions.map((c) => c.label_ja.split("(")[0].trim());
  const values = topContributions.map((c) => c.shap_value);
  const colors = values.map((v) => (v >= 0 ? "#34d399" : "#f43f5e"));

  const canvas = document.getElementById("animeShapChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (animeShapChartInstance) {
    animeShapChartInstance.destroy();
  }

  animeShapChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "SHAP寄与度",
          data: values,
          backgroundColor: colors,
          borderRadius: 4,
          barThickness: 15,
          maxBarThickness: 18,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `寄与度: ${ctx.raw >= 0 ? "+" : ""}${ctx.raw.toFixed(3)}`,
          },
        },
      },
      scales: {
        x: {
          grid: {
            color: (c) => (c.tick.value === 0 ? "rgba(255, 255, 255, 0.35)" : "rgba(255, 255, 255, 0.05)"),
            lineWidth: (c) => (c.tick.value === 0 ? 1.5 : 1),
          },
          ticks: { color: "#a1a1aa", font: { family: "'Fira Code', monospace", size: 10 } },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#ffffff", font: { family: "'Inter', 'Noto Sans JP', sans-serif", size: 11, weight: "500" } },
        },
      },
    },
  });
}
