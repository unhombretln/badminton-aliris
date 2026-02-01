import streamlit as st
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from collections import defaultdict
import random
import re

TZ = ZoneInfo("Europe/Tallinn")


# -------------------- Parsing --------------------
def parse_pairs(raw: str):
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    pairs = []
    for ln in lines:
        ln = re.sub(r"\s+", " ", ln)
        pairs.append(ln)
    return pairs


# -------------------- Core scheduling --------------------
@dataclass(frozen=True)
class Match:
    a: int  # 0-based rank index
    b: int
    forced_repeat_early: bool = False  # repeat happened before tail window (only if unavoidable)


def canonical(a: int, b: int):
    return (a, b) if a < b else (b, a)


def gap(a: int, b: int) -> int:
    return abs(a - b)


def build_one_round(
    n_pairs: int,
    courts: int,
    used_counts: dict,
    round_index: int,
    rounds_total: int,
    max_gap: int,
    max_repeat_per_matchup: int,
    repeat_tail_rounds: int,
):
    """
    Returns: list[Match] of length == courts (or None if impossible)
    Strategy:
      - Always enforce max_gap.
      - Prefer no repeats unless we are in the tail window.
      - If not enough matches without repeats, allow repeats (still capped),
        but mark them as forced if this round is before tail.
    """

    allowed_total_per_matchup = 1 + max_repeat_per_matchup  # first match + repeats
    in_tail = round_index >= max(0, rounds_total - repeat_tail_rounds)

    # Stage A: repeats allowed only if in tail
    matches = try_build_round(
        n_pairs=n_pairs,
        courts=courts,
        used_counts=used_counts,
        max_gap=max_gap,
        allowed_total_per_matchup=allowed_total_per_matchup,
        allow_repeats=in_tail,
        mark_forced_repeat_early=False,
    )
    if matches is not None:
        return matches

    # Stage B: if not in tail and cannot fill without repeats, allow repeats (forced)
    if not in_tail:
        matches = try_build_round(
            n_pairs=n_pairs,
            courts=courts,
            used_counts=used_counts,
            max_gap=max_gap,
            allowed_total_per_matchup=allowed_total_per_matchup,
            allow_repeats=True,
            mark_forced_repeat_early=True,
        )
        if matches is not None:
            return matches

    # Impossible even with repeats
    return None


def try_build_round(
    n_pairs: int,
    courts: int,
    used_counts: dict,
    max_gap: int,
    allowed_total_per_matchup: int,
    allow_repeats: bool,
    mark_forced_repeat_early: bool,
    tries: int = 2000,
):
    """
    Greedy with randomized retries.
    Ensures:
      - no pair plays twice in the same round
      - max_gap always respected
      - repeat count capped
    """
    all_pairs = list(range(n_pairs))

    def eligible_opponents(a, remaining_set):
        opts = []
        for b in remaining_set:
            if b == a:
                continue
            if gap(a, b) > max_gap:
                continue
            key = canonical(a, b)
            cnt = used_counts.get(key, 0)
            if cnt == 0:
                opts.append((b, 0))  # 0 means fresh
            else:
                if allow_repeats and cnt < allowed_total_per_matchup:
                    opts.append((b, 1))  # 1 means repeat
        return opts

    best = None
    best_cost = None

    for _ in range(tries):
        remaining = set(all_pairs)
        matches = []
        cost = 0

        while len(matches) < courts:
            if len(remaining) < 2:
                break

            # Pick the "most constrained" player: fewest options
            # (helps avoid dead ends)
            candidates_a = list(remaining)
            random.shuffle(candidates_a)

            best_a = None
            best_a_opts = None
            best_a_len = None

            for a in candidates_a:
                opts = eligible_opponents(a, remaining - {a})
                if not opts:
                    continue
                if best_a_len is None or len(opts) < best_a_len:
                    best_a = a
                    best_a_opts = opts
                    best_a_len = len(opts)
                    if best_a_len == 1:
                        break

            if best_a is None:
                break

            a = best_a
            opts = best_a_opts

            # Choose opponent:
            # Prefer fresh matches; among them smallest gap.
            # If repeats exist, they get a penalty; still choose smallest gap.
            best_b = None
            best_local = None
            best_is_repeat = None

            for b, is_repeat in opts:
                local = gap(a, b) * 10
                if is_repeat:
                    local += 1000  # repeats are expensive
                if best_local is None or local < best_local:
                    best_local = local
                    best_b = b
                    best_is_repeat = is_repeat

            if best_b is None:
                break

            remaining.remove(a)
            remaining.remove(best_b)

            matches.append(
                Match(
                    a=a,
                    b=best_b,
                    forced_repeat_early=(mark_forced_repeat_early and best_is_repeat == 1),
                )
            )
            cost += best_local

        if len(matches) != courts:
            continue

        if best is None or cost < best_cost:
            best = matches
            best_cost = cost

        # Early exit if we found a round with zero repeats and low cost
        if best_cost is not None and best_cost <= courts * 10:
            break

    return best


def schedule_session(
    n_pairs: int,
    courts: int,
    rounds_requested: int,
    max_gap: int,
    max_repeat_per_matchup: int,
    repeat_tail_rounds: int,
):
    """
    Try to generate schedule for rounds_requested.
    If impossible, auto-reduce rounds until possible.

    Returns:
      rounds_actual, schedule(list[list[Match]]), used_counts, forced_early_repeats_count
    """
    for rounds_total in range(rounds_requested, 0, -1):
        used_counts = defaultdict(int)
        sched = []
        forced_early = 0
        ok = True

        for r in range(rounds_total):
            round_matches = build_one_round(
                n_pairs=n_pairs,
                courts=courts,
                used_counts=used_counts,
                round_index=r,
                rounds_total=rounds_total,
                max_gap=max_gap,
                max_repeat_per_matchup=max_repeat_per_matchup,
                repeat_tail_rounds=repeat_tail_rounds,
            )

            if round_matches is None:
                ok = False
                break

            # Commit matches into used_counts
            for m in round_matches:
                used_counts[canonical(m.a, m.b)] += 1
                if m.forced_repeat_early:
                    forced_early += 1

            sched.append(round_matches)

        if ok:
            return rounds_total, sched, used_counts, forced_early

    # If even 1 round impossible (should only happen with very strict gap and tiny n)
    return 0, [], defaultdict(int), 0


# -------------------- Formatting --------------------
def format_schedule(pairs, sched, start_dt, round_minutes, courts):
    lines = []
    for r, matches in enumerate(sched, start=1):
        t = start_dt + timedelta(minutes=round_minutes * (r - 1))
        lines.append(f"🏸 Tour {r} — {t.strftime('%Y-%m-%d %H:%M')} (Tallinn)")

        # deterministic output: sort by average rank
        matches_sorted = sorted(matches, key=lambda m: (m.a + m.b) / 2)

        for ci in range(courts):
            m = matches_sorted[ci]
            a_name = pairs[m.a]
            b_name = pairs[m.b]
            flag = " ⚠️(repeat)" if m.forced_repeat_early else ""
            lines.append(f"  Court {ci+1}: {a_name}  vs  {b_name}{flag}")

        lines.append("")

    return "\n".join(lines).strip()


# -------------------- UI --------------------
st.set_page_config(page_title="Badminton Scheduler", page_icon="🏸", layout="centered")

st.markdown(
    """
<style>
:root { --accent: #E6FF2A; }

body, .stApp {
  background-color: #0b0f14;
  color: #F2F6FF;
}

h1, h2, h3 {
  color: #F8FAFF;
}

/* inputs */
.stTextArea textarea, .stNumberInput input, .stTextInput input, .stSelectbox div {
  background: #111827 !important;
  color: #F2F6FF !important;
  border: 1px solid #243043 !important;
}

/* buttons */
.stButton button {
  background: var(--accent) !important;
  color: #0b0f14 !important;
  border: 0 !important;
  font-weight: 700 !important;
  border-radius: 10px !important;
}

/* captions */
small, .stCaption { color: #B8C6DA !important; }

hr { border-color: #243043; }

/* Make schedule output readable (text & code blocks) */
div[data-testid="stText"] pre {
  background-color: #0b0f14 !important;
  color: #F2F6FF !important;
  border: 1px solid #243043 !important;
  border-radius: 12px !important;
  padding: 14px !important;
}

div[data-testid="stCodeBlock"] pre {
  background-color: #0b0f14 !important;
  color: #F2F6FF !important;
  border: 1px solid #243043 !important;
  border-radius: 12px !important;
  padding: 14px !important;
}

div[data-testid="stCodeBlock"] code {
  color: #F2F6FF !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title('Бадминтон с "Aliris" 🏸')

st.caption("Честные матчи по рейтингу. Повторы — только когда иначе никак. В идеале — ближе к концу.")

raw = st.text_area(
    "Вставь рейтинг пар (1 строка = 1 пара, сверху сильнейшие):",
    height=200,
    placeholder="1) Maksim + Stas\n2) Oksana + Mikhail\n3) ...",
)

col1, col2, col3 = st.columns(3)
with col1:
    courts = st.number_input("Courts", min_value=1, max_value=20, value=3, step=1)
with col2:
    rounds = st.number_input("Rounds (requested)", min_value=1, max_value=30, value=8, step=1)
with col3:
    round_minutes = st.number_input("Minutes per round", min_value=10, max_value=90, value=15, step=5)

col4, col5 = st.columns(2)
with col4:
    start_time_str = st.text_input("Start time (Tallinn) HH:MM", value=datetime.now(TZ).strftime("%H:%M"))
with col5:
    max_gap = st.number_input("Max rank gap", min_value=1, max_value=50, value=4, step=1)

colA, colB, colC = st.columns(3)
with colA:
    max_repeat_per_matchup = st.number_input("Max repeats per matchup", min_value=0, max_value=3, value=1, step=1)
with colB:
    repeat_tail_rounds = st.number_input("Allow repeats only in last N rounds", min_value=1, max_value=10, value=2, step=1)
with colC:
    seed = st.number_input("Random seed (optional)", min_value=0, max_value=999999, value=0, step=1)

btn = st.button("Generate schedule")

if btn:
    pairs = parse_pairs(raw)
    if len(pairs) < 2:
        st.error("Нужно минимум 2 пары.")
    else:
        if seed != 0:
            random.seed(int(seed))

        # Parse start time
        try:
            hh, mm = start_time_str.strip().split(":")
            start_t = dtime(hour=int(hh), minute=int(mm))
        except Exception:
            start_t = datetime.now(TZ).time().replace(second=0, microsecond=0)

        start_dt = datetime.now(TZ).replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)

        rounds_actual, sched, used_counts, forced_early = schedule_session(
            n_pairs=len(pairs),
            courts=int(courts),
            rounds_requested=int(rounds),
            max_gap=int(max_gap),
            max_repeat_per_matchup=int(max_repeat_per_matchup),
            repeat_tail_rounds=int(repeat_tail_rounds),
        )

        if rounds_actual == 0:
            st.error("При текущих настройках невозможно собрать даже 1 тур. Увеличь Max rank gap или уменьшай courts.")
        else:
            if rounds_actual < int(rounds):
                st.warning(
                    f"Сделал {rounds_actual} тур(ов) вместо {int(rounds)}: "
                    "иначе пришлось бы нарушать ограничения (слишком большой разрыв/слишком много повторов)."
                )

            if forced_early > 0:
                st.warning(
                    f"⚠️ Вынужденные повторы ДО последних {int(repeat_tail_rounds)} туров: {forced_early}. "
                    "Это значит, что иначе нельзя было заполнить все корты, сохранив Max rank gap."
                )

            out = format_schedule(pairs, sched, start_dt, int(round_minutes), int(courts))

            st.subheader("Schedule")
            st.code(out, language=None)

            st.divider()
            st.subheader("Copy for WhatsApp/Telegram")
            st.text_area("Ready-to-copy text:", value=out, height=250)

            # Small stats
            total_matches = sum(len(rm) for rm in sched)
            unique_matchups = sum(1 for k, v in used_counts.items() if v > 0)
            repeats_total = sum(max(0, v - 1) for v in used_counts.values())

            st.caption(f"Matches: {total_matches} • Unique matchups: {unique_matchups} • Total repeats: {repeats_total}")
            st.caption("Подсказка: если хочешь меньше вынужденных повторов — чуть увеличь Max rank gap или уменьшай Rounds.")
