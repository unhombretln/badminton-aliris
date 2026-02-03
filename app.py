import streamlit as st
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import random
import re

# -------------------- Session State & Demo Logic --------------------
if "input_text_area" not in st.session_state:
    st.session_state.input_text_area = ""

def load_demo():
    names = [
        "Alex", "Jordan", "Casey", "Taylor", "Jamie", "Morgan", 
        "Riley", "Chris", "Pat", "Drew", "Avery", "Cameron", 
        "Quinn", "Kim", "Lee", "Sam", "Charlie", "Dakota", 
        "Reese", "Parker", "Skyler", "Sage", "River", "Phoenix"
    ]
    random.shuffle(names)
    demo_lines = [f"{i+1}. {names[i*2]} + {names[i*2+1]}" for i in range(8)]
    st.session_state.input_text_area = "\n".join(demo_lines)

# -------------------- Parsing --------------------
def parse_pairs(raw: str):
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return [re.sub(r"\s+", " ", ln) for ln in lines]

# -------------------- Core scheduling --------------------
@dataclass(frozen=True)
class Match:
    a: int
    b: int
    forced_repeat_early: bool = False

def canonical(a: int, b: int):
    return (a, b) if a < b else (b, a)

def gap(a: int, b: int) -> int:
    return abs(a - b)

def try_build_round(n_pairs, courts, used_counts, max_gap, allowed_total_per_matchup, allow_repeats, mark_forced_repeat_early, tries=2000):
    all_pairs = list(range(n_pairs))
    best, best_cost = None, None

    for _ in range(tries):
        remaining = set(all_pairs)
        matches, cost = [], 0
        while len(matches) < courts:
            if len(remaining) < 2: break
            c_a = list(remaining)
            random.shuffle(c_a)
            b_a, b_opts = None, None
            for a in c_a:
                opts = []
                for b in (remaining - {a}):
                    if gap(a, b) > max_gap: continue
                    key = canonical(a, b)
                    cnt = used_counts.get(key, 0)
                    if cnt == 0: opts.append((b, 0))
                    elif allow_repeats and cnt < allowed_total_per_matchup: opts.append((b, 1))
                if not opts: continue
                if b_a is None or len(opts) < len(b_opts): b_a, b_opts = a, opts
                if b_opts and len(b_opts) == 1: break
            if b_a is None: break
            random.shuffle(b_opts)
            b_b, b_is_rep = b_opts[0]
            remaining.remove(b_a); remaining.remove(b_b)
            matches.append(Match(b_a, b_b, mark_forced_repeat_early and b_is_rep == 1))
            cost += (1000 if b_is_rep else 0) + random.random()
        if len(matches) == courts:
            if best is None or cost < best_cost: best, best_cost = matches, cost
            if best_cost <= courts * 10: break
    return best

def schedule_session(n_pairs, courts, rounds_requested, max_gap, max_repeat_per_matchup, repeat_tail_rounds):
    for r_total in range(rounds_requested, 0, -1):
        used_counts, sched, ok = defaultdict(int), [], True
        for r in range(r_total):
            in_tail = r >= max(0, r_total - repeat_tail_rounds)
            m = try_build_round(n_pairs, courts, used_counts, max_gap, 1 + max_repeat_per_matchup, in_tail, False)
            if not m and not in_tail:
                m = try_build_round(n_pairs, courts, used_counts, max_gap, 1 + max_repeat_per_matchup, True, True)
            if not m: ok = False; break
            for match in m: used_counts[canonical(match.a, match.b)] += 1
            sched.append(m)
        if ok: return r_total, sched
    return 0, []

def format_schedule(pairs, sched, start_dt, round_minutes, courts):
    lines = []
    for r, matches in enumerate(sched, start=1):
        t = start_dt + timedelta(minutes=round_minutes * (r - 1))
        lines.append(f"🏸 Tour {r} — {t.strftime('%H:%M')}")
        for ci, m in enumerate(sorted(matches, key=lambda x: (x.a + x.b)/2)):
            warn = " ⚠️" if m.forced_repeat_early else ""
            lines.append(f"  Court {ci+1}: {pairs[m.a]} vs {pairs[m.b]}{warn}")
        lines.append("")
    return "\n".join(lines).strip()

# -------------------- UI --------------------
st.set_page_config(page_title="Shuttle Shuffle", page_icon="🏸")
st.markdown("""<style>
    :root { --accent: #E6FF2A; --bg: #0b0f14; --panel: #111827; }
    .stApp { background-color: var(--bg); color: #F2F6FF; }
    .stTextArea textarea { background: var(--panel) !important; color: white !important; }
    div.stButton > button:first-child { 
        background: var(--accent) !important; color: black !important; 
        font-weight: 800 !important; width: 100%; border-radius: 12px;
    }
</style>""", unsafe_allow_html=True)

st.title('Shuttle Shuffle 🏸')
st.caption('Badminton Game Scheduler')

col_in1, col_in2 = st.columns([3, 1])
with col_in2:
    st.write(""); st.write("")
    st.button("Load Demo", on_click=load_demo)
with col_in1:
    raw = st.text_area("Paste pair list (1 line = 1 pair). Sort by rank if applicable (1 = Strongest ↓):", 
                       height=150, key="input_text_area")

c1, c2, c3 = st.columns(3)
with c1: courts = st.number_input("Courts", 1, 20, 1)
with c2: rounds = st.number_input("Rounds", 1, 30, 1)
with c3: max_gap = st.number_input("Max Gap", 1, 50, 10)

with st.expander("⚙️ Advanced Settings"):
    round_minutes = st.number_input("Minutes per Round", 5, 60, 12)
    max_repeats = st.number_input("Max Repeats", 0, 5, 1)
    seed = st.number_input("Random Seed (0 = Random)", 0, 999999, 0)

if st.button("GENERATE SCHEDULE 🚀"):
    pairs = parse_pairs(raw)
    if len(pairs) < 2:
        st.error("Need more pairs!")
    else:
        if seed != 0: random.seed(int(seed))
        start_dt = datetime.now().replace(second=0, microsecond=0)
        
        with st.spinner("Processing..."):
            actual_r, sched = schedule_session(len(pairs), int(courts), int(rounds), int(max_gap), int(max_repeats), 2)
        
        if actual_r == 0:
            st.error("No solution found. Try increasing Max Gap.")
        else:
            st.success(f"Done! {actual_r} rounds.")
            t1, t2 = st.tabs(["Display", "Copy Text"])
            with t1:
                for idx, r_m in enumerate(sched):
                    t = start_dt + timedelta(minutes=int(round_minutes) * idx)
                    st.markdown(f"#### Tour {idx+1} ({t.strftime('%H:%M')})")
                    for m in r_m: st.info(f"{pairs[m.a]} vs {pairs[m.b]}")
            with t2:
                st.text_area("For Chat:", value=format_schedule(pairs, sched, start_dt, int(round_minutes), int(courts)), height=250)
