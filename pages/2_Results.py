import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Results & Standings", page_icon="🏸", layout="wide")
st.title("Results & Standings 🏸")

st.markdown(
    """
**Формат ввода:**

Строка матча: `A x-y B`
- A и B — номера пар
- x и y — очки (матч до 21, максимум 21:20 / 20:21)
"""
)

results_text = st.text_area(
    "Вставь результаты матчей:",
    height=320,
    placeholder="Game 1\n1 19-21 2\n3 21-13 4\n\nGame 2\n..."
)

# --- regex ---
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
    if a < 0 or b < 0:
        return "очки не могут быть отрицательными"
    return None

def pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)

def parse_matches(text: str):
    rows = []
    errors = []
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
            errors.append(f"Строка {i}: не понимаю формат → {raw}")
            continue

        team_a, score_a, score_b, team_b = map(int, m.groups())

        if team_a == team_b:
            errors.append(f"Строка {i}: одинаковые номера команд ({team_a})")
            continue

        err = validate_score(score_a, score_b)
        if err:
            errors.append(f"Строка {i}: счёт {score_a}-{score_b} некорректен ({err})")
            continue

        winner = team_a if score_a > score_b else team_b

        rows.append(
            {
                "Line": i,
                "Game": current_game,
                "Team A": team_a,
                "Score A": score_a,
                "Team B": team_b,
                "Score B": score_b,
                "Winner": winner,
            }
        )

    return rows, errors

def compute_stats(matches_df: pd.DataFrame):
    stats = {}
    h2h_winner = {}

    def ensure_team(t: int):
        if t not in stats:
            stats[t] = {"Team": t, "Games": 0, "Wins": 0, "Losses": 0, "PF": 0, "PA": 0}

    for _, r in matches_df.iterrows():
        a = int(r["Team A"])
        b = int(r["Team B"])
        sa = int(r["Score A"])
        sb = int(r["Score B"])
        w = int(r["Winner"])

        ensure_team(a)
        ensure_team(b)

        stats[a]["Games"] += 1
        stats[b]["Games"] += 1

        stats[a]["PF"] += sa
        stats[a]["PA"] += sb
        stats[b]["PF"] += sb
        stats[b]["PA"] += sa

        if w == a:
            stats[a]["Wins"] += 1
            stats[b]["Losses"] += 1
        else:
            stats[b]["Wins"] += 1
            stats[a]["Losses"] += 1

        h2h_winner[pair_key(a, b)] = w

    stats_df = pd.DataFrame(stats.values()).sort_values("Team")
    stats_df["DIFF"] = stats_df["PF"] - stats_df["PA"]
    return stats_df, h2h_winner

def apply_h2h_tiebreak(sorted_rows: list[dict], h2h_winner: dict, keys: list[str]) -> list[dict]:
    out = []
    i = 0
    n = len(sorted_rows)

    while i < n:
        j = i + 1
        while j < n and all(sorted_rows[j][k] == sorted_rows[i][k] for k in keys):
            j += 1

        group = sorted_rows[i:j]

        if len(group) == 2:
            t1 = group[0]["Team"]
            t2 = group[1]["Team"]
            w = h2h_winner.get(pair_key(t1, t2))
            if w is not None:
                if group[0]["Team"] != w:
                    group = [group[1], group[0]]
                group[0]["PlaceShared"] = False
                group[1]["PlaceShared"] = False
            else:
                group[0]["PlaceShared"] = True
                group[1]["PlaceShared"] = True
        else:
            for g in group:
                g["PlaceShared"] = True

        out.extend(group)
        i = j

    return out

def make_ranking(stats_df: pd.DataFrame, h2h_winner: dict, mode: str) -> pd.DataFrame:
    df = stats_df.copy()

    if mode == "wins":
        df = df.sort_values(["Wins", "DIFF", "PF"], ascending=[False, False, False])
        key_cols = ["Wins", "DIFF", "PF"]
        title = "Ranking A — by Wins"
    elif mode == "points":
        df = df.sort_values(["PF", "Wins", "DIFF"], ascending=[False, False, False])
        key_cols = ["PF", "Wins", "DIFF"]
        title = "Ranking B — by Points"
    else:
        raise ValueError("Unknown mode")

    rows = df.to_dict(orient="records")
    rows = apply_h2h_tiebreak(rows, h2h_winner, key_cols)

    place = 1
    i = 0
    while i < len(rows):
        j = i + 1
        while j < len(rows) and all(rows[j][k] == rows[i][k] for k in key_cols):
            j += 1

        group = rows[i:j]
        if len(group) == 1:
            group[0]["Place"] = place
            place += 1
        else:
            for g in group:
                g["Place"] = place
            place += len(group)

        i = j

    out_df = pd.DataFrame(rows)
    cols = ["Place", "Team", "Games", "Wins", "Losses", "PF", "PA", "DIFF", "PlaceShared"]
    out_df = out_df[cols]
    out_df.attrs["title"] = title
    return out_df

if st.button("Посчитать турнир"):
    rows, errors = parse_matches(results_text)

    st.subheader("Распознано матчей")
    if rows:
        matches_df = pd.DataFrame(rows)
        st.dataframe(matches_df, use_container_width=True)
    else:
        st.info("Пока ни одного корректного матча не распознано.")
        matches_df = None

    st.subheader("Ошибки")
    if errors:
        st.error("\n".join(errors))
    else:
        st.success("Ошибок не найдено ✅")

    if matches_df is not None and len(matches_df) > 0 and not errors:
        stats_df, h2h_winner = compute_stats(matches_df)

        st.divider()
        st.subheader("Статистика по парам")
        st.dataframe(stats_df.sort_values("Team"), use_container_width=True)

        rank_a = make_ranking(stats_df, h2h_winner, mode="wins")
        rank_b = make_ranking(stats_df, h2h_winner, mode="points")

        st.divider()
        st.subheader(rank_a.attrs["title"])
        st.caption("Сортировка: Wins → DIFF → PF. Тайбрейк: личная встреча, иначе делёж места.")
        st.dataframe(rank_a, use_container_width=True)

        st.subheader(rank_b.attrs["title"])
        st.caption("Сортировка: PF → Wins → DIFF. Тайбрейк: личная встреча, иначе делёж места.")
        st.dataframe(rank_b, use_container_width=True)

        st.info("PlaceShared=True означает: места делятся (личной встречи между равными не было, либо равных >2).")
    elif matches_df is not None and len(matches_df) > 0 and errors:
        st.warning("Исправь ошибки выше — и пересчитаем.")
