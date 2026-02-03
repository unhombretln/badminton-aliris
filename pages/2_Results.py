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
    """
    Возвращает:
    - stats_df: по каждой паре Games/Wins/Losses/PF/PA/DIFF
    - h2h_winner: {(min_id,max_id): winner_id} если личная встреча была (берём последнюю)
    """
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

        # личная встреча: фиксируем победителя (если встречались несколько раз — берём последнюю запись)
        h2h_winner[pair_key(a, b)] = w

    stats_df = pd.DataFrame(stats.values()).sort_values("Team")
    stats_df["DIFF"] = stats_df["PF"] - stats_df["PA"]
    return stats_df, h2h_winner

def apply_h2h_tiebreak(sorted_rows: list[dict], h2h_winner: dict, keys: list[str]) -> list[dict]:
    """
    sorted_rows уже отсортирован по основным ключам.
    Если группа равных по keys:
      - если 2 пары и была личная встреча → победитель выше, PlaceShared=False (тайбрейк решён)
      - если личной встречи нет → PlaceShared=True (место делится)
      - если 3+ пары → PlaceShared=True (делим место, чтобы не усложнять)
    """
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
                # победитель выше
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

def assign_places_with_ranges(rows: list[dict], key_cols: list[str]) -> list[dict]:
    """
    Назначает:
    - PlaceStart (число для логики/сортировки/медалей)
    - PlaceDisplay (строка: "3" или "3–4")
    Правило:
    - если группа равных по key_cols и ВСЕ PlaceShared=True → делёж места, показываем диапазон
    - иначе → места идут по порядку (включая h2h-решённые случаи)
    """
    place = 1
    i = 0
    n = len(rows)

    while i < n:
        j = i + 1
        while j < n and all(rows[j][k] == rows[i][k] for k in key_cols):
            j += 1

        group = rows[i:j]
        shared = (len(group) > 1) and all(g.get("PlaceShared", False) is True for g in group)

        if shared:
            start = place
            end = place + len(group) - 1
            label = f"{start}–{end}"
            for g in group:
                g["PlaceStart"] = start
                g["PlaceDisplay"] = label
            place = end + 1
        else:
            for g in group:
                g["PlaceStart"] = place
                g["PlaceDisplay"] = str(place)
                place += 1

        i = j

    return rows

def make_ranking(stats_df: pd.DataFrame, h2h_winner: dict, mode: str) -> pd.DataFrame:
    df = stats_df.copy()

    if mode == "wins":
        df = df.sort_values(["Wins", "DIFF", "PF"], ascending=[False, False, False])
        key_cols = ["Wins", "DIFF", "PF"]
        title = "Ranking A — by Wins"
        caption = "Сортировка: Wins → DIFF → PF. Тайбрейк: личная встреча, иначе делёж места."
    elif mode == "points":
        df = df.sort_values(["PF", "Wins", "DIFF"], ascending=[False, False, False])
        key_cols = ["PF", "Wins", "DIFF"]
        title = "Ranking B — by Points"
        caption = "Сортировка: PF → Wins → DIFF. Тайбрейк: личная встреча, иначе делёж места."
    else:
        raise ValueError("Unknown mode")

    rows = df.to_dict(orient="records")
    rows = apply_h2h_tiebreak(rows, h2h_winner, key_cols)
    rows = assign_places_with_ranges(rows, key_cols)

    out_df = pd.DataFrame(rows)
    # Place справа, как ты просил
    cols = ["Team", "Games", "Wins", "Losses", "PF", "PA", "DIFF", "PlaceDisplay"]
    out_df = out_df[cols]
    out_df = out_df.rename(columns={"PlaceDisplay": "Place"})
    out_df.attrs["title"] = title
    out_df.attrs["caption"] = caption
    return out_df

def style_ranking(df: pd.DataFrame):
    """
    - Place справа уже есть
    - подсветка Place-столбца
    - золото/серебро/бронза по PlaceStart (но PlaceStart мы не показываем),
      поэтому вычислим PlaceStart из Place-строки.
    """
    place_series = df["Place"].astype(str)

    def place_start(val: str) -> int:
        # "3" -> 3 ; "3–4" -> 3
        v = val.split("–")[0].strip()
        try:
            return int(v)
        except:
            return 10**9

    starts = place_series.map(place_start)

    def highlight_place_col(col):
        if col.name == "Place":
            return ["font-weight: 900; background-color: #fff3bf"] * len(col)
        return [""] * len(col)

    def medal_row_styles(row):
        # применяем стиль ко всей строке
        p = place_start(str(row["Place"]))
        if p == 1:
            return ["background-color: #ffd70033;"] * len(row)  # золото (полупрозр.)
        if p == 2:
            return ["background-color: #c0c0c033;"] * len(row)  # серебро
        if p == 3:
            return ["background-color: #cd7f3233;"] * len(row)  # бронза
        return [""] * len(row)

    # отдельно усилим саму ячейку Place цветом медали (если 1/2/3)
    def medal_place_cell_styles(col):
        if col.name != "Place":
            return [""] * len(col)
        styles = []
        for v in col.astype(str):
            p = place_start(v)
            if p == 1:
                styles.append("font-weight: 900; background-color: #ffd700;")
            elif p == 2:
                styles.append("font-weight: 900; background-color: #c0c0c0;")
            elif p == 3:
                styles.append("font-weight: 900; background-color: #cd7f32; color: #111;")
            else:
                styles.append("font-weight: 900; background-color: #fff3bf;")
        return styles

    return (
        df.style
          .apply(highlight_place_col, axis=0)
          .apply(medal_row_styles, axis=1)
          .apply(medal_place_cell_styles, axis=0)
          .format({"DIFF": "{:+d}"})
    )

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
        st.caption(rank_a.attrs["caption"])
        st.dataframe(style_ranking(rank_a), use_container_width=True)

        st.subheader(rank_b.attrs["title"])
        st.caption(rank_b.attrs["caption"])
        st.dataframe(style_ranking(rank_b), use_container_width=True)

        st.info("Если Place выглядит как `3–4`, значит место делится (личной встречи для тайбрейка не было или равных больше двух).")
    elif matches_df is not None and len(matches_df) > 0 and errors:
        st.warning("Исправь ошибки выше — и пересчитаем.")
