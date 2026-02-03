import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Results & Standings", page_icon="🏸", layout="wide")
st.title("Results & Standings 🏸")

st.markdown(
    """
**Формат ввода:**
Game 1
1 19-21 2
3 21-13 4"""
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
    if mx != 21:
        return "максимум должен быть 21"
    if mn > 20:
        return "минимум не может быть больше 20"
    return None

if st.button("Распарсить и проверить"):
    rows = []
    errors = []
    current_game = None

    for i, raw in enumerate(results_text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue

        g = game_re.match(line)
        if g:
            current_game = int(g.group(1))
            continue

        m = match_re.match(line)
        if not m:
            errors.append(f"Строка {i}: не понимаю формат → {raw}")
            continue

        team_a, score_a, score_b, team_b = map(int, m.groups())

        if team_a == team_b:
            errors.append(f"Строка {i}: одинаковые номера команд")
            continue

        err = validate_score(score_a, score_b)
        if err:
            errors.append(f"Строка {i}: счёт {score_a}-{score_b} некорректен ({err})")
            continue

        rows.append({
            "Game": current_game,
            "Team A": team_a,
            "Score A": score_a,
            "Team B": team_b,
            "Score B": score_b,
            "Winner": team_a if score_a > score_b else team_b
        })

    if rows:
        st.subheader("Распознано матчей")
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    if errors:
        st.subheader("Ошибки")
        st.error("\n".join(errors))
    else:
        st.success("Ошибок не найдено ✅")
