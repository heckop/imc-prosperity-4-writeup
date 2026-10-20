# prosperity-4

Writeup for IMC Prosperity 4 (2026). The game: every round you upload one Python file with a `Trader` class, it trades against a bunch of bots on a simulated exchange, and you get scored on how much money it made. There's a manual trading each round too, but that's not in here.

Everything is plain Python. The only import outside the standard library is `datamodel.py`, which is just the class definitions the platform gives you (`Order`, `OrderDepth`, `TradingState`...).

## Structure

```
trader_*.py         one file per submission / variant I tried
datamodel.py        platform classes
ROUND_3..5/         price + trade CSVs IMC released for those rounds
round5_v4_logs/     the log and file from one of my live round 5 runs
```

## Running it

I used the community backtester:

```
pip install -U prosperity4btx
prosperity4btx trader_round3.py 3        # all days of round 3
prosperity4btx trader_round3.py 3-0      # just day 0
```

The first time you run it, it downloads the round data into `.btx_data/`. That's just a cache, so it's gitignored.

## A few things that apply to every round

Before the round by round stuff, here's the basic pattern almost every file follows.

Each tick, for each product, I work out what I think the thing is actually worth (the "fair value"). Then I do two things:

1. **Take.** If someone in the order book is selling below fair, I buy from them right away. If someone is bidding above fair, I sell to them.
2. **Make.** Then I put my own buy order a bit below fair and my own sell order a bit above fair, and wait for bots to trade into them. Every time both sides get hit, I earn the gap.

The tricky part is inventory. If I keep getting filled on one side, I end up with a big long or short position. If price then moves against me, that eats all the small profits. So when my position gets big, I shift both quotes away from it. For example, if I'm long, I lower my buy price (so I buy less) and lower my sell price (so I sell more easily). This pushes me back toward flat without having to dump at a bad price.

The other thing to know: if the orders you send could push you past the position limit *in the worst case*, the exchange cancels **all** your orders for that product. So every script works out `limit - position` and `limit + position` first and never sends more than that.

The only memory between ticks is a string called `traderData`, so things like moving averages get stuffed in there as JSON.

---

## Tutorial: `trader_tutorial.py`

Two products to practice on.

**EMERALDS** just sat at 10,000 the whole time. No need to be clever: fair value is 10,000, buy anything offered at or below it, sell anything bid at or above it, and quote 9997 / 10003 the rest of the time (shifted as position builds).

**TOMATOES** wandered around, so a fixed number wouldn't work. I used an exponential moving average of the mid price as fair value, quoted ±2 around it, and leaned the quotes the same way as above once position got past ±15.

## Round 1: `trader_round1.py`, `trader_r1_tight.py`, `trader_r1_wide.py`

Basically the tutorial again with new names.

**ASH_COATED_OSMIUM** was the "emeralds" of this round, stuck around 10,000. Same fixed fair value, quotes at 9996 / 10004.

**INTARIAN_PEPPER_ROOT** moved around, so it got the moving average treatment again. This time it's a faster one (half old value, half new mid), so it keeps up with the price better.

The three files are identical apart from how far from fair I quote pepper root: ±3 in the main one, ±2 in `tight`, ±4 in `wide`. Tighter quotes get filled more often but earn less each time, wider ones earn more but get filled less. I didn't know which would win, so I ran all three.

## Round 2: `trader_r2_A_maxdrift.py`, `trader_r2_B_adaptive.py`, `trader_r2_C_neutral.py`

Same two products. Osmium didn't change, so its code is the same as round 1.

Pepper root, though, was clearly going up over the day in the data. Market making around a moving average is a bit dumb when price is trending, because the average is always behind and you keep selling too early. I wasn't sure how much to trust the trend, so I wrote three versions:

**A, "max drift".** Go all in on the trend. I assume price keeps rising at roughly 0.1 per tick, so the fair value is "where it'll be in 200 ticks", not where it is now. That makes the bot buy almost everything. It mostly sits on the bid one tick above the best bid and only sells if someone bids way above the current price. Near the end of the day it starts unloading, and right at the end it dumps whatever is left so it doesn't hold a position overnight.

**B, "adaptive".** Let the data decide. It keeps the last 300 mid prices, measures the slope, and compares that to how noisy the price has been recently. A steady climb means high confidence, so it aims to be very long. A noisy or flat market means it stays closer to zero. Quotes are centred on a projected price, not the current one, and nudged toward whatever position it's aiming for.

**C, "neutral".** Ignore the trend completely and just market make around a moving average like round 1. It tightens the quotes in the last stretch of the day to get flat. This was the safe fallback in case the trend didn't show up live.

## Round 3: `trader_round3.py`, `trader_round3_v3.py`

This is where it got more interesting. New products:

- **HYDROGEL_PACK**, a normal product hovering around 10,000
- **VELVETFRUIT_EXTRACT**, the "underlying", around 5,250
- **VEV_4000 ... VEV_6500**, call options on velvetfruit at different strikes

**Hydrogel** is the usual moving-average market making, quoting ±4 around fair.

**Options.** A call option's value is how far it's already in the money (the intrinsic value) plus some extra for the chance it goes further (the time value). I priced them with Black-Scholes. The annoying bit is that Black-Scholes needs both volatility and time to expiry, and we weren't told the time to expiry cleanly. So I fixed the volatility at a value that fit the data and worked *backwards* from the market price of the 5300 / 5400 strikes to get the time. That number is smoothed over time so one weird tick doesn't throw it off.

With a fair price for every option:

- If anyone is selling an option for less than its intrinsic value, buy it. That's an outright mistake by the bot.
- Skip market making on options with almost no time value left. There's nothing to earn there, it's all risk.
- Otherwise, take anything clearly mispriced vs. Black-Scholes and quote one tick either side of fair.
- Cap each option at 20 contracts so one strike can't blow up the book.

**Velvetfruit** is market made around its own moving average. The twist is that I also add up the total delta (how much the option book moves when velvetfruit moves). Then I lean my velvetfruit quotes to offset it. So if the options make me effectively long velvetfruit, the bot quotes to sell a bit more velvetfruit, and the other way round.

**v3** changes a few things:

- Hydrogel's limit drops to 40.
- The option cap goes up to 30.
- There's a simple trend filter on hydrogel. If price fell more than 6 over the last 3 ticks, it stops posting bids (don't catch a falling knife), and the same the other way round for asks.

## Round 4: `trader_round4.py`, `trader_round4_v2.py`

Same products as round 3. After staring at more data, the moving averages seemed to be causing more harm than good, because they kept chasing noise. So I switched to fixed levels:

- **Hydrogel:** buy at 9990 or below, sell at 10001 or above, quote at those levels.
- **Velvetfruit:** buy at 5245, sell at 5249.

The deep in-the-money options (**4000 and 4500**) basically move one for one with velvetfruit, so Black-Scholes is overkill. I just quote them 10 either side of intrinsic value. The rest of the options work like round 3.

**v2** relaxes the hydrogel part a bit:

- The 9995 centre is allowed to move very slowly with the market, but only within 9985–10010, so it can't run off.
- It can hold more long (50) than short (25).
- A stop loss: if I'm short and price has run 20 above the centre, stop selling more, and the same for longs. Basically, stop adding to a losing trade.

## Round 5: `trader_round5*.py`

Round 5 dumped a huge list of products on us: snack packs, galaxy sounds, UV visors, oxygen shakes, translators, sleep pods, pebbles... There wasn't time to study each one properly, so the goal was a single simple market maker that runs on all of them.

**`trader_round5.py`** sorts products into groups based on how they did in backtests. Better groups get a bigger position cap. Each product gets its own moving average, and the bot quotes a few ticks either side of it. Pebbles XL was jumpier than the other pebbles, so it gets wider quotes.

**`v2`** cuts down to just snack packs, galaxy sounds and UV visors with a small cap of 15. It throws away the moving average and quotes 3 either side of the current mid.

**`v3`** does that for every product, with cap 35 and edge 4.

**`v4`** is v3 with cap 10 and edge 5. The live logs showed the real position limit was 10, so there was no point pretending otherwise. This is the one in `round5_v4_logs/`.

**`v5`** is v4 with a small safety check. If a product moved more than 20 in the last 5 ticks, pull the quote on the side that would get run over. If price is crashing, don't bid. If it's spiking, don't offer.
