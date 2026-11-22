/* Plain-English explanations for every label on the page.
   Each matching label gets a small ⓘ; hover, focus or tap it to read.
   Labels are matched by their visible text, so new rows (e.g. the Greeks
   table, which is re-rendered) pick up their explanation automatically. */

const GLOSSARY = {
  // ---- Inputs strip
  'symbol': 'The stock or index the option is on.',
  'spot price (s)': 'Current price of the stock or index, pulled live from NSE.',
  'strike (k)': 'The price at which the option lets you buy (call) or sell (put) the underlying at expiry.',
  'days to expiry': 'Calendar days until the contract expires, counting expiry day.',
  'risk-free rate (r)': 'Interest you could earn with no risk (roughly the Indian T-bill yield). Slightly raises call values and lowers put values.',
  'volatility σ': 'How much the price is expected to swing in a year. Higher volatility makes every option more expensive. Defaults to NSE’s implied volatility for this contract.',
  'dividend yield (q)': 'Yearly dividends as a % of the price. Dividends lower call values and raise put values. Usually 0 for indices.',
  'market premium (ltp)': 'Last traded price of this option on NSE — what you would roughly pay to buy one unit.',

  // ---- Card titles
  'black-scholes price': 'The classic formula for a fair option price, given spot, strike, time, interest rate and volatility.',
  'greeks': 'How sensitive the option price is to each input. Each Greek answers a “what if X changes?” question.',
  'crr binomial (150 steps)': 'A second pricing method that models the price moving up or down in 150 small steps. Can also value early exercise (American style).',
  'monte carlo': 'A third pricing method: simulate thousands of possible future prices and average the payoffs.',
  'implied volatility': 'The volatility the market is “using”, worked out backwards from the option’s market price.',
  'contract': 'The exact option being analysed.',
  'probability analysis': 'How likely different outcomes are, according to the model (risk-neutral, so treat as rough guides, not forecasts).',
  'live market data (nse)': 'Raw quote data for this contract straight from NSE.',
  'instrument snapshot': 'Reference details for the selected stock or index.',
  'put-call parity check': 'A sanity check: for the same strike and expiry, call − put must equal spot − discounted strike. A deviation near 0 means the maths is consistent.',
  'scenario p&l': 'Your profit or loss if you buy now and the price moves by the % shown, after the time shown.',
  'option chain': 'Every strike for this expiry, calls on the left and puts on the right. Click a row to analyse it.',
  'payoff diagram at expiry': 'What the option is worth on expiry day for each possible final price.',
  'option price vs. spot price': 'How the option price changes today as the underlying price changes.',
  'option price vs. volatility': 'How the option price changes as volatility rises or falls.',
  'time decay to expiry': 'How the option loses value as days pass, if nothing else changes. Decay speeds up near expiry.',
  'delta & gamma vs. spot': 'How delta (price sensitivity) and gamma (how fast delta changes) vary with the underlying price.',
  'monte carlo terminal price distribution': 'Where the simulated prices ended up on expiry day. The highlighted bar contains the strike.',
  'implied volatility smile': 'Implied volatility at each strike. Usually higher for far-away strikes, especially downside puts.',

  // ---- Suggestion panel
  'suggested entry price': 'A price at or below which the model thinks buying is reasonable.',
  'model fair value': 'What the Black-Scholes model says this option should cost.',
  'mispricing': 'How far the market price is from model fair value. Negative = cheaper than the model.',
  'implied vol (solved)': 'Volatility implied by the market price. Compare it with the volatility you assumed.',
  'breakeven at expiry': 'The underlying price at expiry where you neither make nor lose money (strike ± premium).',
  'theta decay / day': 'How much value the option loses per day just from time passing.',
  '5-day decay cost': 'Time decay over the next five days if nothing else changes.',

  // ---- Black-Scholes card
  'call': 'Right to BUY at the strike. Gains when the price rises.',
  'put': 'Right to SELL at the strike. Gains when the price falls.',
  'd1': 'An intermediate value in the Black-Scholes formula. Larger d1 = call more likely to finish in the money.',
  'd2': 'Another intermediate value. N(d2) is the model probability a call finishes in the money.',
  'n(d1) / n(d2)': 'N(d1) ≈ call delta; N(d2) ≈ chance the call finishes in the money (risk-neutral).',

  // ---- Greeks table
  'delta': 'How much the option price moves when the underlying moves ₹1. 0.5 means ₹0.50 per ₹1. Also a rough chance of finishing in the money.',
  'gamma': 'How fast delta changes when the underlying moves ₹1. High gamma = your exposure changes quickly.',
  'vega (per 1% iv)': 'Change in option price if volatility rises by 1 percentage point.',
  'theta (per day)': 'Change in option price per day from time passing. Negative for buyers — time works against you.',
  'rho (per 1% rate)': 'Change in option price if interest rates rise by 1 percentage point. Usually small.',
  'vanna (δ per 1% iv)': 'How much delta changes if volatility rises 1 point.',
  'vomma (vega per 1% iv)': 'How much vega changes if volatility rises 1 point — how “curved” the price is in volatility.',
  'charm (δ change per day)': 'How much delta drifts each day just from time passing.',

  // ---- CRR / Monte Carlo
  'european (matches bs)': 'Binomial-tree price for an option exercised only at expiry. Should be very close to Black-Scholes.',
  'american (early exercise)': 'Binomial-tree price if the option could be exercised any day. NSE stock and index options are European, so this is for comparison.',
  'early-exercise premium': 'Extra value from being allowed to exercise early (American minus European).',
  'simulated price': 'Average discounted payoff across all simulated paths.',
  'std. error': 'How uncertain the simulated price is. Smaller is more precise.',
  '95% ci': 'Range that should contain the true model price 95% of the time.',
  'vs. black-scholes': 'Difference between the simulated price and the Black-Scholes price. Should be within a couple of standard errors.',

  // ---- Implied volatility card
  'model σ (used)': 'The volatility actually used in the calculations above.',
  'solved from ltp': 'Volatility implied by the last traded price.',
  'nse-reported iv': 'Implied volatility as published by NSE.',
  'solved − model': 'Implied volatility minus the volatility used. Positive = the market is pricing more risk than you assumed.',

  // ---- Contract card
  'expiry': 'The date the contract expires and settles.',
  'strike': 'The contract’s strike price.',
  'type': 'CALL (right to buy) or PUT (right to sell).',

  // ---- Probability card
  'p(itm at expiry)': 'Model chance the option finishes in the money (worth something) on expiry day.',
  'p(profit at expiry, long)': 'Model chance a buyer ends up with a profit at expiry, after paying the premium.',
  'p(touch strike before expiry)': 'Approximate chance the price touches the strike at some point before expiry.',
  'breakeven move needed': 'How far the underlying must move by expiry for a buyer to break even.',
  'expected move (±1σ)': 'Typical size of the move by expiry implied by volatility (about two-thirds of outcomes fall inside it).',
  '1σ range at expiry': 'Price range the model expects about two-thirds of the time on expiry day.',
  'model edge per lot': '(Model value − market price) × lot size. Positive means the model thinks you’re buying below fair value.',

  // ---- Live market data card
  'last traded price': 'Price of the most recent trade in this contract.',
  'nse implied vol': 'NSE’s implied volatility for this contract.',
  'open interest': 'Number of contracts currently open (not yet closed). Higher = more participation.',
  'volume': 'Contracts traded today.',
  'bid / ask': 'Best price buyers will pay / sellers will accept right now.',
  'mid / spread': 'Midpoint of bid and ask, and the gap between them. A small spread is cheaper to trade.',
  'liquidity': 'How easy it is to trade near a fair price, based on the spread and activity.',
  'change in oi': 'Change in open interest today. Rising OI = new positions being opened.',
  'iv from mid': 'Implied volatility using the bid-ask midpoint, often more reliable than the last trade.',
  'fetched at': 'When this data was pulled from NSE.',

  // ---- Snapshot / parity
  'sector': 'Industry the company belongs to.',
  'lot size': 'Units per contract. NSE options trade in whole lots, so multiply per-unit prices by this.',
  'contract type': 'European options can only be exercised at expiry; American can be exercised any day.',
  'c − p': 'Call price minus put price.',
  'se⁻ᵠᵀ − ke⁻ʳᵀ': 'Spot (less dividends) minus the strike discounted to today. Must equal C − P.',
  'deviation': 'Gap between the two sides of put-call parity. Should be ~0.',

  // ---- Option chain headers
  'oi': 'Open interest — contracts currently open at this strike.',
  'chg oi': 'Change in open interest today.',
  'iv': 'Implied volatility (%) at this strike.',
  'ltp': 'Last traded price.',

  // ---- Monte Carlo Lab
  'monte carlo lab': 'Prices the same option by simulating thousands of possible futures, with models that drop Black-Scholes’ simplifying assumptions, and compares them with the formula and the market price.',
  'paths': 'How many possible futures to simulate. More paths give a more precise price but take longer (4× the paths halves the error).',
  'run with every analysis': 'Re-run the simulation automatically after every Fetch Live or Recalc Local.',
  'repeatable (fixed seed)': 'Use the same random numbers every run, so the same inputs always give exactly the same result.',
  'model settings': 'Fine-tune the Heston and jump models. Leave a box blank to use its default, or press “Use calibrated settings” to fill them from today’s market.',
  'black-scholes (formula)': 'The closed-form price: one constant volatility and smooth, bell-curve returns. The yardstick every model is compared with.',
  'monte carlo (constant vol)': 'Black-Scholes’ own assumptions, priced by simulation instead of the formula. It should agree with Black-Scholes — a check that the simulation works.',
  'heston (stochastic vol)': 'Volatility itself moves randomly and tends to rise when prices fall, so big downside moves are likelier than Black-Scholes assumes — matching the “skew” in real option prices.',
  'merton (jumps)': 'Adds sudden price gaps (results, budget day, global shocks) on top of normal moves. Makes far-from-the-money and short-dated options worth more.',
  'american (early exercise)': 'What the option would be worth if it could be exercised on any day before expiry. NSE options are European (expiry only); this shows what that right would add.',
  'market (ltp)': 'The option’s last traded price on NSE — what the models are trying to explain.',
  'convergence: the estimate settles as paths are added': 'How the simulated price homes in as more futures are added. The shaded bands are 95% uncertainty; the lab’s variance reduction makes its band far narrower than plain Monte Carlo.',
  'simulated futures: where the price could go': 'A fan of simulated price paths up to expiry: the middle 50% and 90% of outcomes, the median path and the strike.',
  'fit to today’s market': 'Each model’s settings tuned so its prices match today’s option chain for this expiry as closely as possible. A lower miss means the model explains the market better.',
  "fit to today's market": 'Each model’s settings tuned so its prices match today’s option chain for this expiry as closely as possible. A lower miss means the model explains the market better.',
  'model': 'The pricing model fitted to today’s market. Black-Scholes uses one volatility for every strike; Heston and Merton can bend to the smile.',
  'avg miss': 'Typical gap between the model’s prices and the market’s across all strikes, in implied-volatility points (1 point = 1% volatility).',
  'avg ₹ miss': 'The same typical gap measured in rupees per unit.',
  'starting vol %': 'Heston: today’s volatility. Blank = the volatility in the input strip.',
  'long-run vol %': 'Heston: the level volatility drifts back to over time.',
  'mean reversion κ': 'Heston: how quickly volatility returns to its long-run level. Higher = faster.',
  'vol of vol ξ': 'Heston: how much volatility itself swings. Higher = fatter tails and a stronger smile.',
  'correlation ρ': 'Heston: how price moves and volatility moves are linked. Negative (typical for stocks) means volatility rises when prices fall, making downside puts dearer.',
  'normal vol %': 'Merton: the everyday volatility between jumps. Blank = the volatility in the input strip.',
  'jumps per year': 'Merton: how many sudden gaps to expect in a year on average.',
  'average jump %': 'Merton: the typical size of a jump. Negative means sudden drops are likelier than sudden spikes.',
  'jump size spread %': 'Merton: how much jump sizes vary around the average.',
};

const TIP_SELECTORS = [
  '.card-head h3', '.mini-card h4', '.param label', '.data-row .k', '.mini-row .k', '.sug-row .k',
  '.price-box .pl', '.sug-price-block .lbl', 'table.greeks td:first-child', 'table.chain thead tr:nth-child(2) th',
  // Monte Carlo Lab (its model cards are re-rendered on every run; the observer below re-applies tips)
  '.mc-controls label', '.mc-settings summary', '.mc-settings-title', '.mc-settings-grid label',
  '.mc-model .name', '.mc-chart-title', '.mc-calib-table th',
].join(',');

// Visible label text, ignoring child elements such as the "% — NSE IV" unit hints.
function labelKey(el){
  let text = '';
  el.childNodes.forEach(n=>{ if(n.nodeType===Node.TEXT_NODE) text += n.textContent; });
  // Trailing separators come from titles followed by live text, e.g. "Fit to today's market · NIFTY ...".
  return text.replace(/\s+/g,' ').replace(/[\s·:—-]+$/,'').trim().toLowerCase();
}

function applyTips(root=document){
  root.querySelectorAll(TIP_SELECTORS).forEach(el=>{
    // Check for the icon itself rather than a flag: some labels (e.g. the
    // suggestion price label) are rewritten with textContent, which drops it.
    if(el.querySelector(':scope > .tip-i')) return;
    const tip = GLOSSARY[labelKey(el)];
    if(!tip) return;
    const i = document.createElement('span');
    i.className = 'tip-i';
    i.tabIndex = 0;
    i.setAttribute('role', 'button');
    i.setAttribute('aria-label', 'What does this mean?');
    i.dataset.tip = tip;
    i.textContent = 'i';
    el.appendChild(i);
  });
}

/* One floating bubble, positioned next to the hovered/focused/tapped ⓘ.
   (CSS-only tooltips get clipped by cards with overflow:hidden.) */
const tipBox = document.createElement('div');
tipBox.className = 'tip-box';
tipBox.setAttribute('role', 'tooltip');
document.body.appendChild(tipBox);
let tipAnchor = null;

function showTip(anchor){
  tipAnchor = anchor;
  tipBox.textContent = anchor.dataset.tip;
  tipBox.classList.add('show');
  const r = anchor.getBoundingClientRect();
  const w = tipBox.offsetWidth, h = tipBox.offsetHeight;
  let left = Math.min(Math.max(8, r.left + r.width/2 - w/2), window.innerWidth - w - 8);
  let top = r.top - h - 8;
  if(top < 8) top = r.bottom + 8;
  tipBox.style.left = left + 'px';
  tipBox.style.top = top + 'px';
}
function hideTip(){ tipAnchor = null; tipBox.classList.remove('show'); }

document.addEventListener('mouseover', (e)=>{ const i = e.target.closest('.tip-i'); if(i) showTip(i); });
document.addEventListener('mouseout', (e)=>{ if(e.target.closest('.tip-i')) hideTip(); });
document.addEventListener('focusin', (e)=>{ const i = e.target.closest('.tip-i'); if(i) showTip(i); });
document.addEventListener('focusout', (e)=>{ if(e.target.closest('.tip-i')) hideTip(); });
document.addEventListener('click', (e)=>{
  const i = e.target.closest('.tip-i');
  // Click/tap always opens (hover may already have); a click anywhere else closes.
  if(i){ e.stopPropagation(); e.preventDefault(); showTip(i); return; }
  hideTip();
}, true);
document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') hideTip(); });
window.addEventListener('scroll', hideTip, { passive:true });

applyTips();
// The Greeks table and option chain are re-rendered; label new rows as they appear.
new MutationObserver(()=> applyTips()).observe(document.querySelector('.layout'), { childList:true, subtree:true });
