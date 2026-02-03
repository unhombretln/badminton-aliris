import streamlit as st

st.set_page_config(
    page_title="Results & Standings",
    page_icon="🏸",
    layout="wide",
)

st.title("Results & Standings 🏸")

st.markdown(
    """
    **Формат ввода (из WhatsApp / Telegram):**

    ```
    Game 1
    1 19-21 2
    3 21-13 4

    Game 2
    5 21-18 6
    ```
    """
)

results_text = st.text_area(
    "Вставь результаты матчей:",
    height=300,
    placeholder="Game 1\n1 19-21 2\n3 21-13 4\n\nGame 2\n..."
)

if st.button("Показать, что распознано"):
    st.subheader("Сырой ввод")
    st.code(results_text)
