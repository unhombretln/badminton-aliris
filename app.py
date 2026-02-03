import streamlit as st
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from collections import defaultdict
import random
import re

TZ = ZoneInfo("Europe/Tallinn")

# -------------------- Custom Effects (Shuttle Rain) --------------------
def rain_shuttles():
    shuttles_html = ""
    for _ in range(25): 
        left = random.randint(1, 99)
        duration = random.uniform(3, 7) 
        delay = random.uniform(0, 2)
        size = random.uniform(1.2, 2.0) 
        opacity = random.uniform(0.3, 0.7) 
        
        shuttles_html += f"""
        <div style="
            position: fixed;
            left: {left}%;
            top: -10vh;
            font-size: {size}rem;
            opacity: {opacity};
            animation: fall {duration}s linear forwards;
            animation-delay: {delay}s;
            z-index: 9999;
            pointer-events: none;
        ">🏸</div>
        """
    
    st.markdown(f"""
    <style>
        @keyframes fall {{
            0% {{ transform: translateY(-10vh) rotate(0deg); }}
            100% {{ transform: translateY(110vh) rotate(360deg); }}
        }}
    </style>
    {shuttles_html}
    """, unsafe_allow_html=True)

# -------------------- Session State & Demo Logic --------------------
# Инициализируем состояние текстового поля, если его еще нет
if "input_text_area" not in st.session_state:
    st.session_state.input_text_area = ""

# Функция, которая обновляет напрямую ключ виджета
def load_demo():
    st.session_state.input_text_area = (
        "1. Maksim + Stas\n"
        "2. Oksana + Mikhail\n"
        "3. Maria + Alexey\n"
        "4. Alla + Ilya\n"
        "5. Maria + Andre\n"
        "6. Inna + Andrey\n"
        "7. Iris + Piyush\n"
        "8. Nika + Aulis"
    )

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
    a: int
    b: int
    forced_repeat_early: bool = False

def canonical(a: int, b: int):
    return (a, b) if a < b else (b, a)

def gap(a: int, b: int) -> int:
    return abs(a - b)

def build_one_round(n_pairs, courts, used_counts, round_index, rounds_total, max_gap, max_repeat_per_matchup, repeat_tail_rounds):
    allowed_total_per_matchup = 1 + max_repeat_per_matchup
    in_tail = round_index >= max(0, rounds_total - repeat_tail_rounds)

    matches = try_build_round(
        n_pairs, courts, used_counts, max_gap, allowed_total_per_matchup,
        allow_repeats=in_tail, mark_forced_repeat_early=False
    )
    if matches: return matches

    if not in_tail:
        matches = try_build_round(
            n_pairs, courts, used_counts, max_gap, allowed_total_per_matchup,
            allow_repeats=True, mark_forced_repeat_early=True
        )
        if matches: return matches

    return None

def try_build_round(n_pairs, courts, used_counts, max_gap, allowed_total_per_matchup, allow_repeats, mark_forced_repeat_early, tries=2000):
    all_pairs = list(range(n_pairs))

    def eligible_opponents(a, remaining_set):
        opts = []
        for b in remaining_set:
            if b == a: continue
            if gap(a, b) > max_gap: continue
            key = canonical(a, b)
            cnt = used_counts.get(key, 0)
            if cnt == 0:
                opts.append((b, 0))
            elif allow_repeats and cnt < allowed_total_per_matchup:
                opts.append((b, 1))
        return opts

    best, best_cost = None, None

    for _ in range(tries):
        remaining = set(all_pairs)
        matches = []
        cost = 0

        while len(matches) < courts:
            if len(remaining) < 2: break
            candidates_a = list(remaining)
            random.shuffle(candidates_a)
            best_a, best_a_opts, best_a_len = None, None, None
            for a in candidates_a:
                opts = eligible_opponents(a, remaining - {a})
                if not opts: continue
                if best_a_len is None or len(opts) < best_a_len:
                    best_a, best_a_opts, best_a_len = a, opts, len(opts)
                    if best_a_len == 1: break
            if best_a is None: break
            a = best_a
            opts = best_a_opts
            random.shuffle(opts)
            best_b, best_local, best_is_repeat = None, None, None
            for b, is_repeat in opts:
                local = 0
                if is_repeat: local += 1000
                local += random.random()
                if best_local is None or local < best_local:
                    best_local, best_b, best_is_repeat = local, b, is_repeat
            if best_b is None: break
            remaining.remove(a)
            remaining.remove(best_b)
            matches.append(Match(a, best_b, mark_forced_repeat_early and best_is_repeat == 1))
            cost += best_local

        if len(matches) != courts: continue
        if best is None or cost < best_cost:
            best, best_cost = matches, cost
        if best_cost <= courts * 10: break

    return best

def schedule_session(n_pairs, courts, rounds_requested, max_gap, max_repeat_per_matchup, repeat_tail_rounds):
    for rounds_total in range(rounds_requested, 0, -1):
        used_counts = defaultdict(int)
        sched, forced_early = [], 0
        ok = True
        for r in range(rounds_total):
            round_matches = build_one_round(n_pairs, courts, used_counts, r, rounds_total, max_gap, max_repeat_per_matchup, repeat_tail_rounds)
            if round_matches is None:
                ok = False; break
            for m in round_matches:
                used_counts[canonical(m.a, m.b)] += 1
                if m.forced_repeat_early: forced_early += 1
            sched.append(round_matches)
        if ok: return rounds_total, sched, used_counts, forced_early
    return 0, [], defaultdict(int), 0

def format_schedule(pairs, sched, start_dt, round_minutes, courts):
    lines = []
    for r, matches in enumerate(sched, start=1):
        t = start_dt + timedelta(minutes=round_minutes * (r - 1))
        lines.append(f"🏸 Tour {r} — {t.strftime('%H:%M')}")
        matches_sorted = sorted(matches, key=lambda m: (m.a + m.b) / 2)
        for ci in range(courts):
            m = matches_sorted[ci]
            flag = " ⚠️" if m.forced_repeat_early else ""
            lines.append(f"  Court {ci+1}: {pairs[m.a]}  vs  {pairs[m.b]}{flag}")
        lines.append("")
    return "\n".join(lines).strip()

# -------------------- UI & CSS --------------------
st.set_page_config(page_title="Shuttle Shuffle", page_icon="🏸", layout="centered")

st.markdown("""
<style>
    :root { --accent: #E6FF2A; --bg-dark: #0b0f14; --panel: #111827; }
    body, .stApp { background-color: var(--bg-dark); color: #F2F6FF; }
    h1, h2, h3, .stMarkdown { color: #F8FAFF; }
    .stTextArea textarea, .stNumberInput input, .stTextInput input {
        background: var(--panel) !important; color: white !important; border: 1px solid #243043 !important;
    }
    div.stButton > button:first-child {
        background: var(--accent) !important; color: black !important;
        font-size: 20px !important; font-weight: 800 !important;
        padding: 0.75rem 1rem !important; border-radius: 12px !important;
        border: none !important; width: 100%; text-transform: uppercase; margin-top: 10px;
    }
    div.stButton > button:first-child:hover { opacity: 0.9; transform: scale(1.01); }
    div[data-testid="stVerticalBlock"] > div > div[data-testid="stHorizontalBlock"] button {
        background: #243043 !important; color: white !important; font-size: 14px !important; width: auto !important;
    }
    div[data-testid="stCodeBlock"] pre { background-color: var(--panel) !important; border-radius: 10px; }
    .streamlit-expanderHeader { background-color: var(--panel) !important; color: white !important; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

st.title('Shuttle Shuffle 🏸')
st.caption('Badminton Game Scheduler')

col_in1, col_in2 = st.columns([3, 1])
with col_in2:
    st.write("") 
    st.write("") 
    # Кнопка теперь использует callback on_click
    st.button("Load Demo List", on_click=load_demo)

with col_in1:
    # Важно: ключ key="input_text_area" совпадает с тем, что мы обновляем в load_demo
    raw = st.text_area(
        "Paste pair list (1 line = 1 pair).\nSort by rank if applicable (1 = Strongest ↓)",
        height=180,
        key="input_text_area",
        placeholder="1. Maksim + Stas\n2. Oksana + Mikhail..."
    )

c1, c2, c3 = st.columns(3)
with c1: courts = st.number_input("Courts", 1, 20, 1)
with c2: rounds = st.number_input("Rounds", 1, 30, 1)
with c3: max_gap = st.number_input("Max Rank Gap", 1, 50, 10)

with st.expander("⚙️ Advanced Settings"):
    ac1, ac2 = st.columns(2)
    with ac1:
        start_time_str = st.text_input("Start Time (HH:MM)", value=datetime.now(TZ).strftime("%H:%M"))
        round_minutes = st.number_input("Minutes / Round", 5, 90, 12)
    with ac2:
        max_repeats = st.number_input("Max Repeats", 0, 5, 1)
        tail_rounds = st.number_input("Tail Rounds", 0, 10, 2)
        seed = st.number_input("Random Seed (0 = Random)", 0, 999999, 0)

if st.button("SHUTTLE SHUFFLE 🚀"):
    pairs = parse_pairs(raw) # Читаем напрямую из виджета
    if len(pairs) < 2:
        st.error("⚠️ Need at least 2 pairs to play!")
    else:
        if seed != 0: random.seed(int(seed))
        try:
            hh, mm = start_time_str.strip().split(":")
            start_t = dtime(int(hh), int(mm))
        except:
            start_t = datetime.now(TZ).time().replace(second=0)
        start_dt = datetime.now(TZ).replace(hour=start_t.hour, minute=start_t.minute, second=0)

        with st.spinner("Shuffling players..."):
            rounds_actual, sched, used_counts, forced_early = schedule_session(
                len(pairs), int(courts), int(rounds), int(max_gap), int(max_repeats), int(tail_rounds)
            )

        if rounds_actual == 0:
            st.error("❌ Impossible to generate schedule. Try increasing Gap or reducing Courts.")
        else:
            rain_shuttles()
            if rounds_actual < int(rounds):
                st.warning(f"⚠️ Reduced to {rounds_actual} rounds to avoid conflicts.")
            
            out_text = format_schedule(pairs, sched, start_dt, int(round_minutes), int(courts))
            st.success(f"✅ Generated {rounds_actual} rounds!")
            
            tab1, tab2 = st.tabs(["📱 Display", "📋 Copy Text"])
            with tab1:
                for r_idx, round_matches in enumerate(sched):
                    t = start_dt + timedelta(minutes=int(round_minutes) * r_idx)
                    with st.container():
                        st.markdown(f"#### 🏸 Tour {r_idx+1} <span style='color:#888; font-size:0.8em'>({t.strftime('%H:%M')})</span>", unsafe_allow_html=True)
                        for m in sorted(round_matches, key=lambda x: (x.a + x.b)):
                            p1 = pairs[m.a]
                            p2 = pairs[m.b]
                            warn = "⚠️" if m.forced_repeat_early else ""
                            st.info(f"**{p1}** vs  **{p2}** {warn}")
                        st.divider()
            with tab2:
                st.text_area("Copy for Chat:", value=out_text, height=300)
