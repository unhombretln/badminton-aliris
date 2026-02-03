import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Results & Standings", page_icon="🏸", layout="wide")
st.title("Results & Standings 🏸")

# =======================
# INPUT: TEAMS
# =======================

st.subheader("Список пар (один раз на турнир)")

teams_text = st.text_area(
    "Формат: номер + имя пары (по одной строке)",
    height=220,
    placeholder="1 Максим Щ и Стас Щ\n2 Оксана и Михаил К\n3 Мария и Алексей Т\n..."
)

def parse_teams(text: str) -> dict[int, str]:
    teams: dict[int, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s+(.+)$", line)
        if m:
            teams[int(m.group(1))] = m.group(2).strip()
    return teams

teams_map = parse_teams(teams_text)

def team_name(t: int) -> str:
    return teams_map.get(t, f"Team {t}")

# =======================
# INPUT: RESULTS
# =======================

st.subheader("Результаты матчей")

st.markdown(
    """
**Формат ввода:**

Строка матча: `A x-y B`  
- A и B — номера пар  
- x и y — очки (любой формат игры допустим: 21/15/BWF/гибрид и т.д.)  
- Проверяем только здравый смысл и опечатки (например, 211-19)
"""
)

results_text = st.text_area(
    "Вставь результаты матчей:",
    height=300,
    placeholder="Game 1\n1 19-21 2\n3 21-13 4\n\nGame 2\n..."
)

match_re = re.compile(r"^\s*(\d+)\s+(\d+)\s*-\s*(\d+)\s+(\d+)\s*$")
game_re = re.compile(r"^\s*Game\s+(\d+)\s*$", re.IGNORECASE)

# ✅ Relaxed validation: only sanity checks + typo guard
MAX_POINTS_GUARD = 60

def validate_score_relaxed(a: int, b: int):
    if a == b:
        return "ничья невозможна"
    if a < 0 or b < 0:
        return "очки не могут быть отрицательными"
    if max(a, b) > MAX_POINTS_GUARD:
        return f"слишком большое число (> {MAX_POINTS_GUARD}) — похоже на опечатку"
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

        a, sa, sb, b = map(int, m.groups())

        if a == b:
            errors.append(f"Строка {i}: одинаковые номера команд ({a})")
            continue

        err = validate_score_relaxed(sa, sb)
        if err:
            errors.append(f"Строка {i}: счёт {sa}-{sb} некорректен ({err})")
            continue

        winner = a if sa > sb else b

        rows.append({
            "Line": i,
            "Game": current_game,
            "Team A": a,
            "Score A": sa,
            "Team B": b,
            "Score B": sb,
            "Winner": winner
        })

    return rows, errors

# =======================
# CALCULATION
# =======================

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

        # личная встреча: если встречались несколько раз — берём последнюю запись
        h2h_winner[pair_key(a, b)] = w

    stats_df = pd.DataFrame(stats.values()).sort_values("Team")
    stats_df["DIFF"] = stats_df["PF"] - stats_df["PA"]
    stats_df["Pair"] = stats_df["Team"].map(team_name)
    return stats_df, h2h_winner

def apply_h2h_tiebreak(sorted_rows: list[dict], h2h_winner: dict, keys: list[str]) -> list[dict]:
    """
    Если группа равных по keys:
      - если 2 пары и была личная встреча → победитель выше, PlaceShared=False
      - если личной встречи нет → PlaceShared=True (место делится)
      - если 3+ пары → PlaceShared=True (делим место)
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
    PlaceDisplay:
      - "3" если место уникальное
      - "3–4" если место делится
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

    # Place справа
    out_df = out_df[["Pair", "Games", "Wins", "Losses", "PF", "PA", "DIFF", "PlaceDisplay"]]
    out_df = out_df.rename(columns={"PlaceDisplay": "Place"})
    out_df.attrs["title"] = title
    out_df.attrs["caption"] = caption
    return out_df

def style_ranking(df: pd.DataFrame):
    place_series = df["Place"].astype(str)

    def place_start(val: str) -> int:
        v = val.split("–")[0].strip()
        try:
            return int(v)
        except:
            return 10**9

    def highlight_place_col(col):
        if col.name == "Place":
            return ["font-weight: 900; background-color: #fff3bf"] * len(col)
        return [""] * len(col)

    def medal_row_styles(row):
        p = place_start(str(row["Place"]))
        if p == 1:
            return ["background-color: #ffd70033;"] * len(row)  # gold
        if p == 2:
            return ["background-color: #c0c0c033;"] * len(row)  # silver
        if p == 3:
            return ["background-color: #cd7f3233;"] * len(row)  # bronze
        return [""] * len(row)

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

def build_share_text(rank_a: pd.DataFrame, rank_b: pd.DataFrame) -> str:
    def medal_for(place: str) -> str:
        p = place.split("–")[0].strip()
        return "🥇 " if p == "1" else "🥈 " if p == "2" else "🥉 " if p == "3" else ""

    def fmt(df: pd.DataFrame, title: str, top_n: int = 16) -> str:
        lines = [title]
        for _, r in df.head(top_n).iterrows():
            place = str(r["Place"])
            pair = str(r["Pair"])
            wins = int(r["Wins"])
            losses = int(r["Losses"])
            pf = int(r["PF"])
            pa = int(r["PA"])
            diff = int(r["DIFF"])
            lines.append(f"{medal_for(place)}{place}. {pair} — W{wins}-L{losses}, PF {pf}, PA {pa}, DIFF {diff:+d}")
        return "\n".join(lines)

    text_a = fmt(rank_a, "🏆 Ranking A (by Wins):")
    text_b = fmt(rank_b, "🎯 Ranking B (by Points):")
    return text_a + "\n\n" + text_b

# =======================
# BUTTON ACTION
# =======================

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
        stats_view = stats_df[["Team", "Pair", "Games", "Wins", "Losses", "PF", "PA", "DIFF"]].sort_values("Team")
        st.dataframe(stats_view, use_container_width=True)

        rank_a = make_ranking(stats_df, h2h_winner, mode="wins")
        rank_b = make_ranking(stats_df, h2h_winner, mode="points")

        st.divider()
        st.subheader(rank_a.attrs["title"])
        st.caption(rank_a.attrs["caption"])
        st.dataframe(style_ranking(rank_a), use_container_width=True)

        st.subheader(rank_b.attrs["title"])
        st.caption(rank_b.attrs["caption"])
        st.dataframe(style_ranking(rank_b), use_container_width=True)

        # =======================
        # DOWNLOADS (CSV)
        # =======================
        st.divider()
        st.subheader("⬇️ Скачать таблицы")

        st.download_button(
            "Download Stats (CSV)",
            data=stats_view.to_csv(index=False).encode("utf-8"),
            file_name="stats.csv",
            mime="text/csv"
        )

        st.download_button(
            "Download Ranking A - Wins (CSV)",
            data=rank_a.to_csv(index=False).encode("utf-8"),
            file_name="ranking_a_wins.csv",
            mime="text/csv"
        )

        st.download_button(
            "Download Ranking B - Points (CSV)",
            data=rank_b.to_csv(index=False).encode("utf-8"),
            file_name="ranking_b_points.csv",
            mime="text/csv"
        )

        # =======================
        # SHARE TEXT (copy/paste + txt)
        # =======================
        st.divider()
        st.subheader("📋 Итоги для чата")

        share_text = build_share_text(rank_a, rank_b)
        st.write("Кликни в поле → Ctrl+A → Ctrl+C (и вставляй в WhatsApp/Telegram).")
        st.text_area("Готовый текст", value=share_text, height=260)

        st.download_button(
            "⬇️ Скачать итоги (.txt)",
            data=share_text.encode("utf-8"),
            file_name="badminton_results.txt",
            mime="text/plain"
        )

        st.info("Если Place выглядит как `3–4`, значит место делится (личной встречи не было или равных больше двух).")

    elif matches_df is not None and len(matches_df) > 0 and errors:
        st.warning("Исправь ошибки выше — и пересчитаем.")
