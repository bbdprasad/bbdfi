const quotes = [
  { symbol: "NIFTY 50", name: "NSE index", price: 25418.75, change: 0.68 },
  { symbol: "RELIANCE", name: "Reliance Industries", price: 1428.3, change: 1.24 },
  { symbol: "HDFCBANK", name: "HDFC Bank", price: 968.45, change: -0.37 },
  { symbol: "INFY", name: "Infosys", price: 1542.8, change: 0.91 },
  { symbol: "TCS", name: "Tata Consultancy", price: 3237.6, change: -0.22 },
  { symbol: "BANKNIFTY", name: "Nifty Bank", price: 57182.4, change: 0.42 },
];

const initialState = {
  cash: 1000000,
  positions: {},
  trades: [],
  strategies: [
    { id: "opening-range", title: "Opening range breakout", description: "Track a break above the first 15-minute high on Nifty 50.", active: true, icon: "bi-box-arrow-up-right" },
    { id: "mean-reversion", title: "Large-cap pullback", description: "Watch for a 1.5% pullback from the previous close.", active: false, icon: "bi-arrow-repeat" },
  ],
};

const storageKey = "basis-paper-mvp-v1";
let state = loadState();
let tradeSide = "BUY";
let toastTimeout;

const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const shortCurrency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved && typeof saved.cash === "number" && saved.positions && Array.isArray(saved.trades) && Array.isArray(saved.strategies)) return saved;
  } catch (error) {
    console.warn("Could not load the saved paper account.", error);
  }
  return structuredClone(initialState);
}

function saveState() {
  localStorage.setItem(storageKey, JSON.stringify(state));
}

function getQuote(symbol) {
  return quotes.find((quote) => quote.symbol === symbol);
}

function renderWatchlist(filter = "") {
  const list = document.querySelector("#watchlistList");
  const filtered = quotes.filter((quote) => `${quote.symbol} ${quote.name}`.toLowerCase().includes(filter.toLowerCase()));
  if (!filtered.length) {
    list.innerHTML = '<div class="empty-search">No matching instruments</div>';
    return;
  }
  list.innerHTML = filtered.map((quote) => {
    const direction = quote.change >= 0 ? "positive" : "negative";
    const sign = quote.change >= 0 ? "+" : "";
    return `<button class="watch-row" type="button" data-trade-symbol="${quote.symbol}" aria-label="Practice trade ${quote.symbol}">
      <span><span class="watch-symbol">${quote.symbol}</span><span class="watch-name d-block">${quote.name}</span></span>
      <span><span class="watch-price d-block">${number.format(quote.price)}</span><span class="watch-change d-block ${direction}">${sign}${quote.change.toFixed(2)}%</span></span>
    </button>`;
  }).join("");
}

function renderStrategies() {
  const activeCount = state.strategies.filter((strategy) => strategy.active).length;
  document.querySelector("#strategyCount").textContent = state.strategies.length;
  document.querySelector("#activeStrategyLabel").textContent = `${activeCount} active`;
  const list = document.querySelector("#strategyList");
  list.innerHTML = state.strategies.map((strategy) => `<div class="strategy-row">
    <span class="strategy-icon"><i class="bi ${strategy.icon}"></i></span>
    <div class="strategy-copy"><div class="strategy-title">${escapeHtml(strategy.title)}</div><div class="strategy-description">${escapeHtml(strategy.description)}</div></div>
    <input class="strategy-toggle" type="checkbox" role="switch" aria-label="${strategy.active ? "Disable" : "Enable"} ${escapeHtml(strategy.title)}" data-strategy-id="${strategy.id}" ${strategy.active ? "checked" : ""} />
  </div>`).join("");
}

function renderAccount() {
  const holdings = Object.entries(state.positions).filter(([, position]) => position.quantity > 0);
  const marketValue = holdings.reduce((total, [symbol, position]) => total + position.quantity * getQuote(symbol).price, 0);
  const unrealized = holdings.reduce((total, [symbol, position]) => total + position.quantity * (getQuote(symbol).price - position.averagePrice), 0);
  const equity = state.cash + marketValue;
  const totalReturn = ((equity / initialState.cash) - 1) * 100;
  document.querySelector("#equityValue").textContent = shortCurrency.format(equity);
  const returnElement = document.querySelector("#totalReturn");
  returnElement.innerHTML = `${totalReturn === 0 ? '<i class="bi bi-dash"></i> ' : totalReturn > 0 ? '<i class="bi bi-caret-up-fill"></i> ' : '<i class="bi bi-caret-down-fill"></i> '}${totalReturn > 0 ? "+" : ""}${totalReturn.toFixed(2)}%`;
  returnElement.className = `metric-neutral ${totalReturn > 0 ? "positive" : totalReturn < 0 ? "negative" : ""}`;
  document.querySelector("#pnlValue").textContent = currency.format(unrealized);
  document.querySelector("#pnlValue").className = `metric-value ${unrealized > 0 ? "positive" : unrealized < 0 ? "negative" : ""}`;
  const invested = holdings.reduce((total, [, position]) => total + position.quantity * position.averagePrice, 0);
  const pnlPercent = invested ? (unrealized / invested) * 100 : 0;
  document.querySelector("#pnlPercent").textContent = `${pnlPercent > 0 ? "+" : ""}${pnlPercent.toFixed(2)}%`;
  document.querySelector("#pnlPercent").className = `metric-neutral ${pnlPercent > 0 ? "positive" : pnlPercent < 0 ? "negative" : ""}`;
  document.querySelector("#buyingPowerValue").textContent = shortCurrency.format(state.cash);
  document.querySelector("#orderCount").textContent = state.trades.length;
  renderActivity();
}

function renderActivity() {
  const rows = document.querySelector("#activityRows");
  document.querySelector("#activityCount").textContent = `${state.trades.length} ${state.trades.length === 1 ? "order" : "orders"}`;
  if (!state.trades.length) {
    rows.innerHTML = '<tr><td class="empty-activity" colspan="6">No paper orders yet. Start with a small practice trade.</td></tr>';
    return;
  }
  rows.innerHTML = [...state.trades].reverse().slice(0, 10).map((trade) => `<tr>
    <td class="instrument-cell">${trade.symbol}</td>
    <td><span class="side-label ${trade.side.toLowerCase()}">${trade.side}</span></td>
    <td>${number.format(trade.quantity)}</td>
    <td>${currency.format(trade.price)}</td>
    <td>${new Date(trade.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</td>
    <td><span class="order-status"><i class="bi bi-check-circle-fill"></i> Paper filled</span></td>
  </tr>`).join("");
}

function renderAll() {
  renderWatchlist(document.querySelector("#watchlistSearch").value);
  renderStrategies();
  renderAccount();
  drawChart("1W");
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function showToast(message) {
  const toast = document.querySelector("#toastMessage");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove("visible"), 2800);
}

const chartSeries = {
  "1D": [34, 36, 32, 38, 35, 41, 39, 44, 40, 46, 43, 49, 47, 53, 50, 55, 52, 59, 56, 62, 60, 65, 62, 69, 65, 71, 68, 73],
  "1W": [30, 35, 33, 37, 31, 39, 42, 37, 44, 41, 47, 42, 49, 46, 51, 48, 55, 51, 57, 53, 61, 56, 63, 60, 68, 64, 70, 76, 72, 80, 77, 85],
  "1M": [28, 32, 30, 35, 33, 38, 34, 41, 37, 43, 39, 46, 44, 50, 47, 52, 49, 55, 51, 58, 55, 62, 58, 65, 60, 68, 64, 71, 68, 76, 72, 82],
  "1Y": [22, 27, 24, 29, 31, 28, 36, 33, 39, 35, 42, 39, 44, 48, 43, 51, 47, 54, 52, 58, 55, 63, 59, 66, 62, 71, 68, 74, 71, 80, 76, 86],
};

function drawChart(range) {
  const canvas = document.querySelector("#marketChart");
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const width = rect.width;
  const height = rect.height;
  const padding = { top: 10, right: 42, bottom: 9, left: 2 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = chartSeries[range];
  const min = Math.min(...values) - 12;
  const max = Math.max(...values) + 8;
  const x = (index) => padding.left + (index / (values.length - 1)) * plotWidth;
  const y = (value) => padding.top + ((max - value) / (max - min)) * plotHeight;

  context.clearRect(0, 0, width, height);
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
    const labelValue = max - ((max - min) * line) / 3;
    context.fillStyle = "#97a39c";
    context.textAlign = "right";
    context.fillText((25400 + (labelValue - 50) * 2).toFixed(0), width - 1, lineY);
  }

  context.beginPath();
  context.moveTo(x(0), y(values[0]));
  values.forEach((value, index) => context.lineTo(x(index), y(value)));
  context.lineTo(x(values.length - 1), height - padding.bottom);
  context.lineTo(x(0), height - padding.bottom);
  context.closePath();
  const fill = context.createLinearGradient(0, padding.top, 0, height);
  fill.addColorStop(0, "rgba(52, 133, 91, .16)");
  fill.addColorStop(1, "rgba(52, 133, 91, 0)");
  context.fillStyle = fill;
  context.fill();

  context.beginPath();
  values.forEach((value, index) => index ? context.lineTo(x(index), y(value)) : context.moveTo(x(index), y(value)));
  context.strokeStyle = "#38845d";
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();
  context.beginPath();
  context.arc(x(values.length - 1), y(values[values.length - 1]), 3.3, 0, Math.PI * 2);
  context.fillStyle = "#38845d";
  context.fill();
  context.beginPath();
  context.arc(x(values.length - 1), y(values[values.length - 1]), 6, 0, Math.PI * 2);
  context.strokeStyle = "rgba(56,132,93,.18)";
  context.lineWidth = 4;
  context.stroke();
}

const dialog = document.querySelector("#tradeDialog");
const symbolSelect = document.querySelector("#tradeSymbol");
const quantityInput = document.querySelector("#tradeQuantity");
const errorBox = document.querySelector("#tradeError");

function updateEstimate() {
  const quote = getQuote(symbolSelect.value);
  const quantity = Math.max(0, Number(quantityInput.value) || 0);
  document.querySelector("#tradeEstimate").textContent = quote ? currency.format(quote.price) : currency.format(0);
  document.querySelector("#orderValue").textContent = quote ? currency.format(quote.price * quantity) : currency.format(0);
  const button = document.querySelector("#submitTrade");
  button.textContent = `Review paper ${tradeSide.toLowerCase()}`;
  button.classList.toggle("sell-submit", tradeSide === "SELL");
  errorBox.hidden = true;
}

function openTrade(symbol = "RELIANCE") {
  symbolSelect.value = getQuote(symbol) ? symbol : "RELIANCE";
  tradeSide = "BUY";
  document.querySelectorAll(".side-button").forEach((button) => button.classList.toggle("selected", button.dataset.side === tradeSide));
  quantityInput.value = "1";
  updateEstimate();
  dialog.showModal();
}

quotes.forEach((quote) => {
  const option = document.createElement("option");
  option.value = quote.symbol;
  option.textContent = `${quote.symbol} · ${quote.name}`;
  symbolSelect.append(option);
});

document.querySelectorAll("[data-open-trade]").forEach((button) => button.addEventListener("click", () => openTrade()));
document.querySelectorAll("[data-close-trade]").forEach((button) => button.addEventListener("click", () => dialog.close()));
document.querySelectorAll(".side-button").forEach((button) => button.addEventListener("click", () => {
  tradeSide = button.dataset.side;
  document.querySelectorAll(".side-button").forEach((sideButton) => sideButton.classList.toggle("selected", sideButton === button));
  updateEstimate();
}));
symbolSelect.addEventListener("change", updateEstimate);
quantityInput.addEventListener("input", updateEstimate);

document.querySelector("#tradeForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const symbol = symbolSelect.value;
  const quote = getQuote(symbol);
  const quantity = Number(quantityInput.value);
  const position = state.positions[symbol] || { quantity: 0, averagePrice: 0 };
  const orderValue = quote.price * quantity;
  let error = "";

  if (!Number.isInteger(quantity) || quantity < 1) error = "Enter a whole-number quantity of at least 1.";
  else if (tradeSide === "BUY" && orderValue > state.cash) error = "Not enough paper funds for this order.";
  else if (tradeSide === "SELL" && quantity > position.quantity) error = `You only hold ${number.format(position.quantity)} ${symbol} in this paper account.`;

  if (error) {
    errorBox.textContent = error;
    errorBox.hidden = false;
    return;
  }

  if (tradeSide === "BUY") {
    const nextQuantity = position.quantity + quantity;
    position.averagePrice = ((position.quantity * position.averagePrice) + orderValue) / nextQuantity;
    position.quantity = nextQuantity;
    state.cash -= orderValue;
    state.positions[symbol] = position;
  } else {
    position.quantity -= quantity;
    state.cash += orderValue;
    if (position.quantity === 0) delete state.positions[symbol];
    else state.positions[symbol] = position;
  }

  state.trades.push({ id: crypto.randomUUID(), symbol, side: tradeSide, quantity, price: quote.price, timestamp: new Date().toISOString() });
  saveState();
  renderAccount();
  dialog.close();
  showToast(`${tradeSide === "BUY" ? "Bought" : "Sold"} ${number.format(quantity)} ${symbol} in paper mode.`);
});

document.querySelector("#watchlistList").addEventListener("click", (event) => {
  const button = event.target.closest("[data-trade-symbol]");
  if (button) openTrade(button.dataset.tradeSymbol);
});
document.querySelector("#watchlistSearch").addEventListener("input", (event) => renderWatchlist(event.target.value));
document.querySelector("#watchlistSearchButton").addEventListener("click", () => document.querySelector("#watchlistSearch").focus());
document.querySelector("#strategyList").addEventListener("change", (event) => {
  const id = event.target.dataset.strategyId;
  if (!id) return;
  const strategy = state.strategies.find((item) => item.id === id);
  if (!strategy) return;
  strategy.active = event.target.checked;
  saveState();
  renderStrategies();
});
document.querySelector("#addStrategyButton").addEventListener("click", () => {
  if (state.strategies.some((strategy) => strategy.id === "nifty-pullback")) {
    showToast("Your sample rule is already in the list.");
    return;
  }
  state.strategies.push({ id: "nifty-pullback", title: "Nifty pullback watch", description: "Practice tracking a 1.5% dip from the previous close.", active: false, icon: "bi-graph-down-arrow" });
  saveState();
  renderStrategies();
  showToast("Sample rule added. Switch it on to track it in practice mode.");
});
document.querySelector(".range-switch").addEventListener("click", (event) => {
  const button = event.target.closest("[data-range]");
  if (!button) return;
  document.querySelectorAll("[data-range]").forEach((item) => item.classList.toggle("selected", item === button));
  const labels = { "1D": ["09:15", "12:00", "15:30"], "1W": ["Mon, Sep 21", "Wed, Sep 23", "Fri, Sep 25"], "1M": ["Aug 31", "Sep 11", "Sep 25"], "1Y": ["Sep '25", "Mar '26", "Sep '26"] };
  ["#chartStart", "#chartMid", "#chartEnd"].forEach((selector, index) => document.querySelector(selector).textContent = labels[button.dataset.range][index]);
  drawChart(button.dataset.range);
});
document.querySelector("#refreshButton").addEventListener("click", (event) => {
  event.currentTarget.classList.add("refreshing");
  drawChart(document.querySelector(".range-switch .selected").dataset.range);
  setTimeout(() => event.currentTarget.classList.remove("refreshing"), 400);
  showToast("Paper account is up to date.");
});
document.querySelectorAll(".app-nav .nav-link").forEach((link) => link.addEventListener("click", () => {
  document.querySelectorAll(".app-nav .nav-link").forEach((item) => item.classList.toggle("active", item === link));
}));
window.addEventListener("resize", () => drawChart(document.querySelector(".range-switch .selected").dataset.range));

function updateClock() {
  document.querySelector("#currentTime").textContent = `${new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date())} IST`;
}

document.querySelector("#todayLabel").textContent = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date()).toUpperCase();
updateClock();
setInterval(updateClock, 60000);
renderAll();