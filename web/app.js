import {
  $, $$, ApiError, accessToken, api, currency, escapeHtml, hideLogin, initials, longDate, number, setupAuth,
  shortCurrency, shortDate, showLogin, signOut, signed, tone,
} from "./common.js";

const state = {
  status: null,
  quotes: [],
  account: null,
  strategies: [],
  orders: [],
  leaderboard: null,
  chart: { view: "instrument", symbol: "NIFTY 50", range: 63, points: [], hover: null },
  tradeSide: "BUY",
  aiEnabled: false,
};

$("#signOutButton").addEventListener("click", async () => {
  $("#profileDialog").close();
  await signOut();
});

// ---------------------------------------------------------------- data

async function loadPublic() {
  const [status, quotes, leaderboard] = await Promise.all([
    api("/api/market/status", { auth: false }),
    api("/api/market/quotes", { auth: false }),
    api("/api/leaderboard", { auth: false }),
  ]);
  Object.assign(state, { status, quotes, leaderboard });
  renderStatus();
  renderWatchlist($("#watchlistSearch").value);
  renderLeaderboard();
  fillSymbolSelect($("#tradeSymbol"));
}

async function loadPrivate() {
  const [account, strategies, orders] = await Promise.all([api("/api/account"), api("/api/strategies"), api("/api/orders?limit=25")]);
  Object.assign(state, { account, strategies, orders });
  renderAccount();
  renderStrategies();
  renderActivity();
  renderLeaderboard();
}

async function refreshAll() {
  try {
    await loadPublic();
    if (await accessToken()) {
      hideLogin();
      await loadPrivate();
    } else {
      showLogin();
    }
    await loadChart();
  } catch (error) {
    if (!(error instanceof ApiError)) console.error(error);
    else if (error.message !== "Sign in required") showToast(error.message);
  }
}

// ---------------------------------------------------------------- render

function renderStatus() {
  const { as_of: asOf, sample_data: sample } = state.status;
  $("#dataStatus").textContent = asOf ? `${sample ? "Sample prices" : "NSE close"} · ${shortDate(asOf)}` : "No prices loaded";
  $("#dataDot").style.background = sample || !asOf ? "var(--amber)" : "";
  $("#dataNotice").innerHTML = sample
    ? '<i class="bi bi-exclamation-triangle"></i><span>Sample prices for development · Load NSE data to go real</span>'
    : `<i class="bi bi-info-circle"></i><span>Paper trading only · Prices as of ${asOf ? longDate(asOf) : "--"}</span>`;
}

function renderWatchlist(filter = "") {
  const list = $("#watchlistList");
  const query = filter.toLowerCase();
  const filtered = state.quotes.filter((quote) => `${quote.symbol} ${quote.name}`.toLowerCase().includes(query));
  if (!filtered.length) {
    list.innerHTML = `<div class="empty-search">${state.quotes.length ? "No matching instruments" : "No prices loaded yet"}</div>`;
    return;
  }
  list.innerHTML = filtered.map((quote) => `<div class="watch-row ${quote.symbol === state.chart.symbol && state.chart.view === "instrument" ? "selected" : ""}" role="button" tabindex="0" data-chart-symbol="${escapeHtml(quote.symbol)}">
      <span><span class="watch-symbol">${escapeHtml(quote.symbol)}</span><span class="watch-name d-block">${escapeHtml(quote.kind === "INDEX" ? "Index" : quote.name === quote.symbol ? "NSE equity" : quote.name)}</span></span>
      <span class="watch-right"><span><span class="watch-price d-block">${number.format(quote.close)}</span><span class="watch-change d-block ${tone(quote.change_pct)}">${signed(quote.change_pct)}</span></span>
      <button class="icon-button small-icon watch-trade" type="button" data-trade-symbol="${escapeHtml(quote.symbol)}" aria-label="Trade ${escapeHtml(quote.symbol)}"><i class="bi bi-cart-plus"></i></button></span>
    </div>`).join("");
}

function renderAccount() {
  const account = state.account;
  $("#profileName").textContent = account.display_name;
  $("#profileHandle").textContent = `@${account.handle}`;
  $("#profileAvatar").textContent = initials(account.display_name);
  $("#welcomeTitle").innerHTML = `Welcome back, <span>${escapeHtml(account.display_name)}.</span>`;
  $("#equityValue").textContent = shortCurrency.format(account.equity);
  const ret = account.total_return_pct;
  $("#totalReturn").innerHTML = `<i class="bi ${ret > 0 ? "bi-caret-up-fill" : ret < 0 ? "bi-caret-down-fill" : "bi-dash"}"></i> ${signed(ret)}`;
  $("#totalReturn").className = `metric-neutral ${tone(ret)}`;
  $("#pnlValue").textContent = currency.format(account.unrealized_pnl);
  $("#pnlValue").className = `metric-value ${tone(account.unrealized_pnl)}`;
  $("#pnlPercent").textContent = signed(account.unrealized_pct);
  $("#pnlPercent").className = `metric-neutral ${tone(account.unrealized_pct)}`;
  $("#buyingPowerValue").textContent = shortCurrency.format(account.cash);
  $("#orderCount").textContent = account.orders_filled;

  $("#positionCount").textContent = `${account.positions.length} open`;
  $("#positionRows").innerHTML = account.positions.length
    ? account.positions.map((position) => `<tr>
        <td class="instrument-cell">${escapeHtml(position.symbol)}</td>
        <td>${number.format(position.quantity)}</td>
        <td>${currency.format(position.average_price)}</td>
        <td>${currency.format(position.last_price)}</td>
        <td class="${tone(position.pnl)}">${currency.format(position.pnl)} <small>(${signed(position.pnl_pct)})</small></td>
        <td class="text-end"><button class="text-button" type="button" data-sell-symbol="${escapeHtml(position.symbol)}">Sell</button></td>
      </tr>`).join("")
    : '<tr><td class="empty-activity" colspan="6">No open positions. Buy something from the watchlist or switch on a rule.</td></tr>';
}

function renderStrategies() {
  const active = state.strategies.filter((strategy) => strategy.active).length;
  $("#strategyCount").textContent = state.strategies.length;
  $("#activeStrategyLabel").textContent = `${active} active`;
  $("#strategyList").innerHTML = state.strategies.length
    ? state.strategies.map((strategy) => {
      const icon = { prev_close_move: "bi-graph-down-arrow", sma_cross: "bi-bezier2", take_profit_stop_loss: "bi-bullseye" }[strategy.rule_type] || "bi-sliders";
      const run = strategy.last_run_date ? `Last checked ${shortDate(strategy.last_run_date)}` : strategy.start_after ? `Starts after ${shortDate(strategy.start_after)} close` : "Waiting for the next close";
      return `<div class="strategy-row">
        <span class="strategy-icon"><i class="bi ${icon}"></i></span>
        <div class="strategy-copy"><div class="strategy-title">${escapeHtml(strategy.name)}</div><div class="strategy-description">${escapeHtml(strategy.description)}</div><div class="strategy-meta">${run}</div></div>
        <button class="icon-button small-icon" type="button" data-delete-strategy="${strategy.id}" aria-label="Delete ${escapeHtml(strategy.name)}"><i class="bi bi-trash3"></i></button>
        <input class="strategy-toggle" type="checkbox" role="switch" aria-label="${strategy.active ? "Pause" : "Switch on"} ${escapeHtml(strategy.name)}" data-strategy-id="${strategy.id}" ${strategy.active ? "checked" : ""} />
      </div>`;
    }).join("")
    : '<div class="empty-search">No rules yet. Add one and preview how it would have done.</div>';
}

function renderActivity() {
  $("#activityCount").textContent = `${state.orders.length} ${state.orders.length === 1 ? "order" : "orders"}`;
  $("#activityRows").innerHTML = state.orders.length
    ? state.orders.map((order) => `<tr title="${escapeHtml(order.note)}">
        <td class="instrument-cell">${escapeHtml(order.symbol)}</td>
        <td><span class="side-label ${order.side.toLowerCase()}">${order.side}</span></td>
        <td>${number.format(order.quantity)}</td>
        <td>${currency.format(order.price)}</td>
        <td>${shortDate(order.trade_date)}</td>
        <td>${order.source === "strategy" ? `<i class="bi bi-robot"></i> ${escapeHtml(order.strategy || "Rule")}` : '<i class="bi bi-hand-index"></i> Manual'}</td>
        <td>${order.status === "filled"
          ? '<span class="order-status"><i class="bi bi-check-circle-fill"></i> Paper filled</span>'
          : `<span class="order-status rejected"><i class="bi bi-x-circle-fill"></i> ${escapeHtml(order.note.split(". ").pop())}</span>`}</td>
      </tr>`).join("")
    : '<tr><td class="empty-activity" colspan="7">No paper orders yet. Start with a small practice trade.</td></tr>';
}

function renderLeaderboard() {
  const board = state.leaderboard;
  const me = state.account?.handle;
  const entries = board?.entries ?? [];
  const mine = entries.find((entry) => entry.handle === me);
  $("#rankLabel").textContent = mine ? `Rank #${mine.rank}` : "Unranked";
  $("#leaderboardFoot").textContent = board?.as_of ? `7-day paper return to ${shortDate(board.as_of)}` : "Rankings appear after the first market close";
  const top = entries.slice(0, 6);
  if (mine && !top.includes(mine)) top.push(mine);
  $("#leaderboardList").innerHTML = top.length
    ? top.map((entry) => `<div class="leader-row ${entry.handle === me ? "is-me" : ""}">
        <span class="leader-rank">${entry.rank}</span>
        <span class="leader-avatar ${["", "avatar-coral", "avatar-blue"][entry.rank % 3]}">${escapeHtml(initials(entry.display_name))}</span>
        <div><div class="leader-name">${escapeHtml(entry.display_name)}${entry.handle === me ? " (you)" : ""}</div><div class="leader-caption">@${escapeHtml(entry.handle)} · ${entry.trades} trades</div></div>
        <span class="leader-return ${tone(entry.return_pct)}">${signed(entry.return_pct)}</span>
      </div>`).join("")
    : '<div class="empty-search">No one is ranked yet. Place a trade to get on the board.</div>';
}

// ---------------------------------------------------------------- chart

async function loadChart() {
  const chart = state.chart;
  if (chart.view === "equity") {
    const curve = state.account?.equity_curve ?? [];
    chart.points = curve.slice(-chart.range).map((point) => ({ date: point.date, value: point.equity }));
    $("#chartKicker").textContent = "YOUR PAPER ACCOUNT";
    $("#chartTitle").textContent = "Equity";
    $("#chartNote").textContent = "Your account value at each NSE close.";
  } else {
    const history = await api(`/api/market/history?symbol=${encodeURIComponent(chart.symbol)}&days=${chart.range}`, { auth: false }).catch(() => []);
    chart.points = history.map((bar) => ({ date: bar.date, value: bar.close }));
    const quote = state.quotes.find((item) => item.symbol === chart.symbol);
    $("#chartKicker").textContent = quote?.kind === "INDEX" ? "INDEX" : "NSE EQUITY";
    const name = quote?.name && quote.name !== chart.symbol ? quote.name : "";
    $("#chartTitle").innerHTML = quote?.kind === "INDEX" ? escapeHtml(chart.symbol) : `${escapeHtml(chart.symbol)}${name ? ` <span class="index-symbol">${escapeHtml(name)}</span>` : ""}`;
    $("#chartNote").textContent = "End-of-day closing prices. Hover the chart for details.";
  }
  const { points } = chart;
  if (points.length) {
    const last = points[points.length - 1].value;
    const first = points[0].value;
    const change = ((last / first) - 1) * 100;
    $("#chartPrice").textContent = chart.view === "equity" ? shortCurrency.format(last) : number.format(last);
    $("#chartChange").className = change >= 0 ? "quote-up" : "quote-down";
    $("#chartChange").innerHTML = `<i class="bi ${change >= 0 ? "bi-caret-up-fill" : "bi-caret-down-fill"}"></i> ${signed(change)} <small>this range</small>`;
    const mid = points[Math.floor(points.length / 2)];
    $("#chartStart").textContent = shortDate(points[0].date);
    $("#chartMid").textContent = shortDate(mid.date);
    $("#chartEnd").textContent = shortDate(points[points.length - 1].date);
  } else {
    $("#chartPrice").textContent = "--";
    $("#chartChange").innerHTML = "";
    ["#chartStart", "#chartMid", "#chartEnd"].forEach((selector) => { $(selector).textContent = ""; });
    if (chart.view === "equity") $("#chartNote").textContent = "Your equity curve starts after your first market close.";
  }
  drawChart();
}

const chartPadding = { top: 10, right: 52, bottom: 9, left: 2 };

function drawChart() {
  const canvas = $("#marketChart");
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const { width, height } = rect;
  const padding = chartPadding;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = state.chart.points.map((point) => point.value);
  context.clearRect(0, 0, width, height);
  if (values.length < 2) {
    context.fillStyle = "#97a39c";
    context.font = '11px "DM Sans", sans-serif';
    context.textAlign = "center";
    context.fillText("Not enough data yet", width / 2, height / 2);
    return;
  }
  const spread = Math.max(...values) - Math.min(...values) || Math.max(...values) * 0.01 || 1;
  const min = Math.min(...values) - spread * 0.12;
  const max = Math.max(...values) + spread * 0.08;
  const x = (index) => padding.left + (index / (values.length - 1)) * plotWidth;
  const y = (value) => padding.top + ((max - value) / (max - min)) * plotHeight;
  const up = values[values.length - 1] >= values[0];
  const lineColor = up ? "#38845d" : "#be5149";

  context.font = '9px "DM Sans", sans-serif';
  context.textBaseline = "middle";
  for (let line = 0; line < 4; line += 1) {
    const lineY = padding.top + (plotHeight * line) / 3;
    context.beginPath();
    context.strokeStyle = "#edf1ee";
    context.lineWidth = 1;
    context.moveTo(padding.left, lineY);
    context.lineTo(width - padding.right + 2, lineY);
    context.stroke();
    context.fillStyle = "#97a39c";
    context.textAlign = "right";
    context.fillText(number.format(Math.round(max - ((max - min) * line) / 3)), width - 1, lineY);
  }

  context.beginPath();
  context.moveTo(x(0), y(values[0]));
  values.forEach((value, index) => context.lineTo(x(index), y(value)));
  context.lineTo(x(values.length - 1), height - padding.bottom);
  context.lineTo(x(0), height - padding.bottom);
  context.closePath();
  const fill = context.createLinearGradient(0, padding.top, 0, height);
  fill.addColorStop(0, up ? "rgba(52, 133, 91, .16)" : "rgba(190, 81, 73, .14)");
  fill.addColorStop(1, "rgba(255, 255, 255, 0)");
  context.fillStyle = fill;
  context.fill();

  context.beginPath();
  values.forEach((value, index) => (index ? context.lineTo(x(index), y(value)) : context.moveTo(x(index), y(value))));
  context.strokeStyle = lineColor;
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();

  const marker = state.chart.hover ?? values.length - 1;
  if (state.chart.hover !== null) {
    context.beginPath();
    context.strokeStyle = "#c9d3cd";
    context.setLineDash([3, 3]);
    context.moveTo(x(marker), padding.top);
    context.lineTo(x(marker), height - padding.bottom);
    context.stroke();
    context.setLineDash([]);
  }
  context.beginPath();
  context.arc(x(marker), y(values[marker]), 3.3, 0, Math.PI * 2);
  context.fillStyle = lineColor;
  context.fill();
}

$("#marketChart").addEventListener("mousemove", (event) => {
  const points = state.chart.points;
  if (points.length < 2) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const plotWidth = rect.width - chartPadding.left - chartPadding.right;
  const index = Math.max(0, Math.min(points.length - 1, Math.round(((event.clientX - rect.left - chartPadding.left) / plotWidth) * (points.length - 1))));
  state.chart.hover = index;
  drawChart();
  const tooltip = $("#chartTooltip");
  const point = points[index];
  const change = ((point.value / points[0].value) - 1) * 100;
  tooltip.innerHTML = `<strong>${state.chart.view === "equity" ? shortCurrency.format(point.value) : number.format(point.value)}</strong><span>${longDate(point.date)}</span><span class="${tone(change)}">${signed(change)} from range start</span>`;
  tooltip.hidden = false;
  const left = chartPadding.left + (index / (points.length - 1)) * plotWidth;
  tooltip.style.left = `${Math.min(Math.max(left, 70), rect.width - 70)}px`;
});
$("#marketChart").addEventListener("mouseleave", () => {
  state.chart.hover = null;
  $("#chartTooltip").hidden = true;
  drawChart();
});

$$("[data-view]").forEach((button) => button.addEventListener("click", () => {
  $$("[data-view]").forEach((item) => item.classList.toggle("selected", item === button));
  state.chart.view = button.dataset.view;
  renderWatchlist($("#watchlistSearch").value);
  loadChart();
}));
$("#rangeSwitch").addEventListener("click", (event) => {
  const button = event.target.closest("[data-range]");
  if (!button) return;
  $$("[data-range]").forEach((item) => item.classList.toggle("selected", item === button));
  state.chart.range = Number(button.dataset.range);
  loadChart();
});

// ---------------------------------------------------------------- trading

function fillSymbolSelect(select, { includeIndices = true } = {}) {
  const current = select.value;
  select.innerHTML = state.quotes
    .filter((quote) => includeIndices || quote.kind !== "INDEX")
    .map((quote) => `<option value="${escapeHtml(quote.symbol)}">${escapeHtml(quote.symbol)}${quote.kind === "INDEX" ? " (index)" : ""}</option>`).join("");
  if (current && [...select.options].some((option) => option.value === current)) select.value = current;
}

function heldQuantity(symbol) {
  return state.account?.positions.find((position) => position.symbol === symbol)?.quantity ?? 0;
}

function updateEstimate() {
  const quote = state.quotes.find((item) => item.symbol === $("#tradeSymbol").value);
  const quantity = Math.max(0, Number($("#tradeQuantity").value) || 0);
  $("#tradeEstimateLabel").textContent = quote ? `Close on ${shortDate(quote.date)}` : "Closing price";
  $("#tradeEstimate").textContent = currency.format(quote?.close ?? 0);
  $("#tradeHolding").textContent = number.format(heldQuantity(quote?.symbol));
  $("#orderValue").textContent = currency.format((quote?.close ?? 0) * quantity);
  const button = $("#submitTrade");
  button.textContent = `Place paper ${state.tradeSide.toLowerCase()}`;
  button.classList.toggle("sell-submit", state.tradeSide === "SELL");
  $("#tradeError").hidden = true;
}

function setSide(side) {
  state.tradeSide = side;
  $$(".side-button").forEach((button) => button.classList.toggle("selected", button.dataset.side === side));
  updateEstimate();
}

function openTrade(symbol, side = "BUY") {
  if (!state.quotes.length) { showToast("No prices loaded yet."); return; }
  fillSymbolSelect($("#tradeSymbol"));
  $("#tradeSymbol").value = symbol && state.quotes.some((quote) => quote.symbol === symbol) ? symbol : state.chart.symbol;
  $("#tradeQuantity").value = side === "SELL" ? String(heldQuantity($("#tradeSymbol").value) || 1) : "1";
  setSide(side);
  $("#tradeDialog").showModal();
}

$$("[data-open-trade]").forEach((button) => button.addEventListener("click", () => openTrade()));
$$("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
$$(".side-button").forEach((button) => button.addEventListener("click", () => setSide(button.dataset.side)));
$("#tradeSymbol").addEventListener("change", updateEstimate);
$("#tradeQuantity").addEventListener("input", updateEstimate);

$("#tradeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = { symbol: $("#tradeSymbol").value, side: state.tradeSide, quantity: Number($("#tradeQuantity").value) };
  const button = $("#submitTrade");
  button.disabled = true;
  try {
    const order = await api("/api/orders", { method: "POST", body });
    $("#tradeDialog").close();
    showToast(`${order.side === "BUY" ? "Bought" : "Sold"} ${number.format(order.quantity)} ${order.symbol} at ${currency.format(order.price)}.`);
    await Promise.all([loadPrivate(), api("/api/leaderboard", { auth: false }).then((board) => { state.leaderboard = board; renderLeaderboard(); })]);
  } catch (error) {
    $("#tradeError").textContent = error.message;
    $("#tradeError").hidden = false;
  } finally {
    button.disabled = false;
  }
});

$("#watchlistList").addEventListener("click", (event) => {
  const trade = event.target.closest("[data-trade-symbol]");
  if (trade) { openTrade(trade.dataset.tradeSymbol); return; }
  const row = event.target.closest("[data-chart-symbol]");
  if (row) selectChartSymbol(row.dataset.chartSymbol);
});
$("#watchlistList").addEventListener("keydown", (event) => {
  const row = event.target.closest("[data-chart-symbol]");
  if (row && event.target === row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); selectChartSymbol(row.dataset.chartSymbol); }
});
$("#positionRows").addEventListener("click", (event) => {
  const button = event.target.closest("[data-sell-symbol]");
  if (button) openTrade(button.dataset.sellSymbol, "SELL");
});

function selectChartSymbol(symbol) {
  state.chart.symbol = symbol;
  state.chart.view = "instrument";
  $$("[data-view]").forEach((item) => item.classList.toggle("selected", item.dataset.view === "instrument"));
  renderWatchlist($("#watchlistSearch").value);
  loadChart();
}

$("#watchlistSearch").addEventListener("input", (event) => renderWatchlist(event.target.value));
$("#watchlistSearchButton").addEventListener("click", () => $("#watchlistSearch").focus());

// ---------------------------------------------------------------- strategies

const RULE_FIELDS = {
  prev_close_move: [
    { key: "watch_symbol", label: "Watch", type: "symbol", value: "NIFTY 50" },
    { key: "direction", label: "Moves", type: "select", options: [["down", "Down"], ["up", "Up"]], value: "down" },
    { key: "threshold_pct", label: "By at least (%)", type: "number", step: "0.1", min: "0.1", value: 1.5 },
    { key: "side", label: "Then", type: "select", options: [["BUY", "Buy"], ["SELL", "Sell"]], value: "BUY" },
    { key: "quantity", label: "Quantity", type: "number", step: "1", min: "1", value: 10 },
    { key: "trade_symbol", label: "Of", type: "symbol", value: "RELIANCE" },
  ],
  sma_cross: [
    { key: "symbol", label: "Instrument", type: "symbol", value: "RELIANCE" },
    { key: "period", label: "Moving average (days)", type: "number", step: "1", min: "2", value: 20 },
    { key: "quantity", label: "Quantity to buy", type: "number", step: "1", min: "1", value: 10 },
  ],
  take_profit_stop_loss: [
    { key: "symbol", label: "Instrument", type: "symbol", value: "RELIANCE" },
    { key: "take_profit_pct", label: "Take profit at (%)", type: "number", step: "0.5", min: "0.5", value: 8 },
    { key: "stop_loss_pct", label: "Stop loss at (%)", type: "number", step: "0.5", min: "0.5", value: 4 },
  ],
};

const TEMPLATES = [
  { name: "Nifty dip buyer", rule_type: "prev_close_move", params: { watch_symbol: "NIFTY 50", direction: "down", threshold_pct: 1.5, side: "BUY", quantity: 20, trade_symbol: "HDFCBANK" } },
  { name: "20-day trend rider", rule_type: "sma_cross", params: { symbol: "RELIANCE", period: 20, quantity: 50 } },
  { name: "Lock in gains", rule_type: "take_profit_stop_loss", params: { symbol: "RELIANCE", take_profit_pct: 8, stop_loss_pct: 4 } },
];

$("#templateRow").innerHTML = TEMPLATES.map((template, index) => `<button class="template-chip" type="button" data-template="${index}">${escapeHtml(template.name)}</button>`).join("");

function renderRuleFields(values = {}) {
  const type = $("#ruleType").value;
  $("#ruleFields").innerHTML = RULE_FIELDS[type].map((field) => {
    const value = values[field.key] ?? field.value;
    const id = `rule_${field.key}`;
    if (field.type === "number") {
      return `<div><label class="form-label" for="${id}">${field.label}</label><input class="form-control" id="${id}" data-key="${field.key}" type="number" step="${field.step}" min="${field.min}" value="${value}" required /></div>`;
    }
    const options = field.type === "symbol"
      ? state.quotes.map((quote) => [quote.symbol, quote.symbol])
      : field.options;
    return `<div><label class="form-label" for="${id}">${field.label}</label><select class="form-select" id="${id}" data-key="${field.key}">${options.map(([optionValue, text]) => `<option value="${escapeHtml(optionValue)}" ${optionValue === value ? "selected" : ""}>${escapeHtml(text)}</option>`).join("")}</select></div>`;
  }).join("");
  updateRuleSentence();
}

function ruleParams() {
  const params = {};
  $$("#ruleFields [data-key]").forEach((input) => {
    params[input.dataset.key] = input.type === "number" ? (input.value === "" ? null : Number(input.value)) : input.value;
  });
  return params;
}

function updateRuleSentence() {
  const p = ruleParams();
  const type = $("#ruleType").value;
  let sentence = "";
  if (type === "prev_close_move") sentence = `If ${p.watch_symbol} closes ${p.threshold_pct}% ${p.direction === "down" ? "below" : "above"} yesterday's close, ${p.side === "BUY" ? "buy" : "sell"} ${p.quantity} ${p.trade_symbol}.`;
  if (type === "sma_cross") sentence = `Buy ${p.quantity} ${p.symbol} when it closes above its ${p.period}-day average. Sell the position when it closes below.`;
  if (type === "take_profit_stop_loss") sentence = `Sell all ${p.symbol} once the position is up ${p.take_profit_pct ?? "-"}% or down ${p.stop_loss_pct ?? "-"}%.`;
  $("#ruleSentence").textContent = sentence;
  $("#backtestBox").hidden = true;
}

function openStrategyBuilder(template = TEMPLATES[0]) {
  $("#strategyName").value = template.name;
  $("#ruleType").value = template.rule_type;
  renderRuleFields(template.params);
  $("#strategyError").hidden = true;
  $("#backtestBox").hidden = true;
  $("#aiBuilder").hidden = !state.aiEnabled;
  aiReply("");
  if (!$("#strategyDialog").open) $("#strategyDialog").showModal();
}

$("#addStrategyButton").addEventListener("click", () => openStrategyBuilder());
$("#templateRow").addEventListener("click", (event) => {
  const chip = event.target.closest("[data-template]");
  if (chip) openStrategyBuilder(TEMPLATES[Number(chip.dataset.template)]);
});
$("#ruleType").addEventListener("change", () => renderRuleFields());
$("#ruleFields").addEventListener("input", updateRuleSentence);
$("#ruleFields").addEventListener("change", updateRuleSentence);

$("#previewButton").addEventListener("click", async () => {
  const box = $("#backtestBox");
  const button = $("#previewButton");
  $("#strategyError").hidden = true;
  button.disabled = true;
  box.hidden = false;
  box.innerHTML = '<span class="backtest-loading">Replaying the last 90 market days...</span>';
  try {
    const result = await api("/api/strategies/backtest", { method: "POST", body: { rule_type: $("#ruleType").value, params: ruleParams(), days: 90 } });
    if (result.error) { box.textContent = result.error; return; }
    const trades = result.trades.slice(-4).reverse().map((trade) => `<li><span class="side-label ${trade.side.toLowerCase()}">${trade.side}</span> ${number.format(trade.quantity)} ${escapeHtml(trade.symbol)} at ${currency.format(trade.price)} <small>${shortDate(trade.date)}</small></li>`).join("");
    box.innerHTML = `<div class="backtest-stats">
        <div><span>Return</span><strong class="${tone(result.return_pct)}">${signed(result.return_pct)}</strong></div>
        <div><span>Worst dip</span><strong>${result.max_drawdown_pct.toFixed(2)}%</strong></div>
        <div><span>Trades</span><strong>${result.trades.length}</strong></div>
      </div>
      <canvas class="backtest-curve" id="backtestCurve"></canvas>
      <div class="backtest-range">${result.start ? `${shortDate(result.start)} to ${shortDate(result.end)} with ${shortCurrency.format(result.starting_cash)} paper cash` : ""}${result.rejected ? ` · ${result.rejected} signals skipped for cash or holdings` : ""}</div>
      ${result.buy_and_hold_pct != null ? `<div class="backtest-range">Buying and holding ${escapeHtml(result.buy_and_hold_symbol)} over the same days: <span class="${tone(result.buy_and_hold_pct)}">${signed(result.buy_and_hold_pct)}</span></div>` : ""}
      ${trades ? `<ul class="backtest-trades">${trades}</ul>` : '<div class="backtest-range">This rule would not have traded in this period.</div>'}
      ${state.aiEnabled ? '<button class="ai-explain-button" type="button" id="aiExplainButton"><i class="bi bi-stars"></i> Explain these results</button><div id="aiExplain"></div>' : ""}`;
    drawSparkline($("#backtestCurve"), result.equity_curve.map((point) => point.equity));
  } catch (error) {
    box.hidden = true;
    $("#strategyError").textContent = error.message;
    $("#strategyError").hidden = false;
  } finally {
    button.disabled = false;
  }
});

// ---------------------------------------------------------------- AI builder and coach

function aiReply(text, warn = false) {
  const reply = $("#aiReply");
  reply.textContent = text;
  reply.classList.toggle("warn", warn);
  reply.hidden = !text;
}

async function buildWithAi() {
  const text = $("#aiText").value.trim();
  if (text.length < 3) { aiReply("Describe the rule first, for example: buy 10 Infosys when it crosses its 50-day average.", true); return; }
  const button = $("#aiBuildButton");
  button.disabled = true;
  aiReply("Drafting your rule...");
  try {
    const draft = await api("/api/ai/strategy", { method: "POST", body: { text } });
    if (!draft.supported) {
      aiReply([draft.reply, draft.problem].filter(Boolean).join(" "), true);
      return;
    }
    $("#strategyName").value = draft.name || "My rule";
    $("#ruleType").value = draft.rule_type;
    renderRuleFields(draft.params);
    aiReply(`${draft.reply} Check the fields below; ${draft.remaining_today} AI requests left today.`);
    $("#previewButton").click();
  } catch (error) {
    aiReply(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function explainWithAi() {
  const button = $("#aiExplainButton");
  const target = $("#aiExplain");
  button.disabled = true;
  target.innerHTML = '<div class="ai-explain backtest-loading">Testing nearby settings and writing an explanation...</div>';
  try {
    const coach = await api("/api/ai/explain", { method: "POST", body: { rule_type: $("#ruleType").value, params: ruleParams(), days: 90 } });
    const rows = coach.variations.map((row) => `<tr><td>${escapeHtml(row.variant)}</td><td class="${tone(row.return_pct)}">${signed(row.return_pct)}</td><td>${row.max_drawdown_pct.toFixed(2)}%</td><td>${row.trades}</td></tr>`).join("");
    target.innerHTML = `<div class="ai-explain">
        <strong>${escapeHtml(coach.headline)}</strong>
        <ul>${coach.points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>
        <table class="ai-variations"><thead><tr><th>Setting</th><th>Return</th><th>Worst dip</th><th>Trades</th></tr></thead><tbody>${rows}</tbody></table>
        <p class="ai-caution"><i class="bi bi-info-circle"></i> ${escapeHtml(coach.caution)} Educational simulation, not investment advice.</p>
      </div>`;
    button.remove();
  } catch (error) {
    target.innerHTML = `<p class="dialog-error">${escapeHtml(error.message)}</p>`;
    button.disabled = false;
  }
}

$("#aiBuildButton").addEventListener("click", buildWithAi);
$("#aiText").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); buildWithAi(); }
});
$("#backtestBox").addEventListener("click", (event) => {
  if (event.target.closest("#aiExplainButton")) explainWithAi();
});

function drawSparkline(canvas, values) {
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || values.length < 2) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  context.beginPath();
  values.forEach((value, index) => {
    const px = (index / (values.length - 1)) * rect.width;
    const py = rect.height - 3 - ((value - min) / span) * (rect.height - 6);
    if (index) context.lineTo(px, py); else context.moveTo(px, py);
  });
  context.strokeStyle = values[values.length - 1] >= values[0] ? "#38845d" : "#be5149";
  context.lineWidth = 1.6;
  context.stroke();
}

$("#strategyForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const strategy = await api("/api/strategies", { method: "POST", body: { name: $("#strategyName").value.trim(), rule_type: $("#ruleType").value, params: ruleParams() } });
    $("#strategyDialog").close();
    showToast(`"${strategy.name}" is on. It starts trading from the next NSE close.`);
    await loadPrivate();
  } catch (error) {
    $("#strategyError").textContent = error.message;
    $("#strategyError").hidden = false;
  }
});

$("#strategyList").addEventListener("change", async (event) => {
  const id = event.target.dataset.strategyId;
  if (!id) return;
  try {
    const strategy = await api(`/api/strategies/${id}`, { method: "PATCH", body: { active: event.target.checked } });
    showToast(strategy.active ? `"${strategy.name}" switched on.` : `"${strategy.name}" paused.`);
  } catch (error) {
    showToast(error.message);
  }
  await loadPrivate();
});
$("#strategyList").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-strategy]");
  if (!button) return;
  const strategy = state.strategies.find((item) => item.id === button.dataset.deleteStrategy);
  if (!strategy || !window.confirm(`Delete "${strategy.name}"? Its past paper orders stay in your history.`)) return;
  await api(`/api/strategies/${strategy.id}`, { method: "DELETE" }).catch((error) => showToast(error.message));
  await loadPrivate();
});

// ---------------------------------------------------------------- profile

$("#profileButton").addEventListener("click", () => {
  if (!state.account) { showLogin(); return; }
  $("#profileNameInput").value = state.account.display_name;
  $("#profileHandleInput").value = state.account.handle;
  $("#profileError").hidden = true;
  $("#profileDialog").showModal();
});
$("#profileForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/me", { method: "PATCH", body: { display_name: $("#profileNameInput").value.trim(), handle: $("#profileHandleInput").value.trim() } });
    $("#profileDialog").close();
    await refreshAll();
  } catch (error) {
    $("#profileError").textContent = error.message;
    $("#profileError").hidden = false;
  }
});

// ---------------------------------------------------------------- shell

let toastTimeout;
function showToast(message) {
  const toast = $("#toastMessage");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove("visible"), 3200);
}

$("#refreshButton").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.classList.add("refreshing");
  await refreshAll();
  button.classList.remove("refreshing");
  showToast("Up to date with the latest NSE close.");
});
$$(".app-nav .nav-link").forEach((link) => link.addEventListener("click", () => {
  $$(".app-nav .nav-link").forEach((item) => item.classList.toggle("active", item === link));
}));
window.addEventListener("resize", drawChart);

function updateClock() {
  $("#currentTime").textContent = `${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date())} IST`;
}
$("#todayLabel").textContent = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata" }).format(new Date()).toUpperCase();
updateClock();
setInterval(updateClock, 30000);
// Prices change once a day and strategies fill after the evening job, so a light poll is enough.
setInterval(() => { if (document.visibilityState === "visible") refreshAll(); }, 60000);

// The terminal's RULE command links here with ?build=1 (and &ai=<idea>) to open the strategy builder.
let builderQueryHandled = false;
function openBuilderFromQuery() {
  const query = new URLSearchParams(window.location.search);
  if (builderQueryHandled || !query.has("build") || !state.account) return;
  builderQueryHandled = true;
  openStrategyBuilder();
  if (query.get("ai") && state.aiEnabled) {
    $("#aiText").value = query.get("ai");
    buildWithAi();
  }
}

setupAuth({ onSignedIn: () => refreshAll().then(openBuilderFromQuery) }).then(async (config) => {
  state.aiEnabled = Boolean(config?.ai_enabled);
  await refreshAll();
  openBuilderFromQuery();
}).catch((error) => {
  console.error(error);
  showToast("Could not reach the BBDFi server.");
});
