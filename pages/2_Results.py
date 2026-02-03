import re
import io
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
    placeholder="1 Максим и Стас\n2 Оксана и Михаил\n3 Мария и Алексей\n..."
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
    out_df = out_df[["Pair", "Games", "Wins", "Losses", "PF", "PA", "DIFF", "PlaceDisplay"]]
    out_df = out_df.rename(columns={"PlaceDisplay": "Place"})
    out_df.attrs["title"] = title
    out_df.attrs["caption"] = caption
    return out_df

def style_ranking(df: pd.DataFrame):
    def place_start(val: str) -> int:
        v = str(val).split("–")[0].strip()
        try:
            return int(v)
        except:
            return 10**9

    def highlight_place_col(col):
        if col.name == "Place":
            return ["font-weight: 900; background-color: #fff3bf"] * len(col)
        return [""] * len(col)

    def medal_row_styles(row):
        p = place_start(row["Place"])
        if p == 1:
            return ["background-color: #ffd70033;"] * len(row)
        if p == 2:
            return ["background-color: #c0c0c033;"] * len(row)
        if p == 3:
            return ["background-color: #cd7f3233;"] * len(row)
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

    return fmt(rank_a, "🏆 Ranking A (by Wins):") + "\n\n" + fmt(rank_b, "🎯 Ranking B (by Points):")

def build_xlsx_bytes(stats_view: pd.DataFrame, rank_a: pd.DataFrame, rank_b: pd.DataFrame) -> bytes:
    """
    Делает один XLSX с тремя листами.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        stats_view.to_excel(writer, index=False, sheet_name="Stats")
        rank_a.to_excel(writer, index=False, sheet_name="Ranking_A_Wins")
        rank_b.to_excel(writer, index=False, sheet_name="Ranking_B_Points")
    return output.getvalue()

# =======================
# SESSION STATE helpers
# =======================

if "computed" not in st.session_state:
    st.session_state.computed = False

def store_results(
    matches_df: pd.DataFrame,
    stats_view: pd.DataFrame,
    rank_a: pd.DataFrame,
    rank_b: pd.DataFrame,
    share_text: str,
    xlsx_bytes: bytes,
):
    st.session_state.computed = True
    st.session_state.matches_df = matches_df
    st.session_state.stats_view = stats_view
    st.session_state.rank_a = rank_a
    st.session_state.rank_b = rank_b
    st.session_state.share_text = share_text
    st.session_state.xlsx_bytes = xlsx_bytes

def clear_results():
    st.session_state.computed = False
    for k in ["matches_df", "stats_view", "rank_a", "rank_b", "share_text", "xlsx_bytes"]:
        if k in st.session_state:
            del st.session_state[k]

# =======================
# ACTIONS (buttons)
# =======================

cbtn1, cbtn2 = st.columns([1, 1])
with cbtn1:
    do_compute = st.button("Посчитать турнир", type="primary")
with cbtn2:
    if st.button("Сбросить результаты"):
        clear_results()

if do_compute:
    rows, errors = parse_matches(results_text)

    if errors:
        st.session_state.computed = False
        st.subheader("Ошибки")
        st.error("\n".join(errors))
    elif not rows:
        st.session_state.computed = False
        st.info("Пока ни одного корректного матча не распознано.")
    else:
        matches_df = pd.DataFrame(rows)
        stats_df, h2h_winner = compute_stats(matches_df)

        stats_view = stats_df[["Team", "Pair", "Games", "Wins", "Losses", "PF", "PA", "DIFF"]].sort_values("Team")
        rank_a = make_ranking(stats_df, h2h_winner, mode="wins")
        rank_b = make_ranking(stats_df, h2h_winner, mode="points")
        share_text = build_share_text(rank_a, rank_b)
        xlsx_bytes = build_xlsx_bytes(stats_view, rank_a, rank_b)

        store_results(matches_df, stats_view, rank_a, rank_b, share_text, xlsx_bytes)

# =======================
# RENDER (uses session_state)
# =======================

if st.session_state.computed:
    matches_df = st.session_state.matches_df
    stats_view = st.session_state.stats_view
    rank_a = st.session_state.rank_a
    rank_b = st.session_state.rank_b
    share_text = st.session_state.share_text
    xlsx_bytes = st.session_state.xlsx_bytes

    st.subheader("Распознано матчей")
    st.dataframe(matches_df, use_container_width=True)

    st.divider()
    st.subheader("Статистика по парам")
    st.dataframe(stats_view, use_container_width=True)

    st.divider()
    st.subheader(rank_a.attrs.get("title", "Ranking A"))
    st.caption(rank_a.attrs.get("caption", ""))
    st.dataframe(style_ranking(rank_a), use_container_width=True)

    st.subheader(rank_b.attrs.get("title", "Ranking B"))
    st.caption(rank_b.attrs.get("caption", ""))
    st.dataframe(style_ranking(rank_b), use_container_width=True)

    # Downloads
    st.divider()
    st.subheader("⬇️ Скачать таблицы")

    # ✅ Excel-friendly CSV: UTF-8 with BOM
    st.download_button(
        "Download Stats (CSV, Excel-safe)",
        data=stats_view.to_csv(index=False).encode("utf-8-sig"),
        file_name="stats.csv",
        mime="text/csv",
        key="dl_stats",
    )

    st.download_button(
        "Download Ranking A - Wins (CSV, Excel-safe)",
        data=rank_a.to_csv(index=False).encode("utf-8-sig"),
        file_name="ranking_a_wins.csv",
        mime="text/csv",
        key="dl_rank_a",
    )

    st.download_button(
        "Download Ranking B - Points (CSV, Excel-safe)",
        data=rank_b.to_csv(index=False).encode("utf-8-sig"),
        file_name="ranking_b_points.csv",
        mime="text/csv",
        key="dl_rank_b",
    )

    # ✅ One XLSX file (best for Excel)
    st.download_button(
        "Download ALL tables (XLSX)",
        data=xlsx_bytes,
        file_name="badminton_tables.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_xlsx",
    )

    # Share text
    st.divider()
    st.subheader("📋 Итоги для чата")

    st.write("Кликни в поле → Ctrl+A → Ctrl+C (и вставляй в WhatsApp/Telegram).")
    st.text_area("Готовый текст", value=share_text, height=260, key="share_text_area")

    st.download_button(
        "⬇️ Скачать итоги (.txt)",
        data=share_text.encode("utf-8"),
        file_name="badminton_results.txt",
        mime="text/plain",
        key="dl_txt",
    )

    st.info("Если Place выглядит как `3–4`, значит место делится (личной встречи не было или равных больше двух).")
else:
    st.info("Вставь список пар и результаты, затем нажми «Посчитать турнир».")
