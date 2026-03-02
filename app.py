import streamlit as st
import pandas as pd
import uuid
import random
from datetime import datetime
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# -------------------- Конфигурация --------------------
APP_DIR = Path(__file__).parent
CSV_PATH = APP_DIR / "texts.csv"

TEXTS_PER_PARTICIPANT = 2
RANDOMIZE_ORDER = True
SPREADSHEET_NAME = "Название вашей таблицы"  # <-- изменить

# -------------------- Настройки страницы --------------------
st.set_page_config(
    page_title="Оценка исторических текстов",
    layout="centered"
)

st.title("Аннотирование исторических текстов")
st.markdown(
    "Оцените комментарий к представленному историческому источнику. "
    "Насколько вероятно, что текст сгенерирован искусственным интеллектом?"
)

# -------------------- Google Sheets --------------------
@st.cache_resource
def get_worksheets():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open(SPREADSHEET_NAME)
    return (
        spreadsheet.worksheet("participants"),
        spreadsheet.worksheet("responses")
    )

participants_ws, responses_ws = get_worksheets()

# -------------------- Сохранение --------------------
def save_participant(data):
    participants_ws.append_row([
        st.session_state.user_id,
        data["full_name"],
        data["education_level"],
        data["ai_usage"],
        int(data["consent"]),
        datetime.utcnow().isoformat()
    ])

def save_response(row):
    responses_ws.append_row([
        st.session_state.user_id,
        int(row["text_id"]),
        int(row["ai_probability"]),
        int(row["clarity"]),
        int(row["factuality"]),
        int(row["completeness"]),
        (row.get("comments") or "").strip(),
        datetime.utcnow().isoformat()
    ])

# -------------------- Загрузка текстов --------------------
@st.cache_data
def load_texts():
    df = pd.read_csv(CSV_PATH)
    df["text_id"] = df["text_id"].astype(int)
    return df

TEXTS = load_texts()

# -------------------- Сессия --------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "participant_filled" not in st.session_state:
    st.session_state.participant_filled = False

if "queue" not in st.session_state:
    ids = TEXTS["text_id"].tolist()
    if RANDOMIZE_ORDER:
        random.shuffle(ids)
    ids = (ids * ((TEXTS_PER_PARTICIPANT // max(1, len(ids))) + 1))[:TEXTS_PER_PARTICIPANT]
    st.session_state.queue = ids

if "seen" not in st.session_state:
    st.session_state.seen = []

# -------------------- Разбиение текста --------------------
def split_text(body: str):
    comment_marker = "===КОММЕНТАРИЙ ИСТОРИКА==="
    source_marker = "===ТЕКСТ ИСТОЧНИКА==="

    comment_text = ""
    source_text = ""

    if comment_marker in body and source_marker in body:
        after_comment = body.split(comment_marker, 1)[1]
        comment_text, source_text = after_comment.split(source_marker, 1)
    elif source_marker in body:
        source_text = body.split(source_marker, 1)[1]
    else:
        source_text = body

    return comment_text.strip(), source_text.strip()

# -------------------- Первая страница --------------------
if not st.session_state.participant_filled:
    st.header("Сведения о респонденте")

    with st.form("participant_form"):
        full_name = st.text_input("ФИО")

        education_level = st.selectbox(
            "Ваш уровень образования",
            [
                "Есть научная степень по истории",
                "Аспирант исторического факультета",
                "Оконченное высшее историческое образование",
                "Студент исторического факультета",
                "Не обладаю профильным историческим образованием"
            ]
        )

        ai_usage = st.selectbox(
            "Как часто вы используете генеративный ИИ?",
            [
                "использую каждый день для работы или учебы",
                "обращаюсь примерно раз в неделю",
                "обращаюсь не чаще одного раза в месяц",
                "не использую в своей работе"
            ]
        )

        consent = st.checkbox("Даю согласие на обработку персональных данных")

        submitted = st.form_submit_button("Продолжить")

        if submitted:
            if not full_name.strip():
                st.error("Поле обязательно.")
            elif not consent:
                st.error("Необходимо согласие.")
            else:
                save_participant({
                    "full_name": full_name.strip(),
                    "education_level": education_level,
                    "ai_usage": ai_usage,
                    "consent": consent
                })
                st.session_state.participant_filled = True
                st.success("Данные сохранены.")
                st.rerun()

    st.stop()

# -------------------- Основная логика --------------------
def next_item():
    remaining = [i for i in st.session_state.queue if i not in st.session_state.seen]
    return int(remaining[0]) if remaining else None

current_id = next_item()

if current_id is None:
    st.success("Опрос завершён. Благодарим за участие.")
else:
    row = TEXTS.loc[TEXTS["text_id"] == current_id].iloc[0]
    total = len(st.session_state.queue)
    progress = len(st.session_state.seen) + 1

    st.markdown(f"**Прогресс:** {progress} / {total}")

    commentary, source = split_text(row.get("body", ""))

    st.subheader(f"Текст №{progress}")

    if commentary:
        st.markdown("### Комментарий историка")
        st.write(commentary)

    if source:
        st.markdown("### Текст исторического источника")
        st.write(source)

    with st.form(key=f"form_{current_id}"):

        ai_probability = st.slider(
            "Вероятность генерации ИИ (%)",
            0, 100, 50, 10
        )

        factuality = st.radio(
            "Фактическая корректность",
            [
                "Полностью соответствует",
                "Содержит неточности",
                "Не отражает содержание"
            ]
        )

        emotionality = st.radio(
            "Эмоциональность",
            [
                "Нейтральный текст",
                "Есть эмоциональные оценки",
                "Выходит за рамки академического письма"
            ]
        )

        coherence = st.radio(
            "Связность",
            [
                "Логика соблюдена",
                "Есть разрозненность",
                "Логика нарушена"
            ]
        )

        comments = st.text_area("Комментарий (необязательно)")

        submitted = st.form_submit_button("Сохранить и продолжить")

        if submitted:
            save_response({
                "text_id": current_id,
                "ai_probability": ai_probability,
                "clarity": emotionality,
                "factuality": factuality,
                "completeness": coherence,
                "comments": comments
            })
            st.session_state.seen.append(current_id)
            st.success("Ответ сохранён.")
            st.rerun()
