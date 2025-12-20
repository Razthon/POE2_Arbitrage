import requests
import itertools
from datetime import datetime, timezone
from decimal import Decimal

# ==========================
# CONFIG / CURRENCY IDS
# ==========================

# These are the IDs of the currencies in the game.
EXALTED   = 290
DIVINE    = 291
CHAOS     = 287
CHANCE    = 285
ANNULMENT = 292
PERFECT_CHAOS = 4277
PERFECT_EXALTED = 4285


CURRENCY_NAMES = {
    EXALTED: "Exalted",
    DIVINE: "Divine",
    CHAOS: "Chaos",
    CHANCE: "Chance",
    ANNULMENT: "Annulment",
    PERFECT_CHAOS: "PChaos",
    PERFECT_EXALTED: "PExalted"
}

CURRENCIES = [
    EXALTED,
    DIVINE,
    CHAOS,
    CHANCE,
    ANNULMENT,
    PERFECT_CHAOS,
    PERFECT_EXALTED
]

# SELECT WHICH CURRENCIES YOU WANT TO START WITH
STARTING_CURRENCIES = [
    EXALTED,
    DIVINE,
    CHAOS,
    CHANCE,
    ANNULMENT,
    PERFECT_CHAOS,
    PERFECT_EXALTED
]


MIN_CYCLE_VOLUME = 500     # adjust freely (e.g. 500, 1000, 5000)
SHOW_LOW_LIQUIDITY = False   # show filtered cycles in a separate table

BASE_URL = "https://poe2scout.com/api/currencyExchange/PairHistory"

# ==========================
# API / DATA HELPERS
# ==========================

def get_pair_history(c1_id, c2_id, league="Fate of the Vaal", limit=3):
    params = {
        "league": league,
        "currencyOneItemId": c1_id,
        "currencyTwoItemId": c2_id,
        "limit": limit
    }
    r = requests.get(BASE_URL, params=params)
    r.raise_for_status()
    return r.json()

def extract_rates(history_json):
    rates = []
    for entry in history_json.get("History", []):
        d = entry["Data"]
        c1 = d["CurrencyOneData"]
        c2 = d["CurrencyTwoData"]

        p1 = Decimal(c1["RelativePrice"])
        p2 = Decimal(c2["RelativePrice"])

        rates.append({
            "epoch": entry["Epoch"],
            "c1_id": c1["CurrencyItemId"],
            "c2_id": c2["CurrencyItemId"],
            "c1_to_c2": float(p2 / p1),
            "c2_to_c1": float(p1 / p2),
            "volume_c1": c1["VolumeTraded"],
            "volume_c2": c2["VolumeTraded"]
        })
    return rates

def epoch_to_time(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ==========================
# DISPLAY FUNCTIONS
# ==========================

def print_rates_table(rates, c1_name, c2_name):
    if not rates:
        return

    time_w, rate_w, vol_w = 20, 12, 12

    header = (
        f"{'Time':<{time_w}} | "
        f"{c1_name+'→'+c2_name:>{rate_w}} | "
        f"{c2_name+'→'+c1_name:>{rate_w}} | "
        f"{'Vol '+c1_name:>{vol_w}} | "
        f"{'Vol '+c2_name:>{vol_w}}"
    )

    print(header)
    print("-" * len(header))

    for r in rates:
        print(
            f"{epoch_to_time(r['epoch']):<{time_w}} | "
            f"{r['c1_to_c2']:>{rate_w}.6f} | "
            f"{r['c2_to_c1']:>{rate_w}.6f} | "
            f"{r['volume_c1']:>{vol_w}} | "
            f"{r['volume_c2']:>{vol_w}}"
        )

# ==========================
# ARBITRAGE LOGIC
# ==========================

def normalize_cycle(cycle):
    c = list(cycle[:-1])
    i = c.index(min(c))
    c = c[i:] + c[:i]
    c.append(c[0])
    return tuple(c)

def rotate_cycle_to_start(cycle, start_currency):
    c = list(cycle[:-1])
    if start_currency not in c:
        return None

    i = c.index(start_currency)
    rotated = c[i:] + c[:i]
    rotated.append(rotated[0])
    return tuple(rotated)

def scan_all_cycles(graph, currencies):
    cycles = {}

    for c1, c2, c3 in itertools.permutations(currencies, 3):
        try:
            e1 = graph[c1][c2]
            e2 = graph[c2][c3]
            e3 = graph[c3][c1]
        except KeyError:
            continue

        r1, r2, r3 = e1["rate"], e2["rate"], e3["rate"]
        v1, v2, v3 = e1["volume"], e2["volume"], e3["volume"]

        multiplier = r1 * r2 * r3
        min_volume = min(v1, v2, v3)

        raw = (c1, c2, c3, c1)
        norm = normalize_cycle(raw)

        if norm not in cycles:
            cycles[norm] = {
                "rates": (r1, r2, r3),
                "multiplier": multiplier,
                "min_volume": min_volume
            }

    return cycles


def _print_cycle_row(cycle, data, starting_currencies):
    for start in starting_currencies or []:
        rotated = rotate_cycle_to_start(cycle, start)
        if not rotated:
            continue

        c1, c2, c3, _ = rotated
        r1, r2, r3 = data["rates"]
        m = data["multiplier"]
        v = data["min_volume"]

        status = (
            "PROFITABLE" if m > 1.001 else
            "LOSS" if m < 0.999 else
            "NEUTRAL"
        )

        name = (
            f"{CURRENCY_NAMES[c1]} → "
            f"{CURRENCY_NAMES[c2]} → "
            f"{CURRENCY_NAMES[c3]} → "
            f"{CURRENCY_NAMES[c1]}"
        )

        print(
            f"{name:<50} | "
            f"{r1:>10.6f} | "
            f"{r2:>10.6f} | "
            f"{r3:>10.6f} | "
            f"{m:>12.6f} | "
            f"{v:>8} | {status}"
        )
        break

def print_all_cycles_table(cycles, starting_currencies=None):
    print("\n=== 3-CURRENCY ARBITRAGE (LIQUIDITY FILTERED) ===")

    header = (
        f"{'Cycle':<50} | "
        f"{'Rate 1':>10} | "
        f"{'Rate 2':>10} | "
        f"{'Rate 3':>10} | "
        f"{'Multiplier':>12} | "
        f"{'Min Vol':>8} | Status"
    )
    print(header)
    print("-" * len(header))

    low_liquidity = []

    for cycle, data in sorted(
        cycles.items(),
        key=lambda x: x[1]["multiplier"],
        reverse=True
    ):
        if data["min_volume"] < MIN_CYCLE_VOLUME:
            low_liquidity.append((cycle, data))
            continue

        _print_cycle_row(cycle, data, starting_currencies)

    if SHOW_LOW_LIQUIDITY and low_liquidity:
        print("\n=== LOW LIQUIDITY CYCLES (FILTERED OUT) ===")
        print(header)
        print("-" * len(header))

        for cycle, data in low_liquidity:
            _print_cycle_row(cycle, data, starting_currencies)




def analyze_cycles_by_start(cycles, starting_currencies):
    """
    For each starting currency, find all usable cycles,
    rotated to start with that currency.
    """
    results = {c: [] for c in starting_currencies}

    for cycle, data in cycles.items():
        for start in starting_currencies:
            rotated = rotate_cycle_to_start(cycle, start)
            if not rotated:
                continue

            results[start].append({
                "cycle": rotated,
                "rates": data["rates"],
                "multiplier": data["multiplier"]
            })

    # Sort best → worst per starting currency
    for start in results:
        results[start].sort(
            key=lambda x: x["multiplier"],
            reverse=True
        )

    return results


def print_best_cycles_by_start(results, top_n=5):
    for start_currency, cycles in results.items():
        print(f"\n=== BEST CYCLES STARTING WITH {CURRENCY_NAMES[start_currency]} ===")

        header = (
            f"{'Cycle':<50} | "
            f"{'Rate 1':>10} | "
            f"{'Rate 2':>10} | "
            f"{'Rate 3':>10} | "
            f"{'Multiplier':>12} | Status"
        )
        print(header)
        print("-" * len(header))

        for entry in cycles[:top_n]:
            c1, c2, c3, _ = entry["cycle"]
            r1, r2, r3 = entry["rates"]
            m = entry["multiplier"]

            status = (
                "PROFITABLE" if m > 1.001 else
                "LOSS" if m < 0.999 else
                "NEUTRAL"
            )

            name = (
                f"{CURRENCY_NAMES[c1]} → "
                f"{CURRENCY_NAMES[c2]} → "
                f"{CURRENCY_NAMES[c3]} → "
                f"{CURRENCY_NAMES[c1]}"
            )

            print(
                f"{name:<50} | "
                f"{r1:>10.6f} | "
                f"{r2:>10.6f} | "
                f"{r3:>10.6f} | "
                f"{m:>12.6f} | {status}"
            )

# ==========================
# MAIN PROGRAM
# ==========================

all_rates = {}

for c1, c2 in itertools.permutations(CURRENCIES, 2):
    try:
        history = get_pair_history(c1, c2)
        rates = extract_rates(history)
        if rates:
            all_rates[(c1, c2)] = rates
    except Exception:
        continue

for (c1, c2), rates in all_rates.items():
    print(f"\n=== {CURRENCY_NAMES[c1]} ↔ {CURRENCY_NAMES[c2]} ===")
    print_rates_table(rates, CURRENCY_NAMES[c1], CURRENCY_NAMES[c2])

graph = {}

for (c1, c2), rates in all_rates.items():
    latest = rates[0]

    graph.setdefault(c1, {})[c2] = {
        "rate": latest["c1_to_c2"],
        "volume": latest["volume_c1"]
    }

    graph.setdefault(c2, {})[c1] = {
        "rate": latest["c2_to_c1"],
        "volume": latest["volume_c2"]
    }

cycles = scan_all_cycles(graph, CURRENCIES)

# Existing table (optional to keep)
print_all_cycles_table(cycles, STARTING_CURRENCIES)

# New: analyze by starting currency
cycle_analysis = analyze_cycles_by_start(cycles, STARTING_CURRENCIES)

# New: show best cycles per start
print_best_cycles_by_start(cycle_analysis, top_n=5)