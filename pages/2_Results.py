import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Results & Standings", page_icon="🏸", layout="wide")
st.title("Results & Standings 🏸")

# =======================
# TEAMS INPUT
# =======================

st.subheader("Список пар (один раз на турнир)")

teams_text = st.text_area(
    "Формат: номер + имя пары",
    height=260,
    placeholder="1 Максим Щ и Стас Щ\n2 Оксана и Михаил К\n3 Мария и Алексей Т\n..."
)

def parse_teams(text: str) -> dict[int, str]:
    teams = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s+(.+)$", line)
        if m:
            teams[int(m.group(1))] = m.group(2).strip()
    return teams

teams_map = parse_teams(teams_text)

# =======================
# RESULTS INPUT
# =======================

st.subheader("Результаты матчей")

st.markdown(
    """
"""
)

results_text = st.text_area(
    "Вставь результаты матчей:",
    height=320,
    placeholder="Game 1\n1 19-21 2\n3 21-13 4\n\nGame 2\n..."
)

match_re = re.compile(r"^\s*(\d+)\s+(\d+)\s*-\s*(\d+)\s+(\d+)\s*$")
game_re = re.compile(r"^\s*Game\s+(\d+)\s*$", re.IGNORECASE)

def validate_score(a: int, b: int):
    if a == b:
        return "ничья невозможна"
    mx, mn = max(a, b), min(a, b)
    if mx != 21 or mn > 20:
        return "неверный счёт"
    return None

def parse_matches(text: str):
    rows, errors = [], []
    current_game = None

    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue

        g = game_re.match(line)
        if g:
            current_game = int(g.group(1))
            continue

        m = match_re.match(line)
        if not m:
            errors.append(f"Строка {i}: {raw}")
            continue

        a, sa, sb, b = map(int, m.groups())
        err = validate_score(sa, sb)
        if err:
            errors.append(f"Строка {i}: {sa}-{sb}")
            continue

        rows.append({
            "Game": current_game,
            "Team": a,
            "Opponent": b,
            "PF": sa,
            "PA": sb,
            "Win": sa > sb
        })
        rows.append({
            "Game": current_game,
            "Team": b,
            "Opponent": a,
            "PF": sb,
            "PA": sa,
            "Win": sb > sa
        })

    return pd.DataFrame(rows), errors

# =======================
# CALCULATION
# =======================

if st.button("Посчитать турнир"):
    df, errors = parse_matches(results_text)

    if errors:
        st.error("\n".join(errors))
        st.stop()

    stats = (
        df.groupby("Team")
          .agg(
              Games=("Game", "count"),
              Wins=("Win", "sum"),
              PF=("PF", "sum"),
              PA=("PA", "sum")
          )
          .reset_index()
    )
    stats["Losses"] = stats["Games"] - stats["Wins"]
    stats["DIFF"] = stats["PF"] - stats["PA"]

    # подставляем имена
    stats["Pair"] = stats["Team"].map(lambda x: teams_map.get(x, f"Team {x}"))

    # сортировка по победам
    stats = stats.sort_values(
        ["Wins", "DIFF", "PF"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    stats["Place"] = stats.index + 1

    # финальный вид
    final = stats[[
        "Place", "Pair", "Games", "Wins", "Losses", "PF", "PA", "DIFF"
    ]]

    st.subheader("🏆 Итоговая таблица")
    st.dataframe(final, use_container_width=True)

    st.success("Готово! Теперь везде используются имена пар 🎉")
