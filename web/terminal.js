import {
  $, $$, ApiError, accessToken, api, currency, escapeHtml, hideLogin, longDate, number, setupAuth, shortCurrency,
  shortDate, showLogin, signOut, signed, tone,
} from "./common.js";

const LWC = window.LightweightCharts;
const COLORS = { up: "#28d07d", down: "#ff5a52", text: "#7c8794", grid: "#141a22", amber: "#ffa028" };
const OVERLAY_COLORS = { sma20: "#ffa028", sma50: "#5aa9ff", sma200: "#c77dff", ema20: "#f5e663", bb20_upper: "#5d6b7a", bb20_lower: "#5d6b7a" };

const state = {
  quotes: [],
  symbols: new Set(),
  signedIn: false,
  account: null,
  symbol: "NIFTY 50",
  days: 126,
  overlays: new Set(["sma20", "sma50"]),
  study: "rsi14",
  moversTab: "gainers",
  movers: null,
  dock: "heatmap",
  sort: { key: "symbol", dir: 1 },
  side: "BUY",
  history: [],
  historyIndex: -1,
  suggestions: [],
  suggestIndex: -1,
};

const FUNCTIONS = [
  ["MOV", "Movers and breadth"], ["HMAP", "Sector heatmap"], ["PORT", "Portfolio risk"], ["BLOT", "Order blotter"],
  ["RULES", "Your strategies"], ["RULE", "Build a strategy"], ["LB", "Leaderboard"], ["HELP", "All commands"],
];

// ---------------------------------------------------------------- messages

let messageTimer;
function say(text, { error = false, suggestions = [] } = {}) {
  const box = $("#commandMessage");
  box.className = `term-message${error ? " error" : ""}`;
  box.innerHTML = escapeHtml(text) + suggestions.map((s) => `<button type="button" data-run="${escapeHtml(s)}">${escapeHtml(s)}</button>`).join("");
  box.hidden = false;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => { box.hidden = true; }, error ? 9000 : 5000);
}
$("#commandMessage").addEventListener("click", (event) => {
  const button = event.target.closest("[data-run]");
  if (button) run(button.dataset.run);
});

// ---------------------------------------------------------------- command line

async function run(text) {
  const input = $("#commandInput");
  input.value = "";
  closeSuggest();
  if (!text.trim()) return;
  state.history.unshift(text.trim().toUpperCase());
  state.historyIndex = -1;
  let result;
  try {
    result = await api("/api/command", { method: "POST", body: { text }, auth: false });
  } catch (error) {
    say(error.message, { error: true });
    return;
  }
  switch (result.action) {
    case "security":
      await loadSecurity(result.symbol);
      if (result.view === "trade") $("#ticketQty").focus();
      break;
    case "order":
      await placeOrder(result.side, result.quantity, result.symbol);
      break;
    case "movers":
      $("#moverRows").scrollIntoView({ block: "nearest" });
      say("Movers are in the right panel. Use UP, DOWN and ACTIVE to switch.");
      break;
    case "new_rule":
      window.location.href = "./?build=1#strategies";
      break;
    case "help":
      setDock("help", result.commands);
      break;
    case "error":
      say(result.message, { error: true, suggestions: result.suggestions || [] });
      break;
    default:
      setDock(result.action);
  }
}

function buildSuggestions(value) {
  const query = value.trim().toUpperCase();
  if (!query || /^(BUY|SELL|B|S)\s/.test(query)) return [];
  const functions = FUNCTIONS.filter(([code]) => code.startsWith(query)).map(([code, label]) => ({ value: code, label }));
  const symbols = state.quotes
    .filter((quote) => quote.symbol.startsWith(query) || quote.name.toUpperCase().includes(query))
    .slice(0, 8)
    .map((quote) => ({ value: quote.symbol, label: `${signed(quote.change_pct)}  ${quote.kind === "INDEX" ? "INDEX" : quote.name}` }));
  return [...functions, ...symbols].slice(0, 9);
}

function renderSuggest() {
  const list = $("#commandSuggest");
  if (!state.suggestions.length) { closeSuggest(); return; }
  list.innerHTML = state.suggestions.map((item, index) => `<li role="option" data-value="${escapeHtml(item.value)}" class="${index === state.suggestIndex ? "active" : ""}"><span>${escapeHtml(item.value)}</span><span>${escapeHtml(item.label)}</span></li>`).join("");
  list.hidden = false;
}

function closeSuggest() {
  state.suggestions = [];
  state.suggestIndex = -1;
  $("#commandSuggest").hidden = true;
}

$("#commandInput").addEventListener("input", (event) => {
  state.suggestions = buildSuggestions(event.target.value);
  state.suggestIndex = -1;
  renderSuggest();
});
$("#commandInput").addEventListener("keydown", (event) => {
  const input = event.target;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const step = event.key === "ArrowDown" ? 1 : -1;
    if (state.suggestions.length) {
      state.suggestIndex = (state.suggestIndex + step + state.suggestions.length) % state.suggestions.length;
      renderSuggest();
    } else if (state.history.length) {
      state.historyIndex = Math.max(-1, Math.min(state.history.length - 1, state.historyIndex - step));
      input.value = state.historyIndex >= 0 ? state.history[state.historyIndex] : "";
    }
  } else if (event.key === "Tab" && state.suggestions.length) {
    event.preventDefault();
    input.value = state.suggestions[Math.max(0, state.suggestIndex)].value;
    closeSuggest();
  } else if (event.key === "Escape") {
    input.value = "";
    closeSuggest();
    input.blur();
  }
});
$("#commandForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const typed = $("#commandInput").value.trim().toUpperCase();
  // Enter on a partial symbol ("RELI") takes the top suggestion, like a terminal's autocomplete.
  const exact = state.symbols.has(typed) || FUNCTIONS.some(([code]) => code === typed);
  const picked = state.suggestIndex >= 0 ? state.suggestions[state.suggestIndex].value
    : !exact && state.suggestions.length ? state.suggestions[0].value : $("#commandInput").value;
  run(picked);
});
$("#commandSuggest").addEventListener("mousedown", (event) => {
  const item = event.target.closest("[data-value]");
  if (item) { event.preventDefault(); run(item.dataset.value); }
});
$("#commandInput").addEventListener("blur", () => setTimeout(closeSuggest, 100));

// Like a terminal keyboard: start typing anywhere and it goes to the command line.
document.addEventListener("keydown", (event) => {
  const target = event.target;
  const typing = target.closest("input, textarea, select, [contenteditable]");
  if (typing || event.ctrlKey || event.metaKey || event.altKey || !$("#loginScreen").hidden) return;
  if (event.key === "/" || (event.key.length === 1 && /[a-z0-9?]/i.test(event.key))) {
    const input = $("#commandInput");
    input.focus();
    if (event.key === "/") event.preventDefault();
  }
});

// ---------------------------------------------------------------- market data

async function loadMarket() {
  const [status, quotes, movers] = await Promise.all([
    api("/api/market/status", { auth: false }),
    api("/api/market/quotes", { auth: false }),
    api("/api/market/movers", { auth: false }),
  ]);
  state.quotes = quotes;
  state.symbols = new Set(quotes.map((quote) => quote.symbol));
  state.movers = movers;
  const statusBox = $("#dataStatus");
  statusBox.textContent = status.as_of ? `${status.sample_data ? "SAMPLE" : "NSE EOD"} ${shortDate(status.as_of).toUpperCase()}` : "NO DATA";
  statusBox.className = status.sample_data || !status.as_of ? "sample" : "";
  statusBox.title = status.sample_data ? "Sample prices for development. Load NSE Bhavcopy for real closes." : "End-of-day NSE closing prices";
  renderTape();
  renderMonitor();
  renderMovers();
}

function renderTape() {
  const indices = state.quotes.filter((quote) => quote.kind === "INDEX");
  const breadth = state.movers?.breadth ?? {};
  const items = [
    ...indices.map((quote) => `<button type="button" data-symbol="${escapeHtml(quote.symbol)}"><b>${escapeHtml(quote.symbol)}</b>${number.format(quote.close)} <span class="${tone(quote.change_pct)}">${signed(quote.change_pct)}</span></button>`),
    breadth.total ? `<span><b>A/D</b><span class="positive">${breadth.advances}</span>/<span class="negative">${breadth.declines}</span></span>` : "",
    breadth.total ? `<span><b>52W H/L</b>${breadth.new_highs}/${breadth.new_lows}</span>` : "",
    ...[...(state.movers?.gainers ?? []).slice(0, 5), ...(state.movers?.losers ?? []).slice(0, 5)].map((row) => `<button type="button" data-symbol="${escapeHtml(row.symbol)}"><b>${escapeHtml(row.symbol)}</b><span class="${tone(row.change_pct)}">${signed(row.change_pct)}</span></button>`),
  ];
  $("#tape").innerHTML = items.join("");
}
$("#tape").addEventListener("click", (event) => {
  const button = event.target.closest("[data-symbol]");
  if (button) loadSecurity(button.dataset.symbol);
});

function renderMonitor() {
  const filter = $("#monitorFilter").value.trim().toUpperCase();
  const { key, dir } = state.sort;
  const rows = state.quotes
    .filter((quote) => !filter || quote.symbol.includes(filter) || quote.name.toUpperCase().includes(filter))
    .sort((a, b) => {
      if (a.kind !== b.kind && key === "symbol") return a.kind === "INDEX" ? -1 : 1;
      return (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir;
    });
  $$("#monitorTable th").forEach((th) => th.classList.toggle("sorted", th.dataset.sort === key));
  $("#monitorRows").innerHTML = rows.length
    ? rows.map((quote) => `<tr data-symbol="${escapeHtml(quote.symbol)}" class="${quote.symbol === state.symbol ? "current" : ""}">
        <td class="sym">${escapeHtml(quote.symbol)}</td>
        <td class="num">${number.format(quote.close)}</td>
        <td class="num ${tone(quote.change_pct)}">${signed(quote.change_pct)}</td>
      </tr>`).join("")
    : '<tr><td colspan="3" class="empty">No match</td></tr>';
}
$("#monitorRows").addEventListener("click", (event) => {
  const row = event.target.closest("[data-symbol]");
  if (row) loadSecurity(row.dataset.symbol);
});
$("#monitorFilter").addEventListener("input", renderMonitor);
$("#monitorTable thead").addEventListener("click", (event) => {
  const th = event.target.closest("[data-sort]");
  if (!th) return;
  state.sort = { key: th.dataset.sort, dir: state.sort.key === th.dataset.sort ? -state.sort.dir : (th.dataset.sort === "symbol" ? 1 : -1) };
  renderMonitor();
});

function renderMovers() {
  const movers = state.movers;
  const breadth = movers?.breadth;
  if (breadth?.total) {
    const pct = (n) => (n / breadth.total) * 100;
    $("#breadth").innerHTML = `<div class="breadth-row"><span>ADV <b class="positive">${breadth.advances}</b></span><span>UNCH ${breadth.unchanged}</span><span>DEC <b class="negative">${breadth.declines}</b></span></div>
      <div class="breadth-bar"><i style="width:${pct(breadth.advances)}%;background:var(--green)"></i><i style="width:${pct(breadth.unchanged)}%;background:#4a5563"></i><i style="width:${pct(breadth.declines)}%;background:var(--red)"></i></div>
      <div class="breadth-row"><span>52W HIGHS ${breadth.new_highs}</span><span>52W LOWS ${breadth.new_lows}</span></div>`;
  }
  const rows = movers?.[state.moversTab] ?? [];
  $("#moverRows").innerHTML = rows.length
    ? rows.map((row) => `<tr data-symbol="${escapeHtml(row.symbol)}">
        <td class="sym">${escapeHtml(row.symbol)}<span class="sub">${escapeHtml(row.sector)}</span></td>
        <td class="num">${number.format(row.close)}<span class="sub">${state.moversTab === "active" ? `₹${number.format(row.value_cr)} Cr` : ""}</span></td>
        <td class="num ${tone(row.change_pct)}">${signed(row.change_pct)}</td>
      </tr>`).join("")
    : '<tr><td class="empty">Nothing here today</td></tr>';
}
$("#moverTabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-movers]");
  if (!button) return;
  state.moversTab = button.dataset.movers;
  $$("#moverTabs button").forEach((b) => b.classList.toggle("on", b === button));
  renderMovers();
});
$("#moverRows").addEventListener("click", (event) => {
  const row = event.target.closest("[data-symbol]");
  if (row) loadSecurity(row.dataset.symbol);
});

// ---------------------------------------------------------------- security: description + chart

async function loadSecurity(symbol) {
  state.symbol = symbol;
  renderMonitor();
  updateTicket();
  const [info] = await Promise.all([api(`/api/market/describe?symbol=${encodeURIComponent(symbol)}`, { auth: false }).catch(() => null), loadChart()]);
  renderDescription(info);
  try { history.replaceState(null, "", `#${encodeURIComponent(symbol)}`); } catch { /* sandboxed */ }
}

function renderDescription(info) {
  if (!info) { $("#des").innerHTML = '<div class="empty">No data for this instrument.</div>'; return; }
  const pos = info.year_high > info.year_low ? ((info.close - info.year_low) / (info.year_high - info.year_low)) * 100 : 50;
  const fmt = (value, suffix = "") => (value === null || value === undefined ? "--" : `${number.format(value)}${suffix}`);
  const pctCell = (value) => (value === null || value === undefined ? "--" : `<b class="${tone(value)}">${signed(value)}</b>`);
  $("#des").innerHTML = `
    <div class="des-title">
      <strong>${escapeHtml(info.symbol)}</strong>
      <span>${escapeHtml(info.kind === "INDEX" ? "NSE index" : info.name)} · ${escapeHtml(info.sector)}</span>
      <div class="des-price"><b>${number.format(info.close)}</b><span class="${tone(info.change_pct)}">${signed(info.change_pct)}</span></div>
      <span>Close ${escapeHtml(longDate(info.date))}</span>
    </div>
    <div class="des-grid">
      <div><span>OPEN</span>${fmt(info.open)}</div><div><span>HIGH</span>${fmt(info.high)}</div>
      <div><span>LOW</span>${fmt(info.low)}</div><div><span>PREV</span>${fmt(info.prev_close)}</div>
      <div><span>VOL</span>${info.volume ? number.format(info.volume) : "--"}</div><div><span>AVG VOL 20D</span>${info.avg_volume_20d ? number.format(info.avg_volume_20d) : "--"}</div>
      <div><span>1W</span>${pctCell(info.returns["1W"])}</div><div><span>1M</span>${pctCell(info.returns["1M"])}</div>
      <div><span>3M</span>${pctCell(info.returns["3M"])}</div><div><span>1Y</span>${pctCell(info.returns["1Y"])}</div>
      <div><span>RSI 14</span>${fmt(info.rsi_14)}</div><div><span>BETA 1Y</span>${fmt(info.beta_1y)}</div>
      <div><span>VOL 20D</span>${fmt(info.volatility_20d, "%")}</div><div><span>VOL 1Y</span>${fmt(info.volatility_1y, "%")}</div>
      <div><span>vs SMA50</span>${pctCell(info.vs_sma[50])}</div><div><span>vs SMA200</span>${pctCell(info.vs_sma[200])}</div>
      <div class="des-range"><span>52W ${number.format(info.year_low)}</span><span style="flex:1;margin:0 8px"><div class="range-bar"><i style="left:${pos}%"></i></div></span><span>${number.format(info.year_high)}</span></div>
    </div>`;
}

let priceChart, studyChart, candleSeries, volumeSeries, overlaySeries = [], studySeries = [], chartData = null;

function chartOptions(element, extra = {}) {
  return {
    width: element.clientWidth,
    height: element.clientHeight,
    layout: { background: { type: "solid", color: "#0d1116" }, textColor: COLORS.text, fontFamily: "IBM Plex Mono, monospace", fontSize: 10 },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    rightPriceScale: { borderColor: "#1d2530", minimumWidth: 70 },
    timeScale: { borderColor: "#1d2530" },
    crosshair: { mode: LWC.CrosshairMode.Normal },
    ...extra,
  };
}

function setupCharts() {
  const priceElement = $("#priceChart");
  const studyElement = $("#studyChart");
  priceChart = LWC.createChart(priceElement, chartOptions(priceElement));
  candleSeries = priceChart.addCandlestickSeries({
    upColor: COLORS.up, downColor: COLORS.down, borderUpColor: COLORS.up, borderDownColor: COLORS.down,
    wickUpColor: COLORS.up, wickDownColor: COLORS.down,
  });
  volumeSeries = priceChart.addHistogramSeries({ priceScaleId: "volume", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  priceChart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  // The TradingView attribution stays on the main price chart; the study pane shares it.
  const studyOptions = chartOptions(studyElement, { timeScale: { visible: false } });
  studyOptions.layout = { ...studyOptions.layout, attributionLogo: false };
  studyChart = LWC.createChart(studyElement, studyOptions);

  // Keep both panes scrolled and zoomed together.
  let syncing = false;
  const sync = (from, to) => (range) => {
    if (syncing || !range) return;
    syncing = true;
    to.timeScale().setVisibleLogicalRange(range);
    syncing = false;
  };
  priceChart.timeScale().subscribeVisibleLogicalRangeChange(sync(priceChart, studyChart));
  studyChart.timeScale().subscribeVisibleLogicalRangeChange(sync(studyChart, priceChart));
  priceChart.subscribeCrosshairMove((param) => renderLegend(param.time));

  new ResizeObserver(() => {
    priceChart.applyOptions({ width: priceElement.clientWidth, height: priceElement.clientHeight });
    if (!studyElement.hidden) studyChart.applyOptions({ width: studyElement.clientWidth, height: studyElement.clientHeight });
  }).observe(document.querySelector(".term-main"));
}

async function loadChart() {
  const wanted = [...state.overlays, state.study].filter(Boolean).join(",");
  try {
    chartData = await api(`/api/market/chart?symbol=${encodeURIComponent(state.symbol)}&days=${state.days}&indicators=${wanted}`, { auth: false });
  } catch {
    chartData = null;
  }
  drawChart();
}

function line(values, bars) {
  return values.map((value, index) => (value === null ? null : { time: bars[index].date, value })).filter(Boolean);
}

function drawChart() {
  overlaySeries.forEach((series) => priceChart.removeSeries(series));
  studySeries.forEach((series) => studyChart.removeSeries(series));
  overlaySeries = [];
  studySeries = [];
  if (!chartData) { candleSeries.setData([]); volumeSeries.setData([]); renderLegend(); return; }
  const { bars, indicators } = chartData;
  candleSeries.setData(bars.map((bar) => ({ time: bar.date, open: bar.open, high: bar.high, low: bar.low, close: bar.close })));
  volumeSeries.setData(bars.map((bar) => ({ time: bar.date, value: bar.volume, color: bar.close >= bar.open ? "rgba(40,208,125,.35)" : "rgba(255,90,82,.35)" })));

  for (const [name, values] of Object.entries(indicators)) {
    if (!OVERLAY_COLORS[name]) continue;
    const series = priceChart.addLineSeries({ color: OVERLAY_COLORS[name], lineWidth: name.startsWith("bb") ? 1 : 1.5, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, lineStyle: name.startsWith("bb") ? 2 : 0 });
    series.setData(line(values, bars));
    overlaySeries.push(series);
  }

  const studyElement = $("#studyChart");
  studyElement.hidden = !state.study;
  if (state.study === "rsi14" && indicators.rsi14) {
    const rsi = studyChart.addLineSeries({ color: COLORS.amber, lineWidth: 1.5, priceLineVisible: false });
    rsi.setData(line(indicators.rsi14, bars));
    rsi.createPriceLine({ price: 70, color: "#5c1f1b", lineStyle: 2, axisLabelVisible: true, title: "" });
    rsi.createPriceLine({ price: 30, color: "#0f3b25", lineStyle: 2, axisLabelVisible: true, title: "" });
    studySeries.push(rsi);
  } else if (state.study === "macd" && indicators.macd) {
    const hist = studyChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
    hist.setData(line(indicators.macd_hist, bars).map((point) => ({ ...point, color: point.value >= 0 ? "rgba(40,208,125,.6)" : "rgba(255,90,82,.6)" })));
    const macdLine = studyChart.addLineSeries({ color: "#5aa9ff", lineWidth: 1.5, priceLineVisible: false });
    macdLine.setData(line(indicators.macd, bars));
    const signalLine = studyChart.addLineSeries({ color: COLORS.amber, lineWidth: 1, priceLineVisible: false });
    signalLine.setData(line(indicators.macd_signal, bars));
    studySeries.push(hist, macdLine, signalLine);
  }
  requestAnimationFrame(() => {
    priceChart.applyOptions({ width: $("#priceChart").clientWidth, height: $("#priceChart").clientHeight });
    if (!studyElement.hidden) studyChart.applyOptions({ width: studyElement.clientWidth, height: studyElement.clientHeight });
    priceChart.timeScale().fitContent();
  });
  renderLegend();
}

function renderLegend(time) {
  const legend = $("#chartLegend");
  if (!chartData?.bars.length) { legend.textContent = "No chart data."; return; }
  const bars = chartData.bars;
  const index = time ? bars.findIndex((bar) => bar.date === time) : bars.length - 1;
  const bar = bars[index < 0 ? bars.length - 1 : index];
  const i = bars.indexOf(bar);
  const overlays = Object.keys(chartData.indicators).filter((name) => OVERLAY_COLORS[name] && !name.endsWith("_lower"))
    .map((name) => `<span class="key" style="background:${OVERLAY_COLORS[name]}"></span>${name.replace("_upper", "").toUpperCase()} <b>${chartData.indicators[name][i] === null ? "--" : number.format(chartData.indicators[name][i])}</b>`).join(" ");
  const study = state.study === "rsi14" && chartData.indicators.rsi14 ? ` · RSI <b>${chartData.indicators.rsi14[i] ?? "--"}</b>` : "";
  legend.innerHTML = `${escapeHtml(state.symbol)} ${escapeHtml(shortDate(bar.date))} · O <b>${number.format(bar.open)}</b> H <b>${number.format(bar.high)}</b> L <b>${number.format(bar.low)}</b> C <b class="${tone(bar.close - bar.open)}">${number.format(bar.close)}</b>${bar.volume ? ` V <b>${number.format(bar.volume)}</b>` : ""}${study} ${overlays}`;
}

$("#rangeButtons").addEventListener("click", (event) => {
  const button = event.target.closest("[data-days]");
  if (!button) return;
  state.days = Number(button.dataset.days);
  $$("#rangeButtons button").forEach((b) => b.classList.toggle("on", b === button));
  loadChart();
});
$("#overlayButtons").addEventListener("click", (event) => {
  const button = event.target.closest("[data-overlay]");
  if (!button) return;
  const name = button.dataset.overlay;
  if (state.overlays.has(name)) state.overlays.delete(name); else state.overlays.add(name);
  button.classList.toggle("on", state.overlays.has(name));
  loadChart();
});
$("#studyButtons").addEventListener("click", (event) => {
  const button = event.target.closest("[data-study]");
  if (!button) return;
  state.study = button.dataset.study;
  $$("#studyButtons button").forEach((b) => b.classList.toggle("on", b === button));
  loadChart();
});

// ---------------------------------------------------------------- ticket + orders

function quoteFor(symbol) { return state.quotes.find((quote) => quote.symbol === symbol); }
function heldQuantity(symbol) { return state.account?.positions.find((p) => p.symbol === symbol)?.quantity ?? 0; }

function updateTicket() {
  const quote = quoteFor(state.symbol);
  const quantity = Math.max(0, Number($("#ticketQty").value) || 0);
  $("#ticketSymbol").textContent = state.symbol;
  $("#ticketPrice").textContent = quote ? number.format(quote.close) : "--";
  $("#ticketValue").textContent = quote ? currency.format(quote.close * quantity) : "--";
  $("#ticketHeld").textContent = state.account ? `${number.format(heldQuantity(state.symbol))} / ${shortCurrency.format(state.account.cash)}` : "sign in";
  const submit = $("#ticketSubmit");
  submit.textContent = `PLACE PAPER ${state.side}`;
  submit.classList.toggle("sell", state.side === "SELL");
}
$$(".term-side-switch button").forEach((button) => button.addEventListener("click", () => {
  state.side = button.dataset.side;
  $$(".term-side-switch button").forEach((b) => b.classList.toggle("on", b === button));
  updateTicket();
}));
$("#ticketQty").addEventListener("input", updateTicket);
$("#ticket").addEventListener("submit", (event) => {
  event.preventDefault();
  placeOrder(state.side, Number($("#ticketQty").value), state.symbol);
});

async function placeOrder(side, quantity, symbol) {
  if (!(await accessToken())) { showLogin(); return; }
  const submit = $("#ticketSubmit");
  submit.disabled = true;
  try {
    const order = await api("/api/orders", { method: "POST", body: { symbol, side, quantity } });
    say(`FILLED ${order.side} ${number.format(order.quantity)} ${order.symbol} @ ${number.format(order.price)} (paper, ${shortDate(order.trade_date)} close)`);
    await loadAccount();
    if (["portfolio", "orders"].includes(state.dock)) setDock(state.dock);
  } catch (error) {
    if (error.message !== "Sign in required") say(`REJECTED: ${error.message}`, { error: true });
  } finally {
    submit.disabled = false;
  }
}

// ---------------------------------------------------------------- account + dock

async function loadAccount() {
  if (!(await accessToken())) {
    state.signedIn = false;
    state.account = null;
    $("#userButton").textContent = "SIGN IN";
    updateTicket();
    return;
  }
  try {
    state.account = await api("/api/account");
    state.signedIn = true;
    $("#userButton").textContent = `@${state.account.handle.toUpperCase()} · ${shortCurrency.format(state.account.equity)}`;
  } catch (error) {
    if (!(error instanceof ApiError)) console.error(error);
  }
  updateTicket();
}

$("#userButton").addEventListener("click", async () => {
  if (!state.signedIn) { showLogin(); return; }
  if (window.confirm(`Signed in as @${state.account.handle}. Sign out?`)) {
    await signOut();
    await loadAccount();
  }
});
$("#loginSkip").addEventListener("click", hideLogin);

$("#dockTabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab]");
  if (button) setDock(button.dataset.tab);
});
$("#dockBody").addEventListener("click", async (event) => {
  const target = event.target.closest("[data-symbol]");
  if (target) { loadSecurity(target.dataset.symbol); return; }
  const signIn = event.target.closest("[data-sign-in]");
  if (signIn) showLogin();
});
$("#dockBody").addEventListener("change", async (event) => {
  const id = event.target.dataset.strategyId;
  if (!id) return;
  try {
    const strategy = await api(`/api/strategies/${id}`, { method: "PATCH", body: { active: event.target.checked } });
    say(`${strategy.name}: ${strategy.active ? "ON from the next close" : "PAUSED"}`);
  } catch (error) {
    say(error.message, { error: true });
  }
});

const needsLogin = '<div class="empty">Sign in to see this. <button class="term-link" type="button" data-sign-in>Sign in</button></div>';

async function setDock(tab, payload) {
  state.dock = tab;
  $$("#dockTabs button").forEach((button) => button.classList.toggle("on", button.dataset.tab === tab));
  const body = $("#dockBody");
  const note = $("#dockNote");
  note.textContent = "";
  try {
    if (tab === "heatmap") {
      const data = await api("/api/market/heatmap", { auth: false });
      note.textContent = data.as_of ? `SECTORS · SIZE = TURNOVER · ${shortDate(data.as_of).toUpperCase()}` : "";
      body.innerHTML = renderHeatmap(data);
    } else if (tab === "help") {
      const commands = payload ?? (await api("/api/command", { method: "POST", body: { text: "HELP" }, auth: false })).commands;
      body.innerHTML = `<table class="term-table static"><tbody>${commands.map((c) => `<tr><td class="sym" style="color:var(--amber)">${escapeHtml(c.command)}</td><td>${escapeHtml(c.does)}</td></tr>`).join("")}
        <tr><td class="sym" style="color:var(--amber)">↑ ↓ TAB ESC</td><td>Pick suggestions, recall past commands, clear the line. Start typing anywhere to use the command line.</td></tr></tbody></table>`;
    } else if (tab === "leaderboard") {
      const board = await api("/api/leaderboard", { auth: false });
      note.textContent = board.as_of ? `7-DAY PAPER RETURN TO ${shortDate(board.as_of).toUpperCase()}` : "";
      body.innerHTML = board.entries.length
        ? `<table class="term-table static"><thead><tr><th>#</th><th>TRADER</th><th class="num">TRADES 7D</th><th class="num">EQUITY</th><th class="num">RETURN 7D</th></tr></thead><tbody>${board.entries.map((e) => `<tr class="${e.handle === state.account?.handle ? "current" : ""}"><td class="num">${e.rank}</td><td>${escapeHtml(e.display_name)} <span class="term-muted">@${escapeHtml(e.handle)}</span></td><td class="num">${e.trades}</td><td class="num">${shortCurrency.format(e.equity)}</td><td class="num ${tone(e.return_pct)}">${signed(e.return_pct)}</td></tr>`).join("")}</tbody></table>`
        : '<div class="empty">No one is ranked yet.</div>';
    } else if (!state.signedIn) {
      body.innerHTML = needsLogin;
    } else if (tab === "portfolio") {
      const [stats, account] = await Promise.all([api("/api/account/analytics"), api("/api/account")]);
      state.account = account;
      body.innerHTML = renderPortfolio(stats, account);
    } else if (tab === "orders") {
      const orders = await api("/api/orders?limit=100");
      body.innerHTML = orders.length
        ? `<table class="term-table static"><thead><tr><th>DATE</th><th>SIDE</th><th>SYMBOL</th><th class="num">QTY</th><th class="num">PRICE</th><th class="num">VALUE</th><th>SOURCE</th><th>STATUS</th></tr></thead><tbody>${orders.map((o) => `<tr><td class="num">${escapeHtml(shortDate(o.trade_date))}</td><td class="${o.side === "BUY" ? "positive" : "negative"}">${o.side}</td><td class="sym" data-symbol="${escapeHtml(o.symbol)}" style="cursor:pointer">${escapeHtml(o.symbol)}</td><td class="num">${number.format(o.quantity)}</td><td class="num">${number.format(o.price)}</td><td class="num">${number.format(o.quantity * o.price)}</td><td>${o.source === "strategy" ? escapeHtml(o.strategy || "RULE") : "MANUAL"}</td><td class="${o.status === "filled" ? "" : "negative"}" title="${escapeHtml(o.note)}">${o.status === "filled" ? "FILLED" : `REJ: ${escapeHtml(o.note.split(". ").pop())}`}</td></tr>`).join("")}</tbody></table>`
        : '<div class="empty">No orders yet. Try BUY 10 RELIANCE.</div>';
    } else if (tab === "strategies") {
      const strategies = await api("/api/strategies");
      note.innerHTML = '<a class="term-link" href="./?build=1#strategies">+ NEW RULE</a>';
      body.innerHTML = strategies.length
        ? `<table class="term-table static"><thead><tr><th>ON</th><th>NAME</th><th>RULE</th><th>LAST RUN</th></tr></thead><tbody>${strategies.map((s) => `<tr><td><input class="term-switch" type="checkbox" data-strategy-id="${s.id}" ${s.active ? "checked" : ""} aria-label="Toggle ${escapeHtml(s.name)}" /></td><td class="sym">${escapeHtml(s.name)}</td><td>${escapeHtml(s.description)}</td><td class="num">${s.last_run_date ? escapeHtml(shortDate(s.last_run_date)) : "--"}</td></tr>`).join("")}</tbody></table>`
        : '<div class="empty">No rules yet. Type RULE to build one with a 90-day preview.</div>';
    }
  } catch (error) {
    if (error.message === "Sign in required") body.innerHTML = needsLogin;
    else body.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function heatColor(change) {
  const strength = Math.min(Math.abs(change) / 3, 1);
  if (Math.abs(change) < 0.05) return "#2a323d";
  return change > 0
    ? `rgb(${Math.round(20 + 10 * strength)}, ${Math.round(70 + 110 * strength)}, ${Math.round(50 + 50 * strength)})`
    : `rgb(${Math.round(90 + 150 * strength)}, ${Math.round(40 + 20 * strength)}, ${Math.round(40 + 10 * strength)})`;
}

function renderHeatmap(data) {
  if (!data.sectors.length) return '<div class="empty">No sector data yet.</div>';
  return `<div class="heatmap">${data.sectors.map((sector) => `<div class="hm-sector">
      <header><span>${escapeHtml(sector.sector.toUpperCase())}</span><span class="${tone(sector.change_pct)}">${signed(sector.change_pct)}</span></header>
      <div class="hm-tiles">${sector.members.map((m) => `<button type="button" class="hm-tile" data-symbol="${escapeHtml(m.symbol)}" style="background:${heatColor(m.change_pct)};flex-grow:${Math.max(m.value_cr, 1)}" title="${escapeHtml(m.symbol)} ${signed(m.change_pct)} · ₹${number.format(m.value_cr)} Cr traded"><b>${escapeHtml(m.symbol)}</b>${signed(m.change_pct)}</button>`).join("")}</div>
    </div>`).join("")}</div>`;
}

function renderPortfolio(stats, account) {
  const kpi = (label, value, cls = "") => `<div><span>${label}</span><b class="${cls}">${value}</b></div>`;
  const pct = (value) => (value === null ? "--" : `${number.format(value)}%`);
  const risk = stats.days_tracked < 5 ? '<p class="term-muted" style="margin:6px 0 0">Risk ratios fill in after 5 market closes.</p>' : "";
  const positions = account.positions.length
    ? `<table class="term-table"><thead><tr><th>SYMBOL</th><th class="num">QTY</th><th class="num">AVG</th><th class="num">LAST</th><th class="num">P&amp;L</th></tr></thead><tbody>${account.positions.map((p) => `<tr data-symbol="${escapeHtml(p.symbol)}"><td class="sym">${escapeHtml(p.symbol)}</td><td class="num">${number.format(p.quantity)}</td><td class="num">${number.format(p.average_price)}</td><td class="num">${number.format(p.last_price)}</td><td class="num ${tone(p.pnl)}">${number.format(p.pnl)} <span class="term-muted">${signed(p.pnl_pct)}</span></td></tr>`).join("")}</tbody></table>`
    : '<div class="empty">No open positions.</div>';
  const maxWeight = Math.max(...stats.sectors.map((s) => s.weight_pct), 1);
  const sectors = stats.sectors.length
    ? stats.sectors.map((s) => `<div class="bar-row"><span>${escapeHtml(s.sector)}</span><i style="width:${(s.weight_pct / maxWeight) * 100}%"></i><span class="num">${s.weight_pct.toFixed(1)}%</span></div>`).join("")
    : '<div class="term-muted">All cash.</div>';
  return `<div class="dock-grid">
    <div class="dock-section">
      <h3>ACCOUNT</h3>
      <div class="kpis">
        ${kpi("EQUITY", shortCurrency.format(stats.equity))}
        ${kpi("TOTAL RETURN", signed(account.total_return_pct), tone(account.total_return_pct))}
        ${kpi("UNREALIZED", number.format(account.unrealized_pnl), tone(account.unrealized_pnl))}
        ${kpi("REALIZED", number.format(stats.realized_pnl), tone(stats.realized_pnl))}
        ${kpi("CASH", pct(stats.cash_pct))}
        ${kpi("LARGEST POS", pct(stats.largest_position_pct))}
        ${kpi("WIN RATE", stats.win_rate === null ? "--" : `${stats.win_rate}% (${stats.closed_trades})`)}
      </div>
      <h3 style="margin-top:10px">RISK</h3>
      <div class="kpis">
        ${kpi("SHARPE", stats.sharpe ?? "--", tone(stats.sharpe ?? 0))}
        ${kpi("VOLATILITY", pct(stats.volatility_pct))}
        ${kpi("MAX DRAWDOWN", pct(stats.max_drawdown_pct), stats.max_drawdown_pct ? "negative" : "")}
        ${kpi("BETA vs NIFTY", stats.beta ?? "--")}
      </div>${risk}
    </div>
    <div class="dock-section"><h3>POSITIONS</h3>${positions}</div>
    <div class="dock-section"><h3>SECTOR EXPOSURE (% OF EQUITY)</h3>${sectors}</div>
  </div>`;
}

// ---------------------------------------------------------------- boot

function updateClock() {
  $("#clock").textContent = `${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date())} IST`;
}

async function refresh() {
  await loadMarket();
  await loadAccount();
}

async function boot() {
  setupCharts();
  updateClock();
  setInterval(updateClock, 1000);
  await setupAuth({ onSignedIn: async () => { await loadAccount(); setDock(state.dock); } });
  await refresh();
  const fromHash = decodeURIComponent(window.location.hash.slice(1));
  await loadSecurity(state.symbols.has(fromHash) ? fromHash : state.symbol);
  setDock("heatmap");
  setInterval(() => { if (document.visibilityState === "visible") refresh(); }, 60000);
}

boot().catch((error) => {
  console.error(error);
  say("Could not reach the BBDFi server.", { error: true });
});
